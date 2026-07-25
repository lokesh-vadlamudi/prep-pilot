"""Database models: the curriculum, spaced-repetition cards, and study history."""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlmodel import SQLModel, Field


def utcnow() -> datetime:
    return datetime.utcnow()


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
    created_at: datetime = Field(default_factory=utcnow)
    # --- book-ingestion fields (source == "book") ---
    book: str = Field(default="", index=True)   # book title ("" for non-book concepts)
    chapter: str = ""                           # chapter/section label
    sequence: int = 0                           # study order; 0 = legacy (studied after books)
    citation: str = ""                          # e.g. "Inference Engineering, Ch.1 (p25-30)"


class Card(SQLModel, table=True):
    """A spaced-repetition question attached to a concept."""
    id: Optional[int] = Field(default=None, primary_key=True)
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
    card_id: int = Field(index=True, foreign_key="card.id")
    concept_id: int = Field(index=True)
    track: str = ""
    grade: int = 0                          # SM-2 quality 0..5
    correct: bool = False
    user_answer: str = ""
    ai_feedback: str = ""
    created_at: datetime = Field(default_factory=utcnow, index=True)


class DayLog(SQLModel, table=True):
    """One row per calendar day the user studied — powers the streak."""
    id: Optional[int] = Field(default=None, primary_key=True)
    day: date = Field(index=True, unique=True)
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
    """Single-row app settings (id always 1)."""
    id: Optional[int] = Field(default=1, primary_key=True)
    daily_problem_target: int = 2
    goal_total: int = 150
    goal_date: Optional[date] = None


class ProblemStatus(SQLModel, table=True):
    """Per-problem progress: solved state, confidence, spaced revision."""
    id: Optional[int] = Field(default=None, primary_key=True)
    problem_id: int = Field(index=True, unique=True, foreign_key="problem.id")
    status: str = "todo"                   # todo | attempted | solved
    confidence: int = 0                    # 0..3 self-rated recall
    notes: str = ""
    times_reviewed: int = 0
    last_touched: Optional[datetime] = None
    # spaced revision: when this solved problem should be resurfaced
    revisit_date: Optional[date] = None
