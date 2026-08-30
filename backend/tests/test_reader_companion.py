from __future__ import annotations

import json
import hashlib
import importlib
import io
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import fitz
from fastapi import FastAPI, HTTPException, Response, UploadFile
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import auth, book_service, db
from app.config import settings
from app.models import (
    Attempt, Book, BookBookmark, BookChatMessage, BookReadingProgress, Card, Concept,
    ConceptStatus, CourseEnrollment, IngestionSection, User,
)
from app.routers.book_routes import (
    BookmarkIn, ChatIn, ChatMessageOut, ChatOut, CitationOut, ProgressIn,
    activate_book, chat, chat_history, delete_book,
    delete_bookmark, get_book, list_books, put_bookmark, read_page, reader_state,
    retry_book, search_book, update_progress, upload_book,
)
from app.routers import book_routes


def memory_session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def add_user(session: Session, name: str) -> User:
    value = User(username=name, password_hash="x")
    session.add(value)
    session.commit()
    session.refresh(value)
    return value


def response_json(response: Response) -> dict:
    return json.loads(response.body)


class ReaderCompanionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.old_storage = settings.book_storage_dir
        settings.book_storage_dir = self.storage.name

    def tearDown(self):
        settings.book_storage_dir = self.old_storage
        self.storage.cleanup()

    def make_book(self, session: Session, owner: User, pages: list[str], suffix: str = "") -> Book:
        book = Book(
            user_id=owner.id,
            title=f"Reader{suffix}",
            original_filename="reader.pdf",
            storage_path="",
            sha256=f"reader-{owner.id}-{suffix}-{len(pages)}",
            page_count=len(pages),
            status="ready",
        )
        session.add(book)
        session.commit()
        session.refresh(book)
        owner_dir = Path(self.storage.name) / str(owner.id)
        owner_dir.mkdir(parents=True, exist_ok=True)
        path = owner_dir / f"{book.id}.pdf"
        document = fitz.open()
        for text in pages:
            page = document.new_page()
            page.insert_textbox((50, 50, 560, 790), text, fontsize=10)
        document.save(path)
        document.close()
        book.storage_path = str(path)
        session.add(book)
        session.commit()
        session.refresh(book)
        return book

    def test_progress_reader_state_and_bookmarks_have_exact_private_contract(self):
        with memory_session() as session:
            alice = add_user(session, "reader-state-alice")
            book = self.make_book(session, alice, ["one", "two", "three"])
            response = Response()

            initial = reader_state(book.id, alice, session, response)

            self.assertEqual(initial, {
                "book_id": book.id, "page": 1, "progress_updated_at": None, "bookmarks": [],
            })
            self.assertEqual(response.headers["cache-control"], "private, no-store")

            progress_response = Response()
            progress = update_progress(book.id, ProgressIn(page=2), alice, session, progress_response)
            self.assertEqual((progress["book_id"], progress["page"]), (book.id, 2))
            self.assertIsInstance(progress["updated_at"], str)
            self.assertEqual(progress_response.headers["cache-control"], "private, no-store")
            self.assertEqual(update_progress(
                book.id, ProgressIn(page=2), alice, session, Response(),
            )["page"], 2)

            saved = put_bookmark(
                book.id, 2, BookmarkIn(note="  remember this  "), alice, session, Response(),
            )
            self.assertEqual((saved["page"], saved["note"]), (2, "remember this"))
            updated = put_bookmark(book.id, 2, BookmarkIn(note="  "), alice, session, Response())
            self.assertIsNone(updated["note"])
            maximum = "x" * 2000
            saved_maximum = put_bookmark(
                book.id, 3, BookmarkIn(note=maximum), alice, session, Response(),
            )
            self.assertEqual(saved_maximum["note"], maximum)
            state = reader_state(book.id, alice, session, Response())
            self.assertEqual(state["page"], 2)
            self.assertEqual(len(state["bookmarks"]), 2)
            self.assertEqual(delete_bookmark(book.id, 2, alice, session).status_code, 204)
            self.assertEqual(delete_bookmark(book.id, 2, alice, session).status_code, 204)

    def test_progress_and_bookmark_validation_and_owner_isolation(self):
        with memory_session() as session:
            alice = add_user(session, "state-owner")
            bob = add_user(session, "state-other")
            book = self.make_book(session, alice, ["one", "two"])

            for invalid in (True, 1.0, "1"):
                with self.subTest(strict_progress=invalid), self.assertRaises(ValidationError):
                    ProgressIn(page=invalid)
                with self.subTest(strict_chat=invalid), self.assertRaises(ValidationError):
                    ChatIn(question="q", scope="page", page=invalid)
                for action in (
                    lambda value=invalid: put_bookmark(
                        book.id, value, BookmarkIn(note=None), alice, session, Response(),
                    ),
                    lambda value=invalid: delete_bookmark(book.id, value, alice, session),
                ):
                    with self.subTest(strict_bookmark=invalid):
                        with self.assertRaises(HTTPException) as caught:
                            action()
                        self.assertEqual(caught.exception.status_code, 422)

            for page in (0, 3):
                with self.assertRaises(HTTPException) as caught:
                    update_progress(book.id, ProgressIn(page=page), alice, session, Response())
                self.assertEqual(caught.exception.status_code, 422)
            with self.assertRaises(ValidationError):
                BookmarkIn(note="x" * 2001)
            for action in (
                lambda: reader_state(book.id, bob, session, Response()),
                lambda: update_progress(book.id, ProgressIn(page=1), bob, session, Response()),
                lambda: put_bookmark(book.id, 1, BookmarkIn(note=None), bob, session, Response()),
                lambda: delete_bookmark(book.id, 1, bob, session),
                lambda: search_book(book.id, "one", bob, session, Response()),
            ):
                with self.assertRaises(HTTPException) as caught:
                    action()
                self.assertEqual(caught.exception.status_code, 404)
            self.assertEqual(session.exec(select(BookReadingProgress)).all(), [])
            self.assertEqual(session.exec(select(BookBookmark)).all(), [])

    def test_literal_search_normalizes_unicode_whitespace_and_reports_truncation(self):
        with memory_session() as session:
            alice = add_user(session, "search-alice")
            book = self.make_book(session, alice, [
                "Alpha\n beta and a+b are exact on this page.",
                "No matching phrase here.",
                "ALPHA   BETA repeats alpha beta.",
            ])

            result = search_book(book.id, "  alpha\t beta  ", alice, session, Response())

            self.assertEqual(result["query"], "alpha beta")
            self.assertEqual([row["page"] for row in result["results"]], [1, 3])
            self.assertEqual(result["results"][1]["match_count"], 2)
            self.assertFalse(result["truncated"])
            literal = search_book(book.id, "a+b", alice, session, Response())
            self.assertEqual([row["page"] for row in literal["results"]], [1])
            empty = search_book(book.id, "absent", alice, session, Response())
            self.assertEqual(empty, {"query": "absent", "results": [], "truncated": False})

    def test_search_rejects_invalid_normalized_query_before_opening_pdf(self):
        with memory_session() as session:
            alice = add_user(session, "search-validation")
            book = self.make_book(session, alice, ["some text"])
            for query in ("", " \t ", "ab", "x" * 201):
                with patch("app.book_service.source_pdf_path") as resolver:
                    response = search_book(book.id, query, alice, session, Response())
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response_json(response)["error"]["code"], "invalid_search_query")
                resolver.assert_not_called()

    def test_search_caps_results_and_marks_additional_matches(self):
        with memory_session() as session:
            alice = add_user(session, "search-cap")
            book = self.make_book(session, alice, ["repeat phrase"] * 501)

            result = search_book(book.id, "repeat", alice, session, Response())

            self.assertEqual(len(result["results"]), 50)
            self.assertEqual((result["results"][0]["page"], result["results"][-1]["page"]),
                             (1, 50))
            self.assertTrue(result["truncated"])

    def test_canonical_page_path_cache_and_cross_owner_path_rejection(self):
        with memory_session() as session:
            alice = add_user(session, "page-owner")
            bob = add_user(session, "page-other")
            book = self.make_book(session, alice, ["page one", "page two"])

            rendered = read_page(book.id, 2, alice, session)
            self.assertTrue(rendered.body.startswith(b"\x89PNG"))
            self.assertEqual(rendered.headers["cache-control"], "private, no-store")
            with self.assertRaises(HTTPException) as caught:
                read_page(book.id, 1, bob, session)
            self.assertEqual(caught.exception.status_code, 404)

            other = self.make_book(session, bob, ["bob secret"], "bob")
            book.storage_path = other.storage_path
            session.add(book)
            session.commit()
            with self.assertRaises(HTTPException) as caught:
                read_page(book.id, 1, alice, session)
            self.assertEqual(caught.exception.status_code, 404)

    def test_private_pdf_http_response_matrix_is_no_store(self):
        with memory_session() as session:
            alice = add_user(session, "http-private")
            book = self.make_book(session, alice, ["Private searchable page text."])
            app = FastAPI()
            app.include_router(book_routes.router)

            def override_session():
                yield session

            app.dependency_overrides[book_routes.get_session] = override_session
            app.dependency_overrides[auth.current_user] = lambda: alice
            client = TestClient(app)
            requests = [
                lambda: client.get(f"/api/books/{book.id}"),
                lambda: client.get(f"/api/books/{book.id}/pages/1"),
                lambda: client.get(f"/api/books/{book.id}/reader-state"),
                lambda: client.put(f"/api/books/{book.id}/progress", json={"page": 1}),
                lambda: client.put(f"/api/books/{book.id}/bookmarks/1", json={"note": "private"}),
                lambda: client.get(f"/api/books/{book.id}/search", params={"q": "searchable"}),
                lambda: client.get(f"/api/books/{book.id}/search", params={"q": "ab"}),
                lambda: client.get(f"/api/books/{book.id}/search"),
            ]
            for request in requests:
                result = request()
                self.assertIn(result.status_code, {200, 422}, result.text)
                self.assertEqual(result.headers.get("cache-control"), "private, no-store")

    def test_page_context_boundaries_are_deterministic(self):
        self.assertEqual(book_service.validate_page_context("x" * 12_000), "x" * 12_000)
        self.assertEqual(book_service.estimated_tokens("é" * 6_000), math.ceil(12_000 / 3))
        for text in ("x" * 12_001, "é" * 6_001):
            with self.assertRaises(book_service.ReaderContextError) as caught:
                book_service.validate_page_context(text, page=4)
            self.assertEqual(caught.exception.status_code, 422)
            self.assertEqual(caught.exception.payload["error"]["code"], "page_context_too_large")
            self.assertEqual(caught.exception.payload["error"]["page"], 4)

    def test_page_chat_adjacent_fallback_stays_bounded_when_no_fallback_is_needed_or_readable(self):
        with memory_session() as session:
            alice = add_user(session, "chat-adjacent-bounds")
            defined = self.make_book(session, alice, ["Disaggregation is defined on this page."])
            self.assertEqual(
                book_service.page_chat_sources(defined, 1, "What is disaggregation?"),
                [(1, "Disaggregation is defined on this page.")],
            )

            unreadable_neighbor = self.make_book(session, alice, ["Visible current text.", ""])
            self.assertEqual(
                book_service.page_chat_sources(unreadable_neighbor, 1, "What is a missing concept?"),
                [(1, "Visible current text.")],
            )

    def test_chat_scope_is_closed_and_citations_are_defensively_decoded(self):
        typed = ChatOut(answer="grounded", citations=[CitationOut(
            section_id=None, citation="Reader p1", page_start=1, page_end=1,
        )])
        history_row = ChatMessageOut(role="assistant", content=typed.answer, citations=typed.citations)
        self.assertEqual(history_row.citations[0].page_start, 1)
        with self.assertRaises(ValidationError):
            CitationOut(section_id=None, citation="bad", page_start=True, page_end=1)

        with self.assertRaises(ValidationError):
            ChatIn(question="question", scope="invalid")
        with self.assertRaises(ValidationError):
            ChatIn(question="question", scope="page")
        with self.assertRaises(ValidationError):
            ChatIn(question="question", scope="chapter")
        with self.assertRaises(ValidationError):
            ChatIn(question="question", scope="page", page=1, section_id=2)

        with memory_session() as session:
            alice = add_user(session, "citation-alice")
            book = self.make_book(session, alice, ["Exact visible fact."])
            section = IngestionSection(
                book_id=book.id, ordinal=0, chapter="One", label="One", page_start=1,
                page_end=1, citation="Reader p1", extracted_text="Exact visible fact.", content_hash="x",
            )
            session.add(section)
            session.commit()
            session.refresh(section)
            rows = [
                BookChatMessage(book_id=book.id, user_id=alice.id, role="assistant", content="bad", citations_json="not-json"),
                BookChatMessage(book_id=book.id, user_id=alice.id, role="assistant", content="range", citations_json=json.dumps([{
                    "section_id": section.id, "citation": "bad", "page_start": 0, "page_end": 9,
                }])),
                BookChatMessage(book_id=book.id, user_id=alice.id, role="assistant", content="good", citations_json=json.dumps([{
                    "section_id": section.id, "citation": "Reader p1", "page_start": 1, "page_end": 1,
                }])),
                BookChatMessage(book_id=book.id, user_id=alice.id, role="assistant", content="boolean", citations_json=json.dumps([{
                    "section_id": section.id, "citation": "not a page", "page_start": True, "page_end": True,
                }])),
                BookChatMessage(book_id=book.id, user_id=alice.id, role="assistant", content="section-type", citations_json=json.dumps([{
                    "section_id": "not-an-id", "citation": "Reader p1", "page_start": 1, "page_end": 1,
                }])),
            ]
            session.add_all(rows)
            session.commit()

            history = chat_history(book.id, alice, session, Response())

            self.assertEqual(history[0]["citations"], [])
            self.assertEqual(history[1]["citations"], [])
            self.assertEqual(history[2]["citations"][0]["page_start"], 1)
            self.assertEqual(history[3]["citations"], [])
            self.assertEqual(history[4]["citations"], [])

    async def test_generated_citations_are_validated_before_response_and_persistence(self):
        with memory_session() as session:
            alice = add_user(session, "citation-persist")
            book = self.make_book(session, alice, ["Only page one exists."])
            invalid = type("Excerpt", (), {
                "id": None, "citation": "invalid", "page_start": True,
                "page_end": True, "extracted_text": "unsafe bounds",
            })()
            with patch("app.routers.book_routes.book_service.retrieve", return_value=[invalid]), patch(
                "app.routers.book_routes.llm.chat", new=AsyncMock(return_value="answer"),
            ):
                result = await chat(book.id, ChatIn(question="q"), alice, session, Response())

            self.assertEqual(result["citations"], [])
            persisted = session.exec(select(BookChatMessage).where(
                BookChatMessage.book_id == book.id, BookChatMessage.role == "assistant",
            )).one()
            self.assertEqual(json.loads(persisted.citations_json), [])

    async def test_page_chat_uses_full_bounded_page_and_sets_no_store(self):
        with memory_session() as session:
            alice = add_user(session, "chat-page")
            book = self.make_book(session, alice, ["Only this exact visible fact."])
            response = Response()
            with patch("app.routers.book_routes.llm.chat", new=AsyncMock(return_value="Grounded [Source 1, page 1]")) as model:
                result = await chat(
                    book.id, ChatIn(question="What is here?", scope="page", page=1),
                    alice, session, response,
                )
            prompt = model.await_args.args[0][1]["content"]
            self.assertIn("Only this exact visible fact", prompt)
            self.assertEqual(result["citations"][0]["page_start"], 1)
            self.assertEqual(response.headers["cache-control"], "private, no-store")

    async def test_page_chat_uses_matching_adjacent_text_for_a_visual_term_and_only_cites_used_sources(self):
        with memory_session() as session:
            alice = add_user(session, "chat-visual-term")
            book = self.make_book(session, alice, [
                "The diagram summarizes runtime optimizations, including several labels.",
                "Disaggregation separates prefill and decode onto independently scaling workers.",
            ])
            with patch(
                "app.routers.book_routes.llm.chat",
                new=AsyncMock(return_value="It lets the two jobs scale separately. [Source 2, page 2]"),
            ) as model:
                result = await chat(
                    book.id,
                    ChatIn(question="What is disaggregation? Explain in layman terms.", scope="page", page=1),
                    alice,
                    session,
                    Response(),
                )

            prompt = model.await_args.args[0][1]["content"]
            self.assertIn("SOURCE 1: Reader, page 1", prompt)
            self.assertIn("SOURCE 2: Reader, page 2", prompt)
            self.assertEqual(result["citations"], [{
                "section_id": None, "citation": "Reader, page 2", "page_start": 2, "page_end": 2,
            }])

    async def test_chat_does_not_attach_a_source_the_answer_did_not_cite(self):
        with memory_session() as session:
            alice = add_user(session, "chat-unused-citation")
            book = self.make_book(session, alice, ["The available text does not define the requested term."])
            with patch(
                "app.routers.book_routes.llm.chat",
                new=AsyncMock(return_value="The provided excerpt does not contain that definition."),
            ):
                result = await chat(
                    book.id, ChatIn(question="What is disaggregation?", scope="page", page=1),
                    alice, session, Response(),
                )

            self.assertEqual(result["citations"], [])

    def test_delete_removes_reader_children_and_rolls_back_on_unlink_failure(self):
        with memory_session() as session:
            alice = add_user(session, "delete-alice")
            book = self.make_book(session, alice, ["private"])
            update_progress(book.id, ProgressIn(page=1), alice, session, Response())
            put_bookmark(book.id, 1, BookmarkIn(note="note"), alice, session, Response())
            path = Path(book.storage_path)
            owner_dir = path.parent
            owner_dir.chmod(0o500)
            try:
                with self.assertRaises(HTTPException) as caught:
                    delete_book(book.id, alice, session)
                self.assertEqual(caught.exception.status_code, 503)
                self.assertIsNotNone(session.get(Book, book.id))
                self.assertTrue(path.exists())
            finally:
                owner_dir.chmod(0o700)

            delete_book(book.id, alice, session)
            self.assertIsNone(session.get(Book, book.id))
            self.assertEqual(session.exec(select(BookReadingProgress)).all(), [])
            self.assertEqual(session.exec(select(BookBookmark)).all(), [])
            self.assertFalse(path.exists())

    def test_path_page_render_and_search_fail_closed_edges(self):
        with memory_session() as session:
            alice = add_user(session, "reader-edge-path")
            book = self.make_book(session, alice, [""])
            canonical = Path(book.storage_path)

            with self.assertRaisesRegex(HTTPException, "Page not found"):
                book_service.page_text(book, 0)
            with self.assertRaises(book_service.ReaderContextError):
                book_service.page_text(book, 1)
            with patch("app.book_service.source_pdf_path", side_effect=HTTPException(404, "missing")):
                with self.assertRaises(HTTPException):
                    book_service.page_text(book, 1)
                with self.assertRaises(HTTPException):
                    book_service.search_pdf(book, "query")
            with patch("app.book_service.source_pdf_path", return_value=canonical), patch(
                "app.book_service.fitz.open", side_effect=ValueError("corrupt"),
            ):
                for action in (lambda: book_service.page_text(book, 1),
                               lambda: book_service.render_page(book, 1),
                               lambda: book_service.search_pdf(book, "query")):
                    with self.assertRaisesRegex(HTTPException, "could not"):
                        action()

            canonical.unlink()
            canonical.mkdir()
            with self.assertRaisesRegex(HTTPException, "unavailable"):
                book_service.source_pdf_path(book)
            with self.assertRaisesRegex(HTTPException, "unavailable"):
                book_service.deletion_pdf_path(book)
            canonical.rmdir()
            book.storage_path = str(Path(self.storage.name) / "wrong.pdf")
            with self.assertRaisesRegex(HTTPException, "unavailable"):
                book_service.deletion_pdf_path(book)
            canonical.parent.rmdir()
            book.storage_path = str(canonical)
            with self.assertRaisesRegex(HTTPException, "unavailable"):
                book_service.deletion_pdf_path(book)

    async def test_upload_rejects_size_duplicate_encryption_page_text_and_malformed_edges(self):
        class FakePage:
            def __init__(self, text: str): self.text = text
            def get_text(self): return self.text

        class FakeDocument:
            def __init__(self, *, password=False, pages=1, text="enough " * 20):
                self.needs_pass = password; self.page_count = pages; self.text = text; self.metadata = {}
            def __getitem__(self, _index): return FakePage(self.text)
            def close(self): pass

        with memory_session() as session:
            alice = add_user(session, "upload-edge")
            old_limit = settings.max_book_bytes
            settings.max_book_bytes = 5
            try:
                with self.assertRaisesRegex(HTTPException, "size limit"):
                    await book_service.save_upload(session, alice, UploadFile(filename="large.pdf", file=io.BytesIO(b"%PDF-large")))
            finally:
                settings.max_book_bytes = old_limit

            payload = b"%PDF-payload"
            session.add(Book(user_id=alice.id, title="Existing", original_filename="e.pdf",
                             storage_path="x", sha256=hashlib.sha256(payload).hexdigest()))
            session.commit()
            with self.assertRaisesRegex(HTTPException, "already"):
                await book_service.save_upload(session, alice, UploadFile(filename="duplicate.pdf", file=io.BytesIO(payload)))

            cases = [
                (FakeDocument(password=True), "Encrypted"),
                (FakeDocument(pages=0), "page count"),
                (FakeDocument(text=""), "too little"),
            ]
            for document, message in cases:
                with self.subTest(message=message), patch("app.book_service.fitz.open", return_value=document):
                    with self.assertRaisesRegex(HTTPException, message):
                        await book_service.save_upload(session, alice, UploadFile(filename=f"{message}.pdf", file=io.BytesIO(b"%PDF-unique-" + message.encode())))
            with patch("app.book_service.fitz.open", side_effect=ValueError("bad")):
                with self.assertRaisesRegex(HTTPException, "malformed"):
                    await book_service.save_upload(session, alice, UploadFile(filename="bad.pdf", file=io.BytesIO(b"%PDF-malformed")))

    def test_extraction_card_serialization_and_retrieval_edges(self):
        with memory_session() as session:
            alice = add_user(session, "service-edge")
            book = self.make_book(session, alice, ["edge"])
            with patch("app.ingest.sections_for_book", return_value=[]):
                book_service._extract_sections(session, book)
            self.assertEqual(book.status, "failed")

            cards = book_service._valid_cards([
                None,
                {"kind": "mcq", "prompt": "Q", "answer": "A", "choices_json": "not-json"},
                {"kind": "free", "prompt": "Explain", "answer": "Because"},
            ])
            self.assertEqual(cards, [])

            concept = Concept(slug="edge-concept", track=book.title, title="Edge", summary="Summary",
                              owner_user_id=alice.id, book_id=book.id)
            session.add(concept); session.commit(); session.refresh(concept)
            sections = [
                IngestionSection(book_id=book.id, ordinal=index, chapter="One" if index < 2 else "Two",
                                 label=f"S{index}", page_start=1, page_end=1, citation=f"p{index}",
                                 extracted_text=f"retrieval term {index}", content_hash=f"h{index}",
                                 concept_id=concept.id if index == 0 else None)
                for index in range(3)
            ]
            session.add_all(sections); session.commit()
            for section in sections: session.refresh(section)
            self.assertEqual(book_service.serialize_book(session, book, alice.id, True)["sections"][0]["topic_title"], "Edge")
            self.assertEqual(book_service.retrieve(session, book, "unused", "topic", sections[0].id), [sections[0]])
            self.assertEqual(len(book_service.retrieve(session, book, "unused", "chapter", sections[0].id)), 2)
            self.assertEqual(len(book_service.retrieve(session, book, "retrieval", "book", 99999)), 3)

    async def test_route_upload_activation_retry_chat_and_decode_edges(self):
        with memory_session() as session:
            alice = add_user(session, "route-edge")
            invalid = UploadFile(filename="bad.txt", file=io.BytesIO(b"bad"), headers={"content-type": "text/plain"})
            with self.assertRaisesRegex(HTTPException, "Only PDF"):
                await upload_book(invalid, alice, session, Response())

            book = self.make_book(session, alice, ["route exact text"])
            book.status = "processing"; session.add(book); session.commit()
            active_upload = UploadFile(filename="x.pdf", file=io.BytesIO(b"%PDF-x"), headers={"content-type": "application/pdf"})
            with self.assertRaisesRegex(HTTPException, "current import"):
                await upload_book(active_upload, alice, session, Response())
            with self.assertRaisesRegex(HTTPException, "generated material"):
                activate_book(book.id, alice, session)

            book.status = "ready"; session.add(book); session.commit()
            with patch("app.routers.book_routes.book_service.activate", return_value=2):
                self.assertEqual(activate_book(book.id, alice, session)["cards_added"], 2)
            self.assertEqual(list_books(alice, session, Response())[0]["id"], book.id)

            failed = IngestionSection(book_id=book.id, ordinal=0, chapter="One", label="One",
                                      page_start=1, page_end=1, citation="p1", extracted_text="route exact text",
                                      content_hash="route-edge", status="failed")
            session.add(failed); session.commit(); session.refresh(failed)
            self.assertTrue(retry_book(book.id, alice, session)["queued"])
            with self.assertRaises(ValidationError):
                ChatIn(question="q", scope="book", page=1)
            for question in (" ", "x" * 2001):
                with self.assertRaisesRegex(HTTPException, "empty or too long"):
                    await chat(book.id, ChatIn(question=question), alice, session, Response())

            with patch("app.routers.book_routes.book_service.page_text", side_effect=book_service.ReaderContextError(409, {"error": {"code": "empty"}})):
                self.assertEqual((await chat(book.id, ChatIn(question="q", scope="page", page=1), alice, session, Response())).status_code, 409)
            with self.assertRaisesRegex(HTTPException, "section"):
                await chat(book.id, ChatIn(question="q", scope="chapter", section_id=99999), alice, session, Response())
            with patch("app.routers.book_routes.book_service.retrieve", return_value=[]):
                with self.assertRaisesRegex(HTTPException, "No extracted"):
                    await chat(book.id, ChatIn(question="q"), alice, session, Response())
            with patch("app.routers.book_routes.book_service.retrieve", return_value=[failed]), patch(
                "app.routers.book_routes.llm.chat", new=AsyncMock(return_value="answer [Source 1, page 1]"),
            ):
                result = await chat(book.id, ChatIn(question="q", scope="chapter", section_id=failed.id), alice, session, Response())
            self.assertEqual(result["citations"][0]["section_id"], failed.id)

            session.add_all([
                BookChatMessage(book_id=book.id, user_id=alice.id, role="assistant", content="non-list", citations_json="{}"),
                BookChatMessage(book_id=book.id, user_id=alice.id, role="assistant", content="wrong-type", citations_json="[1]"),
                BookChatMessage(book_id=book.id, user_id=alice.id, role="assistant", content="wrong-section", citations_json=json.dumps([{"section_id": 99999, "citation": "p1", "page_start": 1, "page_end": 1}])),
            ])
            session.commit()
            decoded = chat_history(book.id, alice, session, Response())[-3:]
            self.assertEqual([item["citations"] for item in decoded], [[], [], []])


