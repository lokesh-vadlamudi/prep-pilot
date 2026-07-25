"""Database engine + session helpers."""
from __future__ import annotations

from sqlmodel import SQLModel, Session, create_engine

from .config import settings

engine = create_engine(
    settings.database_url,
    # 30s busy timeout so the live app and the book-ingestion job don't collide.
    connect_args={"check_same_thread": False, "timeout": 30},
)


def init_db() -> None:
    # Import models so metadata is registered before create_all.
    from . import models  # noqa: F401
    # WAL mode: concurrent reads + a single writer, so the ingestion job and the
    # live app can run at once without "database is locked".
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA busy_timeout=30000")
    SQLModel.metadata.create_all(engine)
    _migrate()


# Lightweight additive migrations: SQLModel.create_all() never ALTERs existing
# tables, so add any new columns here. Idempotent (checks PRAGMA table_info).
_ADD_COLUMNS = {
    "daylog": [("coding_solved", "INTEGER DEFAULT 0")],
    "concept": [
        ("book", "VARCHAR DEFAULT ''"),
        ("chapter", "VARCHAR DEFAULT ''"),
        ("sequence", "INTEGER DEFAULT 0"),
        ("citation", "VARCHAR DEFAULT ''"),
    ],
}


def _migrate() -> None:
    from sqlalchemy import text
    with engine.begin() as conn:
        for table, columns in _ADD_COLUMNS.items():
            existing = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if not existing:
                continue  # table doesn't exist yet (fresh create already has columns)
            for name, decl in columns:
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def get_session():
    with Session(engine) as session:
        yield session
