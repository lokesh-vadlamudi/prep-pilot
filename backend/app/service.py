"""Core study logic: build the daily plan, record reviews, compute stats."""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta

from sqlmodel import Session, select, func
from sqlalchemy import case

from .config import settings
from .models import Concept, Card, Attempt, DayLog
from .srs import apply_grade


def _card_public(card: Card, concept: Concept, reveal: bool = False) -> dict:
    choices = json.loads(card.choices_json) if card.choices_json else []
    # Shuffle MCQ options each time so repeated reviews test recall, not the
    # memorized position of the answer. Grading matches on the choice TEXT, so
    # reordering is safe.
    if choices:
        choices = choices[:]
        random.shuffle(choices)
    d = {
        "card_id": card.id,
        "concept_id": concept.id,
        "concept_title": concept.title,
        "track": concept.track,
        "tags": concept.tags,
        "kind": card.kind,
        "prompt": card.prompt,
        "choices": choices,
        "is_new": not card.introduced,
    }
    if reveal:
        d["answer"] = card.answer
        d["explanation"] = card.explanation
    return d


def build_daily_plan(session: Session) -> dict:
    """Due reviews + a few brand-new cards, grouped for today."""
    today = date.today()

    due = session.exec(
        select(Card).where(Card.introduced == True, Card.due_date <= today)  # noqa: E712
        .order_by(Card.due_date).limit(settings.max_reviews_per_day)
    ).all()

    # Introduce new material in study order: book concepts by their sequence
    # (reading order), legacy/seed concepts (sequence 0) afterwards.
    order_key = case((Concept.sequence == 0, 1_000_000_000), else_=Concept.sequence)
    new = session.exec(
        select(Card).join(Concept, Concept.id == Card.concept_id)
        .where(Card.introduced == False)  # noqa: E712
        .order_by(order_key, Card.id).limit(settings.new_topics_per_day)
    ).all()

    def hydrate(cards):
        out = []
        for c in cards:
            concept = session.get(Concept, c.concept_id)
            if concept:
                out.append(_card_public(c, concept))
        return out

    return {
        "date": today.isoformat(),
        "reviews": hydrate(due),
        "new": hydrate(new),
        "streak": current_streak(session),
    }


def get_card_detail(session: Session, card_id: int) -> dict | None:
    card = session.get(Card, card_id)
    if not card:
        return None
    concept = session.get(Concept, card.concept_id)
    d = _card_public(card, concept, reveal=True)
    d["lesson_md"] = concept.lesson_md
    return d


def record_attempt(
    session: Session, card: Card, concept: Concept, grade: int,
    correct: bool, user_answer: str, ai_feedback: str = "",
) -> None:
    was_new = not card.introduced
    apply_grade(card, grade)
    session.add(card)
    session.add(Attempt(
        card_id=card.id, concept_id=concept.id, track=concept.track,
        grade=grade, correct=correct, user_answer=user_answer, ai_feedback=ai_feedback,
    ))
    # Update today's day-log.
    today = date.today()
    log = session.exec(select(DayLog).where(DayLog.day == today)).first()
    if not log:
        log = DayLog(day=today)
    log.reviews_done += 1
    if was_new:
        log.new_learned += 1
    if correct:
        log.correct += 1
    session.add(log)
    session.commit()


def record_coding_solve(session: Session) -> None:
    """Count a coding solve toward today's ritual (feeds the streak + flight log)."""
    today = date.today()
    log = session.exec(select(DayLog).where(DayLog.day == today)).first()
    if not log:
        log = DayLog(day=today)
    log.coding_solved += 1
    session.add(log)
    session.commit()


def current_streak(session: Session) -> int:
    """Consecutive days (ending today or yesterday) with any activity: a review OR a coding solve."""
    logs = session.exec(select(DayLog).order_by(DayLog.day.desc())).all()
    if not logs:
        return 0
    days = {log.day for log in logs if log.reviews_done > 0 or log.coding_solved > 0}
    streak, cursor = 0, date.today()
    if cursor not in days:
        cursor = cursor - timedelta(days=1)  # allow "today not done yet"
        if cursor not in days:
            return 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def book_progress(session: Session) -> list[dict]:
    """Per-book study progress: sections seen vs total, and current chapter."""
    books = session.exec(
        select(Concept.book).where(Concept.book != "").distinct()
    ).all()
    out = []
    for book in sorted(books):
        concepts = session.exec(
            select(Concept).where(Concept.book == book).order_by(Concept.sequence)
        ).all()
        total = len(concepts)
        seen = 0
        current_chapter = concepts[0].chapter if concepts else ""
        for c in concepts:
            cards = session.exec(select(Card).where(Card.concept_id == c.id)).all()
            if cards and all(cd.introduced for cd in cards):
                seen += 1
            elif current_chapter == (concepts[0].chapter if concepts else ""):
                current_chapter = c.chapter  # first not-fully-seen concept's chapter
                break
        chapters = []
        seen_ch = set()
        for c in concepts:
            if c.chapter not in seen_ch:
                seen_ch.add(c.chapter)
                chapters.append(c.chapter)
        out.append({
            "book": book, "total": total, "seen": seen,
            "chapters": len(chapters), "current_chapter": current_chapter,
        })
    return out


def progress_stats(session: Session) -> dict:
    total_concepts = session.exec(select(func.count()).select_from(Concept)).one()
    total_cards = session.exec(select(func.count()).select_from(Card)).one()
    introduced = session.exec(
        select(func.count()).select_from(Card).where(Card.introduced == True)  # noqa: E712
    ).one()
    attempts = session.exec(select(func.count()).select_from(Attempt)).one()
    correct = session.exec(
        select(func.count()).select_from(Attempt).where(Attempt.correct == True)  # noqa: E712
    ).one()

    # Mastery per track (avg interval as a rough proxy for retention).
    per_track = {}
    for track in ["DSA", "System Design", "CS Fundamentals", "Behavioral"]:
        cards = session.exec(select(Card).join(Concept).where(Concept.track == track)).all()
        seen = [c for c in cards if c.introduced]
        mastered = [c for c in seen if c.interval_days >= 7]
        per_track[track] = {
            "total": len(cards),
            "seen": len(seen),
            "mastered": len(mastered),
        }

    # 14-day activity for a heatmap/graph (reviews + coding solves = one ritual).
    activity = []
    for i in range(13, -1, -1):
        d = date.today() - timedelta(days=i)
        log = session.exec(select(DayLog).where(DayLog.day == d)).first()
        reviews = log.reviews_done if log else 0
        coding = log.coding_solved if log else 0
        activity.append({
            "day": d.isoformat(),
            "reviews": reviews,
            "coding": coding,
            "total": reviews + coding,
            "correct": log.correct if log else 0,
        })

    return {
        "total_concepts": total_concepts,
        "total_cards": total_cards,
        "introduced": introduced,
        "attempts": attempts,
        "accuracy": round(correct / attempts, 3) if attempts else 0.0,
        "streak": current_streak(session),
        "per_track": per_track,
        "activity": activity,
    }
