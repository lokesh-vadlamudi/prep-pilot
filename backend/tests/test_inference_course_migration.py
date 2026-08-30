from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine

from app import db


COURSE_TABLES = {
    "courseenrollment",
    "coursemissionprogress",
    "courseartifactevidence",
    "coursecheckpointattempt",
    "courseoralturn",
    "courseoralreview",
    "coursecontentlink",
    "coursemutationreceipt",
}
COURSE_MARKER = "inference_course_schema_v1"


def projection_hash(conn, query: str) -> str:
    rows = [list(row) for row in conn.exec_driver_sql(query)]
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def table_names(conn) -> set[str]:
    return {
        row[0]
        for row in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def unique_column_sets(conn, table: str) -> set[tuple[str, ...]]:
    result = set()
    for row in conn.exec_driver_sql(f"PRAGMA index_list({table})"):
        if row[2]:
            columns = tuple(item[2] for item in conn.exec_driver_sql(f"PRAGMA index_info({row[1]})"))
            result.add(columns)
    return result


class InferenceCourseMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "migration.db"
        self.engine = create_engine(
            f"sqlite:///{self.path}",
            connect_args={"check_same_thread": False, "timeout": 5},
        )

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def _init_twice(self) -> None:
        with patch("app.db.engine", self.engine):
            db.init_db()
            db.init_db()

    def _install_pre_constraint_link_table(self, match_kind: str) -> None:
        with patch("app.db.engine", self.engine):
            db.init_db()
        with self.engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO user (id,username,password_hash,is_admin,level,lang,created_at) "
                "VALUES (1,'link-owner','x',1,'senior','','2026-01-01')"
            )
            conn.exec_driver_sql(
                "INSERT INTO concept "
                "(id,slug,track,title,difficulty,tags,summary,lesson_md,source,audience,created_at,"
                "book,chapter,sequence,citation,owner_user_id,book_id) VALUES "
                "(1,'pre-check-link','Inference','Link','core','','','','seed','all','2026-01-01',"
                "'','',0,'',NULL,NULL)"
            )
            conn.exec_driver_sql("ALTER TABLE coursecontentlink RENAME TO coursecontentlink_checked")
            conn.exec_driver_sql(
                "CREATE TABLE coursecontentlink ("
                "id INTEGER NOT NULL PRIMARY KEY, user_id INTEGER NOT NULL, "
                "module_id VARCHAR(40) NOT NULL, concept_id INTEGER NOT NULL, "
                "match_kind VARCHAR(40) NOT NULL, candidate_fingerprint VARCHAR(64) NOT NULL, "
                "confirmed_at DATETIME NOT NULL, revision INTEGER NOT NULL, "
                "CONSTRAINT ux_course_link_user_module UNIQUE (user_id,module_id), "
                "FOREIGN KEY(user_id) REFERENCES user(id), FOREIGN KEY(concept_id) REFERENCES concept(id))"
            )
            conn.exec_driver_sql(
                "INSERT INTO coursecontentlink "
                "(id,user_id,module_id,concept_id,match_kind,candidate_fingerprint,confirmed_at,revision) "
                "VALUES (9,1,'IC-00',1,?,'legacy-fingerprint','2026-01-01',3)",
                (match_kind,),
            )
            conn.exec_driver_sql("DROP TABLE coursecontentlink_checked")
            conn.exec_driver_sql(
                "CREATE INDEX ix_coursecontentlink_user_id ON coursecontentlink(user_id)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_coursecontentlink_module_id ON coursecontentlink(module_id)"
            )
            conn.exec_driver_sql(
                "CREATE INDEX ix_coursecontentlink_concept_id ON coursecontentlink(concept_id)"
            )

    def test_fresh_database_migrates_twice_with_valid_course_schema_and_marker(self):
        self._init_twice()
        with self.engine.connect() as conn:
            self.assertTrue(COURSE_TABLES.issubset(table_names(conn)))
            marker = conn.exec_driver_sql(
                "SELECT value FROM _meta WHERE key=?", (COURSE_MARKER,)
            ).fetchone()
            self.assertIsNotNone(marker)
            for table in COURSE_TABLES:
                self.assertEqual(conn.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one(), 0)
            self.assertIn(("user_id", "course_key"), unique_column_sets(conn, "courseenrollment"))
            self.assertIn(("user_id", "mission_id"), unique_column_sets(conn, "courseoralreview"))
            self.assertIn(
                ("user_id", "course_key", "operation", "request_id"),
                unique_column_sets(conn, "coursemutationreceipt"),
            )
            checkpoint_columns = {
                row[1] for row in conn.exec_driver_sql("PRAGMA table_info(coursecheckpointattempt)")
            }
            self.assertIn("response_json", checkpoint_columns)
            link_sql = conn.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name='coursecontentlink'"
            ).scalar_one()
            for match_kind in ("owned_exact", "legacy_exact", "explicit_supplement_alias"):
                self.assertIn(match_kind, link_sql)

    def test_pre_response_checkpoint_schema_upgrades_without_losing_attempt(self):
        with patch("app.db.engine", self.engine):
            db.init_db()
        with self.engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO user (id,username,password_hash,is_admin,level,lang,created_at) "
                "VALUES (1,'checkpoint-owner','x',1,'senior','','2026-01-01')"
            )
            conn.exec_driver_sql(
                "INSERT INTO coursecheckpointattempt "
                "(id,user_id,checkpoint_id,request_id,payload_sha256,answers_json,passed,feedback,"
                "response_json,created_at) VALUES "
                "(1,1,'IC-00-CHECKPOINT','legacy-attempt','sha','{}',0,'retry','{}','2026-01-01')"
            )
            conn.exec_driver_sql("ALTER TABLE coursecheckpointattempt DROP COLUMN response_json")
            conn.exec_driver_sql("DELETE FROM _meta WHERE key=?", (COURSE_MARKER,))

        self._init_twice()

        with self.engine.connect() as conn:
            columns = {
                row[1] for row in conn.exec_driver_sql("PRAGMA table_info(coursecheckpointattempt)")
            }
            row = conn.exec_driver_sql(
                "SELECT request_id, feedback, response_json FROM coursecheckpointattempt WHERE id=1"
            ).fetchone()
            self.assertIn("response_json", columns)
            self.assertEqual(tuple(row), ("legacy-attempt", "retry", "{}"))

    def test_artifact_draft_columns_are_additive_idempotent_and_preserve_existing_evidence(self):
        with patch("app.db.engine", self.engine):
            db.init_db()
        with self.engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO user (id,username,password_hash,is_admin,level,lang,created_at) "
                "VALUES (1,'artifact-owner','x',1,'senior','','2026-01-01')"
            )
            conn.exec_driver_sql(
                "INSERT INTO courseartifactevidence "
                "(id,user_id,mission_id,artifact_id,note,artifact_uri,template_key,output_format,"
                "draft_json,rubric_json,source_ids_json,catalog_version,revision,created_at,updated_at) "
                "VALUES (7,1,'IC-00','IC-00-ARTIFACT','legacy note','reports/legacy.md','legacy',"
                "'markdown','{}','[]','[]','2026.08.29',3,'2026-01-01','2026-01-01')"
            )
            columns = {
                row[1] for row in conn.exec_driver_sql("PRAGMA table_info(courseartifactevidence)")
            }
            for name in (
                "template_key", "output_format", "draft_json", "rubric_json",
                "source_ids_json", "catalog_version",
            ):
                if name in columns:
                    conn.exec_driver_sql(f"ALTER TABLE courseartifactevidence DROP COLUMN {name}")
            conn.exec_driver_sql("DELETE FROM _meta WHERE key=?", (COURSE_MARKER,))

        self._init_twice()

        with self.engine.connect() as conn:
            columns = {
                row[1] for row in conn.exec_driver_sql("PRAGMA table_info(courseartifactevidence)")
            }
            expected = {
                "template_key", "output_format", "draft_json", "rubric_json",
                "source_ids_json", "catalog_version",
            }
            self.assertTrue(expected.issubset(columns))
            row = conn.exec_driver_sql(
                "SELECT id,note,artifact_uri,revision,draft_json FROM courseartifactevidence WHERE id=7"
            ).fetchone()
            self.assertEqual(tuple(row), (7, "legacy note", "reports/legacy.md", 3, "{}"))

    def test_pre_constraint_link_table_rebuilds_twice_and_preserves_valid_row(self):
        self._install_pre_constraint_link_table("owned_exact")
        self._init_twice()

        with self.engine.connect() as conn:
            link_sql = conn.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name='coursecontentlink'"
            ).scalar_one()
            self.assertIn("ck_course_link_match_kind", link_sql)
            row = conn.exec_driver_sql(
                "SELECT id,user_id,module_id,concept_id,match_kind,candidate_fingerprint,revision "
                "FROM coursecontentlink"
            ).fetchone()
            self.assertEqual(tuple(row), (9, 1, "IC-00", 1, "owned_exact", "legacy-fingerprint", 3))
            self.assertIn(("user_id", "module_id"), unique_column_sets(conn, "coursecontentlink"))
            index_names = {
                item[1] for item in conn.exec_driver_sql("PRAGMA index_list(coursecontentlink)")
            }
            self.assertTrue({
                "ix_coursecontentlink_user_id", "ix_coursecontentlink_module_id",
                "ix_coursecontentlink_concept_id",
            }.issubset(index_names))
            foreign_targets = {
                item[2] for item in conn.exec_driver_sql("PRAGMA foreign_key_list(coursecontentlink)")
            }
            self.assertEqual(foreign_targets, {"user", "concept"})
            conn.rollback()
            transaction = conn.begin()
            with self.assertRaises(Exception):
                conn.exec_driver_sql(
                    "INSERT INTO coursecontentlink "
                    "(user_id,module_id,concept_id,match_kind,candidate_fingerprint,confirmed_at,revision) "
                    "VALUES (1,'IC-01',1,'arbitrary','bad','2026-01-01',1)"
                )
            transaction.rollback()

    def test_invalid_pre_constraint_link_rows_abort_rebuild_without_data_loss(self):
        self._install_pre_constraint_link_table("arbitrary")
        with patch("app.db.engine", self.engine):
            with self.assertRaisesRegex(RuntimeError, "invalid match_kind"):
                db.init_db()

        with self.engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT id,match_kind,candidate_fingerprint,revision FROM coursecontentlink"
            ).fetchone()
            self.assertEqual(tuple(row), (9, "arbitrary", "legacy-fingerprint", 3))
            self.assertNotIn("coursecontentlink_rebuild", table_names(conn))
            link_sql = conn.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name='coursecontentlink'"
            ).scalar_one()
            self.assertNotIn("ck_course_link_match_kind", link_sql)

    def test_observed_legacy_shape_preserves_existing_rows_and_adds_course_schema(self):
        with self.engine.begin() as conn:
            self._create_legacy_schema(conn)
            conn.exec_driver_sql("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.exec_driver_sql(
                "INSERT INTO _meta (key,value) VALUES "
                "('audience_backfilled','existing'),('multiuser_migrated','existing')"
            )
            conn.exec_driver_sql(
                "INSERT INTO user (id,username,password_hash,is_admin,created_at) "
                "VALUES (1,'legacy','x',1,'2026-01-01')"
            )
            conn.exec_driver_sql(
                "INSERT INTO concept (id,slug,track,title,difficulty,tags,summary,lesson_md,source,created_at,"
                "book,chapter,sequence,citation,audience) VALUES "
                "(1,'legacy-concept','DSA','Legacy','core','','summary','lesson','seed','2026-01-01','','',0,'','all')"
            )
            conn.exec_driver_sql(
                "INSERT INTO card (id,concept_id,kind,prompt,choices_json,answer,explanation,source,"
                "introduced,ease,interval_days,repetitions,due_date,last_reviewed,lapses,user_id) VALUES "
                "(1,1,'free','prompt','','answer','explanation','seed',0,2.5,0,0,'2026-01-01',NULL,0,1)"
            )
            before_concept = projection_hash(conn, "SELECT id,slug,track,title,difficulty,tags,summary,lesson_md,source,created_at,book,chapter,sequence,citation,audience FROM concept ORDER BY id")
            before_card = projection_hash(conn, "SELECT id,concept_id,kind,prompt,choices_json,answer,explanation,source,introduced,ease,interval_days,repetitions,due_date,last_reviewed,lapses,user_id FROM card ORDER BY id")

        self._init_twice()

        with self.engine.connect() as conn:
            after_concept = projection_hash(conn, "SELECT id,slug,track,title,difficulty,tags,summary,lesson_md,source,created_at,book,chapter,sequence,citation,audience FROM concept ORDER BY id")
            after_card = projection_hash(conn, "SELECT id,concept_id,kind,prompt,choices_json,answer,explanation,source,introduced,ease,interval_days,repetitions,due_date,last_reviewed,lapses,user_id FROM card ORDER BY id")
            self.assertEqual(after_concept, before_concept)
            self.assertEqual(after_card, before_card)
            concept_columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(concept)")}
            self.assertTrue({"owner_user_id", "book_id"}.issubset(concept_columns))
            self.assertTrue(COURSE_TABLES.issubset(table_names(conn)))
            self.assertEqual(conn.exec_driver_sql("SELECT count(*) FROM courseenrollment").scalar_one(), 0)

    def test_current_owner_scoped_rows_are_unchanged(self):
        with patch("app.db.engine", self.engine):
            db.init_db()
        with self.engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO user (id,username,password_hash,is_admin,level,lang,created_at) "
                "VALUES (1,'owner','x',1,'senior','','2026-01-01')"
            )
            conn.exec_driver_sql(
                "INSERT INTO book (id,user_id,title,original_filename,storage_path,sha256,mime_type,byte_size,"
                "page_count,status,total_sections,completed_sections,error_code,error_message,activated,created_at,updated_at) "
                "VALUES (1,1,'Inference Engineering','i.pdf','private','sha','application/pdf',10,1,'ready',1,1,'','',1,'2026-01-01','2026-01-01')"
            )
            conn.exec_driver_sql(
                "INSERT INTO concept (id,slug,track,title,difficulty,tags,summary,lesson_md,source,audience,created_at,"
                "book,chapter,sequence,citation,owner_user_id,book_id) VALUES "
                "(1,'owned','Inference Engineering','Serving','core','book','summary','lesson','book','senior',"
                "'2026-01-01','Inference Engineering','Serving',1,'p1',1,1)"
            )
            before = projection_hash(conn, "SELECT * FROM book ORDER BY id") + projection_hash(conn, "SELECT * FROM concept ORDER BY id")

        self._init_twice()

        with self.engine.connect() as conn:
            after = projection_hash(conn, "SELECT * FROM book ORDER BY id") + projection_hash(conn, "SELECT * FROM concept ORDER BY id")
            self.assertEqual(after, before)
            self.assertEqual(conn.exec_driver_sql("SELECT count(*) FROM coursecontentlink").scalar_one(), 0)

    def test_marker_failure_does_not_initialize_course_state(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.exec_driver_sql(
                "CREATE TRIGGER reject_course_marker BEFORE INSERT ON _meta "
                f"WHEN NEW.key='{COURSE_MARKER}' BEGIN SELECT RAISE(ABORT, 'marker failure'); END"
            )
        with patch("app.db.engine", self.engine):
            with self.assertRaises(Exception):
                db.init_db()

        with self.engine.connect() as conn:
            marker = conn.exec_driver_sql(
                "SELECT value FROM _meta WHERE key=?", (COURSE_MARKER,)
            ).fetchone()
            self.assertIsNone(marker)
            for table in COURSE_TABLES.intersection(table_names(conn)):
                self.assertEqual(conn.exec_driver_sql(f"SELECT count(*) FROM {table}").scalar_one(), 0)

    def test_schema_validation_rejects_missing_columns_and_unique_constraint(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE courseenrollment (user_id INTEGER)")
            with self.assertRaisesRegex(RuntimeError, "course schema courseenrollment is missing"):
                db._validate_course_schema(conn)
            conn.exec_driver_sql("DROP TABLE courseenrollment")
            conn.exec_driver_sql(
                "CREATE TABLE courseenrollment "
                "(user_id INTEGER, course_key TEXT, catalog_version TEXT)"
            )
            with self.assertRaisesRegex(RuntimeError, "lacks unique index"):
                db._validate_course_schema(conn)

    def test_legacy_progress_is_claimed_once_and_templates_are_minted(self):
        with self.engine.begin() as conn:
            self._create_legacy_schema(conn)
            conn.exec_driver_sql("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.exec_driver_sql(
                "INSERT INTO _meta (key,value) VALUES ('audience_backfilled','existing')"
            )
            conn.exec_driver_sql(
                "INSERT INTO user (id,username,password_hash,is_admin,created_at) "
                "VALUES (7,'legacy-owner','x',1,'2026-01-01')"
            )
            conn.exec_driver_sql(
                "INSERT INTO concept "
                "(id,slug,track,title,difficulty,tags,summary,lesson_md,source,created_at) "
                "VALUES (1,'legacy-owned','DSA','Legacy','core','','','','seed','2026-01-01')"
            )
            conn.exec_driver_sql(
                "INSERT INTO card "
                "(id,concept_id,kind,prompt,choices_json,answer,explanation,source,introduced,"
                "ease,interval_days,repetitions,due_date,last_reviewed,lapses,user_id) "
                "VALUES (1,1,'free','p','','a','','seed',0,2.5,0,0,'2026-01-01',NULL,0,NULL)"
            )

        self._init_twice()

        with self.engine.connect() as conn:
            rows = conn.exec_driver_sql(
                "SELECT user_id, concept_id FROM card ORDER BY user_id IS NULL, user_id"
            ).fetchall()
            self.assertEqual({row[0] for row in rows}, {None, 7})
            self.assertEqual({row[1] for row in rows}, {1})
            marker_count = conn.exec_driver_sql(
                "SELECT count(*) FROM _meta WHERE key='multiuser_migrated'"
            ).scalar_one()
            self.assertEqual(marker_count, 1)

    def test_rebuild_skips_tables_without_legacy_unique_and_session_helper_yields(self):
        with self.engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE daylog "
                "(id INTEGER PRIMARY KEY, day DATE, reviews_done INTEGER, new_learned INTEGER, "
                "correct INTEGER, coding_solved INTEGER, user_id INTEGER)"
            )
            db._rebuild_unique_indexes(conn)
            self.assertNotIn("ux_daylog", conn.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE name='daylog'"
            ).scalar_one())

        with patch("app.db.engine", self.engine):
            generator = db.get_session()
            yielded = next(generator)
            self.assertIsNotNone(yielded)
            generator.close()

    def test_migrate_skips_absent_legacy_table(self):
        with patch("app.db.engine", self.engine):
            db.init_db()
        with self.engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE settings")
        with patch("app.db.engine", self.engine):
            db._migrate()
        with self.engine.connect() as conn:
            self.assertNotIn("settings", table_names(conn))

    def test_multiuser_migration_creates_configured_admin_for_unowned_progress(self):
        with self.engine.begin() as conn:
            self._create_legacy_schema(conn)
            conn.exec_driver_sql(
                "INSERT INTO concept "
                "(id,slug,track,title,difficulty,tags,summary,lesson_md,source,created_at) "
                "VALUES (1,'admin-mint','DSA','Legacy','core','','','','seed','2026-01-01')"
            )
            conn.exec_driver_sql(
                "INSERT INTO card "
                "(id,concept_id,kind,prompt,choices_json,answer,explanation,source,introduced,"
                "ease,interval_days,repetitions,due_date,last_reviewed,lapses,user_id) "
                "VALUES (1,1,'free','p','','a','','seed',0,2.5,0,0,'2026-01-01',NULL,0,NULL)"
            )
        with patch("app.db.engine", self.engine), \
             patch.object(db.settings, "username", "synthetic-admin"), \
             patch.object(db.settings, "password_hash", "synthetic-hash"):
            db.init_db()
            db.init_db()
        with self.engine.connect() as conn:
            admin = conn.exec_driver_sql(
                "SELECT id, username FROM user WHERE is_admin=1"
            ).fetchone()
            self.assertEqual(admin[1], "synthetic-admin")
            self.assertEqual(conn.exec_driver_sql(
                "SELECT user_id FROM card WHERE id=1"
            ).scalar_one(), admin[0])

    def test_multiuser_migration_leaves_unowned_progress_when_no_admin_exists(self):
        with self.engine.begin() as conn:
            self._create_legacy_schema(conn)
            conn.exec_driver_sql(
                "INSERT INTO user (id,username,password_hash,is_admin,created_at) "
                "VALUES (1,'non-admin','x',0,'2026-01-01')"
            )
            conn.exec_driver_sql(
                "INSERT INTO concept "
                "(id,slug,track,title,difficulty,tags,summary,lesson_md,source,created_at) "
                "VALUES (1,'no-admin','DSA','Legacy','core','','','','seed','2026-01-01')"
            )
            conn.exec_driver_sql(
                "INSERT INTO card "
                "(id,concept_id,kind,prompt,choices_json,answer,explanation,source,introduced,"
                "ease,interval_days,repetitions,due_date,last_reviewed,lapses,user_id) "
                "VALUES (1,1,'free','p','','a','','seed',0,2.5,0,0,'2026-01-01',NULL,0,NULL)"
            )
        with patch("app.db.engine", self.engine), patch.object(db.settings, "password_hash", ""):
            db.init_db()
        with self.engine.connect() as conn:
            self.assertIsNone(conn.exec_driver_sql(
                "SELECT user_id FROM card WHERE id=1"
            ).scalar_one())

    @staticmethod
    def _create_legacy_schema(conn) -> None:
        statements = (
            "CREATE TABLE user (id INTEGER PRIMARY KEY, username VARCHAR UNIQUE NOT NULL, password_hash VARCHAR NOT NULL, is_admin BOOLEAN NOT NULL, created_at DATETIME NOT NULL)",
            "CREATE TABLE concept (id INTEGER PRIMARY KEY, slug VARCHAR UNIQUE NOT NULL, track VARCHAR NOT NULL, title VARCHAR NOT NULL, difficulty VARCHAR NOT NULL, tags VARCHAR NOT NULL, summary VARCHAR NOT NULL, lesson_md VARCHAR NOT NULL, source VARCHAR NOT NULL, created_at DATETIME NOT NULL, book VARCHAR DEFAULT '', chapter VARCHAR DEFAULT '', sequence INTEGER DEFAULT 0, citation VARCHAR DEFAULT '', audience VARCHAR DEFAULT 'all')",
            "CREATE TABLE card (id INTEGER PRIMARY KEY, concept_id INTEGER NOT NULL, kind VARCHAR NOT NULL, prompt VARCHAR NOT NULL, choices_json VARCHAR NOT NULL, answer VARCHAR NOT NULL, explanation VARCHAR NOT NULL, source VARCHAR NOT NULL, introduced BOOLEAN NOT NULL, ease FLOAT NOT NULL, interval_days INTEGER NOT NULL, repetitions INTEGER NOT NULL, due_date DATE NOT NULL, last_reviewed DATETIME, lapses INTEGER NOT NULL, user_id INTEGER)",
            "CREATE TABLE attempt (id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL, concept_id INTEGER NOT NULL, track VARCHAR NOT NULL, grade INTEGER NOT NULL, correct BOOLEAN NOT NULL, user_answer VARCHAR NOT NULL, ai_feedback VARCHAR NOT NULL, created_at DATETIME NOT NULL, user_id INTEGER)",
            "CREATE TABLE daylog (id INTEGER PRIMARY KEY, day DATE UNIQUE NOT NULL, reviews_done INTEGER NOT NULL, new_learned INTEGER NOT NULL, correct INTEGER NOT NULL, coding_solved INTEGER DEFAULT 0, user_id INTEGER)",
            "CREATE TABLE mocksession (id INTEGER PRIMARY KEY, user_id INTEGER, kind VARCHAR NOT NULL, topic VARCHAR NOT NULL, difficulty VARCHAR NOT NULL, duration_min INTEGER NOT NULL, transcript_json VARCHAR NOT NULL, rubric_json VARCHAR NOT NULL, status VARCHAR NOT NULL, started_at DATETIME NOT NULL, ended_at DATETIME)",
            "CREATE TABLE problemstatus (id INTEGER PRIMARY KEY, problem_id INTEGER UNIQUE NOT NULL, status VARCHAR NOT NULL, confidence INTEGER NOT NULL, notes VARCHAR NOT NULL, times_reviewed INTEGER NOT NULL, last_touched DATETIME, revisit_date DATE, user_id INTEGER)",
            "CREATE TABLE settings (id INTEGER PRIMARY KEY, user_id INTEGER, daily_problem_target INTEGER NOT NULL, goal_total INTEGER NOT NULL, goal_date DATE)",
        )
        for statement in statements:
            conn.exec_driver_sql(statement)


if __name__ == "__main__":
    unittest.main()
