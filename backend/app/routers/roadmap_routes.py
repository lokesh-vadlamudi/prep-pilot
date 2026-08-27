"""The flight plan: roadmap for the UI + a key-guarded brief for reminder crons.

/api/roadmap        — full plan (cookie auth, drives the Flight Plan page)
/api/roadmap/brief  — compact live snapshot for the Telegram reminder script;
                      guarded by a shared key (X-Prep-Key header or ?key=) so
                      Alfred's cron on the mini can call it without a cookie.
"""
from __future__ import annotations

import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select, func

from ..auth import RequireUser, _append_env, admin_user
from ..config import settings
from ..db import get_session
from ..models import Card, DayLog, Problem, ProblemStatus, Settings, User
from ..content import roadmap as rm
from .problem_routes import pick_problem_of_the_day
from .. import service

router = APIRouter(prefix="/api/roadmap", tags=["roadmap"])


def _phase_progress(session: Session, user_id: int) -> list[dict]:
    """Solved/total problems for each leg's categories (empty = all)."""
    problems = session.exec(select(Problem)).all()
    solved_ids = {s.problem_id for s in session.exec(
        select(ProblemStatus).where(ProblemStatus.user_id == user_id,
                                    ProblemStatus.status == "solved")).all()}
    out = []
    for ph in rm.PHASES:
        cats = set(ph["categories"])
        pool = [p for p in problems if not cats or p.category in cats]
        out.append({
            "total": len(pool),
            "solved": sum(1 for p in pool if p.id in solved_ids),
        })
    return out


@router.get("")
def roadmap(user: User = RequireUser, session: Session = Depends(get_session)):
    today = date.today()
    cur = rm.phase_index(today)
    progress = _phase_progress(session, user.id)
    phases = []
    for i, ph in enumerate(rm.PHASES):
        start, end = rm.phase_range(i)
        phases.append({
            "index": i, "key": ph["key"], "callsign": ph["callsign"],
            "name": ph["name"], "motto": ph["motto"],
            "start": start.isoformat(), "end": end.isoformat(),
            "status": "cleared" if i < cur else ("current" if i == cur else "upcoming"),
            "focus": {k: ph[k] for k in ("code", "design", "dgx", "read", "story")},
            "categories": ph["categories"],
            "coding": progress[i],
        })
    elapsed = max(0, (today - rm.START).days)
    total_days = (rm.END - rm.START).days
    return {
        "today": today.isoformat(),
        "start": rm.START.isoformat(), "end": rm.END.isoformat(),
        "week": rm.week_of(today), "total_weeks": rm.total_weeks(),
        "pct": round(min(1.0, elapsed / total_days) * 100, 1),
        "current_phase": cur,
        "phases": phases,
        "mission": rm.today_mission(today),
        "rhythm": [{"day": d, "track": rm.TRACK_LABEL[rm.WEEKDAY_TRACK[i]]}
                   for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])],
    }


# ---- Alfred's brief -------------------------------------------------------

def _ensure_reminder_key() -> str:
    if not settings.reminder_key:
        settings.reminder_key = secrets.token_urlsafe(24)
        _append_env("REMINDER_KEY", settings.reminder_key)
    return settings.reminder_key


def _require_key(request: Request) -> None:
    supplied = request.headers.get("x-prep-key") or request.query_params.get("key") or ""
    if not secrets.compare_digest(supplied, _ensure_reminder_key()):
        raise HTTPException(401, "Bad reminder key")


@router.get("/brief")
def brief(request: Request, session: Session = Depends(get_session)):
    _require_key(request)
    # The brief is the admin's (the reminder cron predates multi-user).
    owner = admin_user(session)
    if not owner:
        raise HTTPException(503, "No admin account yet")
    today = date.today()
    cur = rm.phase_index(today)
    ph = rm.PHASES[cur]

    due_reviews = session.exec(
        select(func.count()).select_from(Card)
        .where(Card.user_id == owner.id,
               Card.introduced == True, Card.due_date <= today)  # noqa: E712
    ).one()

    app_settings = session.exec(
        select(Settings).where(Settings.user_id == owner.id)).first()
    target = app_settings.daily_problem_target if app_settings else 2
    solved_today = service.coding_solved_today(session, owner.id)

    week_ago = today - timedelta(days=6)
    logs = session.exec(select(DayLog).where(
        DayLog.user_id == owner.id, DayLog.day >= week_ago)).all()
    week_reviews = sum(l.reviews_done for l in logs)
    week_coding = sum(l.coding_solved for l in logs)

    reason, potd = pick_problem_of_the_day(session, owner.id)
    prog = _phase_progress(session, owner.id)[cur]

    return {
        "date": today.isoformat(),
        "week": rm.week_of(today), "total_weeks": rm.total_weeks(),
        "month": cur + 1, "callsign": ph["callsign"], "phase": ph["name"],
        "mission": rm.today_mission(today),
        "stats": {
            "due_reviews": due_reviews, "streak": service.current_streak(session, owner.id),
            "solved_today": solved_today, "daily_target": target,
            "week_reviews": week_reviews, "week_coding": week_coding,
            "phase_solved": prog["solved"], "phase_total": prog["total"],
        },
        "potd": None if not potd else {
            "id": potd.id, "title": potd.title, "category": potd.category,
            "difficulty": potd.difficulty, "reason": reason,
            "solve_path": f"/problems/{potd.id}/solve",
        },
    }
