"""Ingest an owned PDF book into grounded study concepts + spaced-repetition cards.

Sections a book by its table-of-contents chapters, splits each chapter into
word-bounded chunks, and has the DGX author a faithful lesson + cards per chunk
(grounded strictly in that text). Concepts are tagged with book/chapter/sequence
so the daily plan can introduce them in reading order.
"""
from __future__ import annotations

import json
import logging
import re

import fitz  # pymupdf
from sqlmodel import Session, select

from .models import Concept, Card
from . import tutor

log = logging.getLogger("prep.ingest")

# TOC entries that are front/back matter — skipped.
_SKIP = re.compile(
    r"table of contents|^preface|^foreword|^forward|acknowledge|^afterword|^index$|recommended reading",
    re.I,
)
CHUNK_WORDS = 1900


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


def chapters(path: str) -> list[dict]:
    """TOC chapters with page ranges. Auto-detects the chapter level (books nest
    their TOC differently — some put chapters at level 1, others at level 2)."""
    doc = fitz.open(path)
    toc = doc.get_toc()
    if not toc:
        return [{"title": "Full text", "page_start": 1, "page_end": doc.page_count}]
    from collections import Counter
    counts = Counter(lvl for lvl, _, _ in toc)
    # shallowest level that has enough entries to be the chapter division.
    level = next((l for l in sorted(counts) if counts[l] >= 4),
                 max(counts, key=lambda l: counts[l]))
    entries = [(t.strip(), p) for lvl, t, p in toc if lvl == level]
    out = []
    for i, (title, page) in enumerate(entries):
        end = (entries[i + 1][1] - 1) if i + 1 < len(entries) else doc.page_count
        out.append({"title": title, "page_start": page, "page_end": max(page, end)})
    return out


def _page_text(doc, p0: int, p1: int) -> str:
    return "\n".join(doc[p].get_text() for p in range(p0 - 1, min(p1, doc.page_count)))


def _chunk(text: str, size: int = CHUNK_WORDS) -> list[str]:
    words = text.split()
    return [" ".join(words[i : i + size]) for i in range(0, len(words), size)] or [""]


def sections_for_book(path: str, book: str) -> list[dict]:
    """Flatten a book into ingestible sections (skips front/back matter + tiny chunks)."""
    doc = fitz.open(path)
    sections = []
    for ch in chapters(path):
        if _SKIP.search(ch["title"]):
            continue
        text = _page_text(doc, ch["page_start"], ch["page_end"])
        chunks = _chunk(text)
        for k, chunk in enumerate(chunks):
            if len(chunk.split()) < 120:  # too small to be a real section
                continue
            label = ch["title"] if len(chunks) == 1 else f"{ch['title']} — part {k + 1}"
            sections.append({
                "book": book, "chapter": ch["title"], "section": label, "text": chunk,
                "page_start": ch["page_start"], "page_end": ch["page_end"],
                "citation": f"{book}, {ch['title']} (p{ch['page_start']}-{ch['page_end']})",
            })
    return sections


async def ingest_book(
    session: Session, path: str, book: str, seq_base: int,
    limit: int | None = None, on_progress=None,
) -> int:
    """Generate + store concepts for a book. Returns # concepts added. Idempotent by slug."""
    secs = sections_for_book(path, book)
    if limit:
        secs = secs[:limit]
    added = 0
    for idx, sec in enumerate(secs):
        slug = _slugify(f"{book}-{sec['section']}-{idx}")
        if session.exec(select(Concept).where(Concept.slug == slug)).first():
            continue
        try:
            data = await tutor.author_from_text(sec["book"], sec["chapter"], sec["text"])
        except Exception as e:  # noqa: BLE001
            log.warning("author failed for %s: %s", sec["section"], e)
            continue
        if data.get("skip") or not data.get("cards"):
            continue
        concept = Concept(
            slug=slug, track=book, title=data.get("title", sec["section"]),
            difficulty="core", tags=f"book,{_slugify(book)}",
            summary=data.get("summary", ""), lesson_md=data.get("lesson_md", ""),
            source="book", book=book, chapter=sec["chapter"],
            sequence=seq_base + idx, citation=sec["citation"],
        )
        session.add(concept)
        session.commit()
        session.refresh(concept)
        for c in data["cards"]:
            session.add(Card(
                concept_id=concept.id, kind=c.get("kind", "mcq"), prompt=c.get("prompt", ""),
                choices_json=c.get("choices_json", ""), answer=c.get("answer", ""),
                explanation=c.get("explanation", ""), source="book",
            ))
        session.commit()
        added += 1
        if on_progress:
            on_progress(idx + 1, len(secs), sec["section"])
    return added


def section_count(path: str, book: str) -> int:
    return len(sections_for_book(path, book))
