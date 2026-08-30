from __future__ import annotations

import asyncio
from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException, Response, UploadFile
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select
from starlette.datastructures import Headers

from app import auth, book_service, db
from app.models import (
    Attempt, Book, BookBookmark, BookChatMessage, BookReadingProgress, Card, Concept,
    ConceptStatus, CourseContentLink, IngestionSection, User,
)
from app.routers.book_routes import (
    BookmarkIn,
    ChatIn,
    ProgressIn,
    SharingIn,
    activate_book,
    chat,
    delete_book,
    list_books,
    put_bookmark,
    reader_state,
    set_book_sharing,
    update_progress,
    upload_book,
)
from app.routers import book_routes


def memory_session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    return Session(engine)


def add_user(session: Session, username: str) -> User:
    user = User(username=username, password_hash="x")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


class BookSharingDataTests(unittest.TestCase):
    def test_legacy_books_migrate_private_and_the_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine(f"sqlite:///{Path(directory) / 'legacy.db'}")
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    "CREATE TABLE book (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                    "title VARCHAR NOT NULL, original_filename VARCHAR NOT NULL, storage_path VARCHAR NOT NULL, "
                    "sha256 VARCHAR NOT NULL, mime_type VARCHAR NOT NULL DEFAULT 'application/pdf', "
                    "byte_size INTEGER NOT NULL DEFAULT 0, page_count INTEGER NOT NULL DEFAULT 0, "
                    "status VARCHAR NOT NULL DEFAULT 'ready', total_sections INTEGER NOT NULL DEFAULT 0, "
                    "completed_sections INTEGER NOT NULL DEFAULT 0, error_code VARCHAR NOT NULL DEFAULT '', "
                    "error_message VARCHAR NOT NULL DEFAULT '', activated BOOLEAN NOT NULL DEFAULT 0, "
                    "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
                )
                conn.exec_driver_sql(
                    "INSERT INTO book (id,user_id,title,original_filename,storage_path,sha256,created_at,updated_at) "
                    "VALUES (1,1,'Legacy','legacy.pdf','x','legacy','2026-01-01','2026-01-01')"
                )

            with patch("app.db.engine", engine):
                db.init_db()
                db.init_db()

            columns = {column["name"]: column for column in inspect(engine).get_columns("book")}
            self.assertIn("shared_with_all", columns)
            self.assertFalse(columns["shared_with_all"]["nullable"])
            with engine.connect() as conn:
                self.assertEqual(conn.exec_driver_sql("SELECT shared_with_all FROM book").scalar_one(), 0)
                indexes = {row[1] for row in conn.exec_driver_sql("PRAGMA index_list(book)")}
                self.assertIn("ix_book_shared_with_all", indexes)

    def test_sharing_schema_validation_rejects_public_defaults_and_missing_indexes(self):
        unsafe = create_engine("sqlite://")
        with unsafe.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE book (id INTEGER PRIMARY KEY, shared_with_all BOOLEAN DEFAULT 1)")
            conn.exec_driver_sql("CREATE INDEX ix_book_shared_with_all ON book(shared_with_all)")
            with self.assertRaisesRegex(RuntimeError, "private non-null default"):
                db._validate_book_sharing_schema(conn)

        unindexed = create_engine("sqlite://")
        with unindexed.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE book (id INTEGER PRIMARY KEY, shared_with_all BOOLEAN NOT NULL DEFAULT 0)"
            )
            with self.assertRaisesRegex(RuntimeError, "shared access index"):
                db._validate_book_sharing_schema(conn)

    def test_owner_and_shared_reader_access_are_separate(self):
        with memory_session() as session:
            owner = add_user(session, "share-owner")
            viewer = add_user(session, "share-viewer")
            book = Book(
                user_id=owner.id, title="Systems", original_filename="systems.pdf",
                storage_path="x", sha256="share-data", page_count=4, status="ready",
            )
            session.add(book)
            session.commit()
            session.refresh(book)
            concept = Concept(slug="private-lesson", track="Systems", title="Owner lesson", owner_user_id=owner.id)
            session.add(concept)
            session.commit()
            session.refresh(concept)
            session.add(IngestionSection(
                book_id=book.id, ordinal=0, chapter="Serving", label="Batching",
                page_start=2, page_end=3, citation="Systems p2-3", extracted_text="Batching facts",
                content_hash="sharing-section", status="complete", concept_id=concept.id,
            ))
            session.commit()

            self.assertEqual(book_service.owned_book(session, owner.id, book.id).id, book.id)
            with self.assertRaises(HTTPException) as private:
                book_service.readable_book(session, viewer.id, book.id)
            self.assertEqual(private.exception.status_code, 404)
            with self.assertRaises(HTTPException) as private_payload:
                book_service.serialize_book(session, book, viewer.id, detail=True)
            self.assertEqual(private_payload.exception.status_code, 404)

            book.shared_with_all = True
            session.add(book)
            session.commit()
            self.assertEqual(book_service.readable_book(session, viewer.id, book.id).id, book.id)
            with self.assertRaises(HTTPException):
                book_service.owned_book(session, viewer.id, book.id)

            owner_payload = book_service.serialize_book(session, book, owner.id, detail=True)
            self.assertEqual((owner_payload["access"], owner_payload["is_owner"]), ("owner", True))
            self.assertEqual(owner_payload["sections"][0]["concept_id"], concept.id)

            shared_payload = book_service.serialize_book(session, book, viewer.id, detail=True)
            self.assertEqual(set(shared_payload), {
                "id", "title", "page_count", "access", "is_owner", "shared_with_all", "sections",
            })
            self.assertEqual(set(shared_payload["sections"][0]), {
                "id", "chapter", "label", "page_start", "page_end", "citation",
            })


