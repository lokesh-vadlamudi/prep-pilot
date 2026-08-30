"""Transactional persistence for the inference course; no routing or model calls."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Callable, TypeVar
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .content.inference_course import (
    COURSE, COURSE_KEY, COURSE_VERSION, CatalogValidationError, CourseModule,
    canonical_completion_payload, explicit_supplement_aliases, legacy_identity_match,
)
from .models import (
    Book,
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
    utcnow,
)


MAX_REQUEST_ID = 100
MAX_NOTE = 5000
MAX_TURN = 4000
MAX_JSON = 20000
ORAL_STATES = frozenset({"not_started", "practicing", "awaiting_review", "reviewed"})
VALID_MATCH_KINDS = frozenset({"owned_exact", "legacy_exact", "explicit_supplement_alias"})
T = TypeVar("T")
_CHECKPOINT_AUTHORITY = object()
_ORAL_TURN_AUTHORITY = object()


@dataclass(frozen=True, slots=True)
class MutationResult:
    status_code: int
    body: dict
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class TrustedCheckpointEvaluation:
    """Internal evaluator output; request models cannot mint its capability."""

    passed: bool
    feedback: str
    _authority: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class TrustedOralTurnEvaluation:
    feedback: str
    next_question: str
    _authority: object = field(repr=False, compare=False)


class CourseServiceError(Exception):
    """Bounded error suitable for a later HTTP adapter."""

    def __init__(self, status_code: int, code: str, detail: str, *, replayed: bool = False):
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.replayed = replayed

    @property
    def body(self) -> dict:
        return {"error": {"code": self.code, "detail": self.detail}}


def receipt_retention_policy() -> dict:
    """MVP receipts never expire; future enrollment deletion may remove them atomically."""
    return {"automatic_pruning": False, "retention": "enrollment_lifetime"}


def _trusted_checkpoint_evaluation(*, passed: bool, feedback: str) -> TrustedCheckpointEvaluation:
    """Construct a result inside a server-owned deterministic/DGX evaluator."""
    return TrustedCheckpointEvaluation(bool(passed), feedback, _CHECKPOINT_AUTHORITY)


def _require_trusted_evaluation(value: object) -> TrustedCheckpointEvaluation:
    if not isinstance(value, TrustedCheckpointEvaluation) or value._authority is not _CHECKPOINT_AUTHORITY:
        raise CourseServiceError(
            422, "untrusted_checkpoint_evaluation",
            "Checkpoint completion requires a server-owned evaluator result.",
        )
    return value


def _trusted_oral_turn_evaluation(*, feedback: str, next_question: str) -> TrustedOralTurnEvaluation:
    return TrustedOralTurnEvaluation(feedback, next_question, _ORAL_TURN_AUTHORITY)


def _require_trusted_oral_turn(value: object) -> TrustedOralTurnEvaluation:
    if not isinstance(value, TrustedOralTurnEvaluation) or value._authority is not _ORAL_TURN_AUTHORITY:
        raise CourseServiceError(
            422, "untrusted_oral_turn_evaluation",
            "Oral practice feedback requires a server-owned tutor result.",
        )
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload_hash(payload: dict) -> str:
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _validate_request_id(request_id: str) -> str:
    value = request_id.strip()
    if not value or len(value) > MAX_REQUEST_ID:
        raise CourseServiceError(422, "invalid_request_id", "Request ID is missing or too long.")
    return value


def _require_user(session: Session, user_id: int) -> None:
    if session.get(User, user_id) is None:
        raise CourseServiceError(404, "user_not_found", "User not found.")


def _module(mission_id: str) -> CourseModule:
    module = next((item for item in COURSE.modules if item.id == mission_id), None)
    if module is None:
        raise CourseServiceError(404, "unknown_mission", "Course mission not found.")
    return module


def _checkpoint_module(checkpoint_id: str) -> CourseModule:
    module = next((item for item in COURSE.modules if item.checkpoint.id == checkpoint_id), None)
    if module is None:
        raise CourseServiceError(404, "unknown_checkpoint", "Course checkpoint not found.")
    return module


def _require_enrollment(session: Session, user_id: int, catalog_version: str) -> CourseEnrollment:
    row = session.exec(select(CourseEnrollment).where(
        CourseEnrollment.user_id == user_id,
        CourseEnrollment.course_key == COURSE_KEY,
    )).first()
    if row is None:
        raise CourseServiceError(409, "not_enrolled", "Enroll in the course before saving progress.")
    if catalog_version != row.catalog_version or catalog_version != COURSE_VERSION:
        raise CourseServiceError(409, "catalog_version_conflict", "Refresh the course catalog and retry.")
    return row


def _require_prerequisites(session: Session, user_id: int, module: CourseModule) -> None:
    blocked = [item for item in module.prerequisites if _compute_state(session, user_id, _module(item)) != "complete"]
    if blocked:
        raise CourseServiceError(409, "prerequisite_incomplete", "Complete prerequisite missions first.")


def _receipt(session: Session, user_id: int, operation: str, request_id: str) -> CourseMutationReceipt | None:
    return session.exec(select(CourseMutationReceipt).where(
        CourseMutationReceipt.user_id == user_id,
        CourseMutationReceipt.course_key == COURSE_KEY,
        CourseMutationReceipt.operation == operation,
        CourseMutationReceipt.request_id == request_id,
    )).first()


def _from_receipt(row: CourseMutationReceipt, payload_sha256: str) -> MutationResult:
    if row.payload_sha256 != payload_sha256:
        raise CourseServiceError(409, "idempotency_conflict", "Request ID was already used for different input.")
    body = json.loads(row.response_json)
    if row.status_code >= 400:
        error = body["error"]
        raise CourseServiceError(row.status_code, error["code"], error["detail"], replayed=True)
    return MutationResult(row.status_code, body, replayed=True)


def _add_receipt(
    session: Session, user_id: int, operation: str, request_id: str,
    resource_key: str, payload_sha256: str, status_code: int, body: dict,
) -> None:
    session.add(CourseMutationReceipt(
        user_id=user_id, course_key=COURSE_KEY, operation=operation,
        request_id=request_id, resource_key=resource_key,
        payload_sha256=payload_sha256, status_code=status_code,
        response_json=_canonical_json(body),
    ))


def execute_receipted_mutation(
    session: Session, user_id: int, operation: str, request_id: str,
    resource_key: str, payload: dict, mutate: Callable[[], tuple[int, dict]],
) -> MutationResult:
    """Atomically commit one mutation and immutable replay response."""
    request_id = _validate_request_id(request_id)
    _require_user(session, user_id)
    digest = _payload_hash(payload)
    existing = _receipt(session, user_id, operation, request_id)
    if existing is not None:
        return _from_receipt(existing, digest)
    try:
        return _run_new_mutation(
            session, user_id, operation, request_id, resource_key, digest, mutate,
        )
    except IntegrityError:
        session.rollback()
        raced = _receipt(session, user_id, operation, request_id)
        if raced is None:
            raise
        return _from_receipt(raced, digest)


def _run_new_mutation(
    session: Session, user_id: int, operation: str, request_id: str,
    resource_key: str, digest: str, mutate: Callable[[], tuple[int, dict]],
) -> MutationResult:
    try:
        status_code, body = mutate()
        _add_receipt(session, user_id, operation, request_id, resource_key, digest, status_code, body)
        session.commit()
        return MutationResult(status_code, body)
    except CourseServiceError as error:
        session.rollback()
        _add_receipt(session, user_id, operation, request_id, resource_key, digest, error.status_code, error.body)
        session.commit()
        raise error
    except Exception:
        session.rollback()
        raise


def enroll(
    session: Session, user_id: int, *, request_id: str,
    catalog_version: str = COURSE_VERSION,
) -> MutationResult:
    payload = {"course_key": COURSE_KEY, "catalog_version": catalog_version}

    def mutate() -> tuple[int, dict]:
        if catalog_version != COURSE_VERSION:
            raise CourseServiceError(409, "catalog_version_conflict", "Refresh the course catalog and retry.")
        row = session.exec(select(CourseEnrollment).where(
            CourseEnrollment.user_id == user_id,
            CourseEnrollment.course_key == COURSE_KEY,
        )).first()
        created = row is None
        if row is None:
            row = CourseEnrollment(user_id=user_id, course_key=COURSE_KEY, catalog_version=COURSE_VERSION)
            session.add(row)
            session.flush()
        return (201 if created else 200), {
            "enrollment_id": row.id, "course_key": COURSE_KEY,
            "catalog_version": row.catalog_version, "created": created,
        }

    return execute_receipted_mutation(
        session, user_id, "enroll", request_id, COURSE_KEY, payload, mutate,
    )


def _artifact(module: CourseModule, artifact_id: str):
    artifact = next((item for item in module.artifacts if item.id == artifact_id), None)
    if artifact is None:
        raise CourseServiceError(404, "unknown_artifact", "Course artifact not found.")
    return artifact


def _validate_artifact_uri(uri: str) -> str:
    value = uri.strip()
    parsed = urlsplit(value)
    if parsed.scheme:
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise CourseServiceError(422, "unsafe_artifact_uri", "Use HTTPS or a repository-relative reference.")
    elif value.startswith("/") or ".." in PurePosixPath(value).parts or not value:
        raise CourseServiceError(422, "unsafe_artifact_uri", "Use HTTPS or a repository-relative reference.")
    return value


def _validated_note(note: str, *, code: str = "invalid_note") -> str:
    value = note.strip()
    if not value or len(value) > MAX_NOTE:
        raise CourseServiceError(422, code, "A bounded evidence note is required.")
    return value


def save_artifact(
    session: Session, user_id: int, *, mission_id: str, artifact_id: str,
    note: str, artifact_uri: str, draft_fields: dict | None = None,
    expected_revision: int, request_id: str,
    catalog_version: str = COURSE_VERSION,
) -> MutationResult:
    payload_draft = _canonical_draft_for_identity(mission_id, artifact_id, draft_fields)
    payload = {
        "mission_id": mission_id, "artifact_id": artifact_id,
        "note": note.strip(), "artifact_uri": artifact_uri.strip(),
        "draft_fields": payload_draft,
        "expected_revision": expected_revision, "catalog_version": catalog_version,
    }

    def mutate() -> tuple[int, dict]:
        _require_enrollment(session, user_id, catalog_version)
        module = _module(mission_id)
        _require_prerequisites(session, user_id, module)
        descriptor = _artifact(module, artifact_id)
        clean_note = _validated_note(note)
        clean_uri = _validate_artifact_uri(artifact_uri)
        draft = _validated_artifact_draft(module, descriptor, draft_fields)
        row, created = _upsert_artifact(
            session, user_id, mission_id, artifact_id, clean_note, clean_uri,
            expected_revision, descriptor, draft, catalog_version,
        )
        progress = _refresh_progress(session, user_id, module)
        return (201 if created else 200), _artifact_body(row, descriptor) | {
            "artifact_id": artifact_id, "mission_id": mission_id,
            "mission_state": progress.state,
        }

    return execute_receipted_mutation(
        session, user_id, "artifact_upsert", request_id,
        f"{mission_id}:{artifact_id}", payload, mutate,
    )


def _upsert_artifact(
    session: Session, user_id: int, mission_id: str, artifact_id: str,
    note: str, artifact_uri: str, expected_revision: int, descriptor,
    draft: dict, catalog_version: str,
) -> tuple[CourseArtifactEvidence, bool]:
    row = session.exec(select(CourseArtifactEvidence).where(
        CourseArtifactEvidence.user_id == user_id,
        CourseArtifactEvidence.artifact_id == artifact_id,
    )).first()
    current = row.revision if row else 0
    if current != expected_revision:
        raise CourseServiceError(409, "stale_revision", "Artifact changed; refresh before saving.")
    created = row is None
    row = row or CourseArtifactEvidence(user_id=user_id, mission_id=mission_id, artifact_id=artifact_id)
    row.note, row.artifact_uri = note, artifact_uri
    row.template_key, row.output_format = descriptor.template_key, descriptor.output_format
    row.draft_json = _canonical_json(draft)
    row.rubric_json = _canonical_json(list(descriptor.verification_rubric))
    row.source_ids_json = _canonical_json(list(descriptor.source_ids))
    row.catalog_version = catalog_version
    row.revision, row.updated_at = current + 1, utcnow()
    session.add(row)
    session.flush()
    return row, created


def _canonical_draft_for_identity(mission_id: str, artifact_id: str, draft_fields):
    """Canonicalize valid catalog structures before computing request identity."""
    module = next((item for item in COURSE.modules if item.id == mission_id), None)
    if module is None or not isinstance(draft_fields, dict):
        return draft_fields
    descriptor = next((item for item in module.artifacts if item.id == artifact_id), None)
    canonical = dict(draft_fields)
    if module.selection_rule is not None:
        selected = draft_fields.get("selected_experiments")
        if not isinstance(selected, list) or any(not isinstance(item, str) for item in selected):
            raise CourseServiceError(
                422, "invalid_experiment_selection",
                "Choose the required number of unique catalog experiment IDs.",
            )
        allowed = module.selection_rule.options
        if (
            len(selected) == len(set(selected))
            and all(item in allowed for item in selected)
        ):
            canonical["selected_experiments"] = [item for item in allowed if item in selected]
    if descriptor is not None and descriptor.completion_rule is not None:
        fields = _completion_fields(descriptor.completion_rule)
        completion = {key: draft_fields[key] for key in fields if key in draft_fields}
        try:
            canonical.update(canonical_completion_payload(descriptor, completion))
        except CatalogValidationError:
            pass
    return canonical


def _completion_fields(rule) -> set[str]:
    fields = {rule.collection_field}
    if rule.chosen_id_field:
        fields.update((rule.chosen_id_field, rule.evidence_field))
    return fields


def _validated_artifact_draft(module: CourseModule, descriptor, draft_fields) -> dict:
    if not isinstance(draft_fields, dict):
        raise CourseServiceError(422, "missing_template_fields", "Complete every required template field.")
    completion_fields: set[str] = set()
    canonical_completion: dict = {}
    if descriptor.completion_rule is not None:
        completion_fields = _completion_fields(descriptor.completion_rule)
        completion = {key: draft_fields[key] for key in completion_fields if key in draft_fields}
        try:
            canonical_completion = canonical_completion_payload(descriptor, completion)
        except CatalogValidationError as error:
            raise CourseServiceError(
                422, "invalid_completion_payload",
                "Complete the exact catalog-owned artifact evidence contract.",
            ) from error
    required = set(descriptor.template_fields) | completion_fields
    actual = set(draft_fields)
    if required - actual:
        raise CourseServiceError(422, "missing_template_fields", "Complete every required template field.")
    if actual - required:
        raise CourseServiceError(422, "unknown_template_fields", "Remove unknown template fields.")
    clean = dict(draft_fields) | canonical_completion
    if module.selection_rule is not None:
        clean["selected_experiments"] = _validated_experiment_selection(
            module, draft_fields.get("selected_experiments"),
        )
    invalid = any(
        key not in completion_fields
        and not (module.selection_rule is not None and key == "selected_experiments") and (
            not isinstance(value, str) or not value.strip() or len(value) > MAX_TURN
            or any(ord(char) < 32 and char not in "\n\t" for char in value)
        )
        for key, value in clean.items()
    )
    if invalid:
        raise CourseServiceError(422, "invalid_template_fields", "Template fields require bounded text.")
    clean = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in clean.items()
    }
    if len(_canonical_json(clean)) > MAX_JSON:
        raise CourseServiceError(422, "artifact_draft_too_large", "Artifact draft is too large.")
    return clean


def _validated_experiment_selection(module: CourseModule, value) -> list[str]:
    rule = module.selection_rule
    allowed = rule.options
    if (
        not isinstance(value, list)
        or not rule.minimum <= len(value) <= rule.maximum
        or any(not isinstance(item, str) for item in value)
        or len(value) != len(set(value))
        or any(item not in allowed for item in value)
    ):
        raise CourseServiceError(
            422, "invalid_experiment_selection",
            "Choose the required number of unique catalog experiment IDs.",
        )
    return [item for item in allowed if item in value]


def _artifact_body(row: CourseArtifactEvidence, descriptor) -> dict:
    return {
        "revision": row.revision, "note": row.note, "artifact_uri": row.artifact_uri,
        "template_key": row.template_key or descriptor.template_key,
        "output_format": row.output_format or descriptor.output_format,
        "template_fields": list(descriptor.template_fields),
        "draft_fields": json.loads(row.draft_json or "{}"),
        "verification_rubric": json.loads(row.rubric_json or "[]") or list(descriptor.verification_rubric),
        "source_ids": json.loads(row.source_ids_json or "[]") or list(descriptor.source_ids),
        "catalog_version": row.catalog_version or COURSE_VERSION,
    }


def artifact_export(session: Session, user_id: int, artifact_id: str) -> dict:
    _require_user(session, user_id)
    row = session.exec(select(CourseArtifactEvidence).where(
        CourseArtifactEvidence.user_id == user_id,
        CourseArtifactEvidence.artifact_id == artifact_id,
    )).first()
    if row is None:
        raise CourseServiceError(404, "artifact_not_found", "Artifact not found.")
    descriptor = _artifact(_module(row.mission_id), artifact_id)
    return {"artifact_id": artifact_id, "mission_id": row.mission_id} | _artifact_body(row, descriptor)


def self_record_oral(
    session: Session, user_id: int, *, mission_id: str, note: str,
    expected_revision: int, request_id: str, catalog_version: str = COURSE_VERSION,
) -> MutationResult:
    payload = {
        "mission_id": mission_id, "note": note.strip(),
        "expected_revision": expected_revision, "catalog_version": catalog_version,
    }

    def mutate() -> tuple[int, dict]:
        _require_enrollment(session, user_id, catalog_version)
        module = _module(mission_id)
        _require_prerequisites(session, user_id, module)
        clean_note = _validated_note(note, code="invalid_oral_record")
        review = _oral_review(session, user_id, mission_id)
        current = review.revision if review else 0
        state = review.state if review else "not_started"
        if current != expected_revision:
            raise CourseServiceError(409, "stale_revision", "Oral practice changed; refresh before saving.")
        if state not in {"not_started", "practicing"}:
            raise CourseServiceError(409, "invalid_oral_transition", "This oral attempt is already awaiting review.")
        review = review or CourseOralReview(user_id=user_id, mission_id=mission_id)
        review.state, review.mode = "awaiting_review", "self_recorded"
        review.self_record_note, review.attempt_recorded_at = clean_note, utcnow()
        review.revision, review.updated_at = current + 1, utcnow()
        session.add(review)
        session.flush()
        _refresh_progress(session, user_id, module)
        return 200, _oral_body(review)

    return execute_receipted_mutation(
        session, user_id, "oral_self_record", request_id, mission_id, payload, mutate,
    )


def review_oral(
    session: Session, user_id: int, *, mission_id: str, method: str,
    acknowledgements: list[str], feedback: str, expected_revision: int,
    request_id: str, catalog_version: str = COURSE_VERSION,
) -> MutationResult:
    payload = {
        "mission_id": mission_id, "method": method,
        "acknowledgements": sorted(item.strip() for item in acknowledgements),
        "feedback": feedback.strip(), "expected_revision": expected_revision,
        "catalog_version": catalog_version,
    }

    def mutate() -> tuple[int, dict]:
        _require_enrollment(session, user_id, catalog_version)
        module = _module(mission_id)
        review = _oral_review(session, user_id, mission_id)
        if review is None or review.state != "awaiting_review":
            raise CourseServiceError(409, "invalid_oral_transition", "No self-recorded attempt is awaiting review.")
        if review.revision != expected_revision:
            raise CourseServiceError(409, "stale_revision", "Oral practice changed; refresh before reviewing.")
        clean_feedback = _validate_oral_review(module, method, acknowledgements, feedback)
        review.state, review.review_method = "reviewed", method
        review.rubric_acknowledgements_json = _canonical_json(sorted(set(acknowledgements)))
        review.review_feedback, review.reviewed_at = clean_feedback, utcnow()
        review.revision, review.updated_at = review.revision + 1, utcnow()
        session.add(review)
        session.flush()
        _refresh_progress(session, user_id, module)
        return 200, _oral_body(review)

    return execute_receipted_mutation(
        session, user_id, "oral_review", request_id, mission_id, payload, mutate,
    )


def _validate_oral_review(
    module: CourseModule, method: str, acknowledgements: list[str], feedback: str,
) -> str:
    if method not in {"dgx", "self_rubric"}:
        raise CourseServiceError(422, "invalid_review_method", "Choose DGX or self-rubric review.")
    expected = {item.strip() for item in module.oral.rubric}
    actual = {item.strip() for item in acknowledgements if item.strip()}
    if method == "self_rubric" and actual != expected:
        raise CourseServiceError(422, "incomplete_oral_review", "Acknowledge every qualitative rubric item.")
    return _validated_note(feedback, code="invalid_review_feedback")


def _oral_review(session: Session, user_id: int, mission_id: str) -> CourseOralReview | None:
    return session.exec(select(CourseOralReview).where(
        CourseOralReview.user_id == user_id,
        CourseOralReview.mission_id == mission_id,
    )).first()


def _oral_body(review: CourseOralReview) -> dict:
    return {
        "mission_id": review.mission_id,
        "review_state": review.state,
        "review_method": review.review_method,
        "revision": review.revision,
    }


def record_oral_turn(
    session: Session, user_id: int, *, mission_id: str, turn_id: str,
    response: str, evaluation: TrustedOralTurnEvaluation | None,
    expected_revision: int | None = None, catalog_version: str = COURSE_VERSION,
) -> dict:
    _require_user(session, user_id)
    _validate_request_id(turn_id)
    module = _module(mission_id)
    clean_response = _bounded_turn(response)
    payload = {"response": clean_response, "catalog_version": catalog_version}
    digest = _payload_hash(payload)
    existing = _oral_turn(session, user_id, mission_id, turn_id)
    if existing:
        return _existing_turn(existing, digest)
    _require_enrollment(session, user_id, catalog_version)
    _require_prerequisites(session, user_id, module)
    trusted = _require_trusted_oral_turn(evaluation)
    clean_feedback = _bounded_turn(trusted.feedback)
    next_question = _bounded_turn(trusted.next_question)
    return _create_oral_turn(
        session, user_id, module, turn_id, clean_response, clean_feedback,
        next_question, digest, expected_revision,
    )


def oral_turn_replay(
    session: Session, user_id: int, *, mission_id: str, turn_id: str,
    response: str, catalog_version: str = COURSE_VERSION,
) -> dict | None:
    _require_user(session, user_id)
    _validate_request_id(turn_id)
    _module(mission_id)
    clean_response = _bounded_turn(response)
    digest = _payload_hash({"response": clean_response, "catalog_version": catalog_version})
    existing = _oral_turn(session, user_id, mission_id, turn_id)
    return _existing_turn(existing, digest) if existing else None


def prepare_oral_turn(
    session: Session, user_id: int, *, mission_id: str, catalog_version: str,
) -> dict:
    _require_user(session, user_id)
    _require_enrollment(session, user_id, catalog_version)
    module = _module(mission_id)
    _require_prerequisites(session, user_id, module)
    review = _oral_review(session, user_id, mission_id)
    if review and review.state not in {"not_started", "practicing"}:
        raise CourseServiceError(409, "invalid_oral_transition", "This oral practice is already pending or reviewed.")
    turns = session.exec(select(CourseOralTurn).where(
        CourseOralTurn.user_id == user_id,
        CourseOralTurn.mission_id == mission_id,
    ).order_by(CourseOralTurn.created_at, CourseOralTurn.id)).all()
    return {
        "module": module,
        "prompt": turns[-1].next_question if turns else module.oral.opening_prompt,
        "prior_turns": [
            {"prompt": row.prompt, "response": row.response, "feedback": row.feedback}
            for row in turns
        ],
        "expected_revision": review.revision if review else 0,
    }


def _create_oral_turn(
    session: Session, user_id: int, module: CourseModule, turn_id: str,
    response: str, feedback: str, next_question: str, digest: str,
    expected_revision: int | None,
) -> dict:
    review = _oral_review(session, user_id, module.id)
    if review and review.state not in {"not_started", "practicing"}:
        raise CourseServiceError(409, "invalid_oral_transition", "This oral practice is already pending or reviewed.")
    review = review or CourseOralReview(user_id=user_id, mission_id=module.id)
    if expected_revision is not None and review.revision != expected_revision:
        raced = _oral_turn(session, user_id, module.id, turn_id)
        if raced is not None:
            return _existing_turn(raced, digest)
        raise CourseServiceError(409, "stale_revision", "Oral practice changed; refresh before continuing.")
    if review.state == "not_started":
        review.state, review.mode = "practicing", "dgx"
    review.revision, review.updated_at = review.revision + 1, utcnow()
    session.add(review)
    previous = session.exec(select(CourseOralTurn).where(
        CourseOralTurn.user_id == user_id,
        CourseOralTurn.mission_id == module.id,
    ).order_by(CourseOralTurn.created_at.desc(), CourseOralTurn.id.desc())).first()
    row = CourseOralTurn(
        user_id=user_id, mission_id=module.id, turn_id=turn_id,
        payload_sha256=digest,
        prompt=previous.next_question if previous else module.oral.opening_prompt,
        response=response, feedback=feedback, next_question=next_question,
    )
    session.add(row)
    try:
        session.flush()
        body = _turn_body(row, review)
        row.response_json = _canonical_json(body)
        session.add(row)
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = _oral_turn(session, user_id, module.id, turn_id)
        if existing:
            return _existing_turn(existing, digest)
        raise
    return body


def _oral_turn(session: Session, user_id: int, mission_id: str, turn_id: str) -> CourseOralTurn | None:
    return session.exec(select(CourseOralTurn).where(
        CourseOralTurn.user_id == user_id,
        CourseOralTurn.mission_id == mission_id,
        CourseOralTurn.turn_id == turn_id,
    )).first()


def _existing_turn(row: CourseOralTurn, digest: str) -> dict:
    if row.payload_sha256 != digest:
        raise CourseServiceError(409, "idempotency_conflict", "Turn ID was already used for different input.")
    if row.response_json and row.response_json != "{}":
        return json.loads(row.response_json)
    return _turn_body(row, None)


def _turn_body(row: CourseOralTurn, review: CourseOralReview | None) -> dict:
    return {
        "mission_id": row.mission_id, "turn_id": row.turn_id, "recorded": True,
        "prompt": row.prompt, "user_response": row.response,
        "feedback": row.feedback, "next_question": row.next_question,
        "state": review.state if review else "practicing",
        "revision": review.revision if review else 1,
    }


def module_user_state(session: Session, user_id: int, mission_id: str) -> dict:
    """Return owner-scoped persisted state needed to resume one module."""
    _require_user(session, user_id)
    module = _module(mission_id)
    evidence = {
        row.artifact_id: row for row in session.exec(select(CourseArtifactEvidence).where(
            CourseArtifactEvidence.user_id == user_id,
            CourseArtifactEvidence.mission_id == mission_id,
        )).all()
    }
    review = _oral_review(session, user_id, mission_id)
    turns = session.exec(select(CourseOralTurn).where(
        CourseOralTurn.user_id == user_id,
        CourseOralTurn.mission_id == mission_id,
    ).order_by(CourseOralTurn.created_at, CourseOralTurn.id)).all()
    return {
        "oral_state": {
            "state": review.state if review else "not_started",
            "mode": review.mode if review else "",
            "revision": review.revision if review else 0,
            "self_record_note": review.self_record_note if review else "",
            "review_method": review.review_method if review else "",
            "review_feedback": review.review_feedback if review else "",
            "turns": [
                {
                    "turn_id": row.turn_id, "prompt": row.prompt,
                    "response": row.response, "feedback": row.feedback,
                    "next_question": row.next_question,
                    "created_at": row.created_at,
                }
                for row in turns
            ],
        },
        "artifact_state": [
            _artifact_reload_state(descriptor, evidence.get(descriptor.id))
            for descriptor in module.artifacts
        ],
    }


def _artifact_reload_state(descriptor, row: CourseArtifactEvidence | None) -> dict:
    return {
        "artifact_id": descriptor.id,
        "title": descriptor.title,
        "completed": row is not None,
        "revision": row.revision if row else 0,
        "note": row.note if row else "",
        "artifact_uri": row.artifact_uri if row else "",
        "draft_fields": json.loads(row.draft_json) if row else {},
        "catalog_version": row.catalog_version if row else COURSE_VERSION,
    }


def _bounded_turn(value: str) -> str:
    clean = value.strip()
    if not clean or len(clean) > MAX_TURN:
        raise CourseServiceError(422, "invalid_oral_turn", "A bounded oral response is required.")
    return clean


def complete_oral(
    session: Session, user_id: int, *, mission_id: str, feedback: str,
    expected_revision: int, request_id: str, catalog_version: str = COURSE_VERSION,
) -> MutationResult:
    payload = {
        "mission_id": mission_id, "feedback": feedback.strip(),
        "expected_revision": expected_revision, "catalog_version": catalog_version,
    }

    def mutate() -> tuple[int, dict]:
        _require_enrollment(session, user_id, catalog_version)
        module = _module(mission_id)
        review = _oral_review(session, user_id, mission_id)
        if review is None or review.state != "practicing":
            raise CourseServiceError(409, "invalid_oral_transition", "No online oral practice is ready to complete.")
        if review.revision != expected_revision:
            raise CourseServiceError(409, "stale_revision", "Oral practice changed; refresh before completing.")
        review.state, review.review_method = "reviewed", "dgx"
        review.review_feedback = _validated_note(feedback, code="invalid_review_feedback")
        review.reviewed_at, review.updated_at = utcnow(), utcnow()
        review.revision += 1
        session.add(review)
        session.flush()
        _refresh_progress(session, user_id, module)
        return 200, _oral_body(review)

    return execute_receipted_mutation(
        session, user_id, "oral_complete", request_id, mission_id, payload, mutate,
    )


def record_checkpoint_attempt(
    session: Session, user_id: int, *, checkpoint_id: str, request_id: str,
    answers: dict, evaluation: TrustedCheckpointEvaluation | None,
    catalog_version: str = COURSE_VERSION,
) -> dict:
    _require_user(session, user_id)
    _validate_request_id(request_id)
    module = _checkpoint_module(checkpoint_id)
    answers_json = _canonical_json(answers)
    if len(answers_json) > MAX_JSON:
        raise CourseServiceError(422, "checkpoint_too_large", "Checkpoint answers are too large.")
    payload = {
        "checkpoint_id": checkpoint_id, "answers": answers,
        "catalog_version": catalog_version,
    }
    digest = _payload_hash(payload)
    existing = _checkpoint_attempt(session, user_id, checkpoint_id, request_id)
    if existing:
        return _existing_checkpoint(existing, digest)
    _require_enrollment(session, user_id, catalog_version)
    _require_prerequisites(session, user_id, module)
    trusted = _require_trusted_evaluation(evaluation)
    feedback = _validated_note(trusted.feedback, code="invalid_checkpoint_feedback")
    return _create_checkpoint(
        session, user_id, module, checkpoint_id, request_id,
        digest, answers_json, trusted.passed, feedback,
    )


def _create_checkpoint(
    session: Session, user_id: int, module: CourseModule, checkpoint_id: str,
    request_id: str, digest: str, answers_json: str, passed: bool, feedback: str,
) -> dict:
    row = CourseCheckpointAttempt(
        user_id=user_id, checkpoint_id=checkpoint_id, request_id=request_id,
        payload_sha256=digest, answers_json=answers_json, passed=passed,
        feedback=feedback[:MAX_NOTE],
    )
    try:
        session.add(row)
        session.flush()
        progress = _refresh_progress(session, user_id, module)
        body = {
            "checkpoint_id": checkpoint_id, "attempt_id": row.id,
            "passed": passed, "mission_state": progress.state,
        }
        row.response_json = _canonical_json(body)
        session.add(row)
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = _checkpoint_attempt(session, user_id, checkpoint_id, request_id)
        if existing:
            return _existing_checkpoint(existing, digest)
        raise
    return body


def _checkpoint_attempt(
    session: Session, user_id: int, checkpoint_id: str, request_id: str,
) -> CourseCheckpointAttempt | None:
    return session.exec(select(CourseCheckpointAttempt).where(
        CourseCheckpointAttempt.user_id == user_id,
        CourseCheckpointAttempt.checkpoint_id == checkpoint_id,
        CourseCheckpointAttempt.request_id == request_id,
    )).first()


def _existing_checkpoint(row: CourseCheckpointAttempt, digest: str) -> dict:
    if row.payload_sha256 != digest:
        raise CourseServiceError(409, "idempotency_conflict", "Checkpoint request ID has different input.")
    return json.loads(row.response_json)


def mission_progress(session: Session, user_id: int, mission_id: str) -> dict:
    module = _module(mission_id)
    state = _compute_state(session, user_id, module)
    row = session.exec(select(CourseMissionProgress).where(
        CourseMissionProgress.user_id == user_id,
        CourseMissionProgress.mission_id == mission_id,
    )).first()
    return {"mission_id": mission_id, "state": state, "completed_at": row.completed_at if row else None}


def _compute_state(session: Session, user_id: int, module: CourseModule) -> str:
    artifact_ids = {item.id for item in module.artifacts}
    saved = set(session.exec(select(CourseArtifactEvidence.artifact_id).where(
        CourseArtifactEvidence.user_id == user_id,
        CourseArtifactEvidence.artifact_id.in_(artifact_ids),
    )).all()) if artifact_ids else set()
    review = _oral_review(session, user_id, module.id)
    passed = session.exec(select(CourseCheckpointAttempt.id).where(
        CourseCheckpointAttempt.user_id == user_id,
        CourseCheckpointAttempt.checkpoint_id == module.checkpoint.id,
        CourseCheckpointAttempt.passed == True,  # noqa: E712
    )).first() is not None
    if artifact_ids.issubset(saved) and review and review.state == "reviewed":
        return "complete" if passed else "ready_for_checkpoint"
    if saved or review or passed:
        return "in_progress"
    return "not_started"


def _refresh_progress(session: Session, user_id: int, module: CourseModule) -> CourseMissionProgress:
    state = _compute_state(session, user_id, module)
    row = session.exec(select(CourseMissionProgress).where(
        CourseMissionProgress.user_id == user_id,
        CourseMissionProgress.mission_id == module.id,
    )).first()
    row = row or CourseMissionProgress(user_id=user_id, mission_id=module.id)
    row.state, row.updated_at = state, utcnow()
    row.completed_at = utcnow() if state == "complete" and row.completed_at is None else row.completed_at
    if state != "complete":
        row.completed_at = None
    session.add(row)
    session.flush()
    return row


def delete_content_link(
    session: Session, user_id: int, *, link_id: int, expected_revision: int,
    candidate_fingerprint: str, request_id: str, catalog_version: str = COURSE_VERSION,
) -> MutationResult:
    payload = {
        "link_id": link_id, "expected_revision": expected_revision,
        "candidate_fingerprint": candidate_fingerprint, "catalog_version": catalog_version,
    }

    def mutate() -> tuple[int, dict]:
        _require_enrollment(session, user_id, catalog_version)
        row = session.exec(select(CourseContentLink).where(
            CourseContentLink.id == link_id, CourseContentLink.user_id == user_id,
        )).first()
        if row is None:
            raise CourseServiceError(404, "link_not_found", "Course link not found.")
        if row.revision != expected_revision or row.candidate_fingerprint != candidate_fingerprint:
            raise CourseServiceError(409, "stale_revision", "Course link changed; refresh before deleting.")
        body = _link_body(row) | {"deleted": True}
        session.delete(row)
        session.flush()
        return 200, body

    return execute_receipted_mutation(
        session, user_id, "link_delete", request_id, str(link_id), payload, mutate,
    )


def _link_body(row: CourseContentLink) -> dict:
    return {
        "link_id": row.id, "module_id": row.module_id, "concept_id": row.concept_id,
        "match_kind": row.match_kind, "candidate_fingerprint": row.candidate_fingerprint,
        "revision": row.revision,
    }


def _normalized_match(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    punctuation_collapsed = "".join(char if char.isalnum() else " " for char in normalized)
    return " ".join(punctuation_collapsed.split())


def _module_aliases(module: CourseModule) -> set[str]:
    labels = {module.title}
    labels.update(
        item.label for item in COURSE.source_manifest
        if item.module_id == module.id and item.kind == "section"
    )
    return {_normalized_match(label) for label in labels}


def _candidate_fingerprint(concept: Concept, match_kind: str) -> str:
    payload = {
        "concept_id": concept.id, "match_kind": match_kind,
        "owner_user_id": concept.owner_user_id, "book_id": concept.book_id,
        "slug": concept.slug, "title": _normalized_match(concept.title),
        "chapter": _normalized_match(concept.chapter), "book": _normalized_match(concept.book),
        "track": _normalized_match(concept.track), "sequence": concept.sequence,
    }
    return _payload_hash(payload)


def _owned_candidate(session: Session, user_id: int, concept: Concept, aliases: set[str]):
    if concept.owner_user_id != user_id or concept.book_id is None:
        return None
    book = session.get(Book, concept.book_id)
    title_matches = {_normalized_match(concept.title), _normalized_match(concept.chapter)} & aliases
    book_matches = book and _normalized_match(book.title) == _normalized_match(COURSE_KEY)
    if not book or book.user_id != user_id or not book.activated or book.status not in {"ready", "partial"}:
        return None
    if not book_matches or not title_matches:
        return None
    return _candidate_body(concept, "owned_exact", partial=book.status == "partial")


def _legacy_candidate(concept: Concept, module: CourseModule, *, catalog=COURSE):
    book_alias = _normalized_match(COURSE_KEY)
    imported_book = _normalized_match(concept.book) == book_alias or _normalized_match(concept.track) == book_alias
    if (
        concept.owner_user_id is not None or concept.book_id is not None or concept.source != "book"
        or not imported_book
    ):
        return None
    identity = legacy_identity_match(
        module.id, slug=concept.slug, title=concept.title, chapter=concept.chapter,
        sequence=concept.sequence, catalog=catalog,
    )
    if identity is None:
        return None
    return _candidate_body(concept, "legacy_exact", partial=False)


def _supplement_candidate(concept: Concept, module: CourseModule):
    if (
        concept.owner_user_id is not None or concept.book_id is not None
        or concept.source != "ai" or concept.track not in {"Foundations", "Cross-links"}
    ):
        return None
    identity = (_normalized_match(concept.slug), _normalized_match(concept.title))
    approved = {
        (alias.slug_alias, alias.title_alias)
        for alias in explicit_supplement_aliases(module.id)
    }
    return (_candidate_body(concept, "explicit_supplement_alias", partial=False)
            if identity in approved else None)


def _candidate_body(concept: Concept, match_kind: str, *, partial: bool) -> dict:
    return {
        "concept_id": concept.id, "title": concept.title, "match_kind": match_kind,
        "candidate_fingerprint": _candidate_fingerprint(concept, match_kind),
        "partial": partial,
    }


def _reconciliation_candidates(
    session: Session, user_id: int, module: CourseModule,
) -> list[dict]:
    aliases = _module_aliases(module)
    owned, legacy, supplements = [], [], []
    for concept in session.exec(select(Concept)).all():
        candidate = _owned_candidate(session, user_id, concept, aliases)
        if candidate:
            owned.append(candidate)
            continue
        candidate = _legacy_candidate(concept, module)
        if candidate:
            legacy.append(candidate)
            continue
        candidate = _supplement_candidate(concept, module)
        if candidate:
            supplements.append(candidate)
    selected = owned or legacy or supplements
    return sorted(selected, key=lambda item: item["concept_id"])


def reconciliation_preview(
    session: Session, user_id: int, module_id: str, *, scan: bool,
) -> dict:
    _require_user(session, user_id)
    module = _module(module_id)
    if not scan:
        return {"module_id": module_id, "state": "not_scanned", "revision": 0, "candidates": []}
    candidates = _reconciliation_candidates(session, user_id, module)
    link = session.exec(select(CourseContentLink).where(
        CourseContentLink.user_id == user_id, CourseContentLink.module_id == module_id,
    )).first()
    if link:
        candidate = next((item for item in candidates if item["concept_id"] == link.concept_id), None)
        state = "linked" if candidate and candidate["candidate_fingerprint"] == link.candidate_fingerprint else "stale"
        return {
            "module_id": module_id, "state": state, "revision": link.revision,
            "candidates": candidates, "link": _link_body(link),
        }
    state = "none_found" if not candidates else (
        "partial" if len(candidates) == 1 and candidates[0]["partial"] else "needs_confirmation"
    )
    return {"module_id": module_id, "state": state, "revision": 0, "candidates": candidates}


def resolved_content_link(
    session: Session, user_id: int, module_id: str, *, concept_id: int | None = None,
) -> tuple[CourseContentLink, Concept] | None:
    """Resolve only a still-current, owner-visible reconciliation link."""
    module = _module(module_id)
    link = session.exec(select(CourseContentLink).where(
        CourseContentLink.user_id == user_id,
        CourseContentLink.module_id == module_id,
    )).first()
    if link is None or (concept_id is not None and link.concept_id != concept_id):
        return None
    concept = session.get(Concept, link.concept_id)
    if concept is None or concept.owner_user_id not in {None, user_id}:
        return None
    candidate = next(
        (item for item in _reconciliation_candidates(session, user_id, module)
         if item["concept_id"] == concept.id),
        None,
    )
    if candidate is None or candidate["candidate_fingerprint"] != link.candidate_fingerprint:
        return None
    return link, concept


def _chosen_candidate(candidates: list[dict], fingerprint: str):
    candidate = next(
        (item for item in candidates if item["candidate_fingerprint"] == fingerprint), None,
    )
    if candidate is None:
        raise CourseServiceError(409, "candidate_fingerprint_conflict", "Candidate changed; scan again.")
    return candidate


def reconcile_content(
    session: Session, user_id: int, *, module_id: str,
    candidate_fingerprint: str,
    expected_revision: int, request_id: str, catalog_version: str = COURSE_VERSION,
) -> MutationResult:
    payload = {
        "module_id": module_id, "candidate_fingerprint": candidate_fingerprint,
        "expected_revision": expected_revision, "catalog_version": catalog_version,
    }

    def mutate():
        _require_enrollment(session, user_id, catalog_version)
        candidates = _reconciliation_candidates(session, user_id, _module(module_id))
        chosen = _chosen_candidate(candidates, candidate_fingerprint)
        row = session.exec(select(CourseContentLink).where(
            CourseContentLink.user_id == user_id, CourseContentLink.module_id == module_id,
        )).first()
        current = row.revision if row else 0
        if current != expected_revision:
            raise CourseServiceError(409, "stale_revision", "Course link changed; scan again.")
        row = row or CourseContentLink(user_id=user_id, module_id=module_id, concept_id=chosen["concept_id"])
        row.concept_id, row.match_kind = chosen["concept_id"], chosen["match_kind"]
        row.candidate_fingerprint, row.revision = chosen["candidate_fingerprint"], current + 1
        session.add(row); session.flush()
        return 200, {"state": "linked"} | _link_body(row)

    return execute_receipted_mutation(
        session, user_id, "reconcile", request_id, module_id, payload, mutate,
    )


__all__ = [
    "CourseServiceError", "MutationResult", "artifact_export", "complete_oral", "delete_content_link",
    "enroll", "execute_receipted_mutation", "mission_progress", "module_user_state",
    "receipt_retention_policy",
    "oral_turn_replay", "prepare_oral_turn", "record_checkpoint_attempt", "record_oral_turn", "reconcile_content",
    "reconciliation_preview", "review_oral", "save_artifact",
    "resolved_content_link", "self_record_oral",
]
