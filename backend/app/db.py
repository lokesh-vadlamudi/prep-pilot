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
    "daylog": [("coding_solved", "INTEGER DEFAULT 0"), ("user_id", "INTEGER")],
    "concept": [
        ("book", "VARCHAR DEFAULT ''"),
        ("chapter", "VARCHAR DEFAULT ''"),
        ("sequence", "INTEGER DEFAULT 0"),
        ("citation", "VARCHAR DEFAULT ''"),
        ("audience", "VARCHAR DEFAULT 'all'"),
        ("owner_user_id", "INTEGER"),
        ("book_id", "INTEGER"),
    ],
    "user": [
        ("level", "VARCHAR DEFAULT 'senior'"),
        ("lang", "VARCHAR DEFAULT ''"),
    ],
    "card": [("user_id", "INTEGER")],
    "attempt": [("user_id", "INTEGER")],
    "mocksession": [("user_id", "INTEGER")],
    "problemstatus": [("user_id", "INTEGER")],
    "settings": [
        ("user_id", "INTEGER"),
        ("daily_application_target", "INTEGER DEFAULT 5"),
    ],
}


def _migrate() -> None:
    with engine.begin() as conn:
        for table, columns in _ADD_COLUMNS.items():
            existing = {r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            if not existing:
                continue  # table doesn't exist yet (fresh create already has columns)
            for name, decl in columns:
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        _rebuild_unique_indexes(conn)
        _backfill_audience(conn)
    _migrate_multiuser()


def _backfill_audience(conn) -> None:
    """One-time: pre-audience concepts that are clearly senior material (the
    ingested books and their supplements) get audience='senior'."""
    done = conn.exec_driver_sql(
        "SELECT 1 FROM _meta WHERE key = 'audience_backfilled'").fetchone() if conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE name='_meta'").fetchone() else None
    if done:
        return
    conn.exec_driver_sql(
        "CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.exec_driver_sql(
        "UPDATE concept SET audience = 'senior' WHERE audience = 'all' AND "
        "(book != '' OR track IN ('Foundations', 'Cross-links'))")
    conn.exec_driver_sql(
        "INSERT OR IGNORE INTO _meta (key, value) VALUES ('audience_backfilled', datetime('now'))")


def _rebuild_unique_indexes(conn) -> None:
    """Legacy DBs have single-column UNIQUE on daylog.day / problemstatus.problem_id;
    multi-user needs per-user composites. SQLite can't drop inline uniques → rebuild."""
    rebuilds = {
        "daylog": (
            "CREATE TABLE daylog (id INTEGER NOT NULL PRIMARY KEY, day DATE NOT NULL, "
            "reviews_done INTEGER NOT NULL, new_learned INTEGER NOT NULL, "
            "correct INTEGER NOT NULL, coding_solved INTEGER DEFAULT 0, user_id INTEGER, "
            "CONSTRAINT ux_daylog_user_day UNIQUE (user_id, day))",
            "id, day, reviews_done, new_learned, correct, coding_solved, user_id",
            ["CREATE INDEX IF NOT EXISTS ix_daylog_day ON daylog (day)",
             "CREATE INDEX IF NOT EXISTS ix_daylog_user_id ON daylog (user_id)"],
        ),
        "problemstatus": (
            "CREATE TABLE problemstatus (id INTEGER NOT NULL PRIMARY KEY, "
            "problem_id INTEGER NOT NULL, status VARCHAR NOT NULL, confidence INTEGER NOT NULL, "
            "notes VARCHAR NOT NULL, times_reviewed INTEGER NOT NULL, last_touched DATETIME, "
            "revisit_date DATE, user_id INTEGER, "
            "CONSTRAINT ux_status_user_problem UNIQUE (user_id, problem_id))",
            "id, problem_id, status, confidence, notes, times_reviewed, last_touched, revisit_date, user_id",
            ["CREATE INDEX IF NOT EXISTS ix_problemstatus_problem_id ON problemstatus (problem_id)",
             "CREATE INDEX IF NOT EXISTS ix_problemstatus_user_id ON problemstatus (user_id)"],
        ),
    }
    for table, (create_sql, cols, index_sql) in rebuilds.items():
        row = conn.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not row or "ux_" in (row[0] or ""):
            continue  # missing (fresh DB) or already rebuilt
        legacy_unique = ("UNIQUE" in row[0]) or any(
            r[2] == 1 and not r[1].startswith("ux_")
            for r in conn.exec_driver_sql(f"PRAGMA index_list({table})")
        )
        if not legacy_unique:
            continue
        conn.exec_driver_sql(f"ALTER TABLE {table} RENAME TO {table}_old")
        conn.exec_driver_sql(create_sql)
        conn.exec_driver_sql(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM {table}_old")
        conn.exec_driver_sql(f"DROP TABLE {table}_old")
        for stmt in index_sql:
            conn.exec_driver_sql(stmt)


def _migrate_multiuser() -> None:
    """One-time multi-user bootstrap on a legacy single-user DB:
    create the admin from the .env credentials, hand all existing progress to
    them, and mint template cards (user_id NULL) for future users to clone."""
    from .config import settings

    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT)")
        done = conn.exec_driver_sql(
            "SELECT 1 FROM _meta WHERE key = 'multiuser_migrated'").fetchone()
        if done:
            return
        conn.exec_driver_sql(
            "INSERT INTO _meta (key, value) VALUES ('multiuser_migrated', datetime('now'))")

        users = conn.exec_driver_sql("SELECT count(*) FROM user").fetchone()[0]
        legacy_rows = conn.exec_driver_sql(
            "SELECT (SELECT count(*) FROM card) + (SELECT count(*) FROM daylog) "
            "+ (SELECT count(*) FROM problemstatus)").fetchone()[0]
        if legacy_rows == 0:
            return  # fresh install — nothing to hand over

        if users == 0 and settings.password_hash:
            conn.exec_driver_sql(
                "INSERT INTO user (username, password_hash, is_admin, level, lang, created_at) "
                "VALUES (?, ?, 1, 'senior', '', datetime('now'))",
                (settings.username, settings.password_hash),
            )

        admin = conn.exec_driver_sql(
            "SELECT id FROM user WHERE is_admin = 1 ORDER BY id LIMIT 1").fetchone()
        if not admin:
            return
        aid = admin[0]
        for table in ("card", "attempt", "daylog", "mocksession", "problemstatus", "settings"):
            conn.exec_driver_sql(
                f"UPDATE {table} SET user_id = ? WHERE user_id IS NULL", (aid,))

        # Mint templates for concepts that have owned cards but no template yet.
        conn.exec_driver_sql(
            "INSERT INTO card (user_id, concept_id, kind, prompt, choices_json, answer, "
            " explanation, source, introduced, ease, interval_days, repetitions, due_date, "
            " last_reviewed, lapses) "
            "SELECT NULL, c.concept_id, c.kind, c.prompt, c.choices_json, c.answer, "
            " c.explanation, c.source, 0, 2.5, 0, 0, DATE('now'), NULL, 0 "
            "FROM card c WHERE c.user_id = ? AND c.concept_id NOT IN "
            " (SELECT concept_id FROM card WHERE user_id IS NULL)",
            (aid,),
        )


def get_session():
    with Session(engine) as session:
        yield session
