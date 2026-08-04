from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import stat

import fitz
from fastapi import HTTPException, Response, UploadFile
from starlette.requests import Request
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app import auth, book_service, scheduler, service
from app.config import settings
from app.models import Book, Card, Concept, IngestionSection, User
from app.routers.study_routes import topic
from app.routers.book_routes import retry_book


def memory_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def user(session: Session, name: str) -> User:
    value = User(username=name, password_hash="x")
    session.add(value); session.commit(); session.refresh(value)
    return value


class OwnershipTests(unittest.TestCase):
    def test_owned_concepts_never_sync_to_another_user(self):
        with memory_session() as session:
            alice, bob = user(session, "alice"), user(session, "bob")
            private = Concept(slug="alice-private", track="Private", title="Secret", source="book", owner_user_id=alice.id)
            public = Concept(slug="public", track="DSA", title="Public")
            session.add(private); session.add(public); session.commit(); session.refresh(private); session.refresh(public)
            session.add(Card(concept_id=private.id, prompt="private template"))
            session.add(Card(concept_id=public.id, prompt="public template")); session.commit()

            service.sync_user_cards(session, bob)

            bob_concepts = session.exec(select(Card.concept_id).where(Card.user_id == bob.id)).all()
            self.assertIn(public.id, bob_concepts)
            self.assertNotIn(private.id, bob_concepts)

    def test_book_lookup_is_strictly_owner_scoped(self):
        with memory_session() as session:
            alice, bob = user(session, "alice"), user(session, "bob")
            book = Book(user_id=alice.id, title="Private", original_filename="private.pdf", storage_path="x", sha256="abc")
            session.add(book); session.commit(); session.refresh(book)
            with self.assertRaises(HTTPException) as caught:
                book_service.owned_book(session, bob.id, book.id)
            self.assertEqual(caught.exception.status_code, 404)

    def test_topic_query_and_progress_hide_other_users_private_concepts(self):
        with memory_session() as session:
            alice, bob = user(session, "alice"), user(session, "bob")
            public = Concept(slug="public-progress", track="DSA", title="Public")
            private = Concept(slug="private-progress", track="Private", title="Private", owner_user_id=alice.id)
            session.add(public); session.add(private); session.commit(); session.refresh(private)
            self.assertEqual(service.progress_stats(session, bob.id)["total_concepts"], 1)
            with self.assertRaises(HTTPException) as caught:
                topic(private.id, bob, session)
            self.assertEqual(caught.exception.status_code, 404)

    def test_weak_lexical_evidence_is_refused(self):
        with memory_session() as session:
            alice = user(session, "alice")
            book = Book(user_id=alice.id, title="Networks", original_filename="n.pdf", storage_path="x", sha256="abc")
            session.add(book); session.commit(); session.refresh(book)
            session.add(IngestionSection(book_id=book.id, ordinal=0, chapter="TCP", label="TCP", page_start=1,
                page_end=2, citation="Networks p1-2", extracted_text="Congestion windows control sending rate.", content_hash="x")); session.commit()
            self.assertEqual(book_service.retrieve(session, book, "photosynthesis chlorophyll", "book", None), [])
            self.assertEqual(len(book_service.retrieve(session, book, "congestion window", "book", None)), 1)


class UploadValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_pdf_is_stored_under_generated_owner_path(self):
        doc = fitz.open(); page = doc.new_page(); page.insert_textbox((50, 50, 560, 790), "Extractable technical content about systems and networks. " * 80, fontsize=8)
        payload = doc.tobytes(); doc.close()
        with tempfile.TemporaryDirectory() as directory, memory_session() as session:
            old = settings.book_storage_dir; settings.book_storage_dir = directory
            try:
                alice = user(session, "alice")
                upload = UploadFile(filename="../../unsafe name.pdf", file=io.BytesIO(payload))
                book = await book_service.save_upload(session, alice, upload)
                stored = Path(book.storage_path)
                self.assertTrue(stored.is_file())
                self.assertEqual(stored.parent.name, str(alice.id))
                self.assertEqual(stored.name, f"{book.id}.pdf")
                self.assertNotIn("unsafe", book.storage_path)
                self.assertEqual(stat.S_IMODE(Path(directory).stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(stored.parent.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(stored.stat().st_mode), 0o600)
                self.assertGreater(book.total_sections, 0)
                self.assertEqual(book.status, "queued")
            finally:
                settings.book_storage_dir = old

    async def test_non_pdf_signature_is_rejected_and_not_persisted(self):
        with tempfile.TemporaryDirectory() as directory, memory_session() as session:
            old = settings.book_storage_dir; settings.book_storage_dir = directory
            try:
                alice = user(session, "alice")
                upload = UploadFile(filename="fake.pdf", file=io.BytesIO(b"not a pdf"))
                with self.assertRaises(HTTPException) as caught:
                    await book_service.save_upload(session, alice, upload)
                self.assertEqual(caught.exception.status_code, 400)
                self.assertEqual(session.exec(select(Book)).all(), [])
            finally:
                settings.book_storage_dir = old


class GeneratedCardValidationTests(unittest.TestCase):
    def test_invalid_mcq_is_rejected(self):
        cards = book_service._valid_cards([{"kind": "mcq", "prompt": "Q", "choices": ["A", "A", "B", "C"], "answer": "A"}])
        self.assertEqual(cards, [])

    def test_valid_mcq_and_free_response_are_kept(self):
        cards = book_service._valid_cards([
            {"kind": "mcq", "prompt": "Q", "choices": ["A", "B", "C", "D"], "answer": "B"},
            {"kind": "free", "prompt": "Explain", "answer": "Because"},
        ])
        self.assertEqual(len(cards), 2)

    def test_single_or_recognition_only_card_set_is_rejected(self):
        self.assertEqual(book_service._valid_cards([{"kind": "free", "prompt": "Explain", "answer": "Because"}]), [])


class ActivationTests(unittest.TestCase):
    def test_direct_activation_rejects_books_without_generated_material(self):
        for status in ("queued", "extracting", "processing"):
            with self.subTest(status=status), memory_session() as session:
                alice = user(session, "alice")
                book = Book(user_id=alice.id, title="Systems", original_filename="s.pdf", storage_path="x",
                            sha256=f"sha-{status}", status=status)
                session.add(book); session.commit(); session.refresh(book)

                with self.assertRaises(HTTPException) as caught:
                    book_service.activate(session, book)

                self.assertEqual(caught.exception.status_code, 409)
                self.assertFalse(session.get(Book, book.id).activated)
                self.assertEqual(session.exec(select(Card).where(Card.user_id == alice.id)).all(), [])

    def test_direct_activation_is_idempotent_for_ready_and_partial_books(self):
        for status in ("ready", "partial"):
            with self.subTest(status=status), memory_session() as session:
                alice = user(session, "alice")
                book = Book(user_id=alice.id, title="Systems", original_filename="s.pdf", storage_path="x",
                            sha256=f"sha-{status}", status=status)
                session.add(book); session.commit(); session.refresh(book)
                concept = Concept(slug=f"book-{status}", track="Systems", title="Queues", source="book",
                                  owner_user_id=alice.id, book_id=book.id)
                session.add(concept); session.commit(); session.refresh(concept)
                session.add(Card(concept_id=concept.id, kind="free", prompt="Explain", answer="Answer", source="book"))
                session.commit()

                self.assertEqual(book_service.activate(session, book), 1)
                self.assertEqual(book_service.activate(session, book), 0)
                self.assertTrue(session.get(Book, book.id).activated)
                self.assertEqual(len(session.exec(select(Card).where(Card.user_id == alice.id)).all()), 1)


class PersistentWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_is_checkpointed_and_activation_is_owner_only(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            alice = user(session, "alice")
            book = Book(user_id=alice.id, title="Systems", original_filename="s.pdf", storage_path="x",
                        sha256="abc", status="queued", total_sections=1)
            session.add(book); session.commit(); session.refresh(book)
            session.add(IngestionSection(book_id=book.id, ordinal=0, chapter="Queues", label="Queues",
                page_start=1, page_end=3, citation="Systems p1-3", extracted_text="queue " * 200, content_hash="x")); session.commit()
            user_id, book_id = alice.id, book.id
        authored = {"title": "Queue semantics", "summary": "Delivery trade-offs", "lesson_md": "Lesson",
                    "cards": [{"kind": "free", "prompt": "Explain delivery", "answer": "At least once"},
                              {"kind": "mcq", "prompt": "Which mode?", "choices": ["A", "B", "C", "D"], "answer": "A"}]}
        with patch("app.db.engine", engine), patch("app.book_service.tutor.author_from_text", new=AsyncMock(return_value=authored)) as author:
            self.assertEqual(await book_service.process_next_book(), 1)
            self.assertEqual(await book_service.process_next_book(), 0)
        author.assert_awaited_once()
        with Session(engine) as session:
            book = session.get(Book, book_id)
            concepts = session.exec(select(Concept).where(Concept.book_id == book_id)).all()
            self.assertEqual(len(concepts), 1)
            self.assertEqual(book.status, "ready")
            self.assertEqual(session.exec(select(Card).where(Card.user_id == user_id)).all(), [])
            self.assertEqual(book_service.activate(session, book), 2)
            self.assertEqual(book_service.activate(session, book), 0)
            self.assertEqual(len(session.exec(select(Card).where(Card.user_id == user_id)).all()), 2)

    async def test_dgx_failure_exposes_only_safe_metadata(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            alice = user(session, "alice")
            book = Book(user_id=alice.id, title="Systems", original_filename="s.pdf", storage_path="x",
                        sha256="abc", status="queued", total_sections=1)
            session.add(book); session.commit(); session.refresh(book)
            session.add(IngestionSection(book_id=book.id, ordinal=0, chapter="C", label="S", page_start=1,
                page_end=2, citation="p1-2", extracted_text="text " * 200, content_hash="x")); session.commit(); book_id = book.id
        with patch("app.db.engine", engine), patch("app.book_service.tutor.author_from_text", new=AsyncMock(side_effect=RuntimeError("SECRET prompt body"))):
            await book_service.process_next_book()
        with Session(engine) as session:
            section = session.exec(select(IngestionSection).where(IngestionSection.book_id == book_id)).one()
            self.assertEqual(section.status, "failed")
            self.assertNotIn("SECRET", section.error_message)
            self.assertEqual(section.error_message, "DGX could not generate valid grounded material for this section.")

    async def test_partial_failed_book_does_not_starve_new_queued_book(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            alice = user(session, "alice")
            partial = Book(user_id=alice.id, title="Old", original_filename="old.pdf", storage_path="x",
                sha256="old", status="partial", total_sections=1)
            queued = Book(user_id=alice.id, title="New", original_filename="new.pdf", storage_path="y",
                sha256="new", status="queued", total_sections=1)
            session.add(partial); session.add(queued); session.commit(); session.refresh(partial); session.refresh(queued)
            session.add(IngestionSection(book_id=partial.id, ordinal=0, chapter="Old", label="Old", page_start=1,
                page_end=2, citation="old", extracted_text="old " * 200, content_hash="old", status="failed"))
            session.add(IngestionSection(book_id=queued.id, ordinal=0, chapter="New", label="New", page_start=1,
                page_end=2, citation="new", extracted_text="new " * 200, content_hash="new")); session.commit()
            partial_id, queued_id = partial.id, queued.id
        authored = {"title": "New topic", "summary": "Summary", "lesson_md": "Lesson", "cards": [
            {"kind": "free", "prompt": "Explain", "answer": "Answer"},
            {"kind": "mcq", "prompt": "Choose", "choices": ["A", "B", "C", "D"], "answer": "A"},
        ]}
        with patch("app.db.engine", engine), patch("app.book_service.tutor.author_from_text", new=AsyncMock(return_value=authored)):
            self.assertEqual(await book_service.process_next_book(), 1)
        with Session(engine) as session:
            self.assertEqual(session.get(Book, partial_id).status, "partial")
            self.assertEqual(session.get(Book, queued_id).status, "ready")

    async def test_retry_rejects_zero_section_or_nonfailed_book(self):
        with memory_session() as session:
            alice = user(session, "alice")
            book = Book(user_id=alice.id, title="Broken", original_filename="b.pdf", storage_path="x",
                        sha256="broken", status="failed", total_sections=0)
            session.add(book); session.commit(); session.refresh(book)
            with self.assertRaises(HTTPException) as caught:
                retry_book(book.id, alice, session)
            self.assertEqual(caught.exception.status_code, 409)
            self.assertEqual(session.get(Book, book.id).status, "failed")


class SchedulerAndCsrfTests(unittest.IsolatedAsyncioTestCase):
    async def test_dev_scheduler_registers_book_worker_but_not_nightly_job(self):
        instance = scheduler.start_scheduler(enable_nightly=False)
        try:
            self.assertIsNotNone(instance.get_job("book_ingestion"))
            self.assertIsNone(instance.get_job("nightly_content"))
        finally:
            instance.shutdown(wait=False)

    async def test_explicit_cross_origin_is_rejected(self):
        scope = {"type": "http", "method": "POST", "scheme": "https", "server": ("prep.local", 443),
                 "path": "/api/books", "root_path": "", "query_string": b"",
                 "headers": [(b"host", b"prep.local"), (b"origin", b"https://evil.example"), (b"sec-fetch-site", b"cross-site")]}
        with self.assertRaises(HTTPException) as caught:
            auth.require_same_origin(Request(scope))
        self.assertEqual(caught.exception.status_code, 403)

    async def test_tls_terminated_same_origin_is_accepted_by_host_authority(self):
        scope = {"type": "http", "method": "POST", "scheme": "http", "server": ("127.0.0.1", 8000),
                 "path": "/api/books", "root_path": "", "query_string": b"",
                 "headers": [(b"host", b"prep.tailnet.ts.net"), (b"origin", b"https://prep.tailnet.ts.net"),
                             (b"sec-fetch-site", b"same-origin")]}
        self.assertIsNone(auth.require_same_origin(Request(scope)))

    async def test_production_session_cookie_is_secure_and_deletion_matches_path(self):
        old_environment, old_secret = settings.environment, settings.secret_key
        settings.environment, settings.secret_key = "production", "test-secret"
        try:
            response = Response(); auth.issue_session(response, User(id=1, username="alice"))
            issued = response.headers["set-cookie"]
            self.assertIn("HttpOnly", issued); self.assertIn("Secure", issued); self.assertIn("Path=/", issued)
            cleared = Response(); auth.clear_session(cleared)
            deleted = cleared.headers["set-cookie"]
            self.assertIn("Secure", deleted); self.assertIn("Path=/", deleted)
        finally:
            settings.environment, settings.secret_key = old_environment, old_secret


if __name__ == "__main__":
    unittest.main()
