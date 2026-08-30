"""Authenticated, owner-scoped API for the inference engineering course."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlmodel import Session, select

from .. import course_service
from ..auth import RequireUser, require_same_origin
from ..course_tutor import CourseTutor, CourseTutorError, get_course_tutor
from ..content.inference_course import COURSE, COURSE_KEY, COURSE_VERSION, CourseModule
from ..db import get_session
from ..models import (
    CourseArtifactEvidence, CourseCheckpointAttempt,
    CourseEnrollment, CourseOralReview, CourseOralTurn, User,
    CourseMutationReceipt, utcnow,
)
from ..ratelimit import require_course_ai_rate, require_course_mutation_rate


router = APIRouter(
    prefix=f"/api/courses/{COURSE_KEY}", tags=["inference-course"],
    dependencies=[RequireUser, Depends(require_same_origin)],
)
BoundedText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
AnswerKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
RequestId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
CatalogVersion = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EnrollIn(StrictBody):
    request_id: RequestId
    catalog_version: CatalogVersion


class ArtifactIn(EnrollIn):
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
    artifact_uri: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2048)]
    draft_fields: dict[AnswerKey, object] = Field(
        min_length=1, max_length=50,
    )
    expected_revision: int = Field(ge=0)


class CheckpointIn(EnrollIn):
    answers: dict[AnswerKey, BoundedText] = Field(min_length=1, max_length=10)


class OralTurnIn(EnrollIn):
    response: BoundedText


class OralSelfRecordIn(EnrollIn):
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
    expected_revision: int = Field(ge=0)


class OralCompleteIn(EnrollIn):
    expected_revision: int = Field(ge=0)


class OralReviewIn(EnrollIn):
    method: Literal["self"]
    acknowledgements: list[BoundedText] = Field(min_length=1, max_length=20)
    reflection: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
    expected_revision: int = Field(ge=0)


class ReconcileIn(EnrollIn):
    module_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    candidate_fingerprint: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"),
    ]
    expected_revision: int = Field(ge=0)


class DeleteLinkIn(EnrollIn):
    candidate_fingerprint: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    expected_revision: int = Field(ge=0)


class LinkedTopicOut(BaseModel):
    id: int
    module_id: str
    title: str
    track: str
    summary: str
    lesson_md: str
    source: str
    audience: str
    course_url: str


class ReplayMetaOut(BaseModel):
    replayed: bool


class ProgressOut(BaseModel):
    mission_id: str
    state: Literal["not_started", "in_progress", "ready_for_checkpoint", "complete"]
    completed_at: datetime | None


class ModuleSummaryOut(BaseModel):
    id: str
    order: int
    callsign: str
    title: str
    prerequisites: list[str]
    platform: str
    artifacts: list["ArtifactRequirementSummaryOut"]
    state: str
    next_action: str
    url: str


class ArtifactRequirementSummaryOut(BaseModel):
    id: str
    title: str
    expectations: list[str]


class CourseOverviewOut(BaseModel):
    key: str
    version: str
    title: str
    audience: str
    enrolled: bool
    modules: list[ModuleSummaryOut]


class LinkedSummaryOut(BaseModel):
    concept_id: int
    title: str
    course_url: str
    revision: int


class ModuleDetailOut(BaseModel):
    id: str
    title: str
    callsign: str
    mission_brief: str
    prerequisites: list[str]
    learning_objectives: list[str]
    lesson_outline: list[str]
    lab: dict[str, object]
    checkpoint: dict[str, object]
    oral: dict[str, object]
    artifacts: list["ArtifactDescriptorOut"]
    sources: list["SourceItemOut"]
    oral_state: "OralReloadStateOut"
    artifact_state: list["ArtifactReloadStateOut"]
    selection_rule: "SelectionRuleOut | None" = None
    debrief_prompt: str
    progress: ProgressOut
    next_action: str
    linked_topic: LinkedSummaryOut | None


class SourceItemOut(BaseModel):
    id: str
    kind: str
    label: str


class SelectionOptionOut(BaseModel):
    id: str
    label: str


class SelectionRuleOut(BaseModel):
    minimum: int
    maximum: int
    options: list[SelectionOptionOut]


class CompletionEntryOut(BaseModel):
    source_id: str
    label: str


class ArtifactCompletionRuleOut(BaseModel):
    id: str
    collection_field: str
    entry_id_field: str
    entry_value_field: str
    entries: list[CompletionEntryOut]
    chosen_id_field: str | None = None
    evidence_field: str | None = None
    evidence_id_field: str | None = None
    evidence_value_field: str | None = None
    maximum_value_length: int


class ArtifactDescriptorOut(BaseModel):
    id: str
    title: str
    template_key: str
    output_format: str
    template_fields: list[str]
    verification_rubric: list[str]
    source_ids: list[str]
    completion_rule: ArtifactCompletionRuleOut | None = None


class OralTurnStateOut(BaseModel):
    turn_id: str
    prompt: str
    response: str
    feedback: str
    next_question: str
    created_at: datetime


class OralReloadStateOut(BaseModel):
    state: Literal["not_started", "practicing", "awaiting_review", "reviewed"]
    mode: str
    revision: int
    self_record_note: str
    review_method: str
    review_feedback: str
    turns: list[OralTurnStateOut]


class ArtifactReloadStateOut(BaseModel):
    artifact_id: str
    title: str
    completed: bool
    revision: int
    note: str
    artifact_uri: str
    draft_fields: dict[str, object]
    catalog_version: str


class EnrollmentOut(BaseModel):
    enrollment_id: int
    course_key: str
    catalog_version: str
    created: bool
    meta: ReplayMetaOut = Field(alias="_meta")


class ArtifactMutationOut(BaseModel):
    artifact_id: str
    mission_id: str
    revision: int
    note: str
    artifact_uri: str
    template_key: str
    output_format: str
    template_fields: list[str]
    draft_fields: dict[str, object]
    verification_rubric: list[str]
    source_ids: list[str]
    catalog_version: str
    mission_state: str
    meta: ReplayMetaOut = Field(alias="_meta")


class CheckpointMutationOut(BaseModel):
    checkpoint_id: str
    attempt_id: int
    passed: bool
    mission_state: str
    feedback: str
    meta: ReplayMetaOut = Field(alias="_meta")


class OralTurnOut(BaseModel):
    mission_id: str
    turn_id: str
    recorded: bool
    prompt: str
    user_response: str
    feedback: str
    next_question: str
    state: Literal["practicing"]
    revision: int
    meta: ReplayMetaOut = Field(alias="_meta")


class OralMutationOut(BaseModel):
    mission_id: str
    review_state: str
    review_method: str
    revision: int
    meta: ReplayMetaOut = Field(alias="_meta")


class LinkMutationOut(BaseModel):
    link_id: int
    module_id: str
    concept_id: int
    match_kind: str
    candidate_fingerprint: str
    revision: int
    deleted: bool = False
    meta: ReplayMetaOut = Field(alias="_meta")


class ReconciliationCandidateOut(BaseModel):
    concept_id: int
    title: str
    match_kind: Literal["owned_exact", "legacy_exact", "explicit_supplement_alias"]
    candidate_fingerprint: str
    partial: bool


class LinkStateOut(BaseModel):
    link_id: int
    module_id: str
    concept_id: int
    match_kind: str
    candidate_fingerprint: str
    revision: int


class ReconciliationPreviewOut(BaseModel):
    module_id: str
    state: Literal["not_scanned", "linked", "partial", "needs_confirmation", "none_found", "stale"]
    revision: int = 0
    candidates: list[ReconciliationCandidateOut]
    link: LinkStateOut | None = None


def _module(module_id: str) -> CourseModule:
    module = next((item for item in COURSE.modules if item.id == module_id), None)
    if module is None:
        raise HTTPException(404, "Course module not found")
    return module


def _enrolled(session: Session, user_id: int) -> bool:
    return session.exec(select(CourseEnrollment.id).where(
        CourseEnrollment.user_id == user_id,
        CourseEnrollment.course_key == COURSE_KEY,
    )).first() is not None


def _next_action(state: str, enrolled: bool) -> str:
    if not enrolled:
        return "enroll"
    return {
        "not_started": "save_evidence", "in_progress": "continue_mission",
        "ready_for_checkpoint": "submit_checkpoint", "complete": "review_debrief",
    }[state]


def _module_summary(session: Session, user_id: int, module: CourseModule, enrolled: bool) -> dict:
    progress = course_service.mission_progress(session, user_id, module.id)
    return {
        "id": module.id, "order": module.order, "callsign": module.callsign,
        "title": module.title, "prerequisites": list(module.prerequisites),
        "platform": module.lab.platform,
        "artifacts": [
            {
                "id": item.id, "title": item.title,
                "expectations": list(item.verification_rubric),
            }
            for item in module.artifacts
        ],
        "state": progress["state"], "next_action": _next_action(progress["state"], enrolled),
        "url": f"/courses/{COURSE_KEY}/{module.id}",
    }


def _linked_summary(session: Session, user_id: int, module_id: str) -> dict | None:
    resolved = course_service.resolved_content_link(session, user_id, module_id)
    if resolved is None:
        return None
    link, concept = resolved
    return {
        "concept_id": concept.id, "title": concept.title,
        "course_url": f"/courses/{COURSE_KEY}/{module_id}/linked-topics/{concept.id}",
        "revision": link.revision,
    }


def _error(error: course_service.CourseServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content=error.body | {"_meta": {"replayed": error.replayed}},
    )


def _invoke(call):
    try:
        value = call()
    except course_service.CourseServiceError as error:
        return _error(error)
    if isinstance(value, course_service.MutationResult):
        body = value.body | {"_meta": {"replayed": value.replayed}}
        return JSONResponse(status_code=value.status_code, content=jsonable_encoder(body))
    return value


@router.get("", response_model=CourseOverviewOut)
def overview(user: User = RequireUser, session: Session = Depends(get_session)):
    enrolled = _enrolled(session, user.id)
    return {
        "key": COURSE.key, "version": COURSE.version, "title": COURSE.title,
        "audience": COURSE.audience, "enrolled": enrolled,
        "modules": [_module_summary(session, user.id, item, enrolled) for item in COURSE.modules],
    }


@router.get(
    "/modules/{module_id}", response_model=ModuleDetailOut,
    response_model_exclude_none=True,
)
def module_detail(module_id: str, user: User = RequireUser, session: Session = Depends(get_session)):
    module = _module(module_id)
    progress = course_service.mission_progress(session, user.id, module.id)
    user_state = course_service.module_user_state(session, user.id, module.id)
    source_by_id = {item.id: item for item in COURSE.source_manifest}
    return {
        "id": module.id, "title": module.title, "callsign": module.callsign,
        "mission_brief": module.mission_brief, "prerequisites": list(module.prerequisites),
        "learning_objectives": list(module.learning_objectives),
        "lesson_outline": list(module.lesson_outline), "lab": asdict(module.lab),
        "checkpoint": {"id": module.checkpoint.id, "prompts": list(module.checkpoint.prompts)},
        "oral": asdict(module.oral), "artifacts": [asdict(item) for item in module.artifacts],
        "sources": [
            {"id": source_id, "kind": source_by_id[source_id].kind,
             "label": source_by_id[source_id].label}
            for source_id in module.source_ids
        ],
        "selection_rule": ({
            "minimum": module.selection_rule.minimum,
            "maximum": module.selection_rule.maximum,
            "options": [
                {"id": source_id, "label": source_by_id[source_id].label}
                for source_id in module.selection_rule.options
            ],
        } if module.selection_rule is not None else None),
        **user_state,
        "debrief_prompt": module.debrief_prompt, "progress": progress,
        "next_action": _next_action(progress["state"], _enrolled(session, user.id)),
        "linked_topic": _linked_summary(session, user.id, module.id),
    }


@router.get("/modules/{module_id}/linked-topics/{concept_id}", response_model=LinkedTopicOut)
def linked_topic(
    module_id: str, concept_id: int, user: User = RequireUser,
    session: Session = Depends(get_session),
):
    _module(module_id)
    resolved = course_service.resolved_content_link(
        session, user.id, module_id, concept_id=concept_id,
    )
    if resolved is None:
        raise HTTPException(404, "Linked lesson not found")
    _, concept = resolved
    return LinkedTopicOut(
        id=concept.id, module_id=module_id, title=concept.title, track=concept.track,
        summary=concept.summary, lesson_md=concept.lesson_md, source=concept.source,
        audience=concept.audience,
        course_url=f"/courses/{COURSE_KEY}/{module_id}/linked-topics/{concept.id}",
    )


@router.get("/reconcile/{module_id}", response_model=ReconciliationPreviewOut)
def reconcile_preview(
    module_id: str, scan: bool = False,
    user: User = RequireUser, session: Session = Depends(get_session),
):
    return _invoke(lambda: course_service.reconciliation_preview(
        session, user.id, module_id, scan=scan,
    ))


@router.post(
    "/enroll", response_model=EnrollmentOut,
    dependencies=[Depends(require_course_mutation_rate)],
)
def enroll(body: EnrollIn, user: User = RequireUser, session: Session = Depends(get_session)):
    return _invoke(lambda: course_service.enroll(
        session, user.id, request_id=body.request_id, catalog_version=body.catalog_version,
    ))


@router.put(
    "/missions/{mission_id}/artifacts/{artifact_id}",
    response_model=ArtifactMutationOut,
    dependencies=[Depends(require_course_mutation_rate)],
)
def save_artifact(
    mission_id: str, artifact_id: str, body: ArtifactIn,
    user: User = RequireUser, session: Session = Depends(get_session),
):
    return _invoke(lambda: course_service.save_artifact(
        session, user.id, mission_id=mission_id, artifact_id=artifact_id,
        note=body.note, artifact_uri=body.artifact_uri, draft_fields=body.draft_fields,
        expected_revision=body.expected_revision, request_id=body.request_id,
        catalog_version=body.catalog_version,
    ))


def _artifact_evidence(session: Session, user_id: int, module: CourseModule) -> list[dict[str, str]]:
    artifact_ids = {item.id for item in module.artifacts}
    rows = session.exec(select(CourseArtifactEvidence).where(
        CourseArtifactEvidence.user_id == user_id,
        CourseArtifactEvidence.mission_id == module.id,
        CourseArtifactEvidence.artifact_id.in_(artifact_ids),
    )).all()
    return [{"artifact_id": row.artifact_id, "note": row.note} for row in rows]


def _tutor_error(error: CourseTutorError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {
            "code": error.code, "detail": error.detail, "retryable": error.retryable,
        }},
    )


async def _evaluate_checkpoint(
    tutor: CourseTutor, request: Request, session: Session, user_id: int,
    module: CourseModule, answers: dict[str, str],
):
    require_course_ai_rate(request)
    try:
        result = await tutor.evaluate_checkpoint(
            module=module, answers=answers,
            artifact_evidence=_artifact_evidence(session, user_id, module),
        )
    except TimeoutError as error:
        return _tutor_error(CourseTutorError(
            503, "course_tutor_unavailable",
            "Qualitative review is temporarily unavailable; try again.", retryable=True,
        ))
    except CourseTutorError as error:
        return _tutor_error(error)
    return course_service._trusted_checkpoint_evaluation(
        passed=result.passed, feedback=result.feedback,
    )


@router.post(
    "/checkpoints/{checkpoint_id}/submit",
    response_model=CheckpointMutationOut,
    dependencies=[Depends(require_course_mutation_rate)],
)
async def submit_checkpoint(
    checkpoint_id: str, body: CheckpointIn, request: Request, user: User = RequireUser,
    session: Session = Depends(get_session), tutor: CourseTutor = Depends(get_course_tutor),
):
    module = next((item for item in COURSE.modules if item.checkpoint.id == checkpoint_id), None)
    if module is None:
        raise HTTPException(404, "Course checkpoint not found")
    existing = session.exec(select(CourseCheckpointAttempt).where(
        CourseCheckpointAttempt.user_id == user.id,
        CourseCheckpointAttempt.checkpoint_id == checkpoint_id,
        CourseCheckpointAttempt.request_id == body.request_id,
    )).first()
    evaluation = None if existing else await _evaluate_checkpoint(
        tutor, request, session, user.id, module, body.answers,
    )
    if isinstance(evaluation, JSONResponse):
        return evaluation
    result = _invoke(lambda: course_service.record_checkpoint_attempt(
        session, user.id, checkpoint_id=checkpoint_id, request_id=body.request_id,
        answers=body.answers, evaluation=evaluation, catalog_version=body.catalog_version,
    ))
    if isinstance(result, JSONResponse):
        return result
    attempt = session.get(CourseCheckpointAttempt, result["attempt_id"])
    return result | {"feedback": attempt.feedback, "_meta": {"replayed": existing is not None}}


@router.post(
    "/oral/{mission_id}/turn", response_model=OralTurnOut,
)
async def oral_turn(
    mission_id: str, body: OralTurnIn, request: Request, user: User = RequireUser,
    session: Session = Depends(get_session), tutor: CourseTutor = Depends(get_course_tutor),
):
    replay = _invoke(lambda: course_service.oral_turn_replay(
        session, user.id, mission_id=mission_id, turn_id=body.request_id,
        response=body.response, catalog_version=body.catalog_version,
    ))
    if isinstance(replay, JSONResponse):
        return replay
    if replay is not None:
        return replay | {"_meta": {"replayed": True}}
    prepared = _invoke(lambda: course_service.prepare_oral_turn(
        session, user.id, mission_id=mission_id, catalog_version=body.catalog_version,
    ))
    if isinstance(prepared, JSONResponse):
        return prepared
    require_course_ai_rate(request)
    try:
        evaluation = await tutor.evaluate_turn(
            module=prepared["module"], prompt=prepared["prompt"],
            response=body.response, prior_turns=prepared["prior_turns"],
        )
    except TimeoutError:
        return _tutor_error(CourseTutorError(
            503, "course_tutor_unavailable",
            "Qualitative practice is temporarily unavailable; try again.", retryable=True,
        ))
    except CourseTutorError as error:
        return _tutor_error(error)
    trusted = course_service._trusted_oral_turn_evaluation(
        feedback=evaluation.feedback, next_question=evaluation.next_question,
    )
    result = _invoke(lambda: course_service.record_oral_turn(
        session, user.id, mission_id=mission_id, turn_id=body.request_id,
        response=body.response, evaluation=trusted,
        expected_revision=prepared["expected_revision"],
        catalog_version=body.catalog_version,
    ))
    return result if isinstance(result, JSONResponse) else result | {"_meta": {"replayed": False}}


@router.post(
    "/oral/{mission_id}/self-record", response_model=OralMutationOut,
    dependencies=[Depends(require_course_mutation_rate)],
)
def oral_self_record(
    mission_id: str, body: OralSelfRecordIn, user: User = RequireUser,
    session: Session = Depends(get_session),
):
    return _invoke(lambda: course_service.self_record_oral(
        session, user.id, mission_id=mission_id, note=body.note,
        expected_revision=body.expected_revision, request_id=body.request_id,
        catalog_version=body.catalog_version,
    ))


def _oral_attempt(session: Session, user_id: int, mission_id: str):
    review = session.exec(select(CourseOralReview).where(
        CourseOralReview.user_id == user_id,
        CourseOralReview.mission_id == mission_id,
    )).first()
    turns = session.exec(select(CourseOralTurn).where(
        CourseOralTurn.user_id == user_id,
        CourseOralTurn.mission_id == mission_id,
    )).all()
    return review, [{"prompt": row.prompt, "response": row.response} for row in turns]


def _complete_payload(mission_id: str, body: OralCompleteIn) -> dict:
    return {
        "mission_id": mission_id, "expected_revision": body.expected_revision,
        "catalog_version": body.catalog_version,
    }


def _complete_receipt(session: Session, user_id: int, body: OralCompleteIn):
    return session.exec(select(CourseMutationReceipt).where(
        CourseMutationReceipt.user_id == user_id,
        CourseMutationReceipt.course_key == COURSE_KEY,
        CourseMutationReceipt.operation == "oral_complete",
        CourseMutationReceipt.request_id == body.request_id,
    )).first()


def _apply_oral_completion(
    session: Session, user_id: int, mission_id: str,
    body: OralCompleteIn, evaluation,
):
    def mutate():
        course_service._require_enrollment(session, user_id, body.catalog_version)
        module = course_service._module(mission_id)
        review = course_service._oral_review(session, user_id, mission_id)
        if review is None or review.state not in {"awaiting_review", "practicing"}:
            raise course_service.CourseServiceError(
                409, "invalid_oral_transition", "No oral practice is ready for review.",
            )
        if review.revision != body.expected_revision:
            raise course_service.CourseServiceError(
                409, "stale_revision", "Oral practice changed; refresh before reviewing.",
            )
        if evaluation is None or not evaluation.passed:
            detail = evaluation.feedback if evaluation else "Qualitative evidence is incomplete."
            raise course_service.CourseServiceError(409, "oral_evidence_incomplete", detail)
        review.state, review.review_method = "reviewed", "dgx"
        review.review_feedback = course_service._validate_oral_review(
            module, "dgx", [], evaluation.feedback,
        )
        review.reviewed_at, review.updated_at = utcnow(), utcnow()
        review.revision += 1
        session.add(review); session.flush()
        course_service._refresh_progress(session, user_id, module)
        return 200, course_service._oral_body(review)

    return course_service.execute_receipted_mutation(
        session, user_id, "oral_complete", body.request_id, mission_id,
        _complete_payload(mission_id, body), mutate,
    )


@router.post(
    "/oral/{mission_id}/complete", response_model=OralMutationOut,
)
async def oral_complete(
    mission_id: str, body: OralCompleteIn, request: Request, user: User = RequireUser,
    session: Session = Depends(get_session), tutor: CourseTutor = Depends(get_course_tutor),
):
    receipt = _complete_receipt(session, user.id, body)
    if receipt is not None:
        return _invoke(lambda: _apply_oral_completion(
            session, user.id, mission_id, body, None,
        ))
    module = _module(mission_id)
    review, turns = _oral_attempt(session, user.id, mission_id)
    if review is None or review.state not in {"awaiting_review", "practicing"} or review.revision != body.expected_revision:
        return _invoke(lambda: _apply_oral_completion(
            session, user.id, mission_id, body, None,
        ))
    require_course_ai_rate(request)
    try:
        evaluation = await tutor.evaluate_oral(
            module=module, self_record_note=review.self_record_note,
            turns=turns,
        )
    except TimeoutError as error:
        return _tutor_error(CourseTutorError(
            503, "course_tutor_unavailable",
            "Qualitative review is temporarily unavailable; try again.", retryable=True,
        ))
    except CourseTutorError as error:
        return _tutor_error(error)
    return _invoke(lambda: _apply_oral_completion(
        session, user.id, mission_id, body, evaluation,
    ))


@router.post(
    "/oral/{mission_id}/review", response_model=OralMutationOut,
    dependencies=[Depends(require_course_mutation_rate)],
)
def oral_review(
    mission_id: str, body: OralReviewIn, user: User = RequireUser,
    session: Session = Depends(get_session),
):
    return _invoke(lambda: course_service.review_oral(
        session, user.id, mission_id=mission_id, method="self_rubric",
        acknowledgements=body.acknowledgements, feedback=body.reflection,
        expected_revision=body.expected_revision, request_id=body.request_id,
        catalog_version=body.catalog_version,
    ))


@router.post(
    "/reconcile", response_model=LinkMutationOut,
    dependencies=[Depends(require_course_mutation_rate)],
)
def reconcile(body: ReconcileIn, user: User = RequireUser, session: Session = Depends(get_session)):
    return _invoke(lambda: course_service.reconcile_content(
        session, user.id, module_id=body.module_id,
        candidate_fingerprint=body.candidate_fingerprint,
        expected_revision=body.expected_revision, request_id=body.request_id,
        catalog_version=body.catalog_version,
    ))


@router.delete(
    "/links/{link_id}", response_model=LinkMutationOut,
    dependencies=[Depends(require_course_mutation_rate)],
)
def delete_link(
    link_id: int, body: DeleteLinkIn, user: User = RequireUser,
    session: Session = Depends(get_session),
):
    return _invoke(lambda: course_service.delete_content_link(
        session, user.id, link_id=link_id,
        expected_revision=body.expected_revision,
        candidate_fingerprint=body.candidate_fingerprint,
        request_id=body.request_id, catalog_version=body.catalog_version,
    ))
