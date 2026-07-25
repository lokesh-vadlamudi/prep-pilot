"""Generate supplementary study content after both books are ingested:
  - Foundational PREREQ concepts (studied first)
  - CROSS-LINK cards connecting the two books (studied after both)
Idempotent by slug. Run on the host that owns the live DB.
"""
from __future__ import annotations

import asyncio
import json
import re

from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Concept, Card
from app import tutor

BOOK_A = "Inference Engineering"
BOOK_B = "System Design Interview"
PREREQ_SEQ_BASE = 100
BRIDGE_SEQ_BASE = 500_000


def log(m: str) -> None:
    print(m, flush=True)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def titles(session: Session, book: str) -> list[str]:
    return [c.title for c in session.exec(
        select(Concept).where(Concept.book == book).order_by(Concept.sequence)).all()]


async def main() -> None:
    init_db()
    with Session(engine) as session:
        ta, tb = titles(session, BOOK_A), titles(session, BOOK_B)
        if not ta or not tb:
            log("INGEST_ERROR: books not found; run book ingestion first")
            return
        log(f"proposing supplements from {len(ta)} + {len(tb)} topics…")
        plan = await tutor.propose_supplements(BOOK_A, ta, BOOK_B, tb)

        # ---- prereqs ----
        prereqs = plan.get("prereqs", [])
        for i, topic in enumerate(prereqs):
            s = slug(f"prereq-{topic}")
            if session.exec(select(Concept).where(Concept.slug == s)).first():
                continue
            try:
                d = await tutor.generate_concept("Foundations", topic, ta + tb)
            except Exception as e:  # noqa: BLE001
                log(f"prereq failed {topic}: {e}"); continue
            c = Concept(
                slug=s, track="Foundations", title=d.get("title", topic),
                difficulty="intro", tags="prereq,foundation", summary=d.get("summary", ""),
                lesson_md=d.get("lesson_md", ""), source="ai", sequence=PREREQ_SEQ_BASE + i,
            )
            session.add(c); session.commit(); session.refresh(c)
            for card in d.get("cards", []):
                session.add(Card(
                    concept_id=c.id, kind=card.get("kind", "mcq"), prompt=card.get("prompt", ""),
                    choices_json=card.get("choices_json", ""), answer=card.get("answer", ""),
                    explanation=card.get("explanation", ""), source="ai"))
            session.commit()
            log(f"[prereq {i+1}/{len(prereqs)}] {c.title}")

        # ---- cross-links ----
        bridges = plan.get("bridges", [])
        for i, br in enumerate(bridges):
            a, b = br.get("a", ""), br.get("b", "")
            if not a or not b:
                continue
            s = slug(f"xlink-{a}-{b}-{i}")
            if session.exec(select(Concept).where(Concept.slug == s)).first():
                continue
            try:
                d = await tutor.cross_link(BOOK_A, a, BOOK_B, b)
            except Exception as e:  # noqa: BLE001
                log(f"bridge failed {a}~{b}: {e}"); continue
            c = Concept(
                slug=s, track="Cross-links", title=d.get("title", f"{a} ↔ {b}"),
                difficulty="advanced", tags="cross-link,synthesis", summary=d.get("summary", ""),
                lesson_md="", source="ai", sequence=BRIDGE_SEQ_BASE + i,
            )
            session.add(c); session.commit(); session.refresh(c)
            session.add(Card(
                concept_id=c.id, kind="free", prompt=d.get("prompt", ""),
                answer=d.get("answer", ""), explanation=d.get("explanation", ""), source="ai"))
            session.commit()
            log(f"[cross-link {i+1}/{len(bridges)}] {c.title}")

    log("SUPPLEMENTS_DONE")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:  # noqa: BLE001
        log(f"SUPPLEMENT_ERROR: {e}")
