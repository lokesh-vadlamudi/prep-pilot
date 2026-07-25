"""Nightly job: grow the content bank with fresh AI-authored concepts."""
from __future__ import annotations

import json
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select

from .config import settings
from .db import engine
from .models import Concept, Card
from . import tutor

log = logging.getLogger("prep.scheduler")

# Rotating theme hints so new concepts stay varied across senior-SWE surface area.
THEMES = {
    "DSA": ["graphs & BFS/DFS", "backtracking", "heaps & priority queues", "binary search on answer",
            "tries & string algorithms", "union-find", "sliding window", "greedy vs DP"],
    "System Design": ["rate limiting", "message queues & Kafka", "idempotency & exactly-once",
                      "sharding & partitioning", "search/indexing", "CDN & edge", "observability",
                      "API gateway design", "distributed locks", "event sourcing / CQRS"],
    "CS Fundamentals": ["memory & GC", "TCP flow/congestion control", "database indexing (B-tree/LSM)",
                        "OS scheduling", "hashing & bloom filters", "Go scheduler/goroutines",
                        "Python asyncio internals", "TLS & certificates"],
    "Behavioral": ["driving cross-team projects", "mentoring & growing others", "handling conflict",
                   "ambiguity & scoping", "influencing without authority", "prioritization & trade-offs"],
}


async def generate_new_concepts(per_track: int = 1) -> int:
    """Author `per_track` new concepts for each track. Returns count added."""
    added = 0
    with Session(engine) as session:
        existing = session.exec(select(Concept)).all()
        titles = [c.title for c in existing]
        counts = {}
        for c in existing:
            counts[c.track] = counts.get(c.track, 0) + 1

        for track, themes in THEMES.items():
            for _ in range(per_track):
                # Rotate theme by how many concepts already exist in the track.
                theme = themes[counts.get(track, 0) % len(themes)]
                try:
                    data = await tutor.generate_concept(track, theme, titles)
                except Exception as e:  # noqa: BLE001
                    log.warning("generation failed for %s/%s: %s", track, theme, e)
                    continue

                slug = str(data.get("slug", "")).strip()
                if not slug or session.exec(
                    select(Concept).where(Concept.slug == slug)
                ).first():
                    continue

                concept = Concept(
                    slug=slug, track=track, title=data.get("title", theme),
                    difficulty=data.get("difficulty", "core"), tags=data.get("tags", ""),
                    summary=data.get("summary", ""), lesson_md=data.get("lesson_md", ""),
                    source="ai",
                )
                session.add(concept)
                session.commit()
                session.refresh(concept)
                for c in data.get("cards", []):
                    session.add(Card(
                        concept_id=concept.id, kind=c.get("kind", "mcq"),
                        prompt=c.get("prompt", ""),
                        choices_json=c.get("choices_json", json.dumps(c["choices"]) if c.get("choices") else ""),
                        answer=c.get("answer", ""), explanation=c.get("explanation", ""),
                        source="ai",
                    ))
                session.commit()
                titles.append(concept.title)
                counts[track] = counts.get(track, 0) + 1
                added += 1
                log.info("added AI concept: [%s] %s", track, concept.title)
    return added


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        generate_new_concepts,
        CronTrigger(hour=settings.daily_generation_hour, minute=0),
        id="nightly_content", replace_existing=True, misfire_grace_time=3600,
    )
    scheduler.start()
    log.info("scheduler started; nightly content at %02d:00", settings.daily_generation_hour)
    return scheduler
