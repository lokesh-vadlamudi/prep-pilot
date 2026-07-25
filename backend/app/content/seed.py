"""Load the curated curriculum into the DB (idempotent)."""
from __future__ import annotations

import json

from sqlmodel import Session, select

from ..models import Concept, Card, Problem
from .curriculum import SEED
from .foundations import FOUNDATIONS
from .neetcode150 import problems as neetcode_problems


def seed_problems(session: Session) -> tuple[int, int]:
    """Upsert the NeetCode 150 (superset of Blind 75). Returns (added, updated).

    Existing rows are updated in place by slug so cached AI approaches and the
    user's ProblemStatus (keyed by problem id) are preserved.
    """
    added = updated = 0
    for p in neetcode_problems():
        existing = session.exec(select(Problem).where(Problem.slug == p["slug"])).first()
        if existing:
            existing.collection = p["collections"]
            existing.category = p["category"]
            existing.difficulty = p["difficulty"]
            existing.order_idx = p["order_idx"]
            existing.title = p["title"]
            existing.url = p["url"]
            existing.blurb = p["blurb"]
            existing.pattern = p["pattern"]
            # NOTE: approach_md is intentionally left untouched (keep the cache).
            session.add(existing)
            updated += 1
        else:
            session.add(Problem(
                slug=p["slug"], collection=p["collections"], order_idx=p["order_idx"],
                title=p["title"], category=p["category"], difficulty=p["difficulty"],
                url=p["url"], blurb=p["blurb"], pattern=p["pattern"], approach_md="",
            ))
            added += 1
    session.commit()
    return added, updated


def seed_database(session: Session) -> int:
    """Insert any seed concepts/cards not already present. Returns # concepts added."""
    added = 0
    for item in list(SEED) + list(FOUNDATIONS):
        existing = session.exec(
            select(Concept).where(Concept.slug == item["slug"])
        ).first()
        if existing:
            continue
        concept = Concept(
            slug=item["slug"],
            track=item["track"],
            title=item["title"],
            difficulty=item.get("difficulty", "core"),
            tags=item.get("tags", ""),
            summary=item.get("summary", ""),
            lesson_md=item.get("lesson_md", ""),
            source="seed",
            audience=item.get("audience", "all"),
            sequence=item.get("sequence", 0),
        )
        session.add(concept)
        session.commit()
        session.refresh(concept)
        for c in item.get("cards", []):
            session.add(Card(
                concept_id=concept.id,
                kind=c.get("kind", "mcq"),
                prompt=c.get("prompt", ""),
                choices_json=json.dumps(c["choices"]) if c.get("choices") else "",
                answer=c.get("answer", ""),
                explanation=c.get("explanation", ""),
                source="seed",
            ))
        session.commit()
        added += 1
    return added
