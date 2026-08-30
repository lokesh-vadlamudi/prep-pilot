"""Database models: users, the curriculum, spaced-repetition cards, and study history."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Column, text
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
    """A user-uploaded source document that is private unless its owner shares it."""
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
    shared_with_all: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("0"), index=True),
    )
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


class BookReadingProgress(SQLModel, table=True):
    """Last committed page for one user-owned book."""
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="ux_book_progress_user_book"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    book_id: int = Field(index=True, foreign_key="book.id")
    page_number: int = 1
    updated_at: datetime = Field(default_factory=utcnow)


class BookBookmark(SQLModel, table=True):
    """One private optional note for one page in a user-owned book."""
    __table_args__ = (
        UniqueConstraint(
            "user_id", "book_id", "page_number", name="ux_bookmark_user_book_page",
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    book_id: int = Field(index=True, foreign_key="book.id")
    page_number: int
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


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


class CourseEnrollment(SQLModel, table=True):
    """Explicit opt-in to one immutable course catalog."""
    __table_args__ = (
        UniqueConstraint("user_id", "course_key", name="ux_course_enrollment_user_course"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    course_key: str = Field(index=True, max_length=100)
    catalog_version: str = Field(max_length=40)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class CourseMissionProgress(SQLModel, table=True):
    """Derived, nonnumeric state for one learner and course mission."""
    __table_args__ = (
        UniqueConstraint("user_id", "mission_id", name="ux_course_progress_user_mission"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    mission_id: str = Field(index=True, max_length=40)
    state: str = Field(default="not_started", max_length=40)
    completed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=utcnow)


class CourseArtifactEvidence(SQLModel, table=True):
    """Metadata for a learner-owned artifact; referenced content is never read."""
    __table_args__ = (
        UniqueConstraint("user_id", "artifact_id", name="ux_course_artifact_user_artifact"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    mission_id: str = Field(index=True, max_length=40)
    artifact_id: str = Field(index=True, max_length=80)
    note: str = Field(default="", max_length=5000)
    artifact_uri: str = Field(default="", max_length=2048)
    template_key: str = Field(default="", max_length=100)
    output_format: str = Field(default="", max_length=20)
    draft_json: str = Field(default="{}", max_length=30000)
    rubric_json: str = Field(default="[]", max_length=20000)
    source_ids_json: str = Field(default="[]", max_length=20000)
    catalog_version: str = Field(default="", max_length=40)
    revision: int = 1
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class CourseCheckpointAttempt(SQLModel, table=True):
    """One qualitative checkpoint submission; request IDs preserve genuine retries."""
    __table_args__ = (
        UniqueConstraint(
            "user_id", "checkpoint_id", "request_id",
            name="ux_course_checkpoint_user_checkpoint_request",
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    checkpoint_id: str = Field(index=True, max_length=80)
    request_id: str = Field(max_length=100)
    payload_sha256: str = Field(max_length=64)
    answers_json: str = Field(default="{}", max_length=20000)
    passed: bool = False
    feedback: str = Field(default="", max_length=5000)
    response_json: str = Field(default="{}", max_length=20000)
    created_at: datetime = Field(default_factory=utcnow)


class CourseOralTurn(SQLModel, table=True):
    """One persisted oral-practice turn with a durable client identity."""
    __table_args__ = (
        UniqueConstraint(
            "user_id", "mission_id", "turn_id", name="ux_course_oral_user_mission_turn"
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    mission_id: str = Field(index=True, max_length=40)
    turn_id: str = Field(max_length=100)
    payload_sha256: str = Field(max_length=64)
    prompt: str = Field(default="", max_length=4000)
    response: str = Field(default="", max_length=4000)
    feedback: str = Field(default="", max_length=4000)
    next_question: str = Field(default="", max_length=4000)
    response_json: str = Field(default="{}", max_length=20000)
    created_at: datetime = Field(default_factory=utcnow)


class CourseOralReview(SQLModel, table=True):
    """Nonnumeric review state for online or self-recorded oral practice."""
    __table_args__ = (
        UniqueConstraint("user_id", "mission_id", name="ux_course_oral_review_user_mission"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    mission_id: str = Field(index=True, max_length=40)
    state: str = Field(default="not_started", max_length=40)
    mode: str = Field(default="", max_length=40)
    self_record_note: str = Field(default="", max_length=5000)
    rubric_acknowledgements_json: str = Field(default="[]", max_length=10000)
    review_method: str = Field(default="", max_length=40)
    review_feedback: str = Field(default="", max_length=5000)
    attempt_recorded_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    revision: int = 0
    updated_at: datetime = Field(default_factory=utcnow)


class CourseContentLink(SQLModel, table=True):
    """A reversible pointer from a course module to already-visible content."""
    __table_args__ = (
        UniqueConstraint("user_id", "module_id", name="ux_course_link_user_module"),
        CheckConstraint(
            "match_kind IN ('owned_exact','legacy_exact','explicit_supplement_alias')",
            name="ck_course_link_match_kind",
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    module_id: str = Field(index=True, max_length=40)
    concept_id: int = Field(index=True, foreign_key="concept.id")
    match_kind: str = Field(max_length=40)
    candidate_fingerprint: str = Field(max_length=64)
    confirmed_at: datetime = Field(default_factory=utcnow)
    revision: int = 1


class CourseMutationReceipt(SQLModel, table=True):
    """Immutable replay ledger retained for the lifetime of an enrollment."""
    __table_args__ = (
        UniqueConstraint(
            "user_id", "course_key", "operation", "request_id",
            name="ux_course_receipt_user_course_operation_request",
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, foreign_key="user.id")
    course_key: str = Field(index=True, max_length=100)
    operation: str = Field(index=True, max_length=60)
    request_id: str = Field(max_length=100)
    resource_key: str = Field(max_length=200)
    payload_sha256: str = Field(max_length=64)
    status_code: int
    response_json: str = Field(max_length=30000)
    created_at: datetime = Field(default_factory=utcnow, index=True)
