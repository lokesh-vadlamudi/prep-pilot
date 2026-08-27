"""Database models: users, the curriculum, spaced-repetition cards, and study history."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlmodel import SQLModel, Field, UniqueConstraint


def utcnow() -> datetime:
    return datetime.utcnow()


class User(SQLModel, table=True):
    """An account. Content (concepts/problems) is shared; progress is per-user."""
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    password_hash: str = ""
    is_admin: bool = False
    # Learner profile: tunes curriculum selection and every AI interaction.
    level: str = "senior"                   # senior | newgrad
    lang: str = ""                          # preferred language for examples ("python", ...)
    created_at: datetime = Field(default_factory=utcnow)


class LoginAudit(SQLModel, table=True):
    """Privacy-minimal authentication/activity audit, capped at one event per user/day."""
    __table_args__ = (UniqueConstraint("user_id", "event", "day", name="ux_login_audit_user_event_day"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    event: str = Field(index=True)  # login | active
    day: date = Field(index=True)
    occurred_at: datetime = Field(default_factory=utcnow, index=True)


class Concept(SQLModel, table=True):
    """A single teachable idea (e.g. 'Consistent hashing', 'Two-pointer technique')."""
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    track: str = Field(index=True)          # DSA | System Design | CS Fundamentals | Behavioral
    title: str
    difficulty: str = "core"                # intro | core | advanced
    tags: str = ""                          # comma-separated: go,python,aws,...
    summary: str = ""                       # short one-liner
    lesson_md: str = ""                     # full markdown lesson (curated or AI-authored)
    source: str = "seed"                    # seed | ai | book
    audience: str = Field(default="all", index=True)  # all | senior | newgrad
    created_at: datetime = Field(default_factory=utcnow)
    # --- book-ingestion fields (source == "book") ---
    book: str = Field(default="", index=True)   # book title ("" for non-book concepts)
    chapter: str = ""                           # chapter/section label
    sequence: int = 0                           # study order; 0 = legacy (studied after books)
    citation: str = ""                          # e.g. "Inference Engineering, Ch.1 (p25-30)"
    owner_user_id: Optional[int] = Field(default=None, index=True, foreign_key="user.id")
    book_id: Optional[int] = Field(default=None, index=True, foreign_key="book.id")


class Book(SQLModel, table=True):
    """A private, user-uploaded source document."""
    __table_args__ = (UniqueConstraint("user_id", "sha256", name="ux_book_user_sha"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    title: str
    original_filename: str
    storage_path: str
    sha256: str = Field(index=True)
    mime_type: str = "application/pdf"
    byte_size: int = 0
    page_count: int = 0
    status: str = Field(default="queued", index=True)
    total_sections: int = 0
    completed_sections: int = 0
    error_code: str = ""
    error_message: str = ""
    activated: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class IngestionSection(SQLModel, table=True):
    """Persistent extraction/generation checkpoint for one bounded source section."""
    __table_args__ = (UniqueConstraint("book_id", "ordinal", name="ux_section_book_ordinal"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(index=True, foreign_key="book.id")
    ordinal: int
    chapter: str
    label: str
    page_start: int
    page_end: int
    citation: str
    extracted_text: str
    content_hash: str
    status: str = Field(default="pending", index=True)
    attempt_count: int = 0
    error_message: str = ""
    concept_id: Optional[int] = Field(default=None, foreign_key="concept.id")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class BookChatMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(index=True, foreign_key="book.id")
    user_id: int = Field(index=True, foreign_key="user.id")
    role: str
    content: str
    citations_json: str = "[]"
    created_at: datetime = Field(default_factory=utcnow)


class Card(SQLModel, table=True):
    """A spaced-repetition question attached to a concept.

    user_id NULL = a content template; each user gets their own copy (with its
    own SM-2 state), synced lazily from templates.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True, foreign_key="user.id")
    concept_id: int = Field(index=True, foreign_key="concept.id")
    kind: str = "mcq"                       # mcq | free | code
    prompt: str = ""
    choices_json: str = ""                  # JSON list for mcq
    answer: str = ""                        # correct choice / reference answer
    explanation: str = ""
    source: str = "seed"

    # --- SM-2 scheduling state ---
    introduced: bool = False
    ease: float = 2.5
    interval_days: int = 0
    repetitions: int = 0
    due_date: date = Field(default_factory=lambda: date.today())
    last_reviewed: Optional[datetime] = None
    lapses: int = 0


