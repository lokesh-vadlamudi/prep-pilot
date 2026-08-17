"""Blind 75 coding problems: list, detail, approach (AI-cached), progress, coaching."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func

from ..auth import RequireUser
from ..db import get_session
from ..models import Problem, ProblemStatus, ProblemHarness, ProblemHints, Settings, User
from ..content.neetcode150 import CATEGORY_ORDER
from ..content.cheatsheets import CHEATSHEETS, cheatsheet_for
from .. import tutor, executor, service

router = APIRouter(prefix="/api/problems", tags=["problems"], dependencies=[RequireUser])

# Revision spacing (days) by confidence 0..3 after solving.
_REVISIT = {0: 3, 1: 7, 2: 21, 3: 60}


def _status_for(session: Session, user_id: int, pid: int) -> ProblemStatus:
    st = session.exec(select(ProblemStatus).where(
        ProblemStatus.user_id == user_id, ProblemStatus.problem_id == pid)).first()
    if not st:
        st = ProblemStatus(user_id=user_id, problem_id=pid)
        session.add(st)
        session.commit()
        session.refresh(st)
    return st


@router.get("")
def list_problems(user: User = RequireUser, session: Session = Depends(get_session)):
    problems = session.exec(select(Problem).order_by(Problem.order_idx)).all()
    statuses = {s.problem_id: s for s in session.exec(
        select(ProblemStatus).where(ProblemStatus.user_id == user.id)).all()}
    solved = sum(1 for s in statuses.values() if s.status == "solved")
    items = []
    for p in problems:
        st = statuses.get(p.id)
        tags = p.collection.split(",") if p.collection else []
        items.append({
            "id": p.id, "slug": p.slug, "title": p.title, "category": p.category,
            "difficulty": p.difficulty, "url": p.url, "blurb": p.blurb, "pattern": p.pattern,
            "status": st.status if st else "todo",
            "confidence": st.confidence if st else 0,
            "has_approach": bool(p.approach_md),
            "in_blind75": "blind75" in tags,
        })
    blind75_total = sum(1 for it in items if it["in_blind75"])
    blind75_solved = sum(1 for it in items if it["in_blind75"] and it["status"] == "solved")
    return {
        "total": len(problems), "solved": solved,
        "blind75_total": blind75_total, "blind75_solved": blind75_solved,
        "category_order": CATEGORY_ORDER, "problems": items,
        "cheatsheets": CHEATSHEETS,
    }


@router.get("/cheatsheet/{category:path}")
def cheatsheet(category: str):
    cs = cheatsheet_for(category)
    if not cs:
        raise HTTPException(404, "No cheatsheet for that category")
    return {"category": category, **cs}


def pick_problem_of_the_day(session: Session, user_id: int) -> tuple[str, Problem | None]:
    """A due revision if any; else the next unsolved, preferring the current
    flight-plan leg's categories; else any unsolved."""
    from ..content import roadmap as rm

    today = date.today()
    # 1) a solved problem due for revision
    due = session.exec(
        select(Problem).join(ProblemStatus, ProblemStatus.problem_id == Problem.id)
        .where(ProblemStatus.user_id == user_id,
               ProblemStatus.status == "solved", ProblemStatus.revisit_date <= today)
        .order_by(ProblemStatus.revisit_date)
    ).first()
    if due:
        return "revision", due
    # 2) next unsolved (no status row, or status != solved)
    solved_ids = [s.problem_id for s in session.exec(
        select(ProblemStatus).where(ProblemStatus.user_id == user_id,
                                    ProblemStatus.status == "solved")).all()]
    q = select(Problem).order_by(Problem.order_idx)
    if solved_ids:
        q = q.where(Problem.id.notin_(solved_ids))  # type: ignore[attr-defined]
    # Prefer the current leg's categories so daily picks follow the roadmap.
    cats = rm.PHASES[rm.phase_index(today)]["categories"]
    if cats:
        on_phase = session.exec(q.where(Problem.category.in_(cats))).first()  # type: ignore[attr-defined]
        if on_phase:
            return "phase", on_phase
    return "new", session.exec(q).first()


