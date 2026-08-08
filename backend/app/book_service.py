"""Private PDF lifecycle, persistent generation worker, and grounded retrieval."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

import fitz
from fastapi import HTTPException, UploadFile
from sqlmodel import Session, select

from . import tutor
from .config import settings
from .models import Book, BookChatMessage, Card, Concept, IngestionSection, User

log = logging.getLogger("prep.books")
PDF_MAGIC = b"%PDF-"
MIN_TEXT_CHARS_PER_PAGE = 40


def owned_book(session: Session, user_id: int, book_id: int) -> Book:
    book = session.exec(select(Book).where(Book.id == book_id, Book.user_id == user_id)).first()
    if not book:
        raise HTTPException(404, "Book not found")
    return book


async def save_upload(session: Session, user: User, upload: UploadFile) -> Book:
    """Stream a PDF to a private generated path, validate it, then persist checkpoints."""
    storage = Path(settings.book_storage_dir)
    storage.mkdir(parents=True, exist_ok=True, mode=0o700)
    storage.chmod(0o700)
    tmp = storage / f"upload-{user.id}-{time.time_ns()}.tmp"
    digest = hashlib.sha256()
    size = 0
    try:
        with tmp.open("xb") as target:
            tmp.chmod(0o600)
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_book_bytes:
                    raise HTTPException(413, "PDF exceeds the configured size limit")
                digest.update(chunk)
                target.write(chunk)
        with tmp.open("rb") as source:
            signature = source.read(len(PDF_MAGIC))
        if size < len(PDF_MAGIC) or signature != PDF_MAGIC:
            raise HTTPException(400, "File is not a PDF")
        sha = digest.hexdigest()
        duplicate = session.exec(select(Book).where(Book.user_id == user.id, Book.sha256 == sha)).first()
        if duplicate:
            raise HTTPException(409, "This book is already in your library")
        try:
            doc = fitz.open(tmp)
            if doc.needs_pass:
                raise HTTPException(400, "Encrypted PDFs are not supported")
            if doc.page_count < 1 or doc.page_count > settings.max_book_pages:
                raise HTTPException(400, "PDF page count is outside the configured limit")
            sample_pages = min(doc.page_count, 20)
            sample_text = "".join(doc[p].get_text() for p in range(sample_pages)).strip()
            if len(sample_text) < sample_pages * MIN_TEXT_CHARS_PER_PAGE:
                raise HTTPException(400, "PDF has too little extractable text; OCR is not supported")
            page_count = doc.page_count
            title = (doc.metadata or {}).get("title", "").strip()
            doc.close()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, "PDF is malformed or unreadable") from exc

        safe_title = title or Path(upload.filename or "Book").stem
        book = Book(user_id=user.id, title=safe_title[:200], original_filename=Path(upload.filename or "book.pdf").name[:255],
                    storage_path="", sha256=sha, byte_size=size, page_count=page_count, status="extracting")
        session.add(book); session.commit(); session.refresh(book)
        final = storage / str(user.id) / f"{book.id}.pdf"
        final.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        final.parent.chmod(0o700)
        tmp.replace(final)
        final.chmod(0o600)
        book.storage_path = str(final)
        _extract_sections(session, book)
        return book
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _extract_sections(session: Session, book: Book) -> None:
    from .ingest import sections_for_book
    try:
        sections = sections_for_book(book.storage_path, book.title)
        if not sections:
            raise ValueError("No substantive sections found")
        for ordinal, item in enumerate(sections):
            text = item["text"]
            session.add(IngestionSection(
                book_id=book.id, ordinal=ordinal, chapter=item["chapter"], label=item["section"],
                page_start=item["page_start"], page_end=item["page_end"], citation=item["citation"],
                extracted_text=text, content_hash=hashlib.sha256(text.encode()).hexdigest(),
            ))
        book.total_sections = len(sections)
        book.status = "queued"
        book.updated_at = datetime.utcnow()
        session.add(book); session.commit(); session.refresh(book)
    except Exception:
        book.status = "failed"; book.error_code = "extraction_failed"
        book.error_message = "The PDF could not be separated into readable sections."
        session.add(book); session.commit()
        log.warning("book extraction failed book_id=%s user_id=%s", book.id, book.user_id)


def _valid_cards(cards: object) -> list[dict]:
    valid = []
    for card in cards if isinstance(cards, list) else []:
        if not isinstance(card, dict) or not str(card.get("prompt", "")).strip() or not str(card.get("answer", "")).strip():
            continue
        kind = card.get("kind", "free")
        if kind == "mcq":
            choices = card.get("choices")
            if not isinstance(choices, list) and card.get("choices_json"):
                try: choices = json.loads(card["choices_json"])
                except (TypeError, json.JSONDecodeError): choices = []
            choices = [str(x) for x in (choices or [])]
            if len(choices) != 4 or len(set(choices)) != 4 or str(card["answer"]) not in choices:
                continue
            card["choices_json"] = json.dumps(choices)
        valid.append(card)
    valid = valid[:5]
    # A learning unit needs varied retrieval, not a single recognition prompt.
    if len(valid) < 2 or not any(c.get("kind") in {"free", "application"} for c in valid):
        return []
    return valid


async def process_next_book() -> int:
    """Resume one queued/partial book, checkpointing each section independently."""
    from .db import engine
    with Session(engine) as session:
        # Partial books wait for an explicit retry. Claiming them automatically
        # would repeatedly select failed-only work and starve newer queued books.
        book = session.exec(select(Book).where(Book.status.in_(["queued", "processing"])).order_by(Book.created_at)).first()
        if not book:
            return 0
        book.status = "processing"; session.add(book); session.commit()
        sections = session.exec(select(IngestionSection).where(
            IngestionSection.book_id == book.id,
            IngestionSection.status.in_(["pending", "processing"]),
        ).order_by(IngestionSection.ordinal)).all()
        for section in sections:
            section.status = "processing"; section.attempt_count += 1; session.add(section); session.commit()
            try:
                data = await tutor.author_from_text(book.title, section.chapter, section.extracted_text)
                cards = _valid_cards(data.get("cards", []))
                if data.get("skip"):
                    section.status = "skipped"
                elif not cards:
                    raise ValueError("DGX returned no valid questions")
                else:
                    slug = re.sub(r"[^a-z0-9]+", "-", f"book-{book.id}-{section.ordinal}-{data.get('title', section.label)}".lower()).strip("-")[:100]
                    concept = session.exec(select(Concept).where(Concept.slug == slug)).first()
                    if not concept:
                        concept = Concept(slug=slug, track=book.title, title=str(data.get("title", section.label))[:200],
                            difficulty="core", tags="book", summary=str(data.get("summary", "")), lesson_md=str(data.get("lesson_md", "")),
                            source="book", book=book.title, chapter=section.chapter, sequence=section.ordinal + 1,
                            citation=section.citation, owner_user_id=book.user_id, book_id=book.id)
                        session.add(concept); session.flush()
                        for item in cards:
                            session.add(Card(concept_id=concept.id, kind=item.get("kind", "free"), prompt=str(item["prompt"]),
                                choices_json=item.get("choices_json", ""), answer=str(item["answer"]),
                                explanation=str(item.get("explanation", "")), source="book"))
                    section.concept_id = concept.id; section.status = "complete"; section.error_message = ""
                section.updated_at = datetime.utcnow(); session.add(section); session.commit()
            except Exception:
                session.rollback(); section = session.get(IngestionSection, section.id)
                section.status = "failed"; section.error_message = "DGX could not generate valid grounded material for this section."
                section.updated_at = datetime.utcnow(); session.add(section); session.commit()
                log.warning("book generation failed book_id=%s section=%s attempt=%s", book.id, section.ordinal, section.attempt_count)
        book = session.get(Book, book.id)
        states = session.exec(select(IngestionSection.status).where(IngestionSection.book_id == book.id)).all()
        book.completed_sections = sum(s in ("complete", "skipped") for s in states)
        book.status = "ready" if book.completed_sections == book.total_sections else "partial"
        book.updated_at = datetime.utcnow(); session.add(book); session.commit()
        return 1


def activate(session: Session, book: Book) -> int:
    if book.status not in ("ready", "partial"):
        raise HTTPException(409, "Book has no generated material ready")
    concepts = session.exec(select(Concept).where(Concept.book_id == book.id, Concept.owner_user_id == book.user_id)).all()
    added = 0
    for concept in concepts:
        if session.exec(select(Card).where(Card.concept_id == concept.id, Card.user_id == book.user_id)).first():
            continue
        templates = session.exec(select(Card).where(Card.concept_id == concept.id, Card.user_id == None)).all()  # noqa: E711
        for item in templates:
            session.add(Card(user_id=book.user_id, concept_id=concept.id, kind=item.kind, prompt=item.prompt,
                choices_json=item.choices_json, answer=item.answer, explanation=item.explanation, source="book")); added += 1
    book.activated = True; book.updated_at = datetime.utcnow(); session.add(book); session.commit()
    return added


def serialize_book(session: Session, book: Book, detail: bool = False) -> dict:
    states = session.exec(select(IngestionSection.status).where(IngestionSection.book_id == book.id)).all()
    generated = sum(state == "complete" for state in states)
    failed = sum(state == "failed" for state in states)
    remaining = sum(state in ("pending", "processing") for state in states)
    result = {"id": book.id, "title": book.title, "status": book.status, "page_count": book.page_count,
              "total_sections": book.total_sections, "completed_sections": book.completed_sections,
              "generated_lessons": generated, "failed_sections": failed, "remaining_sections": remaining,
              "activated": book.activated, "error_code": book.error_code, "error_message": book.error_message}
    if detail:
        rows = session.exec(select(IngestionSection).where(IngestionSection.book_id == book.id).order_by(IngestionSection.ordinal)).all()
        sections = []
        for s in rows:
            concept = session.get(Concept, s.concept_id) if s.concept_id else None
            sections.append({"id": s.id, "ordinal": s.ordinal, "chapter": s.chapter, "label": s.label,
                "page_start": s.page_start, "page_end": s.page_end, "citation": s.citation, "status": s.status,
                "error_message": s.error_message, "concept_id": s.concept_id,
                "topic_title": concept.title if concept else "", "summary": concept.summary if concept else ""})
        result["sections"] = sections
    return result


def retrieve(session: Session, book: Book, question: str, scope: str, section_id: int | None) -> list[IngestionSection]:
    rows = session.exec(select(IngestionSection).where(IngestionSection.book_id == book.id)).all()
    if section_id:
        target = next((s for s in rows if s.id == section_id), None)
        if target and scope == "topic": return [target]
        if target and scope == "chapter": return [s for s in rows if s.chapter == target.chapter][:5]
    terms = {w.lower() for w in re.findall(r"[A-Za-z0-9_-]{3,}", question)}
    ranked = sorted(((sum(s.extracted_text.lower().count(t) for t in terms), s) for s in rows), reverse=True, key=lambda x: x[0])
    return [s for score, s in ranked[:5] if score > 0]
