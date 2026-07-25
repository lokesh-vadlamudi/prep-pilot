"""SM-2 spaced-repetition scheduling.

grade (quality) scale:
  5 perfect · 4 correct w/ hesitation · 3 correct but hard ·
  2 wrong but familiar · 1 wrong · 0 blackout
A grade < 3 is a lapse: repetitions reset, card comes back tomorrow.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .models import Card


def apply_grade(card: Card, grade: int) -> Card:
    grade = max(0, min(5, int(grade)))
    card.introduced = True
    card.last_reviewed = datetime.utcnow()

    if grade < 3:
        card.repetitions = 0
        card.interval_days = 1
        card.lapses += 1
    else:
        if card.repetitions == 0:
            card.interval_days = 1
        elif card.repetitions == 1:
            card.interval_days = 6
        else:
            card.interval_days = round(card.interval_days * card.ease)
        card.repetitions += 1

    # Update ease factor (bounded at 1.3).
    card.ease = max(
        1.3,
        card.ease + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)),
    )
    card.due_date = date.today() + timedelta(days=card.interval_days)
    return card