@router.get("/of-the-day")
def problem_of_the_day(user: User = RequireUser, session: Session = Depends(get_session)):
    """Pick one problem for today (revision > current leg > next unsolved)."""
    reason, due = pick_problem_of_the_day(session, user.id)
    if not due:
        return {"problem": None}
    return {"reason": reason, "problem": {
        "id": due.id, "title": due.title, "category": due.category,
        "difficulty": due.difficulty, "url": due.url, "blurb": due.blurb, "pattern": due.pattern,
    }}


@router.get("/{pid}")
def get_problem(pid: int, user: User = RequireUser, session: Session = Depends(get_session)):
    p = session.get(Problem, pid)
    if not p:
        raise HTTPException(404, "Problem not found")
    st = _status_for(session, user.id, pid)
    return {
        "id": p.id, "slug": p.slug, "title": p.title, "category": p.category,
        "difficulty": p.difficulty, "url": p.url, "blurb": p.blurb, "pattern": p.pattern,
        "has_approach": bool(p.approach_md),
        "status": st.status, "confidence": st.confidence, "notes": st.notes,
    }


@router.post("/{pid}/approach")
async def get_approach(pid: int, session: Session = Depends(get_session)):
    """Return the worked approach, authoring + caching it via the DGX model on first request."""
    p = session.get(Problem, pid)
    if not p:
        raise HTTPException(404, "Problem not found")
    if not p.approach_md:
        p.approach_md = await tutor.author_approach(p.title, p.category, p.difficulty, p.pattern)
        session.add(p)
        session.commit()
    return {"approach_md": p.approach_md}


class StatusIn(BaseModel):
    status: str | None = None          # todo | attempted | solved
    confidence: int | None = None      # 0..3
    notes: str | None = Field(default=None, max_length=4000)


@router.post("/{pid}/status")
def set_status(pid: int, body: StatusIn, user: User = RequireUser,
               session: Session = Depends(get_session)):
    p = session.get(Problem, pid)
    if not p:
        raise HTTPException(404, "Problem not found")
    st = _status_for(session, user.id, pid)
    was_solved = st.status == "solved"
    if body.status is not None:
        st.status = body.status
    if body.confidence is not None:
        st.confidence = max(0, min(3, body.confidence))
    if body.notes is not None:
        st.notes = body.notes
    st.last_touched = datetime.utcnow()
    if st.status == "solved":
        st.times_reviewed += 1
        st.revisit_date = date.today() + timedelta(days=_REVISIT.get(st.confidence, 7))
        if not was_solved:
            # First time solved today → count toward the daily ritual / streak.
            service.record_coding_solve(session, user.id)
    session.add(st)
    session.commit()
    return {"ok": True, "status": st.status, "confidence": st.confidence,
            "revisit_date": st.revisit_date.isoformat() if st.revisit_date else None}


class CoachIn(BaseModel):
    plan: str = Field(max_length=4000)


@router.post("/{pid}/coach")
async def coach(pid: int, body: CoachIn, user: User = RequireUser,
                session: Session = Depends(get_session)):
    p = session.get(Problem, pid)
    if not p:
        raise HTTPException(404, "Problem not found")
    return await tutor.coach_problem(p.title, p.pattern, body.plan,
                                     learner=tutor.learner_context(user))


@router.get("/{pid}/hints")
async def hints(pid: int, session: Session = Depends(get_session)):
    """Return the escalating hint ladder, generating + caching it on first request."""
    p = session.get(Problem, pid)
    if not p:
        raise HTTPException(404, "Problem not found")
    row = session.exec(select(ProblemHints).where(ProblemHints.problem_id == pid)).first()
    cached = json.loads(row.hints_json) if (row and row.hints_json) else []
    if cached:
        return {"hints": cached}
    # Generate (retry — model occasionally returns an empty/garbled ladder).
    ladder = []
    for _ in range(3):
        try:
            ladder = await tutor.generate_hint_ladder(p.title, p.category, p.difficulty, p.pattern)
        except Exception:  # noqa: BLE001
            ladder = []
        if ladder:
            break
    if ladder:  # only cache a good ladder, so a transient failure can retry later
        if row:
            row.hints_json = json.dumps(ladder)
        else:
            row = ProblemHints(problem_id=pid, hints_json=json.dumps(ladder))
        session.add(row)
        session.commit()
    return {"hints": ladder}


