from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.main import health


class DevelopmentIsolationTests(unittest.TestCase):
    def settings(self, backend: Path, database: Path, books: Path) -> Settings:
        return Settings(
            _env_file=None,
            environment="development",
            database_url=f"sqlite:///{database}",
            book_storage_dir=str(books),
            scheduler_enabled=False,
        )

    def test_contained_dev_storage_attests_without_disclosing_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = Path(directory) / "prep-pilot-dev" / "backend"
            data = backend / "data"
            data.mkdir(parents=True)
            candidate = self.settings(backend, data / "prep.db", data / "books")

            self.assertEqual(candidate.dev_storage_attestation(backend), {
                "dev_database_isolated": True,
                "dev_book_storage_isolated": True,
            })
            candidate.require_dev_storage_isolation(backend)
            with patch("app.main.settings", candidate), patch("app.main.BASE_DIR", backend):
                result = health()
            self.assertTrue(result["dev_database_isolated"])
            self.assertTrue(result["dev_book_storage_isolated"])
            self.assertNotIn(str(data), repr(result))

            relative = Settings(
                _env_file=None,
                environment="development",
                database_url="sqlite:///data/prep.db",
                book_storage_dir="data/books",
                scheduler_enabled=False,
            )
            relative.require_dev_storage_isolation(backend)

    def test_preserved_env_paths_non_sqlite_and_symlink_escapes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            backend = root / "prep-pilot-dev" / "backend"
            data = backend / "data"
            production = root / "prep-pilot" / "backend" / "data"
            data.mkdir(parents=True)
            production.mkdir(parents=True)
            escape = data / "escape"
            escape.symlink_to(production, target_is_directory=True)
            aliased_dev = root / "prep-pilot-dev-alias"
            aliased_dev.symlink_to(root / "prep-pilot", target_is_directory=True)
            aliased_backend = aliased_dev / "backend"
            candidates = [
                self.settings(backend, production / "prep.db", data / "books"),
                self.settings(backend, data / "prep.db", production / "books"),
                self.settings(backend, data / "prep.db", escape / "books"),
                self.settings(
                    aliased_backend,
                    aliased_backend / "data" / "prep.db",
                    aliased_backend / "data" / "books",
                ),
                Settings(
                    _env_file=None, environment="development",
                    database_url="postgresql://db/prep", book_storage_dir=str(data / "books"),
                    scheduler_enabled=False,
                ),
                Settings(
                    _env_file=None, environment="development",
                    database_url="sqlite:///:memory:", book_storage_dir=str(data / "books"),
                    scheduler_enabled=False,
                ),
            ]
            for candidate in candidates:
                with self.subTest(candidate=candidate.database_url):
                    with self.assertRaisesRegex(RuntimeError, "development storage isolation"):
                        candidate.require_dev_storage_isolation(backend)


if __name__ == "__main__":
    unittest.main()
