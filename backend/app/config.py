"""Application settings, loaded from environment / .env."""
from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # .../backend
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


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


settings = Settings()
