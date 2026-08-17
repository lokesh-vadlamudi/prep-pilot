"""Daily plan, card detail, answer submission (with AI grading), and progress."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ..auth import RequireUser
from ..db import get_session
from ..models import Card, Concept, ConceptStatus, User, utcnow
from .. import service, tutor

router = APIRouter(prefix="/api", tags=["study"], dependencies=[RequireUser])


@router.get("/today")
def today(user: User = RequireUser, session: Session = Depends(get_session)):
    return service.build_daily_plan(session, user)


@router.get("/learn-next")
def learn_next(user: User = RequireUser, session: Session = Depends(get_session)):
    return service.build_learn_next(session, user)


@router.post("/learn-next/diagnose")
async def diagnose_learn_next(
    user: User = RequireUser, session: Session = Depends(get_session)
):
    plan = service.build_learn_next(session, user)
    evidence = service.recent_learning_evidence(session, user.id)
    return await tutor.diagnose_learning_plan(
        plan, evidence, learner=tutor.learner_context(user)
    )


@router.get("/card/{card_id}")
def card_detail(card_id: int, user: User = RequireUser, session: Session = Depends(get_session)):
    detail = service.get_card_detail(session, card_id, user.id)
    if not detail:
        raise HTTPException(404, "Card not found")
    return detail


class SubmitIn(BaseModel):
    card_id: int
    user_answer: str = Field(default="", max_length=10000)  # chosen text (mcq) or written answer (free/code)
    # Optional manual SM-2 grade for mcq/self-rated; clamped to the SM-2 scale.
    self_grade: int | None = Field(default=None, ge=0, le=5)


@router.post("/submit")
async def submit(body: SubmitIn, user: User = RequireUser, session: Session = Depends(get_session)):
    card = session.get(Card, body.card_id)
    if not card or card.user_id != user.id:
        raise HTTPException(404, "Card not found")
    concept = session.get(Concept, card.concept_id)

    ai_feedback = ""
    if card.kind == "mcq":
        correct = body.user_answer.strip() == card.answer.strip()
        grade = 5 if correct else 2
    elif body.self_grade is not None:
        # User self-rated (e.g. flashcard flip) without AI grading.
        grade = int(body.self_grade)
        correct = grade >= 3
    else:
        # Free-text / code: grade with the DGX tutor.
        result = await tutor.grade_free_answer(
            card, concept, body.user_answer, learner=tutor.learner_context(user))
        grade, correct, ai_feedback = result["grade"], result["correct"], result["feedback"]

    service.record_attempt(session, card, concept, grade, correct, body.user_answer, ai_feedback)
    return {
        "grade": grade,
        "correct": correct,
        "ai_feedback": ai_feedback,
        "answer": card.answer,
        "explanation": card.explanation,
        "next_review_days": card.interval_days,
    }


@router.get("/progress")
def progress(user: User = RequireUser, session: Session = Depends(get_session)):
    return service.progress_stats(session, user.id)


@router.get("/topics")
def topics(user: User = RequireUser, session: Session = Depends(get_session)):
    concepts = session.exec(select(Concept).where(
        (Concept.owner_user_id == None) | (Concept.owner_user_id == user.id)  # noqa: E711
    ).order_by(Concept.track, Concept.id)).all()
    completed = {s.concept_id for s in session.exec(select(ConceptStatus).where(
        ConceptStatus.user_id == user.id, ConceptStatus.completed == True  # noqa: E712
    )).all()}
    return [
        {"id": c.id, "slug": c.slug, "track": c.track, "title": c.title,
         "difficulty": c.difficulty, "tags": c.tags, "summary": c.summary,
         "source": c.source, "completed": c.id in completed}
        for c in concepts
    ]


@router.get("/topic/{concept_id}")
def topic(concept_id: int, user: User = RequireUser, session: Session = Depends(get_session)):
    c = session.exec(select(Concept).where(
        Concept.id == concept_id,
        (Concept.owner_user_id == None) | (Concept.owner_user_id == user.id),  # noqa: E711
    )).first()
    if not c:
        raise HTTPException(404, "Not found")
    cards = session.exec(select(Card).where(
        Card.concept_id == concept_id, Card.user_id == user.id)).all()
    status = session.exec(select(ConceptStatus).where(
        ConceptStatus.user_id == user.id, ConceptStatus.concept_id == concept_id)).first()
    book_navigation = None
    if c.book_id:
        siblings = session.exec(select(Concept).where(
            Concept.book_id == c.book_id, Concept.owner_user_id == user.id
        ).order_by(Concept.sequence, Concept.id)).all()
        position = next((i for i, item in enumerate(siblings) if item.id == c.id), -1)
        if position >= 0:
            book_navigation = {
                "book_id": c.book_id,
                "book_title": c.book,
                "position": position + 1,
                "total": len(siblings),
                "previous": ({"id": siblings[position - 1].id, "title": siblings[position - 1].title}
                             if position > 0 else None),
                "next": ({"id": siblings[position + 1].id, "title": siblings[position + 1].title}
                         if position + 1 < len(siblings) else None),
            }
    return {
        "id": c.id, "track": c.track, "title": c.title, "difficulty": c.difficulty,
        "tags": c.tags, "summary": c.summary, "lesson_md": c.lesson_md, "source": c.source,
        "completed": bool(status and status.completed),
        "book_navigation": book_navigation,
        "cards": [{"card_id": x.id, "kind": x.kind, "prompt": x.prompt,
                   "choices": json.loads(x.choices_json) if x.choices_json else [],
                   "due_date": x.due_date.isoformat(), "introduced": x.introduced,
                   "interval_days": x.interval_days} for x in cards],
    }


class TopicStatusIn(BaseModel):
    completed: bool


@router.post("/topic/{concept_id}/status")
def set_topic_status(concept_id: int, body: TopicStatusIn, user: User = RequireUser,
                     session: Session = Depends(get_session)):
    c = session.exec(select(Concept).where(
        Concept.id == concept_id,
        (Concept.owner_user_id == None) | (Concept.owner_user_id == user.id),  # noqa: E711
    )).first()
    if not c:
        raise HTTPException(404, "Not found")
    status = session.exec(select(ConceptStatus).where(
        ConceptStatus.user_id == user.id, ConceptStatus.concept_id == concept_id)).first()
    if not status:
        status = ConceptStatus(user_id=user.id, concept_id=concept_id)
    status.completed = body.completed
    status.completed_at = utcnow() if body.completed else None
    session.add(status); session.commit()
    return {"ok": True, "completed": status.completed}