def _harness(session: Session, pid: int, language: str) -> ProblemHarness | None:
    return session.exec(
        select(ProblemHarness).where(
            ProblemHarness.problem_id == pid, ProblemHarness.language == language)
    ).first()


async def _build_harness(session: Session, p: Problem, language: str) -> ProblemHarness:
    """Generate a harness, run the reference to derive+cache expected outputs.

    Retries once if the reference doesn't run cleanly through the driver.
    """
    best, expected, validated = None, None, False
    for _ in range(3):
        try:
            cand = await tutor.generate_harness(p.title, p.category, p.difficulty, p.pattern, language)
        except Exception:  # noqa: BLE001 — malformed model JSON etc.; retry
            continue
        best = cand
        cap = executor.run_capture(language, cand["reference_code"], cand["driver_code"])
        payload = cap.get("captured")
        if payload and isinstance(payload.get("outputs"), list) and payload["outputs"]:
            errs = sum(1 for o in payload["outputs"] if isinstance(o, dict) and "__error__" in o)
            if errs == 0:
                expected, validated = payload, True
                break
            expected = payload  # keep as fallback
    if best is None:
        raise HTTPException(503, "Couldn't prepare tests for this problem right now — the DGX brain "
                                 "may be busy. Try again, or use the mentor and approach instead.")
    h = ProblemHarness(
        problem_id=p.id, language=language, entry_name=best["entry_name"],
        starter_code=best["starter_code"], driver_code=best["driver_code"],
        reference_code=best["reference_code"],
        expected_json=json.dumps(expected) if expected else "",
        validated=validated,
    )
    session.add(h)
    session.commit()
    session.refresh(h)
    return h


@router.get("/{pid}/starter")
async def starter(pid: int, language: str = "python", session: Session = Depends(get_session)):
    """Return starter code for the editor, generating + caching the harness if needed."""
    p = session.get(Problem, pid)
    if not p:
        raise HTTPException(404, "Problem not found")
    if not executor.language_available(language):
        raise HTTPException(400, f"{language} not available")
    h = _harness(session, pid, language) or await _build_harness(session, p, language)
    return {"language": language, "entry_name": h.entry_name,
            "starter_code": h.starter_code, "validated": h.validated}


class RunIn(BaseModel):
    language: str = "python"
    code: str = Field(max_length=50000)


@router.post("/{pid}/run")
async def run(pid: int, body: RunIn, user: User = RequireUser,
              session: Session = Depends(get_session)):
    p = session.get(Problem, pid)
    if not p:
        raise HTTPException(404, "Problem not found")
    if not executor.language_available(body.language):
        raise HTTPException(400, f"{body.language} not available")
    h = _harness(session, pid, body.language) or await _build_harness(session, p, body.language)
    cap = executor.run_capture(body.language, body.code, h.driver_code)
    result = {k: cap[k] for k in ("ok", "timed_out", "exit_code", "stdout", "stderr", "duration_ms")}
    result["harness_validated"] = h.validated

    expected = json.loads(h.expected_json) if h.expected_json else None
    got = cap.get("captured")
    cases = []
    if expected and got and isinstance(got.get("outputs"), list):
        exp_out, labels = expected["outputs"], expected.get("labels", [])
        usr_out = got["outputs"]
        for i, e in enumerate(exp_out):
            g = usr_out[i] if i < len(usr_out) else {"__error__": "no output"}
            ok = (not (isinstance(g, dict) and "__error__" in g)) and g == e
            cases.append({
                "name": labels[i] if i < len(labels) else f"case {i + 1}",
                "ok": ok,
                "expected": json.dumps(e),
                "got": (g.get("__error__") if isinstance(g, dict) and "__error__" in g else json.dumps(g)),
            })
        passed = sum(1 for c in cases if c["ok"])
        result["tests"] = {"passed": passed, "total": len(cases), "cases": cases}
        result["ok"] = cap["ok"] and passed == len(cases) and len(cases) > 0
    else:
        result["tests"] = None  # couldn't grade (harness/exec issue) — stderr explains
    # Auto-advance status to 'attempted' on any run; caller marks solved explicitly.
    st = _status_for(session, user.id, pid)
    if st.status == "todo":
        st.status = "attempted"
        st.last_touched = datetime.utcnow()
        session.add(st)
        session.commit()
    return result


