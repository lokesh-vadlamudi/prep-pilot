"""Daily plan, card detail, answer submission (with AI grading), and progress."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..auth import RequireUser
from ..db import get_session
from ..models import Card, Concept, User
from .. import service, tutor

router = APIRouter(prefix="/api", tags=["study"], dependencies=[RequireUser])


@router.get("/today")
def today(user: User = RequireUser, session: Session = Depends(get_session)):
    return service.build_daily_plan(session, user.id)


@router.get("/card/{card_id}")
def card_detail(card_id: int, user: User = RequireUser, session: Session = Depends(get_session)):
    detail = service.get_card_detail(session, card_id, user.id)
    if not detail:
        raise HTTPException(404, "Card not found")
    return detail


class SubmitIn(BaseModel):
    card_id: int
    user_answer: str = ""      # chosen text (mcq) or written answer (free/code)
    self_grade: int | None = None  # optional manual SM-2 grade for mcq/self-rated


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
        result = await tutor.grade_free_answer(card, concept, body.user_answer)
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


@router.get("/books")
def books(user: User = RequireUser, session: Session = Depends(get_session)):
    return service.book_progress(session, user.id)


@router.get("/topics")
def topics(user: User = RequireUser, session: Session = Depends(get_session)):
    from sqlmodel import select
    concepts = session.exec(select(Concept).order_by(Concept.track, Concept.id)).all()
    return [
        {"id": c.id, "slug": c.slug, "track": c.track, "title": c.title,
         "difficulty": c.difficulty, "tags": c.tags, "summary": c.summary, "source": c.source}
        for c in concepts
    ]


@router.get("/topic/{concept_id}")
def topic(concept_id: int, user: User = RequireUser, session: Session = Depends(get_session)):
    from sqlmodel import select
    c = session.get(Concept, concept_id)
    if not c:
        raise HTTPException(404, "Not found")
    cards = session.exec(select(Card).where(
        Card.concept_id == concept_id, Card.user_id == user.id)).all()
    return {
        "id": c.id, "track": c.track, "title": c.title, "difficulty": c.difficulty,
        "tags": c.tags, "summary": c.summary, "lesson_md": c.lesson_md, "source": c.source,
        "cards": [{"card_id": x.id, "kind": x.kind, "prompt": x.prompt,
                   "choices": json.loads(x.choices_json) if x.choices_json else [],
                   "due_date": x.due_date.isoformat(), "introduced": x.introduced,
                   "interval_days": x.interval_days} for x in cards],
    }
