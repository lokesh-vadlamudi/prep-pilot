"""Core study logic: build the daily plan, record reviews, compute stats."""
from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta

from sqlmodel import Session, select, func
from .config import settings
from .models import Concept, Card, Attempt, DayLog, User
from .srs import apply_grade

RECENT_ATTEMPT_LIMIT = 20


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


def audiences_for(user: User) -> tuple[str, str]:
    """Which concept audiences this user studies."""
    return ("all", "newgrad") if user.level == "newgrad" else ("all", "senior")


def sync_user_cards(session: Session, user: User) -> int:
    """Give the user their own copy (fresh SM-2 state) of any template card
    (user_id NULL) whose concept they don't have yet, respecting the concept's
    audience (new grads skip the senior book tracks and vice versa)."""
    have = set(session.exec(
        select(Card.concept_id).where(Card.user_id == user.id).distinct()).all())
    templates = session.exec(
        select(Card).join(Concept, Concept.id == Card.concept_id)
        .where(Card.user_id == None,  # noqa: E711
               Concept.audience.in_(audiences_for(user)))  # type: ignore[attr-defined]
    ).all()
    copied = 0
    for t in templates:
        if t.concept_id in have:
            continue
        session.add(Card(
            user_id=user.id, concept_id=t.concept_id, kind=t.kind, prompt=t.prompt,
            choices_json=t.choices_json, answer=t.answer, explanation=t.explanation,
            source=t.source,
        ))
        copied += 1
    if copied:
        session.commit()
    return copied


def _learning_signals(session: Session, user_id: int) -> dict:
    """Small, explainable feature set used by the adaptive scheduler."""
    recent = session.exec(
        select(Attempt)
        .where(Attempt.user_id == user_id)
        .order_by(Attempt.created_at.desc())
        .limit(RECENT_ATTEMPT_LIMIT)
    ).all()
    correct = sum(1 for attempt in recent if attempt.correct)
    accuracy = round(correct / len(recent), 3) if recent else None
    due_reviews = session.exec(
        select(func.count()).select_from(Card).where(
            Card.user_id == user_id,
            Card.introduced == True,  # noqa: E712
            Card.due_date <= date.today(),
        )
    ).one()

    tracks: dict[str, dict[str, int]] = {}
    for attempt in recent:
        if not attempt.track:
            continue
        stat = tracks.setdefault(attempt.track, {"attempts": 0, "correct": 0})
        stat["attempts"] += 1
        stat["correct"] += int(attempt.correct)
    weak_track = None
    if tracks:
        weak_track = min(
            tracks,
            key=lambda track: (
                tracks[track]["correct"] / tracks[track]["attempts"],
                -tracks[track]["attempts"],
                track,
            ),
        )

    return {
        "due_reviews": int(due_reviews),
        "recent_accuracy": accuracy,
        "attempts_considered": len(recent),
        "weak_track": weak_track,
    }


def _adaptive_new_limit(signals: dict) -> tuple[int, str]:
    """Throttle cognitive load while always leaving room for fresh material."""
    configured = max(0, settings.new_topics_per_day)
    if configured == 0:
        return 0, "New material is disabled in settings."

    due = signals["due_reviews"]
    accuracy = signals["recent_accuracy"]
    attempts = signals["attempts_considered"]
    if due >= 10 or (attempts >= 5 and accuracy is not None and accuracy < 0.4):
        return min(1, configured), "Recovery mode: heavy review load or low recent recall."
    if due >= 5 or (attempts >= 5 and accuracy is not None and accuracy < 0.6):
        return min(1, configured), "Review pressure is high, so new material is reduced."
    if due >= 3 or (attempts >= 5 and accuracy is not None and accuracy < 0.75):
        return min(2, configured), "The plan is balancing consolidation with new material."
    return configured, "Recall is stable enough for the full new-topic target."


def _new_card_candidates(session: Session, user_id: int) -> list[tuple[Card, Concept]]:
    rows = session.exec(
        select(Card, Concept)
        .join(Concept, Concept.id == Card.concept_id)
        .where(Card.user_id == user_id, Card.introduced == False)  # noqa: E712
    ).all()
    difficulty_rank = {"intro": 0, "core": 1, "advanced": 2}

    # A book's sequence is an authored prerequisite order. Non-book material is
    # ordered from intro -> core -> advanced.
    return sorted(
        rows,
        key=lambda row: (
            0 if row[1].sequence > 0 else 1,
            row[1].sequence if row[1].sequence > 0 else difficulty_rank.get(row[1].difficulty, 1),
            row[1].id or 0,
            row[0].id or 0,
        ),
    )


def _concept_public(concept: Concept, mastery_state: str) -> dict:
    return {
        "id": concept.id,
        "title": concept.title,
        "track": concept.track,
        "difficulty": concept.difficulty,
        "summary": concept.summary,
        "mastery_state": mastery_state,
    }