class BookSharingRouteTests(unittest.TestCase):
    def test_two_user_http_access_and_revocation_boundary(self):
        with memory_session() as session:
            owner = add_user(session, "http-share-owner")
            viewer = add_user(session, "http-share-viewer")
            book = Book(
                user_id=owner.id, title="HTTP Shared", original_filename="http.pdf",
                storage_path="http.pdf", sha256="http-share", page_count=2, status="ready",
            )
            session.add(book)
            session.commit()
            session.refresh(book)
            session.add(IngestionSection(
                book_id=book.id, ordinal=0, chapter="Serving", label="Batching",
                page_start=1, page_end=2, citation="HTTP Shared pages 1-2",
                extracted_text="Continuous batching shares accelerator capacity.",
                content_hash="http-share-section", status="complete",
            ))
            session.commit()

            identity = {"user": owner}
            app = FastAPI()
            app.include_router(book_routes.router)

            def override_session():
                yield session

            app.dependency_overrides[book_routes.get_session] = override_session
            app.dependency_overrides[auth.current_user] = lambda: identity["user"]
            client = TestClient(app)

            identity["user"] = viewer
            self.assertEqual(client.get("/api/books").json(), [])
            private = client.get(f"/api/books/{book.id}")
            self.assertEqual(private.status_code, 404)
            self.assertIn("no-store", private.headers["cache-control"])

            identity["user"] = owner
            with patch("app.routers.book_routes.book_service.source_pdf_path"):
                shared = client.put(
                    f"/api/books/{book.id}/sharing", json={"shared_with_all": True},
                )
            self.assertEqual(shared.status_code, 200, shared.text)
            self.assertTrue(shared.json()["shared_with_all"])

            identity["user"] = viewer
            listing = client.get("/api/books")
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(listing.json(), [{
                "id": book.id, "title": "HTTP Shared", "page_count": 2,
                "access": "shared", "is_owner": False, "shared_with_all": True,
            }])
            detail = client.get(f"/api/books/{book.id}")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(set(detail.json()), {
                "id", "title", "page_count", "access", "is_owner", "shared_with_all", "sections",
            })
            self.assertEqual(
                client.put(f"/api/books/{book.id}/progress", json={"page": 2}).status_code, 200,
            )
            for method, path in (
                (client.put, f"/api/books/{book.id}/sharing"),
                (client.post, f"/api/books/{book.id}/activate"),
                (client.post, f"/api/books/{book.id}/retry"),
                (client.delete, f"/api/books/{book.id}"),
            ):
                result = method(path, json={"shared_with_all": False}) if method == client.put else method(path)
                self.assertEqual(result.status_code, 404, result.text)

            identity["user"] = owner
            unshared = client.put(
                f"/api/books/{book.id}/sharing", json={"shared_with_all": False},
            )
            self.assertEqual(unshared.status_code, 200)
            identity["user"] = viewer
            self.assertEqual(client.get(f"/api/books/{book.id}").status_code, 404)
            self.assertEqual(
                session.exec(select(BookReadingProgress).where(
                    BookReadingProgress.book_id == book.id,
                    BookReadingProgress.user_id == viewer.id,
                )).one().page_number,
                2,
            )

    def test_sharing_input_is_strict_and_owner_only(self):
        for invalid in (True, False):
            self.assertEqual(SharingIn(shared_with_all=invalid).shared_with_all, invalid)
        for payload in ({}, {"shared_with_all": "true"}, {"shared_with_all": 1},
                        {"shared_with_all": None}, {"shared_with_all": True, "extra": 1}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                SharingIn.model_validate(payload)

        with memory_session() as session:
            owner = add_user(session, "toggle-owner")
            viewer = add_user(session, "toggle-viewer")
            book = Book(
                user_id=owner.id, title="Toggle", original_filename="toggle.pdf",
                storage_path="x", sha256="toggle", page_count=2, status="ready",
            )
            session.add(book)
            session.commit()
            session.refresh(book)
            original_updated_at = book.updated_at

            with patch("app.routers.book_routes.book_service.source_pdf_path"):
                changed = set_book_sharing(
                    book.id, SharingIn(shared_with_all=True), owner, session, Response(),
                )
            self.assertTrue(changed["changed"])
            self.assertTrue(changed["shared_with_all"])
            self.assertEqual((changed["access"], changed["is_owner"]), ("owner", True))

            unchanged = set_book_sharing(book.id, SharingIn(shared_with_all=True), owner, session, Response())
            self.assertFalse(unchanged["changed"])
            self.assertEqual(unchanged["updated_at"], changed["updated_at"])
            self.assertNotEqual(changed["updated_at"], original_updated_at.isoformat())

            with self.assertRaises(HTTPException) as denied:
                set_book_sharing(book.id, SharingIn(shared_with_all=False), viewer, session, Response())
            self.assertEqual(denied.exception.status_code, 404)
            with self.assertRaises(HTTPException):
                activate_book(book.id, viewer, session)

    def test_sharing_rejects_unready_or_missing_source_without_changing_state(self):
        with memory_session() as session:
            owner = add_user(session, "share-failure-owner")
            unready = Book(
                user_id=owner.id, title="Unready", original_filename="unready.pdf",
                storage_path="x", sha256="unready-share", page_count=1, status="processing",
            )
            missing = Book(
                user_id=owner.id, title="Missing", original_filename="missing.pdf",
                storage_path="missing", sha256="missing-share", page_count=1, status="ready",
            )
            session.add(unready)
            session.add(missing)
            session.commit()
            session.refresh(unready)
            session.refresh(missing)

            with self.assertRaises(HTTPException) as not_ready:
                set_book_sharing(
                    unready.id, SharingIn(shared_with_all=True), owner, session, Response(),
                )
            self.assertEqual(not_ready.exception.status_code, 409)
            self.assertIn("no-store", not_ready.exception.headers["Cache-Control"])

            with patch(
                "app.routers.book_routes.book_service.source_pdf_path",
                side_effect=HTTPException(404, "Book file not found"),
            ), self.assertRaises(HTTPException) as absent:
                set_book_sharing(
                    missing.id, SharingIn(shared_with_all=True), owner, session, Response(),
                )
            self.assertEqual(absent.exception.status_code, 404)
            self.assertIn("no-store", absent.exception.headers["Cache-Control"])
            session.refresh(unready)
            session.refresh(missing)
            self.assertFalse(unready.shared_with_all)
            self.assertFalse(missing.shared_with_all)

    def test_owner_upload_response_and_deletion_remove_course_links(self):
        with memory_session() as session, tempfile.TemporaryDirectory() as directory:
            owner = add_user(session, "share-lifecycle-owner")
            book = Book(
                user_id=owner.id, title="Lifecycle", original_filename="lifecycle.pdf",
                storage_path="lifecycle.pdf", sha256="lifecycle-share", page_count=1, status="ready",
            )
            session.add(book)
            session.commit()
            session.refresh(book)
            response = Response()
            upload = UploadFile(
                filename="lifecycle.pdf", file=BytesIO(b"%PDF-1.4"),
                headers=Headers({"content-type": "application/pdf"}),
            )
            with patch(
                "app.routers.book_routes.book_service.save_upload", new=AsyncMock(return_value=book),
            ):
                payload = asyncio.run(upload_book(upload, owner, session, response))
            self.assertEqual((payload["id"], payload["access"]), (book.id, "owner"))
            self.assertIn("no-store", response.headers["Cache-Control"])

            concept = Concept(
                slug="linked-owner-lesson", track="Systems", title="Linked lesson",
                owner_user_id=owner.id, book_id=book.id,
            )
            session.add(concept)
            session.commit()
            session.refresh(concept)
            session.add(CourseContentLink(
                user_id=owner.id, module_id="IC-01", concept_id=concept.id,
                match_kind="owned_exact", candidate_fingerprint="linked-owner-fingerprint",
            ))
            session.add(ConceptStatus(user_id=owner.id, concept_id=concept.id, completed=True))
            card = Card(user_id=owner.id, concept_id=concept.id, prompt="linked card")
            session.add(card)
            session.commit()
            session.refresh(card)
            session.add(Attempt(
                user_id=owner.id, card_id=card.id, concept_id=concept.id, user_answer="answer",
            ))
            session.add(IngestionSection(
                book_id=book.id, ordinal=0, chapter="Delete", label="Delete safely",
                page_start=1, page_end=1, citation="page 1", extracted_text="text",
                content_hash="delete-linked-section", status="complete", concept_id=concept.id,
            ))
            session.commit()
            source = Path(directory) / "lifecycle.pdf"
            source.write_bytes(b"%PDF-1.4")
            with patch("app.routers.book_routes.book_service.deletion_pdf_path", return_value=source):
                delete_book(book.id, owner, session)
            self.assertEqual(session.exec(select(CourseContentLink)).all(), [])
            self.assertEqual(session.exec(select(Book).where(Book.id == book.id)).first(), None)
            self.assertFalse(source.exists())

    def test_delete_restores_the_pdf_when_database_commit_fails(self):
        with memory_session() as session, tempfile.TemporaryDirectory() as directory:
            owner = add_user(session, "delete-compensation-owner")
            book = Book(
                user_id=owner.id, title="Restore", original_filename="restore.pdf",
                storage_path="restore.pdf", sha256="restore-delete", page_count=1, status="ready",
            )
            session.add(book)
            session.commit()
            session.refresh(book)
            source = Path(directory) / "restore.pdf"
            source.write_bytes(b"%PDF-1.4 restore")

            with patch("app.routers.book_routes.book_service.deletion_pdf_path", return_value=source), \
                    patch.object(session, "commit", side_effect=RuntimeError("commit failed")), \
                    self.assertRaises(HTTPException) as failed:
                delete_book(book.id, owner, session)

            self.assertEqual(failed.exception.status_code, 503)
            self.assertTrue(source.exists())
            self.assertEqual(source.read_bytes(), b"%PDF-1.4 restore")
            session.expire_all()
            self.assertIsNotNone(session.exec(select(Book).where(Book.id == book.id)).first())

    def test_delete_reports_restore_failure_without_hiding_the_database_failure(self):
        with memory_session() as session, tempfile.TemporaryDirectory() as directory:
            owner = add_user(session, "delete-restore-failure-owner")
            book = Book(
                user_id=owner.id, title="Restore failure", original_filename="restore-failure.pdf",
                storage_path="restore-failure.pdf", sha256="restore-failure", page_count=1, status="ready",
            )
            session.add(book); session.commit(); session.refresh(book)
            source = Path(directory) / "restore-failure.pdf"
            source.write_bytes(b"%PDF-1.4")
            original_replace = Path.replace

            def fail_only_restore(value: Path, target: Path):
                if ".deleting-" in value.name:
                    raise OSError("restore failed")
                return original_replace(value, target)

            with patch("app.routers.book_routes.book_service.deletion_pdf_path", return_value=source), \
                    patch.object(session, "commit", side_effect=RuntimeError("commit failed")), \
                    patch.object(Path, "replace", autospec=True, side_effect=fail_only_restore), \
                    self.assertRaises(HTTPException) as failed:
                delete_book(book.id, owner, session)
            self.assertEqual(failed.exception.status_code, 503)
            self.assertIn("safely", failed.exception.detail)

    def test_delete_without_a_pdf_and_post_commit_cleanup_failure_remain_consistent(self):
        with memory_session() as session, tempfile.TemporaryDirectory() as directory:
            owner = add_user(session, "delete-cleanup-owner")
            missing = Book(
                user_id=owner.id, title="Already missing", original_filename="missing.pdf",
                storage_path="missing.pdf", sha256="already-missing", page_count=1, status="ready",
            )
            session.add(missing); session.commit(); session.refresh(missing)
            absent = Path(directory) / "absent.pdf"
            with patch("app.routers.book_routes.book_service.deletion_pdf_path", return_value=absent):
                delete_book(missing.id, owner, session)
            self.assertIsNone(session.exec(select(Book).where(Book.id == missing.id)).first())

            cleanup = Book(
                user_id=owner.id, title="Cleanup", original_filename="cleanup.pdf",
                storage_path="cleanup.pdf", sha256="cleanup-failure", page_count=1, status="ready",
            )
            session.add(cleanup); session.commit(); session.refresh(cleanup)
            source = Path(directory) / "cleanup.pdf"
            source.write_bytes(b"%PDF-1.4")
            with patch("app.routers.book_routes.book_service.deletion_pdf_path", return_value=source), \
                    patch.object(Path, "unlink", autospec=True, side_effect=OSError("cleanup failed")), \
                    self.assertLogs("prep.books", level="WARNING") as logged:
                delete_book(cleanup.id, owner, session)
            self.assertIsNone(session.exec(select(Book).where(Book.id == cleanup.id)).first())
            self.assertIn("quarantine cleanup failed", " ".join(logged.output))

    def test_delete_rejects_a_pdf_that_cannot_be_quarantined(self):
        with memory_session() as session, tempfile.TemporaryDirectory() as directory:
            owner = add_user(session, "delete-quarantine-owner")
            book = Book(
                user_id=owner.id, title="Quarantine", original_filename="quarantine.pdf",
                storage_path="quarantine.pdf", sha256="quarantine-failure", page_count=1, status="ready",
            )
            session.add(book); session.commit(); session.refresh(book)
            source = Path(directory) / "quarantine.pdf"
            source.write_bytes(b"%PDF-1.4")
            with patch("app.routers.book_routes.book_service.deletion_pdf_path", return_value=source), \
                    patch.object(Path, "replace", autospec=True, side_effect=OSError("rename failed")), \
                    self.assertRaises(HTTPException) as failed:
                delete_book(book.id, owner, session)
            self.assertEqual(failed.exception.status_code, 503)
            self.assertTrue(source.exists())

    def test_unsharing_during_generation_discards_the_answer(self):
        with memory_session() as session:
            owner = add_user(session, "chat-revoke-owner")
            viewer = add_user(session, "chat-revoke-viewer")
            book = Book(
                user_id=owner.id, title="Revoked Chat", original_filename="chat.pdf",
                storage_path="chat.pdf", sha256="chat-revoke", page_count=1, status="ready",
                shared_with_all=True,
            )
            session.add(book)
            session.commit()
            session.refresh(book)
            session.add(IngestionSection(
                book_id=book.id, ordinal=0, chapter="Serving", label="Batching",
                page_start=1, page_end=1, citation="page 1", extracted_text="Batching shares work.",
                content_hash="chat-revoke-section", status="complete",
            ))
            session.commit()

            async def revoke_while_generating(*_args, **_kwargs):
                book.shared_with_all = False
                session.add(book)
                session.commit()
                return "This answer must be discarded."

            with patch(
                "app.routers.book_routes.llm.chat", new=AsyncMock(side_effect=revoke_while_generating),
            ), self.assertRaises(HTTPException) as revoked:
                asyncio.run(chat(
                    book.id, ChatIn(question="Explain batching"), viewer, session, Response(),
                ))
            self.assertEqual(revoked.exception.status_code, 404)
            self.assertIn("no-store", revoked.exception.headers["Cache-Control"])
            self.assertEqual(session.exec(select(BookChatMessage)).all(), [])

    def test_shared_book_uses_private_state_for_each_viewer(self):
        with memory_session() as session:
            owner = add_user(session, "state-owner-share")
            viewer = add_user(session, "state-viewer-share")
            book = Book(
                user_id=owner.id, title="Shared state", original_filename="state.pdf",
                storage_path="x", sha256="state-sharing", page_count=3, status="ready",
                shared_with_all=True,
            )
            session.add(book)
            session.commit()
            session.refresh(book)

            listed = list_books(viewer, session, Response())
            self.assertEqual([(row["id"], row["access"]) for row in listed], [(book.id, "shared")])
            update_progress(book.id, ProgressIn(page=2), viewer, session, Response())
            put_bookmark(book.id, 2, BookmarkIn(note="viewer only"), viewer, session, Response())

            self.assertEqual(reader_state(book.id, viewer, session, Response())["page"], 2)
            self.assertEqual(reader_state(book.id, owner, session, Response())["page"], 1)
            self.assertEqual(session.exec(select(BookReadingProgress)).one().user_id, viewer.id)
            self.assertEqual(session.exec(select(BookBookmark)).one().user_id, viewer.id)

            book.shared_with_all = False
            session.add(book)
            session.commit()
            with self.assertRaises(HTTPException) as revoked:
                reader_state(book.id, viewer, session, Response())
            self.assertEqual(revoked.exception.status_code, 404)
            self.assertEqual(session.exec(select(BookReadingProgress)).one().page_number, 2)


if __name__ == "__main__":
    unittest.main()