class Attempt(SQLModel, table=True):
    """One answered review — the raw learning-progress record."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True, foreign_key="user.id")
    card_id: int = Field(index=True, foreign_key="card.id")
    concept_id: int = Field(index=True)
    track: str = ""
    grade: int = 0                          # SM-2 quality 0..5
    correct: bool = False
    user_answer: str = ""
    ai_feedback: str = ""
    created_at: datetime = Field(default_factory=utcnow, index=True)


class DayLog(SQLModel, table=True):
    """One row per user per calendar day studied — powers the streak."""
    __table_args__ = (UniqueConstraint("user_id", "day", name="ux_daylog_user_day"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True, foreign_key="user.id")
    day: date = Field(index=True)
    reviews_done: int = 0
    new_learned: int = 0
    correct: int = 0
    coding_solved: int = 0                  # coding problems solved this day


class Problem(SQLModel, table=True):
    """A curated coding-interview problem (e.g. Blind 75)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(index=True, unique=True)
    collection: str = Field(default="", index=True)  # comma tags: "neetcode150,blind75"
    order_idx: int = 0
    title: str = ""
    category: str = Field(index=True)      # Array | Tree | Graph | ...
    difficulty: str = "Medium"             # Easy | Medium | Hard
    url: str = ""                          # official LeetCode link
    blurb: str = ""                        # short task description (our words)
    pattern: str = ""                      # short technique hint (curated)
    approach_md: str = ""                  # full worked approach (AI-authored, cached lazily)


class ProblemHarness(SQLModel, table=True):
    """AI-generated starter code + test driver for a problem+language (cached)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    problem_id: int = Field(index=True, foreign_key="problem.id")
    language: str = Field(index=True)          # python | javascript
    entry_name: str = ""                       # function the user must implement
    starter_code: str = ""
    driver_code: str = ""
    reference_code: str = ""                   # correct impl; the oracle for expected outputs
    expected_json: str = ""                    # cached {labels, outputs} from running the reference
    validated: bool = False                    # reference ran cleanly through the driver
    created_at: datetime = Field(default_factory=utcnow)


class ProblemHints(SQLModel, table=True):
    """Cached progressive hint ladder for a problem (language-agnostic)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    problem_id: int = Field(index=True, unique=True, foreign_key="problem.id")
    hints_json: str = ""                       # JSON list of escalating hint strings
    created_at: datetime = Field(default_factory=utcnow)


class MockSession(SQLModel, table=True):
    """A timed mock-interview session with the DGX as interviewer."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True, foreign_key="user.id")
    kind: str = "coding"                    # coding | system_design | behavioral
    topic: str = ""                         # optional focus (e.g. "graphs", "design a chat app")
    difficulty: str = "senior"
    duration_min: int = 40
    transcript_json: str = "[]"             # [{role: interviewer|candidate, content}]
    rubric_json: str = ""                   # scoring result once finished
    status: str = "active"                  # active | done
    started_at: datetime = Field(default_factory=utcnow, index=True)
    ended_at: Optional[datetime] = None


class Settings(SQLModel, table=True):
    """Per-user app settings (one row per user)."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True, foreign_key="user.id")
    daily_problem_target: int = 2
    daily_application_target: int = 5
    goal_total: int = 150
    goal_date: Optional[date] = None


class JobApplication(SQLModel, table=True):
    """A manually tracked job lead or application owned by one user."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    company: str = Field(index=True)
    role: str
    job_url: str = ""
    location: str = ""
    status: str = Field(default="saved", index=True)
    applied_date: Optional[date] = Field(default=None, index=True)
    follow_up_date: Optional[date] = Field(default=None, index=True)
    notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ProblemStatus(SQLModel, table=True):
    """Per-user, per-problem progress: solved state, confidence, spaced revision."""
    __table_args__ = (UniqueConstraint("user_id", "problem_id", name="ux_status_user_problem"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True, foreign_key="user.id")
    problem_id: int = Field(index=True, foreign_key="problem.id")
    status: str = "todo"                   # todo | attempted | solved
    confidence: int = 0                    # 0..3 self-rated recall
    notes: str = ""
    times_reviewed: int = 0
    last_touched: Optional[datetime] = None
    solved_date: Optional[date] = Field(default=None, index=True)
    # spaced revision: when this solved problem should be resurfaced
    revisit_date: Optional[date] = None


class ConceptStatus(SQLModel, table=True):
    """Per-user manual completion state for syllabus concepts."""
    __table_args__ = (UniqueConstraint("user_id", "concept_id", name="ux_status_user_concept"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    concept_id: int = Field(index=True, foreign_key="concept.id")
    completed: bool = False
    completed_at: Optional[datetime] = None
