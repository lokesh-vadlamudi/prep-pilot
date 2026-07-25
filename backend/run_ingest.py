"""Background book-ingestion runner. Launch on the host that owns the live DB.

Usage: uv run python run_ingest.py
Reads BOOKS below, ingests each into the DB (grounded concepts + cards), logging
progress. Study order = order in BOOKS (seq_base ascending). Idempotent: re-running
skips sections already ingested (by slug), so it's safe to resume after a crash.
"""
from __future__ import annotations

import asyncio
import sys

from sqlmodel import Session

from app.db import engine, init_db
from app import ingest

HOME = __import__("os").path.expanduser("~")
BOOKS = [
    # (pdf_path, book_title, seq_base) — lower seq_base is studied first.
    (f"{HOME}/prep-pilot/books/Inference Engineering.pdf", "Inference Engineering", 1_000),
    (f"{HOME}/prep-pilot/books/SystemDesignInterview.pdf", "System Design Interview", 100_000),
]


def log(msg: str) -> None:
    print(msg, flush=True)


async def main() -> None:
    init_db()
    for path, book, seq_base in BOOKS:
        total = ingest.section_count(path, book)
        log(f"=== INGEST {book}: {total} sections ===")

        def on_progress(done, tot, section, _book=book):
            log(f"[{_book}] {done}/{tot}  {section[:60]}")

        with Session(engine) as session:
            added = await ingest.ingest_book(session, path, book, seq_base, on_progress=on_progress)
        log(f"=== DONE {book}: {added} concepts added ===")
    log("ALL_BOOKS_DONE")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:  # noqa: BLE001
        log(f"INGEST_ERROR: {e}")
        sys.exit(1)