def _concept_mastery(session: Session, user_id: int, concept_id: int) -> str:
    cards = session.exec(
        select(Card).where(Card.user_id == user_id, Card.concept_id == concept_id)
    ).all()
    if any(card.interval_days >= 7 for card in cards):
        return "Retained"
    attempts = session.exec(
        select(Attempt).where(
            Attempt.user_id == user_id, Attempt.concept_id == concept_id
        )
    ).all()
    if any(attempt.correct for attempt in attempts):
        return "Practiced"
    if attempts or any(card.introduced for card in cards):
        return "Learning"
    return "Unseen"


def _focus_concept(
    session: Session, user_id: int, due_cards: list[Card], candidates: list[tuple[Card, Concept]]
) -> Concept | None:
    latest_miss = session.exec(
        select(Attempt)
        .where(Attempt.user_id == user_id, Attempt.correct == False)  # noqa: E712
        .order_by(Attempt.created_at.desc())
    ).first()
    if latest_miss:
        concept = session.get(Concept, latest_miss.concept_id)
        if concept:
            return concept
    if due_cards:
        return session.get(Concept, due_cards[0].concept_id)
    return candidates[0][1] if candidates else None


def build_learn_next(session: Session, user: User) -> dict:
    """Choose one transparent next action from recall, load, and curriculum order."""
    sync_user_cards(session, user)
    signals = _learning_signals(session, user.id)
    new_limit, load_reason = _adaptive_new_limit(signals)
    due_cards = session.exec(
        select(Card)
        .where(
            Card.user_id == user.id,
            Card.introduced == True,  # noqa: E712
            Card.due_date <= date.today(),
        )
        .order_by(Card.due_date, Card.id)
    ).all()
    candidates = _new_card_candidates(session, user.id)
    next_new = candidates[0][1] if candidates else None
    focus = _focus_concept(session, user.id, due_cards, candidates)
    accuracy = signals["recent_accuracy"]
    attempts = signals["attempts_considered"]

    if due_cards:
        recovering = attempts >= 5 and accuracy is not None and accuracy < 0.6
        mode = "recover" if recovering else "review"
        title = "Stabilize recall before adding more" if recovering else "Clear your due reviews"
        accuracy_text = (
            f" Recent accuracy is {round(accuracy * 100)}% across {attempts} answers."
            if accuracy is not None else ""
        )
        reason = f"You have {signals['due_reviews']} reviews due.{accuracy_text} {load_reason}"
        objective = (
            f"Rebuild {focus.title} and related recall."
            if focus else "Retrieve the due material without notes."
        )
        action = {"kind": "review_session", "href": "/", "label": "Start adaptive session"}
        estimated = max(5, min(25, len(due_cards) * 3))
    elif attempts >= 5 and accuracy is not None and accuracy < 0.6 and focus:
        mode = "practice"
        title = f"Revisit {focus.title}"
        reason = (
            f"Recent accuracy is {round(accuracy * 100)}% across {attempts} answers. "
            "A focused refresh is a better next step than adding breadth."
        )
        objective = focus.summary or f"Explain {focus.title}, then apply it from memory."
        action = {
            "kind": "topic",
            "href": f"/topics/{focus.id}",
            "label": "Open focused practice",
        }
        estimated = 12
    elif next_new:
        mode = "learn"
        focus = next_new
        title = f"Learn {next_new.title}"
        reason = (
            "Your due queue is clear. This is the next prerequisite-safe topic "
            "in the authored curriculum."
        )
        objective = next_new.summary or f"Explain and apply {next_new.title}."
        action = {
            "kind": "topic",
            "href": f"/topics/{next_new.id}",
            "label": "Learn this concept",
        }
        estimated = {"intro": 12, "core": 18, "advanced": 25}.get(next_new.difficulty, 18)
    else:
        mode = "practice"
        title = "Apply what you know"
        reason = "No reviews or unseen concepts are waiting, so retrieval through practice is next."
        objective = "Solve one interview problem and explain the pattern and trade-offs."
        action = {"kind": "coding_problem", "href": "/problems", "label": "Choose a problem"}
        estimated = 30

    result = {
        "date": date.today().isoformat(),
        "mode": mode,
        "title": title,
        "reason": reason,
        "objective": objective,
        "estimated_minutes": estimated,
        "action": action,
        "signals": {**signals, "new_topic_limit": new_limit},
        "concept": (
            _concept_public(focus, _concept_mastery(session, user.id, focus.id))
            if focus and focus.id is not None else None
        ),
        "up_next": None,
    }
    if due_cards and next_new and next_new.id is not None:
        result["up_next"] = _concept_public(
            next_new, _concept_mastery(session, user.id, next_new.id)
        )
    return result


