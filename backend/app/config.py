"""Application settings, loaded from environment / .env."""
from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # .../backend
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _lexical_path(path: Path, backend_dir: Path) -> Path:
    expanded = path.expanduser()
    if not expanded.is_absolute():
        expanded = backend_dir / expanded
    return Path(os.path.abspath(expanded))


def _has_symlink_component(path: Path, boundary: Path) -> bool:
    absolute = path.expanduser().absolute()
    floor = boundary.expanduser().absolute().parent
    return any(
        component.is_symlink()
        for component in (absolute, *absolute.parents)
        if component.is_relative_to(floor)
    )


def _isolated_path(path: Path, backend_dir: Path) -> bool:
    backend = _lexical_path(backend_dir, Path.cwd())
    expected = backend / "data"
    candidate = _lexical_path(path, backend)
    if any(_has_symlink_component(item, backend.parent) for item in (backend, expected, candidate)):
        return False
    return candidate.is_relative_to(expected) and candidate.resolve().is_relative_to(expected.resolve())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    # --- Auth (single user) ---
    username: str = "lokesh"
    # bcrypt hash of the login password; generated on first setup if empty.
    password_hash: str = ""
    # Signs the session cookie. Auto-generated & persisted if empty.
    secret_key: str = ""
    # Shared key for /api/roadmap/brief (Alfred's reminder cron). Auto-generated.
    reminder_key: str = ""
    # Code new users must present to register. Auto-generated.
    invite_code: str = ""

    # --- LLM brain (OpenAI-compatible API, served locally by vLLM) ---
    llm_base_url: str = "http://100.127.76.17:8000/v1"
    # This must exactly match an ID served by the DGX `/v1/models` endpoint.
    # Colon-style Ollama names are interpreted as model/adapter requests by vLLM.
    model: str = "qwen3.8-27b"
    llm_timeout: float = 120.0

    # --- Storage ---
    database_url: str = f"sqlite:///{DATA_DIR / 'prep.db'}"
    book_storage_dir: str = str(DATA_DIR / "books")
    max_book_bytes: int = 50 * 1024 * 1024
    max_book_pages: int = 500

    # --- Runtime environment ---
    environment: str = "production"      # production | development
    release: str = "local"               # git tag or short commit shown in the UI
    cookie_name: str = "prep_session"     # dev must differ: cookies ignore ports
    scheduler_enabled: bool = True         # disabled in dev to avoid duplicate jobs

    # --- Learning ---
    new_topics_per_day: int = 3          # fresh concepts introduced daily
    max_reviews_per_day: int = 25        # cap on due reviews shown per day
    daily_generation_hour: int = 4       # local hour for the nightly content job

    def dev_storage_attestation(self, backend_dir: Path = BASE_DIR) -> dict[str, bool]:
        """Report booleans only; never expose configured private filesystem paths."""
        database = self._sqlite_database_path()
        database_safe = database is not None and _isolated_path(database, backend_dir)
        books_safe = _isolated_path(Path(self.book_storage_dir), backend_dir)
        return {
            "dev_database_isolated": self.environment == "development" and database_safe,
            "dev_book_storage_isolated": self.environment == "development" and books_safe,
        }

    def require_dev_storage_isolation(self, backend_dir: Path = BASE_DIR) -> None:
        if self.environment != "development":
            return
        if not all(self.dev_storage_attestation(backend_dir).values()):
            raise RuntimeError("development storage isolation check failed")

    def _sqlite_database_path(self) -> Path | None:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            return None
        value = self.database_url[len(prefix):]
        if not value or value == ":memory:":
            return None
        return Path(value).expanduser()


settings = Settings()