class ReaderMigrationTests(unittest.TestCase):
    def test_reader_and_course_schema_validation_fail_closed_edges(self):
        class FakeConnection:
            def __init__(self, *, missing_column=False, missing_index=False, course_check=True):
                self.missing_column = missing_column
                self.missing_index = missing_index
                self.course_check = course_check

            def exec_driver_sql(self, query, *_args):
                if "sqlite_master" in query:
                    sql = "ck_course_link_match_kind owned_exact legacy_exact explicit_supplement_alias" if self.course_check else "CREATE TABLE coursecontentlink"
                    return type("Rows", (), {"fetchone": lambda self: (sql,)})()
                if "table_info" in query:
                    table = query.removeprefix("PRAGMA table_info(").removesuffix(")")
                    schema = {**db._COURSE_SCHEMA, **db._READER_SCHEMA}
                    required = list(schema[table][0])
                    if self.missing_column: required.pop()
                    return [(0, name) for name in required]
                if "index_list" in query:
                    rows = []
                    table = query.removeprefix("PRAGMA index_list(").removesuffix(")")
                    if not self.missing_index: rows = [(0, f"uq_{table}", 1)]
                    return type("Rows", (list,), {"fetchall": lambda self: list(self)})(rows)
                if "index_info" in query:
                    table = query.split("uq_", 1)[1].removesuffix(")")
                    schema = {**db._COURSE_SCHEMA, **db._READER_SCHEMA}
                    return [(0, index, name) for index, name in enumerate(schema[table][1])]
                raise AssertionError(query)

        with self.assertRaisesRegex(RuntimeError, "missing"):
            db._validate_reader_schema(FakeConnection(missing_column=True))
        with self.assertRaisesRegex(RuntimeError, "unique index"):
            db._validate_reader_schema(FakeConnection(missing_index=True))
        with self.assertRaisesRegex(RuntimeError, "match_kind"):
            db._validate_course_schema(FakeConnection(course_check=False))

    def test_main_no_frontend_fallback_branch(self):
        import app.main as main_module

        with patch.object(Path, "exists", return_value=False):
            fallback = importlib.reload(main_module)
            self.assertIn("Frontend not built", fallback.no_frontend()["message"])
        importlib.reload(main_module)

    def test_reader_schema_is_idempotent_and_preserves_course_data(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine(f"sqlite:///{Path(directory) / 'reader.db'}")
            with patch("app.db.engine", engine):
                db.init_db()
                with Session(engine) as session:
                    owner = add_user(session, "migration-owner")
                    session.add(CourseEnrollment(
                        user_id=owner.id, course_key="inference-engineering", catalog_version="v1",
                    ))
                    book = Book(
                        user_id=owner.id, title="Reader", original_filename="r.pdf",
                        storage_path="x", sha256="migration-reader", page_count=3,
                    )
                    session.add(book); session.commit(); session.refresh(book)
                    session.add(BookReadingProgress(user_id=owner.id, book_id=book.id, page_number=2))
                    session.commit()

                db.init_db()

                names = set(inspect(engine).get_table_names())
                self.assertIn("bookreadingprogress", names)
                self.assertIn("bookbookmark", names)
                with Session(engine) as session:
                    self.assertEqual(session.exec(select(CourseEnrollment)).one().course_key,
                                     "inference-engineering")
                    self.assertEqual(session.exec(select(BookReadingProgress)).one().page_number, 2)


if __name__ == "__main__":
    unittest.main()