def recent_learning_evidence(session: Session, user_id: int, limit: int = 6) -> list[dict]:
    """Compact, non-secret evidence sent to DGX for an on-demand diagnosis."""
    attempts = session.exec(
        select(Attempt)
        .where(Attempt.user_id == user_id)
        .order_by(Attempt.created_at.desc())
        .limit(limit)
    ).all()
    evidence = []
    for attempt in attempts:
        concept = session.get(Concept, attempt.concept_id)
        card = session.get(Card, attempt.card_id)
        evidence.append({
            "concept": concept.title if concept else f"Concept {attempt.concept_id}",
            "track": attempt.track,
            "question": (card.prompt[:300] if card else ""),
            "reference_key_points": (card.explanation[:600] if card else ""),
            "grade": attempt.grade,
            "correct": attempt.correct,
            "feedback": attempt.ai_feedback[:400],
        })
    return evidence


def build_daily_plan(session: Session, user: User) -> dict:
    """Due reviews + a few brand-new cards, grouped for today."""
    today = date.today()
    user_id = user.id
    sync_user_cards(session, user)  # pick up any newly authored content
    signals = _learning_signals(session, user_id)
    new_limit, adaptive_reason = _adaptive_new_limit(signals)

    due = session.exec(
        select(Card).where(Card.user_id == user_id,
                           Card.introduced == True, Card.due_date <= today)  # noqa: E712
        .order_by(Card.due_date).limit(settings.max_reviews_per_day)
    ).all()

    # Use the same prerequisite-aware order exposed by Learn Next so the
    # recommended concept is actually present in today's session.
    new = [card for card, _concept in _new_card_candidates(session, user_id)[:new_limit]]

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
        "streak": current_streak(session, user_id),
        "adaptive": {
            "new_topic_limit": new_limit,
            "reason": adaptive_reason,
            "recent_accuracy": signals["recent_accuracy"],
        },
    }


def get_card_detail(session: Session, card_id: int, user_id: int) -> dict | None:
    card = session.get(Card, card_id)
    if not card or card.user_id != user_id:
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
        user_id=card.user_id, card_id=card.id, concept_id=concept.id, track=concept.track,
        grade=grade, correct=correct, user_answer=user_answer, ai_feedback=ai_feedback,
    ))
    # Update today's day-log.
    log = _day_log(session, card.user_id)
    log.reviews_done += 1
    if was_new:
        log.new_learned += 1
    if correct:
        log.correct += 1
    session.add(log)
    session.commit()


def _day_log(session: Session, user_id: int) -> DayLog:
    today = date.today()
    log = session.exec(
        select(DayLog).where(DayLog.user_id == user_id, DayLog.day == today)).first()
    return log or DayLog(user_id=user_id, day=today)


def record_coding_solve(session: Session, user_id: int) -> None:
    """Count a coding solve toward today's ritual (feeds the streak + flight log)."""
    log = _day_log(session, user_id)
    log.coding_solved += 1
    session.add(log)
    session.commit()


def current_streak(session: Session, user_id: int) -> int:
    """Consecutive days (ending today or yesterday) with any activity: a review OR a coding solve."""
    logs = session.exec(
        select(DayLog).where(DayLog.user_id == user_id).order_by(DayLog.day.desc())).all()
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


def book_progress(session: Session, user_id: int) -> list[dict]:
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
            cards = session.exec(select(Card).where(
                Card.concept_id == c.id, Card.user_id == user_id)).all()
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


def progress_stats(session: Session, user_id: int) -> dict:
    total_concepts = session.exec(select(func.count()).select_from(Concept)).one()
    total_cards = session.exec(
        select(func.count()).select_from(Card).where(Card.user_id == user_id)).one()
    introduced = session.exec(
        select(func.count()).select_from(Card)
        .where(Card.user_id == user_id, Card.introduced == True)  # noqa: E712
    ).one()
    attempts = session.exec(
        select(func.count()).select_from(Attempt).where(Attempt.user_id == user_id)).one()
    correct = session.exec(
        select(func.count()).select_from(Attempt)
        .where(Attempt.user_id == user_id, Attempt.correct == True)  # noqa: E712
    ).one()

    # Mastery per track (avg interval as a rough proxy for retention).
    per_track = {}
    for track in ["DSA", "System Design", "CS Fundamentals", "Behavioral"]:
        cards = session.exec(select(Card).join(Concept).where(
            Concept.track == track, Card.user_id == user_id)).all()
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
        log = session.exec(select(DayLog).where(
            DayLog.user_id == user_id, DayLog.day == d)).first()
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
        "streak": current_streak(session, user_id),
        "per_track": per_track,
        "activity": activity,
    }