class MentorIn(BaseModel):
    language: str = "python"
    code: str = Field(default="", max_length=50000)
    mode: str = "chat"                 # chat | review | explain
    message: str = Field(default="", max_length=4000)
    test_summary: str = Field(default="", max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=20)


@router.post("/{pid}/mentor")
async def mentor(pid: int, body: MentorIn, user: User = RequireUser,
                 session: Session = Depends(get_session)):
    p = session.get(Problem, pid)
    if not p:
        raise HTTPException(404, "Problem not found")
    history = list(body.history)
    if body.message:
        history = history + [{"role": "user", "content": body.message}]
    answer = await tutor.review_code(
        p.title, body.language, body.code, body.test_summary, body.mode, history,
        learner=tutor.learner_context(user))
    return {"answer": answer}


def _get_settings(session: Session, user_id: int) -> Settings:
    s = session.exec(select(Settings).where(Settings.user_id == user_id)).first()
    if not s:
        s = Settings(user_id=user_id)
        session.add(s)
        session.commit()
        session.refresh(s)
    return s


class TargetIn(BaseModel):
    daily_problem_target: int | None = None
    goal_total: int | None = None
    goal_date: str | None = None       # ISO date or "" to clear


@router.get("/target/status")
def target_status(user: User = RequireUser, session: Session = Depends(get_session)):
    s = _get_settings(session, user.id)
    today = date.today()
    solved_today = session.exec(
        select(func.count()).select_from(ProblemStatus)
        .where(ProblemStatus.user_id == user.id, ProblemStatus.status == "solved",
               func.date(ProblemStatus.last_touched) == today.isoformat())
    ).one()
    total_solved = session.exec(
        select(func.count()).select_from(ProblemStatus)
        .where(ProblemStatus.user_id == user.id, ProblemStatus.status == "solved")).one()

    pace = None
    if s.goal_date:
        days_left = (s.goal_date - today).days
        remaining = max(0, s.goal_total - total_solved)
        needed_per_day = (remaining / days_left) if days_left > 0 else remaining
        pace = {
            "days_left": days_left,
            "remaining": remaining,
            "needed_per_day": round(needed_per_day, 1),
            "on_track": needed_per_day <= s.daily_problem_target or remaining == 0,
            "goal_date": s.goal_date.isoformat(),
        }
    return {
        "daily_problem_target": s.daily_problem_target,
        "goal_total": s.goal_total,
        "solved_today": solved_today,
        "total_solved": total_solved,
        "target_met_today": solved_today >= s.daily_problem_target,
        "pace": pace,
    }


@router.post("/target")
def set_target(body: TargetIn, user: User = RequireUser, session: Session = Depends(get_session)):
    from datetime import date as _date
    s = _get_settings(session, user.id)
    if body.daily_problem_target is not None:
        s.daily_problem_target = max(1, body.daily_problem_target)
    if body.goal_total is not None:
        s.goal_total = max(1, body.goal_total)
    if body.goal_date is not None:
        s.goal_date = _date.fromisoformat(body.goal_date) if body.goal_date else None
    session.add(s)
    session.commit()
    return {"ok": True}


@router.get("/stats/summary")
def stats(user: User = RequireUser, session: Session = Depends(get_session)):
    total = session.exec(select(func.count()).select_from(Problem)).one()
    by_diff = {}
    for d in ("Easy", "Medium", "Hard"):
        tot = session.exec(select(func.count()).select_from(Problem).where(Problem.difficulty == d)).one()
        solved = session.exec(
            select(func.count()).select_from(ProblemStatus).join(Problem, Problem.id == ProblemStatus.problem_id)
            .where(Problem.difficulty == d, ProblemStatus.user_id == user.id,
                   ProblemStatus.status == "solved")
        ).one()
        by_diff[d] = {"total": tot, "solved": solved}
    solved_total = session.exec(
        select(func.count()).select_from(ProblemStatus)
        .where(ProblemStatus.user_id == user.id, ProblemStatus.status == "solved")).one()
    return {"total": total, "solved": solved_total, "by_difficulty": by_diff}
