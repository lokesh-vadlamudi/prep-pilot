from __future__ import annotations

import json
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from app import course_service, db
from app.content.inference_course import (
    COURSE, COURSE_VERSION, LegacyIdentity, normalize_alias_identity, validate_catalog,
)
from app.models import (
    Book,
    Card,
    Concept,
    CourseArtifactEvidence,
    CourseCheckpointAttempt,
    CourseContentLink,
    CourseEnrollment,
    CourseMissionProgress,
    CourseMutationReceipt,
    CourseOralReview,
    CourseOralTurn,
    User,
)


class CourseProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "course.db"
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False, "timeout": 5},
        )
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            user = User(username="course-alice", password_hash="x")
            other = User(username="course-bob", password_hash="x")
            session.add(user)
            session.add(other)
            session.commit()
            session.refresh(user)
            session.refresh(other)
            self.user_id = user.id
            self.other_id = other.id
        self.module = COURSE.modules[0]
        self.artifact = self.module.artifacts[0]

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def _enroll(self, session: Session, user_id: int | None = None, request_id: str = "enroll-1"):
        return course_service.enroll(
            session,
            user_id or self.user_id,
            request_id=request_id,
            catalog_version=COURSE_VERSION,
        )

    def _assert_error(self, code: str, call):
        with self.assertRaises(course_service.CourseServiceError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def _evaluation(self, passed: bool, feedback: str = "Qualitative checks evaluated."):
        return course_service._trusted_checkpoint_evaluation(passed=passed, feedback=feedback)

    def _oral_evaluation(self, feedback: str = "Qualitative turn feedback."):
        return course_service._trusted_oral_turn_evaluation(
            feedback=feedback, next_question="What deeper mechanism would you verify next?",
        )

    def _draft(self, artifact=None):
        descriptor = artifact or self.artifact
        return {field: f"bounded {field}" for field in descriptor.template_fields}

    def _race(self, insert_prefix: str, call):
        barrier = threading.Barrier(2)
        lock = threading.Lock()
        arrivals = 0
        results, errors = [], []

        def before_cursor_execute(_conn, _cursor, statement, _params, _context, _many):
            nonlocal arrivals
            if not statement.lstrip().lower().startswith(insert_prefix):
                return
            with lock:
                should_wait = arrivals < 2
                arrivals += 1
            if should_wait:
                barrier.wait(timeout=5)

        def worker():
            try:
                with Session(self.engine) as session:
                    results.append(call(session))
            except Exception as error:  # captured for an assertion in the test thread
                errors.append(error)

        event.listen(self.engine, "before_cursor_execute", before_cursor_execute)
        try:
            threads = [threading.Thread(target=worker) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
        finally:
            event.remove(self.engine, "before_cursor_execute", before_cursor_execute)
        return results, errors

    def test_enrollment_replays_exact_response_after_restart_and_is_user_scoped(self):
        with Session(self.engine) as session:
            first = self._enroll(session)
            self.assertFalse(first.replayed)
            self.assertEqual(first.status_code, 201)
            expected = first.body

        with Session(self.engine) as session:
            replay = self._enroll(session)
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.status_code, 201)
            self.assertEqual(replay.body, expected)

            other = self._enroll(session, self.other_id)
            self.assertFalse(other.replayed)
            self.assertNotEqual(other.body["enrollment_id"], expected["enrollment_id"])
            self.assertEqual(len(session.exec(select(CourseEnrollment)).all()), 2)
            self.assertEqual(len(session.exec(select(CourseMutationReceipt)).all()), 2)

    def test_competing_receipt_sessions_commit_one_domain_row_and_recover_loser(self):
        results, errors = self._race(
            "insert into courseenrollment",
            lambda session: course_service.enroll(
                session, self.user_id, request_id="race-enrollment",
                catalog_version=COURSE_VERSION,
            ),
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].body, results[1].body)
        self.assertEqual(sum(result.replayed for result in results), 1)
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(CourseEnrollment)).all()), 1)
            self.assertEqual(len(session.exec(select(CourseMutationReceipt)).all()), 1)
            self._assert_error(
                "idempotency_conflict",
                lambda: course_service.enroll(
                    session, self.user_id, request_id="race-enrollment",
                    catalog_version="forged-version",
                ),
            )

    def test_same_request_key_with_different_payload_conflicts_without_mutation(self):
        with Session(self.engine) as session:
            self._enroll(session)
            with self.assertRaises(course_service.CourseServiceError) as caught:
                course_service.enroll(
                    session,
                    self.user_id,
                    request_id="enroll-1",
                    catalog_version="different-version",
                )
            self.assertEqual(caught.exception.code, "idempotency_conflict")
            self.assertEqual(len(session.exec(select(CourseEnrollment)).all()), 1)

    def test_request_auth_catalog_and_enrollment_errors_are_durable(self):
        with Session(self.engine) as session:
            self._assert_error("invalid_request_id", lambda: self._enroll(session, request_id=" "))
            self._assert_error(
                "user_not_found",
                lambda: course_service.enroll(
                    session, 999_999, request_id="missing-user", catalog_version=COURSE_VERSION,
                ),
            )
            first = self._assert_error(
                "catalog_version_conflict",
                lambda: course_service.enroll(
                    session, self.user_id, request_id="bad-catalog", catalog_version="old",
                ),
            )
            replay = self._assert_error(
                "catalog_version_conflict",
                lambda: course_service.enroll(
                    session, self.user_id, request_id="bad-catalog", catalog_version="old",
                ),
            )
            self.assertFalse(first.replayed)
            self.assertTrue(replay.replayed)
            created = self._enroll(session)
            existing = self._enroll(session, request_id="enroll-existing")
            self.assertEqual(created.status_code, 201)
            self.assertEqual(existing.status_code, 200)
            self.assertFalse(existing.body["created"])
            self._assert_error(
                "catalog_version_conflict",
                lambda: course_service.save_artifact(
                    session, self.user_id, mission_id=self.module.id,
                    artifact_id=self.artifact.id, note="evidence", artifact_uri="r.md",
                    draft_fields=self._draft(),
                    expected_revision=0, request_id="stale-catalog", catalog_version="old",
                ),
            )

    def test_actions_require_enrollment_and_prerequisites(self):
        with Session(self.engine) as session:
            self._assert_error(
                "not_enrolled",
                lambda: course_service.save_artifact(
                    session, self.user_id, mission_id=self.module.id,
                    artifact_id=self.artifact.id, note="evidence", artifact_uri="r.md",
                    draft_fields=self._draft(),
                    expected_revision=0, request_id="before-enrollment",
                ),
            )
            self._enroll(session)
            blocked = COURSE.modules[1]
            self._assert_error(
                "prerequisite_incomplete",
                lambda: course_service.save_artifact(
                    session, self.user_id, mission_id=blocked.id,
                    artifact_id=blocked.artifacts[0].id, note="evidence", artifact_uri="r.md",
                    draft_fields=self._draft(blocked.artifacts[0]),
                    expected_revision=0, request_id="blocked-mission",
                ),
            )

    def test_artifact_optimistic_revision_and_old_response_replay(self):
        with Session(self.engine) as session:
            self._enroll(session)
            first = course_service.save_artifact(
                session,
                self.user_id,
                mission_id=self.module.id,
                artifact_id=self.artifact.id,
                note="first observation",
                artifact_uri="reports/first.md",
                draft_fields=self._draft(),
                expected_revision=0,
                request_id="artifact-1",
                catalog_version=COURSE_VERSION,
            )
            self.assertEqual(first.body["revision"], 1)
            second = course_service.save_artifact(
                session,
                self.user_id,
                mission_id=self.module.id,
                artifact_id=self.artifact.id,
                note="second observation",
                artifact_uri="https://example.test/report",
                draft_fields=self._draft(),
                expected_revision=1,
                request_id="artifact-2",
                catalog_version=COURSE_VERSION,
            )
            self.assertEqual(second.body["revision"], 2)

        with Session(self.engine) as session:
            replay = course_service.save_artifact(
                session,
                self.user_id,
                mission_id=self.module.id,
                artifact_id=self.artifact.id,
                note="first observation",
                artifact_uri="reports/first.md",
                draft_fields=self._draft(),
                expected_revision=0,
                request_id="artifact-1",
                catalog_version=COURSE_VERSION,
            )
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.body, first.body)
            stored = session.exec(select(CourseArtifactEvidence)).one()
            self.assertEqual(stored.revision, 2)
            self.assertEqual(stored.note, "second observation")

            with self.assertRaises(course_service.CourseServiceError) as caught:
                course_service.save_artifact(
                    session,
                    self.user_id,
                    mission_id=self.module.id,
                    artifact_id=self.artifact.id,
                    note="stale overwrite",
                    artifact_uri="reports/stale.md",
                    draft_fields=self._draft(),
                    expected_revision=1,
                    request_id="artifact-stale",
                    catalog_version=COURSE_VERSION,
                )
            self.assertEqual(caught.exception.code, "stale_revision")
            session.refresh(stored)
            self.assertEqual(stored.note, "second observation")

    def test_artifact_validates_catalog_bounds_and_safe_uri(self):
        with Session(self.engine) as session:
            self._enroll(session)
            cases = [
                ({"mission_id": "missing", "artifact_id": self.artifact.id}, "unknown_mission"),
                ({"mission_id": self.module.id, "artifact_id": "missing"}, "unknown_artifact"),
            ]
            for index, (ids, code) in enumerate(cases):
                with self.subTest(code=code), self.assertRaises(course_service.CourseServiceError) as caught:
                    course_service.save_artifact(
                        session,
                        self.user_id,
                        note="valid note",
                        artifact_uri="reports/value.md",
                        draft_fields=self._draft(),
                        expected_revision=0,
                        request_id=f"invalid-{index}",
                        catalog_version=COURSE_VERSION,
                        **ids,
                    )
                self.assertEqual(caught.exception.code, code)
            with self.assertRaises(course_service.CourseServiceError) as caught:
                course_service.save_artifact(
                    session,
                    self.user_id,
                    mission_id=self.module.id,
                    artifact_id=self.artifact.id,
                    note="valid note",
                    artifact_uri="file:///private/result",
                    draft_fields=self._draft(),
                    expected_revision=0,
                    request_id="unsafe-uri",
                    catalog_version=COURSE_VERSION,
                )
            self.assertEqual(caught.exception.code, "unsafe_artifact_uri")
            for index, uri in enumerate((
                "/absolute.md",
                "../escape.md",
                "https://pilot:secret@example.test/report.md",
            )):
                self._assert_error(
                    "unsafe_artifact_uri",
                    lambda uri=uri, index=index: course_service.save_artifact(
                        session, self.user_id, mission_id=self.module.id,
                        artifact_id=self.artifact.id, note="valid note", artifact_uri=uri,
                        draft_fields=self._draft(),
                        expected_revision=0, request_id=f"unsafe-relative-{index}",
                    ),
                )
            self._assert_error(
                "invalid_note",
                lambda: course_service.save_artifact(
                    session, self.user_id, mission_id=self.module.id,
                    artifact_id=self.artifact.id, note=" ", artifact_uri="reports/value.md",
                    draft_fields=self._draft(),
                    expected_revision=0, request_id="empty-note",
                ),
            )

    def test_artifact_uri_rejects_https_userinfo_without_domain_mutation(self):
        with Session(self.engine) as session:
            self._enroll(session)
            for index, uri in enumerate((
                "https://learner@example.test/report.md",
                "https://learner:secret@example.test/report.md",
            )):
                with self.subTest(uri=uri):
                    error = self._assert_error(
                        "unsafe_artifact_uri",
                        lambda index=index, uri=uri: course_service.save_artifact(
                            session, self.user_id, mission_id=self.module.id,
                            artifact_id=self.artifact.id, note="bounded evidence",
                            artifact_uri=uri, draft_fields=self._draft(),
                            expected_revision=0, request_id=f"userinfo-{index}",
                        ),
                    )
                    self.assertEqual(error.status_code, 422)
                    self.assertEqual(
                        session.exec(select(CourseArtifactEvidence)).all(), [],
                    )

            saved = course_service.save_artifact(
                session, self.user_id, mission_id=self.module.id,
                artifact_id=self.artifact.id, note="bounded evidence",
                artifact_uri="https://example.test/report.md",
                draft_fields=self._draft(), expected_revision=0,
                request_id="safe-hosted-uri",
            )
            replay = course_service.save_artifact(
                session, self.user_id, mission_id=self.module.id,
                artifact_id=self.artifact.id, note="bounded evidence",
                artifact_uri="https://example.test/report.md",
                draft_fields=self._draft(), expected_revision=0,
                request_id="safe-hosted-uri",
            )
            self.assertEqual(saved.body["artifact_uri"], "https://example.test/report.md")
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.body, saved.body)

    def test_artifact_draft_persists_catalog_template_and_exports_owner_scoped_content(self):
        draft = {field: f"value for {field}" for field in self.artifact.template_fields}
        with Session(self.engine) as session:
            self._enroll(session)
            saved = course_service.save_artifact(
                session, self.user_id, mission_id=self.module.id,
                artifact_id=self.artifact.id, note="Useful inline draft.",
                artifact_uri="reports/useful.md", expected_revision=0,
                request_id="artifact-draft", catalog_version=COURSE_VERSION,
                draft_fields=draft,
            )
            self.assertEqual(saved.body["template_key"], self.artifact.template_key)
            self.assertEqual(saved.body["output_format"], self.artifact.output_format)
            self.assertEqual(saved.body["draft_fields"], draft)
            self.assertEqual(saved.body["verification_rubric"], list(self.artifact.verification_rubric))
            row = session.exec(select(CourseArtifactEvidence)).one()
            self.assertEqual(json.loads(row.draft_json), draft)
            self.assertEqual(json.loads(row.source_ids_json), list(self.artifact.source_ids))
            updated_draft = {field: f"updated {field}" for field in self.artifact.template_fields}
            updated = course_service.save_artifact(
                session, self.user_id, mission_id=self.module.id,
                artifact_id=self.artifact.id, note="Updated useful draft.",
                artifact_uri="https://example.test/useful.md", expected_revision=1,
                request_id="artifact-draft-edit", catalog_version=COURSE_VERSION,
                draft_fields=updated_draft,
            )
            self.assertEqual(updated.body["revision"], 2)

        with Session(self.engine) as session:
            replay = course_service.save_artifact(
                session, self.user_id, mission_id=self.module.id,
                artifact_id=self.artifact.id, note="Useful inline draft.",
                artifact_uri="reports/useful.md", expected_revision=0,
                request_id="artifact-draft", catalog_version=COURSE_VERSION,
                draft_fields=draft,
            )
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.body, saved.body)
            exported = course_service.artifact_export(session, self.user_id, self.artifact.id)
            self.assertEqual(exported["draft_fields"], updated_draft)
            self.assertEqual(exported["revision"], 2)
            self.assertEqual(exported["template_fields"], list(self.artifact.template_fields))
            self._assert_error(
                "artifact_not_found",
                lambda: course_service.artifact_export(session, self.other_id, self.artifact.id),
            )

    def test_artifact_draft_rejects_forged_template_missing_fields_and_rolls_back_receipt_failure(self):
        draft = {field: "bounded" for field in self.artifact.template_fields}
        with Session(self.engine) as session:
            self._enroll(session)
            missing = dict(draft)
            missing.pop(next(iter(missing)))
            self._assert_error(
                "missing_template_fields",
                lambda: course_service.save_artifact(
                    session, self.user_id, mission_id=self.module.id,
                    artifact_id=self.artifact.id, note="draft", artifact_uri="reports/draft.md",
                    expected_revision=0, request_id="missing-field",
                    draft_fields=missing,
                ),
            )
        with self.engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TRIGGER fail_artifact_receipt BEFORE INSERT ON coursemutationreceipt "
                "WHEN NEW.operation='artifact_upsert' "
                "BEGIN SELECT RAISE(ABORT, 'artifact receipt failure'); END"
            )
        with Session(self.engine) as session:
            with self.assertRaises(DatabaseError):
                course_service.save_artifact(
                    session, self.user_id, mission_id=self.module.id,
                    artifact_id=self.artifact.id, note="draft", artifact_uri="reports/draft.md",
                    expected_revision=0, request_id="artifact-rollback",
                    draft_fields=draft,
                )
            session.rollback()
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(CourseArtifactEvidence)).all(), [])
            self.assertIsNone(session.exec(select(CourseMutationReceipt).where(
                CourseMutationReceipt.operation == "artifact_upsert",
                CourseMutationReceipt.request_id == "artifact-rollback",
            )).first())

    def test_artifact_requires_complete_bounded_structured_draft(self):
        with Session(self.engine) as session:
            self._enroll(session)
            self._assert_error(
                "missing_template_fields",
                lambda: course_service.save_artifact(
                    session, self.user_id, mission_id=self.module.id,
                    artifact_id=self.artifact.id, note="missing draft",
                    artifact_uri="reports/missing.md", expected_revision=0,
                    request_id="missing-draft",
                ),
            )
            required = {field: "bounded" for field in self.artifact.template_fields}
            for request_id, draft, code in (
                ("empty-draft", {}, "missing_template_fields"),
                ("partial-draft", dict(list(required.items())[1:]), "missing_template_fields"),
                ("unknown-draft", required | {"unknown": "value"}, "unknown_template_fields"),
                ("typed-draft", required | {next(iter(required)): 7}, "invalid_template_fields"),
                ("blank-draft", required | {next(iter(required)): "  "}, "invalid_template_fields"),
                ("control-draft", required | {next(iter(required)): "bad\x00value"}, "invalid_template_fields"),
                ("field-too-large", required | {next(iter(required)): "x" * 4001}, "invalid_template_fields"),
                ("draft-too-large", {field: "x" * 4000 for field in required}, "artifact_draft_too_large"),
            ):
                with self.subTest(request_id=request_id):
                    self._assert_error(
                        code,
                        lambda request_id=request_id, draft=draft: course_service.save_artifact(
                            session, self.user_id, mission_id=self.module.id,
                            artifact_id=self.artifact.id, note="invalid draft",
                            artifact_uri="reports/invalid.md", expected_revision=0,
                            request_id=request_id, draft_fields=draft,
                        ),
                    )
            self.assertEqual(session.exec(select(CourseArtifactEvidence)).all(), [])

    def test_ic12_selection_is_catalog_scoped_canonical_and_idempotent(self):
        frontier = next(module for module in COURSE.modules if module.id == "IC-12")
        descriptor = frontier.artifacts[0]
        options = list(frontier.selection_rule.options)

        def draft(selection):
            value = {field: f"bounded {field}" for field in descriptor.template_fields}
            value["selected_experiments"] = selection
            return value

        with Session(self.engine) as session:
            self._enroll(session)
            invalid = (
                ("under", options[:1]),
                ("over", options[:4]),
                ("duplicate", [options[0], options[0]]),
                ("unknown", [options[0], "SRC-NOT-CATALOGED"]),
                ("wrong-module", [options[0], COURSE.modules[11].source_ids[0]]),
                ("non-list", "free text"),
            )
            with patch("app.course_service._require_prerequisites"):
                for request_id, selection in invalid:
                    with self.subTest(selection=request_id):
                        self._assert_error(
                            "invalid_experiment_selection",
                            lambda request_id=request_id, selection=selection: course_service.save_artifact(
                                session, self.user_id, mission_id=frontier.id,
                                artifact_id=descriptor.id, note="frontier evidence",
                                artifact_uri="reports/frontier.md", draft_fields=draft(selection),
                                expected_revision=0, request_id=f"ic12-{request_id}",
                            ),
                        )
                chosen = [options[2], options[0], options[1]]
                first = course_service.save_artifact(
                    session, self.user_id, mission_id=frontier.id,
                    artifact_id=descriptor.id, note="frontier evidence",
                    artifact_uri="reports/frontier.md", draft_fields=draft(chosen),
                    expected_revision=0, request_id="ic12-valid",
                )
                replay = course_service.save_artifact(
                    session, self.user_id, mission_id=frontier.id,
                    artifact_id=descriptor.id, note="frontier evidence",
                    artifact_uri="reports/frontier.md", draft_fields=draft(list(reversed(chosen))),
                    expected_revision=0, request_id="ic12-valid",
                )
                self._assert_error(
                    "idempotency_conflict",
                    lambda: course_service.save_artifact(
                        session, self.user_id, mission_id=frontier.id,
                        artifact_id=descriptor.id, note="frontier evidence",
                        artifact_uri="reports/frontier.md", draft_fields=draft(options[1:3]),
                        expected_revision=0, request_id="ic12-valid",
                    ),
                )
            expected = options[:3]
            self.assertEqual(first.body["draft_fields"]["selected_experiments"], expected)
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.body, first.body)
            reloaded = course_service.module_user_state(session, self.user_id, frontier.id)
            self.assertEqual(reloaded["artifact_state"][0]["draft_fields"]["selected_experiments"],
                             expected)
            exported = course_service.artifact_export(
                session, self.user_id, descriptor.id,
            )
            self.assertEqual(exported["draft_fields"]["selected_experiments"], expected)

    def test_ic12_malformed_selection_items_are_bounded_before_receipts(self):
        frontier = next(module for module in COURSE.modules if module.id == "IC-12")
        descriptor = frontier.artifacts[0]
        options = list(frontier.selection_rule.options)

        def draft(selection):
            value = {field: f"bounded {field}" for field in descriptor.template_fields}
            value["selected_experiments"] = selection
            return value

        malformed = {
            "dict": [{"id": options[0]}, options[1]],
            "integer": [7, options[0]],
            "null": [None, options[0]],
            "nested": [[options[0]], options[1]],
            "mixed": [options[0], {"id": options[1]}],
        }
        with Session(self.engine) as session:
            self._enroll(session)
            with patch("app.course_service._require_prerequisites"):
                for request_id, selection in malformed.items():
                    with self.subTest(shape=request_id):
                        error = self._assert_error(
                            "invalid_experiment_selection",
                            lambda request_id=request_id, selection=selection: course_service.save_artifact(
                                session, self.user_id, mission_id=frontier.id,
                                artifact_id=descriptor.id, note="frontier evidence",
                                artifact_uri="reports/frontier.md", draft_fields=draft(selection),
                                expected_revision=0, request_id=f"ic12-malformed-{request_id}",
                            ),
                        )
                        self.assertEqual(error.status_code, 422)
            self.assertEqual(session.exec(select(CourseArtifactEvidence)).all(), [])
            self.assertEqual(session.exec(select(CourseMutationReceipt).where(
                CourseMutationReceipt.operation == "artifact_upsert",
            )).all(), [])

    def test_ic14_and_ic16_completion_payloads_are_exact_canonical_and_durable(self):
        workplace = next(module for module in COURSE.modules if module.id == "IC-14")
        papers = next(module for module in COURSE.modules if module.id == "IC-16")
        workplace_artifact, paper_artifact = workplace.artifacts[0], papers.artifacts[0]

        def template(artifact):
            return {field: f"bounded {field}" for field in artifact.template_fields}

        workplace_rule = workplace_artifact.completion_rule
        workplace_ids = [entry.source_id for entry in workplace_rule.entries]
        chosen = workplace_ids[1]
        scopes = [
            {"project_id": source_id, "scope": f"Scope for {source_id}."}
            for source_id in workplace_ids
        ]
        workplace_completion = {
            "project_scopes": scopes,
            "chosen_project_id": chosen,
            "selected_proposal": {"project_id": chosen, "evidence": "Measured gateway need."},
        }
        paper_rule = paper_artifact.completion_rule
        paper_ids = [entry.source_id for entry in paper_rule.entries]
        notes = [
            {"paper_id": source_id, "note": f"Mechanism note for {source_id}."}
            for source_id in paper_ids
        ]
        paper_completion = {"paper_notes": notes}

        invalid_workplace = (
            {**workplace_completion, "project_scopes": scopes[:-1]},
            {**workplace_completion, "project_scopes": [*scopes[:-1], scopes[0]]},
            {**workplace_completion, "project_scopes": [*scopes[:-1], {"project_id": paper_ids[0], "scope": "wrong"}]},
            {**workplace_completion, "project_scopes": "free text"},
            {**workplace_completion, "chosen_project_id": "SRC-WP-99"},
            {**workplace_completion, "selected_proposal": {"project_id": workplace_ids[2], "evidence": "mismatch"}},
            {**workplace_completion, "selected_proposal": {"project_id": chosen, "evidence": "bad\x00evidence"}},
            {**workplace_completion, "project_scopes": [{**scopes[0], "scope": " "}, *scopes[1:]]},
            {**workplace_completion, "selected_proposal": {"project_id": chosen, "evidence": "x" * 2001}},
        )
        invalid_papers = (
            notes[:-1],
            [*notes[:-1], notes[0]],
            [*notes[:-1], {"paper_id": workplace_ids[0], "note": "wrong module"}],
            "free text",
            [{**notes[0], "note": " "}, *notes[1:]],
            [{**notes[0], "note": "bad\x00note"}, *notes[1:]],
            [{**notes[0], "note": "x" * 2001}, *notes[1:]],
        )

        with Session(self.engine) as session:
            self._enroll(session)
            with patch("app.course_service._require_prerequisites"):
                for index, completion in enumerate(invalid_workplace):
                    with self.subTest(workplace=index):
                        self._assert_error(
                            "invalid_completion_payload",
                            lambda index=index, completion=completion: course_service.save_artifact(
                                session, self.user_id, mission_id=workplace.id,
                                artifact_id=workplace_artifact.id, note="invalid workplace",
                                artifact_uri="reports/workplace.md",
                                draft_fields=template(workplace_artifact) | completion,
                                expected_revision=0, request_id=f"ic14-invalid-{index}",
                            ),
                        )
                for index, paper_notes in enumerate(invalid_papers):
                    with self.subTest(papers=index):
                        self._assert_error(
                            "invalid_completion_payload",
                            lambda index=index, paper_notes=paper_notes: course_service.save_artifact(
                                session, self.user_id, mission_id=papers.id,
                                artifact_id=paper_artifact.id, note="invalid papers",
                                artifact_uri="reports/papers.md",
                                draft_fields=template(paper_artifact) | {"paper_notes": paper_notes},
                                expected_revision=0, request_id=f"ic16-invalid-{index}",
                            ),
                        )

                workplace_draft = template(workplace_artifact) | workplace_completion
                first = course_service.save_artifact(
                    session, self.user_id, mission_id=workplace.id,
                    artifact_id=workplace_artifact.id, note="all projects scoped",
                    artifact_uri="reports/workplace.md", draft_fields=workplace_draft,
                    expected_revision=0, request_id="ic14-valid",
                )
                reordered = workplace_draft | {"project_scopes": list(reversed(scopes))}
                replay = course_service.save_artifact(
                    session, self.user_id, mission_id=workplace.id,
                    artifact_id=workplace_artifact.id, note="all projects scoped",
                    artifact_uri="reports/workplace.md", draft_fields=reordered,
                    expected_revision=0, request_id="ic14-valid",
                )
                self._assert_error(
                    "idempotency_conflict",
                    lambda: course_service.save_artifact(
                        session, self.user_id, mission_id=workplace.id,
                        artifact_id=workplace_artifact.id, note="all projects scoped",
                        artifact_uri="reports/workplace.md",
                        draft_fields=workplace_draft | {
                            "selected_proposal": {"project_id": chosen, "evidence": "changed evidence"},
                        },
                        expected_revision=0, request_id="ic14-valid",
                    ),
                )
                paper_draft = template(paper_artifact) | paper_completion
                saved_papers = course_service.save_artifact(
                    session, self.user_id, mission_id=papers.id,
                    artifact_id=paper_artifact.id, note="all papers annotated",
                    artifact_uri="reports/papers.md", draft_fields=paper_draft | {
                        "paper_notes": list(reversed(notes)),
                    }, expected_revision=0, request_id="ic16-valid",
                )
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.body, first.body)
            self.assertEqual(
                [entry["project_id"] for entry in first.body["draft_fields"]["project_scopes"]],
                workplace_ids,
            )
            self.assertEqual(
                [entry["paper_id"] for entry in saved_papers.body["draft_fields"]["paper_notes"]],
                paper_ids,
            )
            for module, artifact, expected_field in (
                (workplace, workplace_artifact, "project_scopes"),
                (papers, paper_artifact, "paper_notes"),
            ):
                reloaded = course_service.module_user_state(session, self.user_id, module.id)
                exported = course_service.artifact_export(session, self.user_id, artifact.id)
                self.assertEqual(reloaded["artifact_state"][0]["draft_fields"][expected_field],
                                 exported["draft_fields"][expected_field])

    def test_offline_oral_attempt_survives_reload_then_requires_review(self):
        with Session(self.engine) as session:
            self._enroll(session)
            pending = course_service.self_record_oral(
                session,
                self.user_id,
                mission_id=self.module.id,
                note="I explained the hardware checks aloud and recorded the gaps.",
                expected_revision=0,
                request_id="oral-self-1",
                catalog_version=COURSE_VERSION,
            )
            self.assertEqual(pending.body["review_state"], "awaiting_review")
            self.assertEqual(pending.body["revision"], 1)
            progress = course_service.mission_progress(session, self.user_id, self.module.id)
            self.assertNotEqual(progress["state"], "complete")

        with Session(self.engine) as session:
            review = session.exec(select(CourseOralReview)).one()
            self.assertEqual(review.state, "awaiting_review")
            with self.assertRaises(course_service.CourseServiceError) as caught:
                course_service.review_oral(
                    session,
                    self.user_id,
                    mission_id=self.module.id,
                    method="self_rubric",
                    acknowledgements=list(self.module.oral.rubric[:-1]),
                    feedback="Reviewed against the rubric.",
                    expected_revision=1,
                    request_id="oral-review-incomplete",
                    catalog_version=COURSE_VERSION,
                )
            self.assertEqual(caught.exception.code, "incomplete_oral_review")

            completed = course_service.review_oral(
                session,
                self.user_id,
                mission_id=self.module.id,
                method="self_rubric",
                acknowledgements=list(self.module.oral.rubric),
                feedback="Reviewed each rubric item and recorded one follow-up.",
                expected_revision=1,
                request_id="oral-review-1",
                catalog_version=COURSE_VERSION,
            )
            self.assertEqual(completed.body["review_state"], "reviewed")
            self.assertEqual(completed.body["revision"], 2)

            replay = course_service.self_record_oral(
                session,
                self.user_id,
                mission_id=self.module.id,
                note="I explained the hardware checks aloud and recorded the gaps.",
                expected_revision=0,
                request_id="oral-self-1",
                catalog_version=COURSE_VERSION,
            )
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.body, pending.body)
            current = session.exec(select(CourseOralReview)).one()
            self.assertEqual(current.state, "reviewed")

    def test_module_user_state_returns_ordered_owner_only_artifacts_and_oral_turns(self):
        with Session(self.engine) as session:
            self._enroll(session)
            session.add(CourseArtifactEvidence(
                user_id=self.user_id, mission_id=self.module.id,
                artifact_id=self.artifact.id, note="owner note", artifact_uri="owner.md",
                revision=2, draft_json=json.dumps(self._draft()),
            ))
            session.add(CourseArtifactEvidence(
                user_id=self.other_id, mission_id=self.module.id,
                artifact_id=self.artifact.id, note="other note", artifact_uri="other.md",
                revision=9, draft_json=json.dumps({"private": "other"}),
            ))
            session.add(CourseOralReview(
                user_id=self.user_id, mission_id=self.module.id, state="practicing",
                mode="dgx", revision=1,
            ))
            session.add(CourseOralTurn(
                user_id=self.user_id, mission_id=self.module.id, turn_id="later",
                payload_sha256="a" * 64, prompt="second", response="second response",
                feedback="second feedback", created_at=datetime(2026, 1, 2),
            ))
            session.add(CourseOralTurn(
                user_id=self.user_id, mission_id=self.module.id, turn_id="earlier",
                payload_sha256="b" * 64, prompt="first", response="first response",
                feedback="first feedback", created_at=datetime(2026, 1, 1),
            ))
            session.commit()
            state = course_service.module_user_state(
                session, self.user_id, self.module.id,
            )
            self.assertEqual([item["turn_id"] for item in state["oral_state"]["turns"]],
                             ["earlier", "later"])
            self.assertEqual(state["artifact_state"][0]["note"], "owner note")
            self.assertEqual(state["artifact_state"][0]["revision"], 2)
            other = course_service.module_user_state(session, self.other_id, self.module.id)
            self.assertEqual(other["artifact_state"][0]["note"], "other note")
            self.assertEqual(other["oral_state"]["turns"], [])

    def test_pre_turn_contract_schema_migrates_twice_without_losing_legacy_turn(self):
        with patch("app.db.engine", self.engine):
            db.init_db()
        with self.engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO courseoralturn "
                "(id,user_id,mission_id,turn_id,payload_sha256,prompt,response,feedback,"
                "next_question,response_json,created_at) VALUES "
                "(41,1,'IC-00','legacy-turn','legacy-sha','legacy prompt','legacy response',"
                "'legacy feedback','legacy next','{}','2026-01-01')"
            )
            conn.exec_driver_sql("ALTER TABLE courseoralturn DROP COLUMN next_question")
            conn.exec_driver_sql("ALTER TABLE courseoralturn DROP COLUMN response_json")
            conn.exec_driver_sql(
                "DELETE FROM _meta WHERE key='inference_course_schema_v1'"
            )

        with patch("app.db.engine", self.engine):
            db.init_db()
            db.init_db()

        with self.engine.connect() as conn:
            columns = {
                row[1] for row in conn.exec_driver_sql("PRAGMA table_info(courseoralturn)")
            }
            preserved = conn.exec_driver_sql(
                "SELECT id,prompt,response,feedback,next_question,response_json "
                "FROM courseoralturn WHERE id=41"
            ).fetchone()
            marker = conn.exec_driver_sql(
                "SELECT value FROM _meta WHERE key='inference_course_schema_v1'"
            ).fetchone()
        self.assertTrue({"next_question", "response_json"}.issubset(columns))
        self.assertEqual(tuple(preserved), (
            41, "legacy prompt", "legacy response", "legacy feedback", "", "{}",
        ))
        self.assertIsNotNone(marker)

    def test_offline_oral_rejects_stale_and_invalid_transitions(self):
        with Session(self.engine) as session:
            self._enroll(session)
            self._assert_error(
                "invalid_oral_transition",
                lambda: course_service.review_oral(
                    session, self.user_id, mission_id=self.module.id, method="self_rubric",
                    acknowledgements=list(self.module.oral.rubric), feedback="review",
                    expected_revision=0, request_id="review-before-attempt",
                ),
            )
            course_service.self_record_oral(
                session, self.user_id, mission_id=self.module.id, note="recorded",
                expected_revision=0, request_id="record-one",
            )
            self._assert_error(
                "stale_revision",
                lambda: course_service.self_record_oral(
                    session, self.user_id, mission_id=self.module.id, note="changed",
                    expected_revision=0, request_id="record-stale",
                ),
            )
            self._assert_error(
                "invalid_oral_transition",
                lambda: course_service.self_record_oral(
                    session, self.user_id, mission_id=self.module.id, note="changed",
                    expected_revision=1, request_id="record-again",
                ),
            )
            self._assert_error(
                "stale_revision",
                lambda: course_service.review_oral(
                    session, self.user_id, mission_id=self.module.id, method="self_rubric",
                    acknowledgements=list(self.module.oral.rubric), feedback="review",
                    expected_revision=0, request_id="review-stale",
                ),
            )
            self._assert_error(
                "invalid_review_method",
                lambda: course_service.review_oral(
                    session, self.user_id, mission_id=self.module.id, method="numeric",
                    acknowledgements=list(self.module.oral.rubric), feedback="review",
                    expected_revision=1, request_id="review-invalid-method",
                ),
            )

    def test_online_oral_turn_dedupes_and_completes_without_numeric_fields(self):
        with Session(self.engine) as session:
            self._enroll(session)
            turn = course_service.record_oral_turn(
                session,
                self.user_id,
                mission_id=self.module.id,
                turn_id="turn-1",
                response="The inventory proves the lab starts from known driver and runtime versions.",
                evaluation=self._oral_evaluation(
                    "Clear evidence boundary; add the container runtime version."
                ),
                catalog_version=COURSE_VERSION,
            )
            duplicate = course_service.record_oral_turn(
                session,
                self.user_id,
                mission_id=self.module.id,
                turn_id="turn-1",
                response="The inventory proves the lab starts from known driver and runtime versions.",
                evaluation=self._oral_evaluation(
                    "Clear evidence boundary; add the container runtime version."
                ),
                catalog_version=COURSE_VERSION,
            )
            self.assertEqual(turn, duplicate)
            with self.assertRaises(course_service.CourseServiceError) as caught:
                course_service.record_oral_turn(
                    session,
                    self.user_id,
                    mission_id=self.module.id,
                    turn_id="turn-1",
                    response="changed",
                    evaluation=self._oral_evaluation("changed"),
                    catalog_version=COURSE_VERSION,
                )
            self.assertEqual(caught.exception.code, "idempotency_conflict")

            finished = course_service.complete_oral(
                session,
                self.user_id,
                mission_id=self.module.id,
                feedback="The debrief covered each qualitative rubric item.",
                expected_revision=1,
                request_id="oral-complete-1",
                catalog_version=COURSE_VERSION,
            )
            self.assertEqual(finished.body["review_state"], "reviewed")
            body_text = json.dumps(finished.body).lower()
            for forbidden in ("score", "grade", "points", "percentage", "sm-2"):
                self.assertNotIn(forbidden, body_text)
            self.assertEqual(len(session.exec(select(CourseOralTurn)).all()), 1)

    def test_online_oral_rejects_invalid_turn_and_completion_transitions(self):
        with Session(self.engine) as session:
            self._enroll(session)
            self._assert_error(
                "invalid_oral_turn",
                lambda: course_service.record_oral_turn(
                    session, self.user_id, mission_id=self.module.id, turn_id="blank-turn",
                    response=" ", evaluation=self._oral_evaluation("feedback"),
                ),
            )
            self._assert_error(
                "invalid_oral_transition",
                lambda: course_service.complete_oral(
                    session, self.user_id, mission_id=self.module.id, feedback="done",
                    expected_revision=0, request_id="complete-before-turn",
                ),
            )
            course_service.record_oral_turn(
                session, self.user_id, mission_id=self.module.id, turn_id="turn-one",
                response="response", evaluation=self._oral_evaluation("feedback"),
            )
            course_service.record_oral_turn(
                session, self.user_id, mission_id=self.module.id, turn_id="turn-two",
                response="another response", evaluation=self._oral_evaluation("more feedback"),
            )
            self._assert_error(
                "stale_revision",
                lambda: course_service.record_oral_turn(
                    session, self.user_id, mission_id=self.module.id, turn_id="late-turn",
                    response="late response", evaluation=self._oral_evaluation("late feedback"),
                    expected_revision=1,
                ),
            )
            self._assert_error(
                "stale_revision",
                lambda: course_service.complete_oral(
                    session, self.user_id, mission_id=self.module.id, feedback="done",
                    expected_revision=0, request_id="complete-stale",
                ),
            )
            course_service.complete_oral(
                session, self.user_id, mission_id=self.module.id, feedback="done",
                expected_revision=2, request_id="complete-valid",
            )
            self._assert_error(
                "invalid_oral_transition",
                lambda: course_service.record_oral_turn(
                    session, self.user_id, mission_id=self.module.id, turn_id="after-review",
                    response="response", evaluation=self._oral_evaluation("feedback"),
                ),
            )

    def test_checkpoint_ids_payload_bounds_and_replay(self):
        with Session(self.engine) as session:
            self._enroll(session)
            self._assert_error(
                "unknown_checkpoint",
                lambda: course_service.record_checkpoint_attempt(
                    session, self.user_id, checkpoint_id="missing", request_id="unknown",
                    answers={}, evaluation=self._evaluation(False),
                ),
            )
            self._assert_error(
                "checkpoint_too_large",
                lambda: course_service.record_checkpoint_attempt(
                    session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                    request_id="too-large", answers={"answer": "x" * 20_001},
                    evaluation=self._evaluation(False),
                ),
            )
            first = course_service.record_checkpoint_attempt(
                session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                request_id="checkpoint-repeat", answers={"answer": "bounded"},
                evaluation=self._evaluation(False, "try again"),
            )
            replay = course_service.record_checkpoint_attempt(
                session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                request_id="checkpoint-repeat", answers={"answer": "bounded"},
                evaluation=self._evaluation(False, "try again"),
            )
            self.assertEqual(replay, first)
            self._assert_error(
                "idempotency_conflict",
                lambda: course_service.record_checkpoint_attempt(
                    session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                    request_id="checkpoint-repeat", answers={"answer": "changed"},
                    evaluation=self._evaluation(False, "try again"),
                ),
            )

    def test_checkpoint_rejects_forged_pass_and_uses_internal_evaluation(self):
        with Session(self.engine) as session:
            self._enroll(session)
            with self.assertRaises(TypeError):
                course_service.record_checkpoint_attempt(
                    session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                    request_id="forged-pass", answers={"explanation": "unsupported"},
                    passed=True, feedback="caller says pass",
                )
            self._assert_error(
                "untrusted_checkpoint_evaluation",
                lambda: course_service.record_checkpoint_attempt(
                    session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                    request_id="forged-evaluator", answers={"explanation": "unsupported"},
                    evaluation=object(),
                ),
            )
            incorrect = course_service.record_checkpoint_attempt(
                session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                request_id="evaluated-incorrect", answers={"explanation": "incorrect"},
                evaluation=self._evaluation(False, "Missing required evidence."),
            )
            correct = course_service.record_checkpoint_attempt(
                session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                request_id="evaluated-correct", answers={"explanation": "correct"},
                evaluation=self._evaluation(True, "Required evidence supported."),
            )
            self.assertFalse(incorrect["passed"])
            self.assertTrue(correct["passed"])
            self.assertEqual(len(session.exec(select(CourseCheckpointAttempt)).all()), 2)

    def test_checkpoint_replay_precedes_changed_or_unavailable_evaluator(self):
        with Session(self.engine) as session:
            self._enroll(session)
            first = course_service.record_checkpoint_attempt(
                session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                request_id="stable-checkpoint", answers={"explanation": "stable input"},
                evaluation=self._evaluation(False, "Original evaluator feedback."),
            )
            row = session.exec(select(CourseCheckpointAttempt).where(
                CourseCheckpointAttempt.request_id == "stable-checkpoint"
            )).one()
            stored_response = row.response_json

        with Session(self.engine) as session:
            unavailable = course_service.record_checkpoint_attempt(
                session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                request_id="stable-checkpoint", answers={"explanation": "stable input"},
                evaluation=None,
            )
            changed_evaluator = course_service.record_checkpoint_attempt(
                session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                request_id="stable-checkpoint", answers={"explanation": "stable input"},
                evaluation=self._evaluation(True, "Different later feedback."),
            )
            self.assertEqual(unavailable, first)
            self.assertEqual(changed_evaluator, first)
            self.assertEqual(stored_response, course_service._canonical_json(unavailable))
            self._assert_error(
                "idempotency_conflict",
                lambda: course_service.record_checkpoint_attempt(
                    session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                    request_id="stable-checkpoint", answers={"explanation": "changed input"},
                    evaluation=None,
                ),
            )
            self._assert_error(
                "idempotency_conflict",
                lambda: course_service.record_checkpoint_attempt(
                    session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                    request_id="stable-checkpoint", answers={"explanation": "stable input"},
                    evaluation=None, catalog_version="changed-version",
                ),
            )
            self._assert_error(
                "untrusted_checkpoint_evaluation",
                lambda: course_service.record_checkpoint_attempt(
                    session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                    request_id="new-without-evaluator", answers={"explanation": "new input"},
                    evaluation=None,
                ),
            )

    def test_competing_oral_turn_and_checkpoint_sessions_recover_exactly(self):
        with Session(self.engine) as session:
            self._enroll(session)
            session.add(CourseOralReview(
                user_id=self.user_id, mission_id=self.module.id,
                state="practicing", mode="dgx", revision=1,
            ))
            session.commit()
        oral_results, oral_errors = self._race(
            "update courseoralreview",
            lambda session: course_service.record_oral_turn(
                session, self.user_id, mission_id=self.module.id, turn_id="race-turn",
                response="same bounded response", evaluation=self._oral_evaluation("same bounded feedback"),
            ),
        )
        self.assertEqual(oral_errors, [])
        self.assertEqual(oral_results[0], oral_results[1])
        checkpoint_results, checkpoint_errors = self._race(
            "insert into coursecheckpointattempt",
            lambda session: course_service.record_checkpoint_attempt(
                session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                request_id="race-checkpoint", answers={"answer": "same"},
                evaluation=self._evaluation(False, "same feedback"),
            ),
        )
        self.assertEqual(checkpoint_errors, [])
        self.assertEqual(checkpoint_results[0], checkpoint_results[1])
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(CourseOralTurn)).all()), 1)
            self.assertEqual(len(session.exec(select(CourseCheckpointAttempt)).all()), 1)
            self._assert_error(
                "idempotency_conflict",
                lambda: course_service.record_oral_turn(
                    session, self.user_id, mission_id=self.module.id, turn_id="race-turn",
                    response="changed", evaluation=self._oral_evaluation("same bounded feedback"),
                ),
            )
            self._assert_error(
                "idempotency_conflict",
                lambda: course_service.record_checkpoint_attempt(
                    session, self.user_id, checkpoint_id=self.module.checkpoint.id,
                    request_id="race-checkpoint", answers={"answer": "changed"},
                    evaluation=self._evaluation(False, "same feedback"),
                ),
            )

    def test_content_link_save_delete_is_owner_scoped_receipted_and_revisioned(self):
        with Session(self.engine) as session:
            self._enroll(session)
            own_book = Book(
                user_id=self.user_id, title="Inference Engineering",
                original_filename="links.pdf", storage_path="links.pdf", sha256="links-own",
                status="ready", activated=True,
            )
            other_book = Book(
                user_id=self.other_id, title="Inference Engineering",
                original_filename="other-links.pdf", storage_path="other-links.pdf",
                sha256="links-other", status="ready", activated=True,
            )
            session.add(own_book); session.add(other_book); session.commit()
            session.refresh(own_book); session.refresh(other_book)
            first = Concept(
                slug="owned-link-first", track="Inference Engineering",
                title=self.module.title, chapter=self.module.title, source="book",
                owner_user_id=self.user_id, book_id=own_book.id,
            )
            second = Concept(
                slug="owned-link-second", track="Inference Engineering",
                title=self.module.title, chapter=self.module.title, source="book",
                owner_user_id=self.user_id, book_id=own_book.id,
            )
            private = Concept(
                slug="private-course-link", track="Inference Engineering",
                title=self.module.title, chapter=self.module.title, source="book",
                owner_user_id=self.other_id, book_id=other_book.id,
            )
            session.add(first); session.add(second); session.add(private); session.commit()
            preview = course_service.reconciliation_preview(
                session, self.user_id, self.module.id, scan=True,
            )
            self.assertEqual(len(preview["candidates"]), 2)
            first_candidate, second_candidate = preview["candidates"]
            self._assert_error(
                "candidate_fingerprint_conflict",
                lambda: course_service.reconcile_content(
                    session, self.user_id, module_id=self.module.id,
                    candidate_fingerprint="0" * 64, expected_revision=0,
                    request_id="private-link",
                ),
            )
            saved = course_service.reconcile_content(
                session, self.user_id, module_id=self.module.id,
                candidate_fingerprint=first_candidate["candidate_fingerprint"], expected_revision=0,
                request_id="link-save-1",
            )
            replay = course_service.reconcile_content(
                session, self.user_id, module_id=self.module.id,
                candidate_fingerprint=first_candidate["candidate_fingerprint"], expected_revision=0,
                request_id="link-save-1",
            )
            self.assertEqual(replay.body, saved.body)
            self.assertTrue(replay.replayed)
            updated = course_service.reconcile_content(
                session, self.user_id, module_id=self.module.id,
                candidate_fingerprint=second_candidate["candidate_fingerprint"], expected_revision=1,
                request_id="link-save-2",
            )
            self.assertEqual(updated.body["revision"], 2)
            self._assert_error(
                "stale_revision",
                lambda: course_service.delete_content_link(
                    session, self.user_id, link_id=updated.body["link_id"], expected_revision=1,
                    candidate_fingerprint=first_candidate["candidate_fingerprint"],
                    request_id="link-delete-stale",
                ),
            )
            deleted = course_service.delete_content_link(
                session, self.user_id, link_id=updated.body["link_id"], expected_revision=2,
                candidate_fingerprint=second_candidate["candidate_fingerprint"],
                request_id="link-delete",
            )
            replay_deleted = course_service.delete_content_link(
                session, self.user_id, link_id=updated.body["link_id"], expected_revision=2,
                candidate_fingerprint=second_candidate["candidate_fingerprint"],
                request_id="link-delete",
            )
            self.assertTrue(deleted.body["deleted"])
            self.assertEqual(replay_deleted.body, deleted.body)
            self.assertEqual(session.exec(select(CourseContentLink)).all(), [])
            self._assert_error(
                "link_not_found",
                lambda: course_service.delete_content_link(
                    session, self.user_id, link_id=updated.body["link_id"], expected_revision=2,
                    candidate_fingerprint=second_candidate["candidate_fingerprint"],
                    request_id="link-delete-missing",
                ),
            )

    def test_content_link_match_kind_is_closed_to_deterministic_precedence(self):
        with Session(self.engine) as session:
            self._enroll(session)
            concept = Concept(slug="match-kind", track="Inference", title="Match Kind")
            session.add(concept)
            session.commit()
            session.refresh(concept)
            self.assertEqual(
                course_service.VALID_MATCH_KINDS,
                {"owned_exact", "legacy_exact", "explicit_supplement_alias"},
            )
            session.add(CourseContentLink(
                user_id=self.user_id, module_id=self.module.id, concept_id=concept.id,
                match_kind="arbitrary", candidate_fingerprint="direct-invalid",
            ))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()

    def test_reconciliation_dry_run_uses_exact_owned_precedence_and_never_mutates_sources(self):
        with Session(self.engine) as session:
            self._enroll(session)
            book = Book(
                user_id=self.user_id, title="Inference Engineering",
                original_filename="inference.pdf", storage_path="private.pdf",
                sha256="owned-sha", status="ready", activated=True,
            )
            session.add(book); session.commit(); session.refresh(book)
            owned = Concept(
                slug="owned-exact-module", track="Inference Engineering",
                title=self.module.title, chapter=self.module.title, source="book",
                book="Inference Engineering", owner_user_id=self.user_id, book_id=book.id,
            )
            legacy = Concept(
                slug="inference-engineering-legacy-module", track="Inference Engineering",
                title=self.module.title, chapter=self.module.title, source="book",
                book="Inference Engineering", sequence=1000,
            )
            supplement = Concept(
                slug="prereq-broad-foundation", track="Foundations",
                title=self.module.title, source="ai",
            )
            session.add(owned); session.add(legacy); session.add(supplement)
            session.commit(); session.refresh(owned)
            session.add(Card(concept_id=owned.id, prompt="preserve", answer="preserve"))
            session.commit()
            source_counts = (
                len(session.exec(select(Book)).all()), len(session.exec(select(Concept)).all()),
                len(session.exec(select(Card)).all()),
            )
            self.assertEqual(
                course_service.reconciliation_preview(
                    session, self.user_id, self.module.id, scan=False,
                )["state"],
                "not_scanned",
            )
            preview = course_service.reconciliation_preview(
                session, self.user_id, self.module.id, scan=True,
            )
            self.assertEqual(preview["state"], "needs_confirmation")
            self.assertEqual([item["concept_id"] for item in preview["candidates"]], [owned.id])
            self.assertEqual(preview["candidates"][0]["match_kind"], "owned_exact")
            self.assertEqual(session.exec(select(CourseContentLink)).all(), [])
            self.assertEqual(source_counts, (
                len(session.exec(select(Book)).all()), len(session.exec(select(Concept)).all()),
                len(session.exec(select(Card)).all()),
            ))

    def test_reconciliation_confirm_accepts_only_current_preview_fingerprint(self):
        with Session(self.engine) as session:
            self._enroll(session)
            book = Book(
                user_id=self.user_id, title="Inference Engineering",
                original_filename="strict.pdf", storage_path="strict.pdf",
                sha256="strict-reconcile", status="ready", activated=True,
            )
            session.add(book); session.commit(); session.refresh(book)
            concept = Concept(
                slug="strict-owned-exact", track="Inference Engineering",
                title=self.module.title, chapter=self.module.title, source="book",
                book="Inference Engineering", owner_user_id=self.user_id, book_id=book.id,
            )
            session.add(concept); session.commit(); session.refresh(concept)
            preview = course_service.reconciliation_preview(
                session, self.user_id, self.module.id, scan=True,
            )
            self.assertEqual(preview["revision"], 0)
            fingerprint = preview["candidates"][0]["candidate_fingerprint"]
            linked = course_service.reconcile_content(
                session, self.user_id, module_id=self.module.id,
                candidate_fingerprint=fingerprint, expected_revision=0,
                request_id="strict-confirm",
            )
            self.assertEqual(linked.body["concept_id"], concept.id)
            self.assertEqual(linked.body["match_kind"], "owned_exact")

        with Session(self.engine) as session:
            session.exec(select(Concept).where(Concept.id == concept.id)).one().title = "Renamed"
            session.commit()
            self._assert_error(
                "candidate_fingerprint_conflict",
                lambda: course_service.reconcile_content(
                    session, self.user_id, module_id=self.module.id,
                    candidate_fingerprint=fingerprint, expected_revision=1,
                    request_id="strict-stale-candidate",
                ),
            )

    def test_legacy_sequence_threshold_never_auto_links_without_catalog_identity(self):
        with Session(self.engine) as session:
            self._enroll(session)
            legacy = Concept(
                slug="inference-engineering-exact", track="Inference Engineering",
                title=self.module.title, chapter=self.module.title, source="book",
                book="Inference Engineering", sequence=1000,
            )
            session.add(legacy); session.commit(); session.refresh(legacy)
            session.add(Card(concept_id=legacy.id, prompt="legacy", answer="unchanged", source="book"))
            session.commit()
            preview = course_service.reconciliation_preview(
                session, self.user_id, self.module.id, scan=True,
            )
            self.assertEqual(preview["state"], "none_found")
            self.assertEqual(preview["candidates"], [])
            self._assert_error(
                "candidate_fingerprint_conflict",
                lambda: course_service.reconcile_content(
                    session, self.user_id, module_id=self.module.id,
                    candidate_fingerprint="0" * 64,
                    expected_revision=0, request_id="legacy-reconcile",
                ),
            )
            self.assertEqual(session.exec(select(CourseContentLink)).all(), [])
            self.assertIsNotNone(session.get(Concept, legacy.id))
            self.assertEqual(session.exec(select(Card).where(Card.concept_id == legacy.id)).one().answer, "unchanged")

    def test_future_legacy_manifest_match_is_exact_and_omission_sensitive_in_service(self):
        source = next(item for item in COURSE.source_manifest if item.kind == "section")
        module = next(item for item in COURSE.modules if item.id == source.module_id)
        exact = normalize_alias_identity(source.label)
        identity = LegacyIdentity(
            id="LEGACY-IDENTITY-EXACT-SECTION-MATCH",
            slug_prefix="inference-engineering-", title_alias=exact, chapter_alias=exact,
            sequence=1000, module_id=module.id, lesson_id=f"{module.id}-LESSON",
            source_id=source.id,
        )
        synthetic = replace(COURSE, legacy_identities=(identity,))
        validate_catalog(synthetic)
        candidate = Concept(
            id=999, slug="inference-engineering-exact-section-0",
            track="Inference Engineering", title=source.label, chapter=source.label,
            source="book", book="Inference Engineering", sequence=1000,
        )
        matched = course_service._legacy_candidate(candidate, module, catalog=synthetic)
        self.assertEqual(matched["match_kind"], "legacy_exact")
        self.assertEqual(matched["concept_id"], 999)
        omissions = (
            {"slug": "other-book-exact-section-0"},
            {"title": f"{source.label} extra"},
            {"chapter": f"{source.label} extra"},
            {"sequence": 1001},
        )
        for update in omissions:
            with self.subTest(update=update):
                changed = candidate.model_copy(update=update)
                self.assertIsNone(course_service._legacy_candidate(
                    changed, module, catalog=synthetic,
                ))

    def test_reconciliation_ambiguity_confirmation_conflict_and_concurrent_replay(self):
        with Session(self.engine) as session:
            self._enroll(session)
            book = Book(
                user_id=self.user_id, title="Inference Engineering",
                original_filename="duplicate.pdf", storage_path="private.pdf",
                sha256="duplicate-sha", status="ready", activated=True,
            )
            session.add(book); session.commit(); session.refresh(book)
            for suffix in ("a", "b"):
                session.add(Concept(
                    slug=f"owned-duplicate-{suffix}", track="Inference Engineering",
                    title=self.module.title, chapter=self.module.title, source="book",
                    book="Inference Engineering", owner_user_id=self.user_id, book_id=book.id,
                ))
            session.commit()
            preview = course_service.reconciliation_preview(
                session, self.user_id, self.module.id, scan=True,
            )
            self.assertEqual(preview["state"], "needs_confirmation")
            self.assertEqual(len(preview["candidates"]), 2)
            chosen = preview["candidates"][0]
            self.assertEqual(session.exec(select(CourseContentLink)).all(), [])
            self._assert_error(
                "candidate_fingerprint_conflict",
                lambda: course_service.reconcile_content(
                    session, self.user_id, module_id=self.module.id,
                    candidate_fingerprint="0" * 64,
                    expected_revision=0, request_id="ambiguous-bad",
                ),
            )

        results, errors = self._race(
            "insert into coursecontentlink",
            lambda session: course_service.reconcile_content(
                session, self.user_id, module_id=self.module.id,
                candidate_fingerprint=chosen["candidate_fingerprint"],
                expected_revision=0, request_id="ambiguous-confirm",
            ),
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].body, results[1].body)
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(CourseContentLink)).all()), 1)
            self.assertEqual(len(session.exec(select(Concept)).all()), 2)
            other = self._enroll(session, self.other_id, "other-reconcile-enroll")
            self.assertFalse(other.replayed)
            self._assert_error(
                "candidate_fingerprint_conflict",
                lambda: course_service.reconcile_content(
                    session, self.other_id, module_id=self.module.id,
                    candidate_fingerprint=chosen["candidate_fingerprint"],
                    expected_revision=0, request_id="ambiguous-confirm",
                ),
            )
            self._assert_error(
                "idempotency_conflict",
                lambda: course_service.reconcile_content(
                    session, self.user_id, module_id=self.module.id,
                    candidate_fingerprint=preview["candidates"][1]["candidate_fingerprint"],
                    expected_revision=0, request_id="ambiguous-confirm",
                ),
            )

    def test_reconciliation_partial_stale_cross_user_and_atomic_failure_states(self):
        with Session(self.engine) as session:
            self._enroll(session)
            other_book = Book(
                user_id=self.other_id, title="Inference Engineering",
                original_filename="other.pdf", storage_path="other.pdf",
                sha256="other-reconcile", status="ready", activated=True,
            )
            partial = Book(
                user_id=self.user_id, title="Inference—Engineering",
                original_filename="partial.pdf", storage_path="partial.pdf",
                sha256="partial-reconcile", status="partial", activated=True,
            )
            session.add(other_book); session.add(partial); session.commit()
            session.refresh(other_book); session.refresh(partial)
            session.add(Concept(
                slug="other-private-exact", track="Inference Engineering",
                title=self.module.title, chapter=self.module.title, source="book",
                owner_user_id=self.other_id, book_id=other_book.id,
            ))
            owned = Concept(
                slug="partial-owned-exact", track="Inference Engineering",
                title=self.module.title.swapcase(), chapter=self.module.title,
                source="book", owner_user_id=self.user_id, book_id=partial.id,
            )
            session.add(owned); session.commit(); session.refresh(owned)
            owned_id = owned.id
            preview = course_service.reconciliation_preview(
                session, self.user_id, self.module.id, scan=True,
            )
            self.assertEqual(preview["state"], "partial")
            self.assertEqual([item["concept_id"] for item in preview["candidates"]], [owned_id])
            linked = course_service.reconcile_content(
                session, self.user_id, module_id=self.module.id,
                candidate_fingerprint=preview["candidates"][0]["candidate_fingerprint"],
                expected_revision=0, request_id="partial-link",
            )
            self.assertEqual(linked.body["state"], "linked")
            self.assertEqual(
                course_service.reconciliation_preview(
                    session, self.user_id, self.module.id, scan=True,
                )["state"],
                "linked",
            )
            owned.title = "Renamed away from the approved exact alias"
            owned.chapter = "Renamed"
            session.add(owned); session.commit()
            self.assertEqual(
                course_service.reconciliation_preview(
                    session, self.user_id, self.module.id, scan=True,
                )["state"],
                "stale",
            )

        with Session(self.engine) as session:
            link = session.exec(select(CourseContentLink)).one()
            session.delete(link); session.commit()
        with self.engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TRIGGER fail_reconcile_receipt BEFORE INSERT ON coursemutationreceipt "
                "WHEN NEW.operation='reconcile' AND NEW.request_id='reconcile-rollback' "
                "BEGIN SELECT RAISE(ABORT, 'reconcile receipt failure'); END"
            )
        with Session(self.engine) as session:
            owned = session.get(Concept, owned_id)
            owned.title = self.module.title; owned.chapter = self.module.title
            session.add(owned); session.commit()
            with self.assertRaises(DatabaseError):
                course_service.reconcile_content(
                    session, self.user_id, module_id=self.module.id,
                    candidate_fingerprint=course_service.reconciliation_preview(
                        session, self.user_id, self.module.id, scan=True,
                    )["candidates"][0]["candidate_fingerprint"],
                    expected_revision=0, request_id="reconcile-rollback",
                )
            session.rollback()
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(CourseContentLink)).all(), [])
            self.assertIsNotNone(session.get(Concept, owned_id))

    def test_receipts_are_not_automatically_pruned(self):
        with Session(self.engine) as session:
            first = self._enroll(session)
            receipt = session.exec(select(CourseMutationReceipt)).one()
            receipt.created_at = datetime(2000, 1, 1)
            session.add(receipt)
            session.commit()
            policy = course_service.receipt_retention_policy()
            self.assertEqual(policy, {"automatic_pruning": False, "retention": "enrollment_lifetime"})

        with Session(self.engine) as session:
            replay = self._enroll(session)
            self.assertTrue(replay.replayed)
            self.assertEqual(replay.body, first.body)
            self.assertEqual(len(session.exec(select(CourseMutationReceipt)).all()), 1)

    def test_receipt_insert_failure_rolls_back_domain_mutation(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TRIGGER fail_course_receipt BEFORE INSERT ON coursemutationreceipt "
                "BEGIN SELECT RAISE(ABORT, 'receipt failure'); END"
            )
        with Session(self.engine) as session:
            with self.assertRaises(DatabaseError):
                self._enroll(session)
            session.rollback()
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(CourseEnrollment)).all(), [])
            self.assertEqual(session.exec(select(CourseMutationReceipt)).all(), [])

    def test_mission_completion_is_rule_based_and_user_isolated(self):
        with Session(self.engine) as session:
            self._enroll(session)
            self._enroll(session, self.other_id, "enroll-other")
            for artifact in self.module.artifacts:
                course_service.save_artifact(
                    session,
                    self.user_id,
                    mission_id=self.module.id,
                    artifact_id=artifact.id,
                    note="Evidence captured for the required artifact.",
                    artifact_uri=f"reports/{artifact.id}.md",
                    draft_fields=self._draft(artifact),
                    expected_revision=0,
                    request_id=f"save-{artifact.id}",
                    catalog_version=COURSE_VERSION,
                )
            course_service.self_record_oral(
                session,
                self.user_id,
                mission_id=self.module.id,
                note="Recorded oral explanation.",
                expected_revision=0,
                request_id="oral-self",
                catalog_version=COURSE_VERSION,
            )
            course_service.review_oral(
                session,
                self.user_id,
                mission_id=self.module.id,
                method="self_rubric",
                acknowledgements=list(self.module.oral.rubric),
                feedback="All qualitative expectations reviewed.",
                expected_revision=1,
                request_id="oral-review",
                catalog_version=COURSE_VERSION,
            )
            ready = course_service.mission_progress(session, self.user_id, self.module.id)
            self.assertEqual(ready["state"], "ready_for_checkpoint")
            course_service.record_checkpoint_attempt(
                session,
                self.user_id,
                checkpoint_id=self.module.checkpoint.id,
                request_id="checkpoint-1",
                answers={"inventory": "captured"},
                evaluation=self._evaluation(True, "All deterministic requirements met."),
                catalog_version=COURSE_VERSION,
            )
            complete = course_service.mission_progress(session, self.user_id, self.module.id)
            self.assertEqual(complete["state"], "complete")
            self.assertEqual(course_service.mission_progress(session, self.other_id, self.module.id)["state"], "not_started")
            rows = session.exec(select(CourseMissionProgress)).all()
            self.assertEqual({row.user_id for row in rows}, {self.user_id})


if __name__ == "__main__":
    unittest.main()
