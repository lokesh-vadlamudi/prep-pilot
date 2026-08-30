from __future__ import annotations

import json
import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI
from fastapi import Response
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import auth
from app.content.inference_course import COURSE, COURSE_VERSION
from app.db import get_session
from app.models import (
    Book, Card, Concept, CourseArtifactEvidence, CourseCheckpointAttempt, CourseContentLink,
    CourseEnrollment, CourseMutationReceipt, CourseOralReview, CourseOralTurn, User,
)
from app.ratelimit import _course_ai, _course_mutation
from app.routers import course_routes


class _FakeCourseTutor:
    async def evaluate_checkpoint(self, **kwargs):
        answers = kwargs["answers"]
        passed = all(len(value.strip()) > 3 for value in answers.values())
        feedback = "Catalog evidence is sufficient." if passed else "Explanation is insufficient."
        return SimpleNamespace(passed=passed, feedback=feedback)

    async def evaluate_oral(self, **_kwargs):
        return SimpleNamespace(passed=True, feedback="Catalog rubric was satisfied.")

    async def evaluate_turn(self, **kwargs):
        return SimpleNamespace(
            feedback="The explanation identifies a concrete evidence boundary.",
            next_question=f"What deeper failure would challenge {kwargs['module'].callsign}?",
        )


class InferenceCourseRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            alice = User(username="route-alice", password_hash="x")
            bob = User(username="route-bob", password_hash="x")
            session.add(alice); session.add(bob); session.commit()
            session.refresh(alice); session.refresh(bob)
            self.alice_id, self.bob_id = alice.id, bob.id
        self.app = FastAPI()
        self.app.include_router(course_routes.router)
        self.app.dependency_overrides[get_session] = self._sessions
        self.app.dependency_overrides[auth.current_user] = self._alice
        self.app.dependency_overrides[course_routes.get_course_tutor] = _FakeCourseTutor
        self.client = TestClient(self.app)
        self.module = COURSE.modules[0]
        _course_mutation.reset(); _course_ai.reset()

    def tearDown(self) -> None:
        self.client.close()
        self.engine.dispose()

    def _sessions(self):
        with Session(self.engine) as session:
            yield session

    def _alice(self):
        with Session(self.engine) as session:
            return session.get(User, self.alice_id)

    def _bob(self):
        with Session(self.engine) as session:
            return session.get(User, self.bob_id)

    def _enroll(self, request_id: str = "route-enroll"):
        return self.client.post(
            "/api/courses/inference-engineering/enroll",
            json={"request_id": request_id, "catalog_version": COURSE_VERSION},
        )

    def _artifact(self, request_id: str = "route-artifact", revision: int = 0):
        artifact = self.module.artifacts[0]
        return self.client.put(
            f"/api/courses/inference-engineering/missions/{self.module.id}/artifacts/{artifact.id}",
            json={
                "request_id": request_id, "catalog_version": COURSE_VERSION,
                "note": "Bounded reproducible evidence.", "artifact_uri": "reports/route.md",
                "draft_fields": {
                    field: f"bounded {field}" for field in artifact.template_fields
                },
                "expected_revision": revision,
            },
        )

    def test_auth_same_origin_and_non_enumerating_unknown_module(self):
        unauthenticated = FastAPI()
        unauthenticated.include_router(course_routes.router)
        unauthenticated.dependency_overrides[get_session] = self._sessions
        with TestClient(unauthenticated) as client:
            self.assertEqual(client.get("/api/courses/inference-engineering").status_code, 401)
        rejected = self.client.post(
            "/api/courses/inference-engineering/enroll",
            headers={"Origin": "https://evil.example"},
            json={"request_id": "csrf", "catalog_version": COURSE_VERSION},
        )
        self.assertEqual(rejected.status_code, 403)
        missing = self.client.get("/api/courses/inference-engineering/modules/IC-999")
        self.assertEqual(missing.status_code, 404)
        self.assertNotIn("IC-999", missing.text)

    def test_overview_enrollment_module_and_exact_replay_metadata(self):
        overview = self.client.get("/api/courses/inference-engineering")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json()["modules"][0]["id"], "IC-00")
        self.assertEqual(overview.json()["modules"][0]["next_action"], "enroll")
        first = self._enroll()
        replay = self._enroll()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 201)
        self.assertFalse(first.json()["_meta"]["replayed"])
        self.assertTrue(replay.json()["_meta"]["replayed"])
        self.assertEqual({k: v for k, v in first.json().items() if k != "_meta"},
                         {k: v for k, v in replay.json().items() if k != "_meta"})
        conflict = self.client.post(
            "/api/courses/inference-engineering/enroll",
            json={"request_id": "route-enroll", "catalog_version": "changed"},
        )
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"]["code"], "idempotency_conflict")
        module = self.client.get(f"/api/courses/inference-engineering/modules/{self.module.id}").json()
        self.assertEqual(module["progress"]["state"], "not_started")
        self.assertIn("safety", module["lab"])
        self.assertIn("rubric", module["oral"])
        self.assertNotIn("pass_condition", module["checkpoint"])

    def test_overview_and_module_reload_contract_is_catalog_complete_owner_scoped_and_score_free(self):
        overview = self.client.get("/api/courses/inference-engineering")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json()["title"], "Inference Flight School: Token to Traffic")
        summary = overview.json()["modules"][0]
        self.assertEqual(summary["platform"], self.module.lab.platform)
        self.assertEqual(
            summary["artifacts"],
            [{
                "id": item.id, "title": item.title,
                "expectations": list(item.verification_rubric),
            } for item in self.module.artifacts],
        )

        all_source_ids = []
        for catalog_module in COURSE.modules:
            detail = self.client.get(
                f"/api/courses/inference-engineering/modules/{catalog_module.id}"
            )
            self.assertEqual(detail.status_code, 200, detail.text)
            expected_ids = list(catalog_module.source_ids)
            self.assertEqual([item["id"] for item in detail.json()["sources"]], expected_ids)
            all_source_ids.extend(expected_ids)
        self.assertEqual(len(all_source_ids), 227)
        self.assertEqual(len(set(all_source_ids)), 227)

        self._enroll()
        saved = self._artifact()
        turn = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/turn",
            json={
                "request_id": "reload-turn", "catalog_version": COURSE_VERSION,
                "response": "A bounded qualitative explanation for the first prompt.",
            },
        )
        self.assertEqual(turn.status_code, 200, turn.text)
        pending = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/self-record",
            json={
                "request_id": "reload-self", "catalog_version": COURSE_VERSION,
                "note": "Persist this offline note for a later reload.", "expected_revision": 1,
            },
        )
        self.assertEqual(pending.status_code, 200, pending.text)
        completed = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/complete",
            json={
                "request_id": "reload-complete", "catalog_version": COURSE_VERSION,
                "expected_revision": 2,
            },
        )
        self.assertEqual(completed.status_code, 200, completed.text)

        reloaded = self.client.get(
            f"/api/courses/inference-engineering/modules/{self.module.id}"
        ).json()
        self.assertEqual(reloaded["oral_state"]["state"], "reviewed")
        self.assertEqual(reloaded["oral_state"]["revision"], 3)
        self.assertEqual(reloaded["oral_state"]["self_record_note"],
                         "Persist this offline note for a later reload.")
        self.assertEqual(reloaded["oral_state"]["review_method"], "dgx")
        self.assertEqual(reloaded["oral_state"]["review_feedback"],
                         "Catalog rubric was satisfied.")
        self.assertEqual(len(reloaded["oral_state"]["turns"]), 1)
        self.assertEqual(reloaded["oral_state"]["turns"][0]["turn_id"], "reload-turn")
        artifact = reloaded["artifact_state"][0]
        self.assertTrue(artifact["completed"])
        self.assertEqual(artifact["revision"], saved.json()["revision"])
        self.assertEqual(artifact["draft_fields"], saved.json()["draft_fields"])
        self.assertEqual(artifact["artifact_uri"], "reports/route.md")

        forbidden = {"cards", "attempts", "score", "grade", "percentage", "sm2", "streak"}

        def nested_tokens(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield str(key).lower()
                    yield from nested_tokens(item)
            elif isinstance(value, list):
                for item in value:
                    yield from nested_tokens(item)
            elif isinstance(value, str):
                yield from value.lower().replace("-", " ").replace("_", " ").split()

        self.assertTrue(forbidden.isdisjoint(nested_tokens(reloaded)))
        self.app.dependency_overrides[auth.current_user] = self._bob
        private = self.client.get(
            f"/api/courses/inference-engineering/modules/{self.module.id}"
        ).json()
        self.assertFalse(any(item["completed"] for item in private["artifact_state"]))
        self.assertEqual(private["oral_state"]["state"], "not_started")
        self.assertEqual(private["oral_state"]["turns"], [])

    def test_ic12_module_and_artifact_route_use_catalog_owned_structured_selection(self):
        frontier = next(module for module in COURSE.modules if module.id == "IC-12")
        rule = frontier.selection_rule
        source_by_id = {item.id: item for item in COURSE.source_manifest}
        detail = self.client.get(
            "/api/courses/inference-engineering/modules/IC-12"
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["selection_rule"], {
            "minimum": 2,
            "maximum": 3,
            "options": [
                {"id": source_id, "label": source_by_id[source_id].label}
                for source_id in rule.options
            ],
        })
        ordinary = self.client.get(
            "/api/courses/inference-engineering/modules/IC-11"
        ).json()
        self.assertNotIn("selection_rule", ordinary)

        self._enroll()
        descriptor = frontier.artifacts[0]
        selected = [rule.options[2], rule.options[0]]
        draft = {field: f"bounded {field}" for field in descriptor.template_fields}
        draft["selected_experiments"] = selected
        path = (
            f"/api/courses/inference-engineering/missions/{frontier.id}/"
            f"artifacts/{descriptor.id}"
        )
        body = {
            "request_id": "ic12-route-selection", "catalog_version": COURSE_VERSION,
            "note": "Structured frontier evidence.", "artifact_uri": "reports/frontier.md",
            "draft_fields": draft, "expected_revision": 0,
        }
        with patch("app.course_service._require_prerequisites"):
            saved = self.client.put(path, json=body)
            replay = self.client.put(path, json=body | {
                "draft_fields": draft | {"selected_experiments": list(reversed(selected))},
            })
        self.assertEqual(saved.status_code, 201, saved.text)
        self.assertEqual(saved.json()["draft_fields"]["selected_experiments"],
                         [rule.options[0], rule.options[2]])
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertTrue(replay.json()["_meta"]["replayed"])

        invalid = draft | {"selected_experiments": "free text"}
        with patch("app.course_service._require_prerequisites"):
            rejected = self.client.put(path, json=body | {
                "request_id": "ic12-route-free-text", "draft_fields": invalid,
            })
        self.assertEqual(rejected.status_code, 422)

    def test_ic12_malformed_selection_items_return_typed_422_without_mutation(self):
        frontier = next(module for module in COURSE.modules if module.id == "IC-12")
        descriptor = frontier.artifacts[0]
        options = list(frontier.selection_rule.options)
        template = {field: f"bounded {field}" for field in descriptor.template_fields}
        path = (
            f"/api/courses/inference-engineering/missions/{frontier.id}/"
            f"artifacts/{descriptor.id}"
        )
        malformed = {
            "dict": [{"id": options[0]}, options[1]],
            "integer": [7, options[0]],
            "null": [None, options[0]],
            "nested": [[options[0]], options[1]],
            "mixed": [options[0], {"id": options[1]}],
        }
        self._enroll()
        for request_id, selection in malformed.items():
            with self.subTest(shape=request_id), patch("app.course_service._require_prerequisites"):
                response = self.client.put(path, json={
                    "request_id": f"ic12-route-malformed-{request_id}",
                    "catalog_version": COURSE_VERSION,
                    "note": "Structured frontier evidence.",
                    "artifact_uri": "reports/frontier.md",
                    "draft_fields": template | {"selected_experiments": selection},
                    "expected_revision": 0,
                })
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(response.json()["error"]["code"],
                                 "invalid_experiment_selection")
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(CourseArtifactEvidence)).all(), [])
            self.assertEqual(session.exec(select(CourseMutationReceipt).where(
                CourseMutationReceipt.operation == "artifact_upsert",
            )).all(), [])

    def test_ic14_ic16_module_rules_and_structured_artifact_route_contract(self):
        workplace = next(module for module in COURSE.modules if module.id == "IC-14")
        papers = next(module for module in COURSE.modules if module.id == "IC-16")
        for module in (workplace, papers):
            detail = self.client.get(
                f"/api/courses/inference-engineering/modules/{module.id}"
            )
            self.assertEqual(detail.status_code, 200, detail.text)
            exposed = detail.json()["artifacts"][0]["completion_rule"]
            rule = module.artifacts[0].completion_rule
            self.assertEqual(exposed["id"], rule.id)
            self.assertEqual(
                [entry["source_id"] for entry in exposed["entries"]],
                [entry.source_id for entry in rule.entries],
            )
        ordinary = self.client.get(
            "/api/courses/inference-engineering/modules/IC-13"
        ).json()
        self.assertNotIn("completion_rule", ordinary["artifacts"][0])

        self._enroll()
        artifact = workplace.artifacts[0]
        rule = artifact.completion_rule
        draft = {field: f"bounded {field}" for field in artifact.template_fields}
        chosen = rule.entries[2].source_id
        draft.update({
            "project_scopes": [
                {"project_id": entry.source_id, "scope": f"Scope for {entry.source_id}."}
                for entry in reversed(rule.entries)
            ],
            "chosen_project_id": chosen,
            "selected_proposal": {"project_id": chosen, "evidence": "Measured private-data need."},
        })
        with patch("app.course_service._require_prerequisites"):
            saved = self.client.put(
                f"/api/courses/inference-engineering/missions/{workplace.id}/artifacts/{artifact.id}",
                json={
                    "request_id": "ic14-route", "catalog_version": COURSE_VERSION,
                    "note": "All options scoped.", "artifact_uri": "reports/workplace.md",
                    "draft_fields": draft, "expected_revision": 0,
                },
            )
        self.assertEqual(saved.status_code, 201, saved.text)
        self.assertEqual(
            [entry["project_id"] for entry in saved.json()["draft_fields"]["project_scopes"]],
            [entry.source_id for entry in rule.entries],
        )

    def test_strict_mutation_schemas_forbid_pass_grade_feedback_and_unknown_fields(self):
        self._enroll()
        path = f"/api/courses/inference-engineering/checkpoints/{self.module.checkpoint.id}/submit"
        base = {
            "request_id": "forged", "catalog_version": COURSE_VERSION,
            "answers": {"response_1": "one", "response_2": "two"},
        }
        for field, value in (("passed", True), ("grade", 100), ("trusted_evaluator", {})):
            response = self.client.post(path, json=base | {field: value})
            self.assertEqual(response.status_code, 422, response.text)
        oral = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/turn",
            json={
                "request_id": "turn-extra", "catalog_version": COURSE_VERSION,
                "response": "candidate response", "feedback": "caller-controlled",
            },
        )
        self.assertEqual(oral.status_code, 422)

    def test_artifact_checkpoint_server_evaluation_and_typed_conflicts(self):
        self._enroll()
        saved = self._artifact()
        self.assertEqual(saved.status_code, 201)
        self.assertFalse(saved.json()["_meta"]["replayed"])
        replay = self._artifact()
        self.assertTrue(replay.json()["_meta"]["replayed"])
        stale = self._artifact("route-artifact-stale", revision=0)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"]["code"], "stale_revision")
        checkpoint_path = (
            f"/api/courses/inference-engineering/checkpoints/{self.module.checkpoint.id}/submit"
        )
        submitted = self.client.post(checkpoint_path, json={
            "request_id": "route-checkpoint", "catalog_version": COURSE_VERSION,
            "answers": {"response_1": "Mechanism explained.", "response_2": "Evidence defended."},
        })
        self.assertEqual(submitted.status_code, 200, submitted.text)
        self.assertTrue(submitted.json()["passed"])
        checkpoint_conflict = self.client.post(checkpoint_path, json={
            "request_id": "route-checkpoint", "catalog_version": COURSE_VERSION,
            "answers": {"response_1": "changed", "response_2": "Evidence defended."},
        })
        self.assertEqual(checkpoint_conflict.status_code, 409)
        body_text = json.dumps(submitted.json()).lower()
        for forbidden in ("grade", "score", "percentage", "points", "streak"):
            self.assertNotIn(forbidden, body_text)
        with Session(self.engine) as session:
            self.assertTrue(session.exec(select(CourseCheckpointAttempt)).one().passed)

    def test_artifact_route_requires_exact_catalog_structured_draft(self):
        self._enroll()
        artifact = self.module.artifacts[0]
        path = (
            f"/api/courses/inference-engineering/missions/{self.module.id}/artifacts/{artifact.id}"
        )
        base = {
            "request_id": "structured-route", "catalog_version": COURSE_VERSION,
            "note": "Structured evidence.", "artifact_uri": "reports/structured.md",
            "expected_revision": 0,
        }
        self.assertEqual(self.client.put(path, json=base).status_code, 422)
        partial = {field: "bounded" for field in artifact.template_fields[1:]}
        self.assertEqual(
            self.client.put(path, json=base | {"request_id": "partial-route", "draft_fields": partial}).status_code,
            422,
        )
        complete = {field: f"value for {field}" for field in artifact.template_fields}
        saved = self.client.put(path, json=base | {"draft_fields": complete})
        self.assertEqual(saved.status_code, 201, saved.text)
        self.assertEqual(saved.json()["draft_fields"], complete)
        for forged in ("template_key", "output_format", "verification_rubric", "source_ids"):
            response = self.client.put(
                path, json=base | {"request_id": f"forged-{forged}", "draft_fields": complete, forged: "x"},
            )
            self.assertEqual(response.status_code, 422, response.text)

    def test_nonsense_checkpoint_answers_cannot_pass_from_shape_alone(self):
        self._enroll()
        self._artifact()
        response = self.client.post(
            f"/api/courses/inference-engineering/checkpoints/{self.module.checkpoint.id}/submit",
            json={
                "request_id": "nonsense-checkpoint", "catalog_version": COURSE_VERSION,
                "answers": {"response_1": "x", "response_2": "x"},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["passed"])

    def test_linked_lesson_is_owner_and_link_scoped_and_data_minimal(self):
        self._enroll()
        with Session(self.engine) as session:
            book = Book(
                user_id=self.alice_id, title="Inference Engineering",
                original_filename="lesson.pdf", storage_path="private/lesson.pdf",
                sha256="route-linked-lesson", status="ready", activated=True,
            )
            session.add(book); session.commit(); session.refresh(book)
            book_id = book.id
            owned = Concept(
                slug="route-private", track="Inference Engineering", title=self.module.title,
                chapter=self.module.title, book="Inference Engineering",
                summary="Safe summary", lesson_md="Owner-only lesson", source="book",
                owner_user_id=self.alice_id, book_id=book.id,
            )
            session.add(owned); session.commit(); session.refresh(owned)
            concept_id = owned.id
        preview = self.client.get(
            f"/api/courses/inference-engineering/reconcile/{self.module.id}?scan=true"
        ).json()
        reconcile = self.client.post("/api/courses/inference-engineering/reconcile", json={
            "request_id": "route-link", "catalog_version": COURSE_VERSION,
            "module_id": self.module.id,
            "candidate_fingerprint": preview["candidates"][0]["candidate_fingerprint"],
            "expected_revision": 0,
        })
        self.assertEqual(reconcile.status_code, 200, reconcile.text)
        linked_module = self.client.get(
            f"/api/courses/inference-engineering/modules/{self.module.id}"
        ).json()
        self.assertEqual(linked_module["linked_topic"]["concept_id"], concept_id)
        lesson_path = (
            f"/api/courses/inference-engineering/modules/{self.module.id}/linked-topics/{concept_id}"
        )
        lesson = self.client.get(lesson_path)
        self.assertEqual(lesson.status_code, 200)
        self.assertEqual(lesson.json()["lesson_md"], "Owner-only lesson")
        forbidden = {"cards", "attempts", "status", "grade", "score", "sm2", "sm-2", "streak"}
        self.assertTrue(forbidden.isdisjoint({key.lower() for key in lesson.json()}))
        self.assertNotIn("/topics/", lesson.json()["course_url"])

        with Session(self.engine) as session:
            renamed = session.get(Concept, concept_id)
            renamed.title = "Renamed after reconciliation"
            session.add(renamed)
            session.commit()
            self.assertIsNotNone(session.exec(select(CourseContentLink).where(
                CourseContentLink.user_id == self.alice_id,
                CourseContentLink.module_id == self.module.id,
                CourseContentLink.concept_id == concept_id,
            )).first())
        stale_module = self.client.get(
            f"/api/courses/inference-engineering/modules/{self.module.id}"
        )
        self.assertEqual(stale_module.status_code, 200)
        self.assertNotIn("linked_topic", stale_module.json())
        self.assertEqual(self.client.get(lesson_path).status_code, 404)
        with Session(self.engine) as session:
            preserved_link = session.exec(select(CourseContentLink).where(
                CourseContentLink.user_id == self.alice_id,
                CourseContentLink.module_id == self.module.id,
            )).one()
            self.assertEqual(preserved_link.concept_id, concept_id)
            self.assertEqual(preserved_link.revision, 1)

            renamed = session.get(Concept, concept_id)
            renamed.title = self.module.title
            source_book = session.get(Book, renamed.book_id)
            source_book.activated = False
            session.add(renamed); session.add(source_book); session.commit()
        ineligible_module = self.client.get(
            f"/api/courses/inference-engineering/modules/{self.module.id}"
        )
        self.assertNotIn("linked_topic", ineligible_module.json())
        self.assertEqual(self.client.get(lesson_path).status_code, 404)

        with Session(self.engine) as session:
            source_book = session.get(Book, book_id)
            source_book.activated = True
            session.add(source_book)
            session.delete(session.get(Concept, concept_id))
            session.commit()
            self.assertIsNotNone(session.exec(select(CourseContentLink).where(
                CourseContentLink.user_id == self.alice_id,
                CourseContentLink.module_id == self.module.id,
            )).first())
        missing_module = self.client.get(
            f"/api/courses/inference-engineering/modules/{self.module.id}"
        )
        self.assertNotIn("linked_topic", missing_module.json())
        self.assertEqual(self.client.get(lesson_path).status_code, 404)

        self.app.dependency_overrides[auth.current_user] = self._bob
        self.assertEqual(self.client.get(lesson_path).status_code, 404)

    def test_reconciliation_route_requires_read_only_preview_then_fingerprinted_confirm(self):
        self._enroll()
        with Session(self.engine) as session:
            book = Book(
                user_id=self.alice_id, title="Inference Engineering",
                original_filename="route.pdf", storage_path="private/route.pdf",
                sha256="route-reconcile", status="ready", activated=True,
            )
            session.add(book); session.commit(); session.refresh(book)
            concept = Concept(
                slug="route-owned-exact", track="Inference Engineering",
                title=self.module.title, chapter=self.module.title, source="book",
                book="Inference Engineering", owner_user_id=self.alice_id, book_id=book.id,
            )
            broad = Concept(
                slug="prereq-broad-route", track="Foundations",
                title=self.module.title, source="ai",
            )
            session.add(concept); session.add(broad); session.commit(); session.refresh(concept)
            session.add(Card(concept_id=concept.id, prompt="preserve", answer="preserve"))
            session.commit()
            concept_id = concept.id
            source_counts = (
                len(session.exec(select(Book)).all()), len(session.exec(select(Concept)).all()),
                len(session.exec(select(Card)).all()),
            )

        preview = self.client.get(
            f"/api/courses/inference-engineering/reconcile/{self.module.id}?scan=true"
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual((preview.json()["state"], preview.json()["revision"]),
                         ("needs_confirmation", 0))
        self.assertEqual([item["concept_id"] for item in preview.json()["candidates"]], [concept_id])
        self.assertEqual(preview.json()["candidates"][0]["match_kind"], "owned_exact")
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(CourseContentLink)).all(), [])
            self.assertEqual(session.exec(select(CourseMutationReceipt).where(
                CourseMutationReceipt.operation == "reconcile",
            )).all(), [])

        fingerprint = preview.json()["candidates"][0]["candidate_fingerprint"]
        strict = {
            "request_id": "route-strict-confirm", "catalog_version": COURSE_VERSION,
            "module_id": self.module.id, "candidate_fingerprint": fingerprint,
            "expected_revision": 0,
        }
        forged = strict | {
            "concept_id": concept_id, "match_kind": "owned_exact", "title": self.module.title,
        }
        self.assertEqual(
            self.client.post("/api/courses/inference-engineering/reconcile", json=forged).status_code,
            422,
        )
        confirmed = self.client.post("/api/courses/inference-engineering/reconcile", json=strict)
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["concept_id"], concept_id)
        replay = self.client.post("/api/courses/inference-engineering/reconcile", json=strict)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["_meta"]["replayed"])
        changed = self.client.post(
            "/api/courses/inference-engineering/reconcile",
            json=strict | {"candidate_fingerprint": "0" * 64},
        )
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(changed.json()["error"]["code"], "idempotency_conflict")
        with Session(self.engine) as session:
            self.assertEqual(source_counts, (
                len(session.exec(select(Book)).all()), len(session.exec(select(Concept)).all()),
                len(session.exec(select(Card)).all()),
            ))

    def test_link_delete_replays_after_row_is_gone_and_preserves_source_rows(self):
        self._enroll()
        with Session(self.engine) as session:
            book = Book(
                user_id=self.alice_id, title="Inference Engineering",
                original_filename="delete.pdf", storage_path="private/delete.pdf",
                sha256="delete-reconcile", status="ready", activated=True,
            )
            session.add(book); session.commit(); session.refresh(book)
            concept = Concept(
                slug="route-delete-exact", track="Inference Engineering",
                title=self.module.title, chapter=self.module.title, source="book",
                book="Inference Engineering", owner_user_id=self.alice_id, book_id=book.id,
            )
            session.add(concept); session.commit(); session.refresh(concept)
            session.add(Card(concept_id=concept.id, prompt="keep", answer="keep")); session.commit()
            concept_id = concept.id
        preview = self.client.get(
            f"/api/courses/inference-engineering/reconcile/{self.module.id}?scan=true"
        ).json()
        confirmed = self.client.post("/api/courses/inference-engineering/reconcile", json={
            "request_id": "delete-confirm", "catalog_version": COURSE_VERSION,
            "module_id": self.module.id,
            "candidate_fingerprint": preview["candidates"][0]["candidate_fingerprint"],
            "expected_revision": 0,
        }).json()
        body = {
            "request_id": "delete-strict", "catalog_version": COURSE_VERSION,
            "expected_revision": 1,
            "candidate_fingerprint": confirmed["candidate_fingerprint"],
        }
        path = f"/api/courses/inference-engineering/links/{confirmed['link_id']}"
        deleted = self.client.request("DELETE", path, json=body)
        replay = self.client.request("DELETE", path, json=body)
        self.assertEqual((deleted.status_code, replay.status_code), (200, 200))
        self.assertTrue(replay.json()["_meta"]["replayed"])
        self.assertEqual(
            {key: value for key, value in deleted.json().items() if key != "_meta"},
            {key: value for key, value in replay.json().items() if key != "_meta"},
        )
        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(Concept, concept_id))
            self.assertEqual(session.exec(select(Card).where(Card.concept_id == concept_id)).one().answer,
                             "keep")
            self.assertEqual(session.exec(select(CourseContentLink)).all(), [])

    def test_link_delete_uses_owner_scoped_id_and_optimistic_preconditions(self):
        self._enroll()
        with Session(self.engine) as session:
            concept = Concept(slug="route-public", track="Inference", title="Public lesson")
            session.add(concept); session.commit(); session.refresh(concept)
            link = CourseContentLink(
                user_id=self.alice_id, module_id=self.module.id, concept_id=concept.id,
                match_kind="legacy_exact", candidate_fingerprint="d" * 64, revision=1,
            )
            session.add(link); session.commit(); session.refresh(link)
            link_id = link.id
        stale = self.client.request(
            "DELETE", f"/api/courses/inference-engineering/links/{link_id}",
            json={
                "request_id": "delete-stale", "catalog_version": COURSE_VERSION,
                "expected_revision": 0, "candidate_fingerprint": "w" * 64,
            },
        )
        self.assertEqual(stale.status_code, 409)
        deleted = self.client.request(
            "DELETE", f"/api/courses/inference-engineering/links/{link_id}",
            json={
                "request_id": "delete-good", "catalog_version": COURSE_VERSION,
                "expected_revision": 1, "candidate_fingerprint": "d" * 64,
            },
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["deleted"])
        missing = self.client.request(
            "DELETE", "/api/courses/inference-engineering/links/999999",
            json={
                "request_id": "delete-missing", "catalog_version": COURSE_VERSION,
                "expected_revision": 0, "candidate_fingerprint": "m" * 64,
            },
        )
        self.assertEqual(missing.status_code, 404)

    def test_offline_oral_review_persists_without_numeric_results(self):
        self._enroll()
        recorded = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/self-record",
            json={
                "request_id": "route-self", "catalog_version": COURSE_VERSION,
                "note": "I recorded the qualitative explanation.", "expected_revision": 0,
            },
        )
        self.assertEqual(recorded.json()["review_state"], "awaiting_review")
        reviewed = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/review",
            json={
                "request_id": "route-review", "catalog_version": COURSE_VERSION,
                "method": "self", "acknowledgements": list(self.module.oral.rubric),
                "reflection": "Reviewed every qualitative expectation.", "expected_revision": 1,
            },
        )
        self.assertEqual(reviewed.status_code, 200, reviewed.text)
        self.assertEqual(reviewed.json()["review_state"], "reviewed")
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(CourseOralReview)).one().state, "reviewed")

    def test_online_oral_turn_replay_conflict_and_server_completion(self):
        self._enroll()
        path = f"/api/courses/inference-engineering/oral/{self.module.id}/turn"
        body = {
            "request_id": "route-turn", "catalog_version": COURSE_VERSION,
            "response": "I separated measured evidence from design inference.",
        }
        first = self.client.post(path, json=body)
        replay = self.client.post(path, json=body)
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["_meta"]["replayed"])
        self.assertTrue(replay.json()["_meta"]["replayed"])
        conflict = self.client.post(path, json=body | {"response": "changed"})
        self.assertEqual(conflict.status_code, 409)
        pending = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/self-record",
            json={
                "request_id": "route-turn-pending", "catalog_version": COURSE_VERSION,
                "note": "Persisted explanation for trusted DGX review.",
                "expected_revision": 1,
            },
        )
        self.assertEqual(pending.json()["review_state"], "awaiting_review")
        async def accepted(**_kwargs):
            return SimpleNamespace(passed=True, feedback="Catalog rubric was satisfied.")

        self.app.dependency_overrides[course_routes.get_course_tutor] = lambda: SimpleNamespace(
            evaluate_oral=accepted,
        )
        completed = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/complete",
            json={
                "request_id": "route-complete", "catalog_version": COURSE_VERSION,
                "expected_revision": 2,
            },
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(completed.json()["review_state"], "reviewed")

        async def unavailable(**_kwargs):
            raise AssertionError("an exact replay must not call the evaluator")

        self.app.dependency_overrides[course_routes.get_course_tutor] = lambda: SimpleNamespace(
            evaluate_oral=unavailable,
        )
        replayed = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/complete",
            json={
                "request_id": "route-complete", "catalog_version": COURSE_VERSION,
                "expected_revision": 2,
            },
        )
        self.assertEqual(replayed.status_code, 200, replayed.text)
        self.assertTrue(replayed.json()["_meta"]["replayed"])

    def test_oral_turn_is_tutor_grounded_persisted_and_replays_before_ai(self):
        self._enroll()
        calls = []

        async def turn_evaluator(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                feedback="The explanation names the observed runtime boundary.",
                next_question="How would that boundary fail under concurrent model loading?",
            )

        self.app.dependency_overrides[course_routes.get_course_tutor] = lambda: SimpleNamespace(
            evaluate_turn=turn_evaluator,
        )
        path = f"/api/courses/inference-engineering/oral/{self.module.id}/turn"
        body = {
            "request_id": "grounded-turn", "catalog_version": COURSE_VERSION,
            "response": "I would inspect the runtime and driver boundary before loading weights.",
        }
        first = self.client.post(path, json=body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["prompt"], self.module.oral.opening_prompt)
        self.assertEqual(first.json()["user_response"], body["response"])
        self.assertEqual(first.json()["feedback"],
                         "The explanation names the observed runtime boundary.")
        self.assertEqual(first.json()["next_question"],
                         "How would that boundary fail under concurrent model loading?")
        self.assertEqual((first.json()["state"], first.json()["revision"]), ("practicing", 1))
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(_course_ai._hits["testclient"]), 1)
        self.assertIn(self.module.oral.opening_prompt, calls[0]["prompt"])

        detail = self.client.get(
            f"/api/courses/inference-engineering/modules/{self.module.id}"
        ).json()
        self.assertEqual(detail["oral_state"]["turns"][0]["next_question"],
                         first.json()["next_question"])

        old_limit = _course_ai.limit
        try:
            _course_ai.reset(); _course_ai.limit = 0
            replay = self.client.post(path, json=body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertTrue(replay.json()["_meta"]["replayed"])
            self.assertEqual(len(calls), 1)
            conflict = self.client.post(path, json=body | {"response": "changed evidence"})
            self.assertEqual(conflict.status_code, 409)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(_course_ai._hits.get("testclient", ())), 0)
        finally:
            _course_ai.limit = old_limit
            _course_ai.reset()

    def test_weak_oral_turn_is_formative_while_tutor_failures_do_not_mutate(self):
        self._enroll()
        path = f"/api/courses/inference-engineering/oral/{self.module.id}/turn"
        body = {
            "request_id": "failed-turn", "catalog_version": COURSE_VERSION,
            "response": "A bounded but insufficient explanation.",
        }

        async def formative(**_kwargs):
            return SimpleNamespace(
                feedback="More mechanism evidence is needed.",
                next_question="Which runtime boundary is directly observable?",
            )

        self.app.dependency_overrides[course_routes.get_course_tutor] = lambda: SimpleNamespace(
            evaluate_turn=formative,
        )
        formative_response = self.client.post(path, json=body)
        self.assertEqual(formative_response.status_code, 200, formative_response.text)
        self.assertEqual(formative_response.json()["state"], "practicing")
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(CourseOralTurn)).all()), 1)
            self.assertEqual(session.exec(select(CourseOralReview)).one().revision, 1)

        async def malformed(**_kwargs):
            raise course_routes.CourseTutorError(
                502, "malformed_evaluator_response",
                "Qualitative practice returned an invalid response; try again.", retryable=True,
            )

        self.app.dependency_overrides[course_routes.get_course_tutor] = lambda: SimpleNamespace(
            evaluate_turn=malformed,
        )
        malformed_response = self.client.post(path, json=body | {"request_id": "malformed-turn"})
        self.assertEqual(malformed_response.status_code, 502)

        async def timeout(**_kwargs):
            raise TimeoutError("private tutor transport")

        self.app.dependency_overrides[course_routes.get_course_tutor] = lambda: SimpleNamespace(
            evaluate_turn=timeout,
        )
        timeout_response = self.client.post(path, json=body | {"request_id": "timeout-turn"})
        self.assertEqual(timeout_response.status_code, 503)
        self.assertNotIn("private tutor transport", timeout_response.text)
        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(CourseOralTurn)).all()), 1)
            self.assertEqual(session.exec(select(CourseOralReview)).one().revision, 1)

        responses = iter((
            SimpleNamespace(feedback="First qualitative feedback.",
                            next_question="What concrete failure follows?"),
            SimpleNamespace(feedback="Second qualitative feedback.",
                            next_question="How would you verify the mitigation?"),
        ))

        async def accepted(**_kwargs):
            return next(responses)

        async def accepted_oral(**_kwargs):
            return SimpleNamespace(passed=True, feedback="Catalog oral rubric was satisfied.")

        self.app.dependency_overrides[course_routes.get_course_tutor] = lambda: SimpleNamespace(
            evaluate_turn=accepted, evaluate_oral=accepted_oral,
        )
        first = self.client.post(path, json=body | {"request_id": "revision-one"})
        second = self.client.post(path, json=body | {
            "request_id": "revision-two", "response": "A deeper bounded explanation.",
        })
        self.assertEqual((first.json()["revision"], second.json()["revision"]), (2, 3))
        self.assertEqual(second.json()["prompt"], first.json()["next_question"])
        replayed_formative = self.client.post(path, json=body)
        self.assertEqual(replayed_formative.status_code, 200, replayed_formative.text)
        self.assertTrue(replayed_formative.json()["_meta"]["replayed"])
        self.assertEqual(replayed_formative.json()["revision"], 1)
        self.assertEqual(replayed_formative.json()["next_question"],
                         formative_response.json()["next_question"])

        stale = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/complete",
            json={
                "request_id": "stale-online-debrief", "catalog_version": COURSE_VERSION,
                "expected_revision": 2,
            },
        )
        self.assertEqual(stale.status_code, 409)
        completed = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/complete",
            json={
                "request_id": "online-debrief", "catalog_version": COURSE_VERSION,
                "expected_revision": 3,
            },
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual((completed.json()["review_state"], completed.json()["revision"]),
                         ("reviewed", 4))

    def test_forged_dgx_review_is_rejected_and_timeout_preserves_pending_attempt(self):
        self._enroll()
        self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/self-record",
            json={
                "request_id": "pending-dgx", "catalog_version": COURSE_VERSION,
                "note": "A persisted attempt awaiting trusted review.", "expected_revision": 0,
            },
        )
        forged = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/review",
            json={
                "request_id": "forged-dgx", "catalog_version": COURSE_VERSION,
                "method": "dgx", "acknowledgements": ["x"], "feedback": "pass",
                "expected_revision": 1,
            },
        )
        self.assertEqual(forged.status_code, 422)

        async def timeout(**_kwargs):
            raise TimeoutError("private transport detail")

        self.app.dependency_overrides[course_routes.get_course_tutor] = lambda: SimpleNamespace(
            evaluate_oral=timeout,
        )
        failed = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/complete",
            json={
                "request_id": "dgx-timeout", "catalog_version": COURSE_VERSION,
                "expected_revision": 1,
            },
        )
        self.assertEqual(failed.status_code, 503)
        self.assertNotIn("private transport detail", failed.text)
        self.assertTrue(failed.json()["error"]["retryable"])
        with Session(self.engine) as session:
            review = session.exec(select(CourseOralReview)).one()
            self.assertEqual((review.state, review.revision), ("awaiting_review", 1))

        async def malformed(**_kwargs):
            raise course_routes.CourseTutorError(
                502, "malformed_evaluator_response",
                "Qualitative review returned an invalid response; try again.", retryable=True,
            )

        self.app.dependency_overrides[course_routes.get_course_tutor] = lambda: SimpleNamespace(
            evaluate_oral=malformed,
        )
        rejected = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/complete",
            json={
                "request_id": "dgx-malformed", "catalog_version": COURSE_VERSION,
                "expected_revision": 1,
            },
        )
        self.assertEqual(rejected.status_code, 502)
        with Session(self.engine) as session:
            review = session.exec(select(CourseOralReview)).one()
            self.assertEqual((review.state, review.revision), ("awaiting_review", 1))

    def test_low_evidence_dgx_result_does_not_mark_reviewed(self):
        self._enroll()
        self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/self-record",
            json={
                "request_id": "low-evidence", "catalog_version": COURSE_VERSION,
                "note": "x", "expected_revision": 0,
            },
        )

        async def rejected(**_kwargs):
            return SimpleNamespace(passed=False, feedback="Evidence did not satisfy the catalog rubric.")

        self.app.dependency_overrides[course_routes.get_course_tutor] = lambda: SimpleNamespace(
            evaluate_oral=rejected,
        )
        response = self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/complete",
            json={
                "request_id": "low-complete", "catalog_version": COURSE_VERSION,
                "expected_revision": 1,
            },
        )
        self.assertEqual(response.status_code, 409)
        with Session(self.engine) as session:
            self.assertEqual(session.exec(select(CourseOralReview)).one().state, "awaiting_review")

    def test_unknown_checkpoint_is_bounded(self):
        self._enroll()
        response = self.client.post(
            "/api/courses/inference-engineering/checkpoints/missing/submit",
            json={
                "request_id": "unknown-checkpoint", "catalog_version": COURSE_VERSION,
                "answers": {"response_1": "bounded"},
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("answers", response.text.lower())

    def test_course_rate_limits_are_separate_and_return_retry_after(self):
        old_limit = _course_mutation.limit
        try:
            _course_mutation.limit = 2
            responses = [self._enroll(f"rate-{index}") for index in range(3)]
            self.assertEqual([response.status_code for response in responses], [201, 200, 429])
            self.assertIn("Retry-After", responses[-1].headers)
        finally:
            _course_mutation.limit = old_limit
            _course_mutation.reset()

    def test_checkpoint_evaluator_charges_ai_window_once_and_keeps_windows_isolated(self):
        self._enroll()
        self._artifact()
        old_ai_limit = _course_ai.limit
        try:
            _course_ai.reset(); _course_ai.limit = 0
            blocked = self.client.post(
                f"/api/courses/inference-engineering/checkpoints/{self.module.checkpoint.id}/submit",
                json={
                    "request_id": "ai-window", "catalog_version": COURSE_VERSION,
                    "answers": {"response_1": "bounded", "response_2": "bounded"},
                },
            )
            self.assertEqual(blocked.status_code, 429)
            self.assertIn("Retry-After", blocked.headers)
            self.assertEqual(self._enroll("mutation-window-still-open").status_code, 200)
            _course_ai.reset(); _course_ai.limit = 1
            allowed_body = {
                "request_id": "ai-once", "catalog_version": COURSE_VERSION,
                "answers": {"response_1": "bounded", "response_2": "bounded"},
            }
            path = (
                f"/api/courses/inference-engineering/checkpoints/"
                f"{self.module.checkpoint.id}/submit"
            )
            self.assertEqual(self.client.post(path, json=allowed_body).status_code, 200)
            self.assertEqual(self.client.post(path, json=allowed_body).status_code, 200)
            self.assertEqual(len(_course_ai._hits["testclient"]), 1)
            self.assertEqual(
                self.client.post(path, json=allowed_body | {"request_id": "ai-twice"}).status_code,
                429,
            )
        finally:
            _course_ai.limit = old_ai_limit
            _course_ai.reset()

    def test_failed_oral_completion_replays_before_tutor_after_state_change_and_restart(self):
        self._enroll()
        path = f"/api/courses/inference-engineering/oral/{self.module.id}/complete"
        body = {
            "request_id": "failed-complete-replay", "catalog_version": COURSE_VERSION,
            "expected_revision": 0,
        }
        first = self.client.post(path, json=body)
        self.assertEqual(first.status_code, 409)
        self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/self-record",
            json={
                "request_id": "intervening-attempt", "catalog_version": COURSE_VERSION,
                "note": "Persisted after the failed completion.", "expected_revision": 0,
            },
        )
        calls = []

        async def must_not_run(**_kwargs):
            calls.append("called")
            return SimpleNamespace(passed=True, feedback="must not be consumed")

        restarted = FastAPI()
        restarted.include_router(course_routes.router)
        restarted.dependency_overrides[get_session] = self._sessions
        restarted.dependency_overrides[auth.current_user] = self._alice
        restarted.dependency_overrides[course_routes.get_course_tutor] = lambda: SimpleNamespace(
            evaluate_oral=must_not_run,
        )
        with TestClient(restarted) as client:
            replay = client.post(path, json=body)
            conflict = client.post(path, json=body | {"expected_revision": 1})
        self.assertEqual(replay.status_code, first.status_code)
        self.assertEqual(replay.json()["error"], first.json()["error"])
        self.assertTrue(replay.json()["_meta"]["replayed"])
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"]["code"], "idempotency_conflict")
        self.assertEqual(calls, [])

    def test_oral_completion_replay_precedes_ai_limit_and_new_evaluation_charges_once(self):
        self._enroll()
        path = f"/api/courses/inference-engineering/oral/{self.module.id}/complete"
        failed_body = {
            "request_id": "zero-budget-failure", "catalog_version": COURSE_VERSION,
            "expected_revision": 0,
        }
        stored_failure = self.client.post(path, json=failed_body)
        self.assertEqual(stored_failure.status_code, 409)
        self.client.post(
            f"/api/courses/inference-engineering/oral/{self.module.id}/self-record",
            json={
                "request_id": "zero-budget-attempt", "catalog_version": COURSE_VERSION,
                "note": "Attempt remains available for trusted review.", "expected_revision": 0,
            },
        )
        calls = []

        async def accepted(**_kwargs):
            calls.append("evaluated")
            return SimpleNamespace(passed=True, feedback="Qualitative rubric satisfied.")

        self.app.dependency_overrides[course_routes.get_course_tutor] = lambda: SimpleNamespace(
            evaluate_oral=accepted,
        )
        old_limit = _course_ai.limit
        try:
            _course_ai.reset(); _course_ai.limit = 0
            replayed_failure = self.client.post(path, json=failed_body)
            changed = self.client.post(path, json=failed_body | {"expected_revision": 1})
            blocked_new = self.client.post(path, json={
                "request_id": "zero-budget-new", "catalog_version": COURSE_VERSION,
                "expected_revision": 1,
            })
            self.assertEqual(replayed_failure.status_code, 409)
            self.assertTrue(replayed_failure.json()["_meta"]["replayed"])
            self.assertEqual(changed.json()["error"]["code"], "idempotency_conflict")
            self.assertEqual(blocked_new.status_code, 429)
            self.assertIn("Retry-After", blocked_new.headers)
            self.assertEqual(calls, [])
            self.assertEqual(len(_course_ai._hits.get("testclient", ())), 0)

            _course_ai.limit = 1
            success_body = {
                "request_id": "one-charge-success", "catalog_version": COURSE_VERSION,
                "expected_revision": 1,
            }
            stored_success = self.client.post(path, json=success_body)
            self.assertEqual(stored_success.status_code, 200)
            self.assertEqual(calls, ["evaluated"])
            self.assertEqual(len(_course_ai._hits["testclient"]), 1)

            _course_ai.reset(); _course_ai.limit = 0
            replayed_success = self.client.post(path, json=success_body)
            self.assertEqual(replayed_success.status_code, 200)
            self.assertTrue(replayed_success.json()["_meta"]["replayed"])
            self.assertEqual(calls, ["evaluated"])
            self.assertEqual(len(_course_ai._hits.get("testclient", ())), 0)
        finally:
            _course_ai.limit = old_limit
            _course_ai.reset()
        with Session(self.engine) as session:
            review = session.exec(select(CourseOralReview)).one()
            self.assertEqual((review.state, review.revision), ("reviewed", 2))

    def test_main_registration_and_standard_topic_route_are_preserved(self):
        from app.main import app as full_app
        client = TestClient(full_app)
        try:
            self.assertEqual(client.get("/api/courses/inference-engineering").status_code, 401)
            self.assertEqual(client.get("/api/topic/999999").status_code, 401)
        finally:
            client.close()

    def test_openapi_has_strict_course_bodies_and_all_approved_paths(self):
        schema = self.app.openapi()
        expected = {
            "/api/courses/inference-engineering",
            "/api/courses/inference-engineering/modules/{module_id}",
            "/api/courses/inference-engineering/modules/{module_id}/linked-topics/{concept_id}",
            "/api/courses/inference-engineering/enroll",
            "/api/courses/inference-engineering/missions/{mission_id}/artifacts/{artifact_id}",
            "/api/courses/inference-engineering/checkpoints/{checkpoint_id}/submit",
            "/api/courses/inference-engineering/oral/{mission_id}/turn",
            "/api/courses/inference-engineering/oral/{mission_id}/self-record",
            "/api/courses/inference-engineering/oral/{mission_id}/complete",
            "/api/courses/inference-engineering/oral/{mission_id}/review",
            "/api/courses/inference-engineering/reconcile",
            "/api/courses/inference-engineering/links/{link_id}",
        }
        self.assertTrue(expected.issubset(schema["paths"]))
        checkpoint = schema["components"]["schemas"]["CheckpointIn"]
        self.assertFalse(checkpoint["additionalProperties"])
        self.assertTrue({"passed", "grade", "trusted_evaluator"}.isdisjoint(checkpoint["properties"]))

    def test_rate_window_prunes_expired_hits_and_no_client_uses_unknown_key(self):
        from starlette.requests import Request
        from app.ratelimit import require_setup_rate, _setup

        _course_ai._hits["expired"] = __import__("collections").deque([time.monotonic() - 1000])
        _course_ai.check("expired")
        self.assertEqual(len(_course_ai._hits["expired"]), 1)
        request = Request({
            "type": "http", "method": "POST", "path": "/api/setup",
            "headers": [], "client": None, "server": ("test", 80),
        })
        _setup.reset()
        require_setup_rate(request)
        self.assertIn("unknown", _setup._hits)

    def test_general_ask_route_has_bounded_ai_window(self):
        from app.ratelimit import _shared_ai
        from app.routers import ask_routes

        app = FastAPI()
        app.include_router(ask_routes.router)
        app.dependency_overrides[auth.current_user] = self._alice
        old_limit = _shared_ai.limit
        _shared_ai.reset(); _shared_ai.limit = 2
        try:
            with patch("app.tutor.answer_question", new=AsyncMock(return_value="answer")):
                with TestClient(app) as client:
                    responses = [client.post("/api/ask", json={"question": "bounded"}) for _ in range(3)]
            self.assertEqual([item.status_code for item in responses], [200, 200, 429])
            self.assertIn("Retry-After", responses[-1].headers)
        finally:
            _shared_ai.limit = old_limit
            _shared_ai.reset()

    def test_existing_ask_generation_and_health_contracts_remain_available(self):
        from app.routers import ask_routes

        app = FastAPI()
        app.include_router(ask_routes.router)
        app.dependency_overrides[auth.current_user] = self._alice
        with patch("app.scheduler.generate_new_concepts", new=AsyncMock(return_value=3)), \
             patch("app.llm.model_status", new=AsyncMock(return_value=(True, "served-model"))):
            with TestClient(app) as client:
                generated = client.post("/api/generate-now?per_track=1")
                health = client.get("/api/brain-health")
        self.assertEqual(generated.json(), {"added": 3})
        self.assertTrue(health.json()["online"])
        self.assertEqual(health.json()["model"], "served-model")

    def test_main_setup_health_and_lifespan_orchestration_use_injected_database(self):
        from app import main as main_module

        setup_engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(setup_engine)
        with patch("app.main.engine", setup_engine):
            self.assertTrue(main_module.needs_setup()["needs_setup"])
            self.assertEqual(
                main_module.setup(main_module.SetupIn(password="short"), Response()).status_code,
                400,
            )
            with patch("app.auth.hash_password", return_value="synthetic"), \
                 patch("app.auth.issue_session") as issue_session, \
                 patch("app.service.sync_user_cards") as sync_cards:
                created = main_module.setup(
                    main_module.SetupIn(password="bounded", username=" NewAdmin "), Response(),
                )
            self.assertEqual(created, {"ok": True, "username": "newadmin"})
            issue_session.assert_called_once()
            sync_cards.assert_called_once()
            self.assertFalse(main_module.needs_setup()["needs_setup"])
            self.assertEqual(
                main_module.setup(main_module.SetupIn(password="bounded"), Response()).status_code,
                409,
            )
            self.assertTrue(main_module.health()["ok"])

            scheduler = Mock()
            with patch("app.main.init_db"), patch("app.main.seed_database", return_value=1), \
                 patch("app.main.seed_problems", return_value=(2, 3)), \
                 patch("app.main.start_scheduler", return_value=scheduler):
                asyncio.run(self._exercise_lifespan(main_module))
            scheduler.shutdown.assert_called_once_with(wait=False)
            with patch("app.main.init_db"), patch("app.main.seed_database", return_value=0), \
                 patch("app.main.seed_problems", return_value=(0, 0)), \
                 patch("app.main.start_scheduler", return_value=None):
                asyncio.run(self._exercise_lifespan(main_module))
        setup_engine.dispose()

    @staticmethod
    async def _exercise_lifespan(main_module):
        async with main_module.lifespan(FastAPI()):
            pass


if __name__ == "__main__":
    unittest.main()
