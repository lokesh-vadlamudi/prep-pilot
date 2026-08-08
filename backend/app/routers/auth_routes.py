"""Login / logout / registration / session status."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import auth, service
from ..db import get_session
from ..models import (Attempt, Card, ConceptStatus, DayLog, LoginAudit,
                      MockSession, ProblemStatus, Settings, User)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def record_login_audit(session: Session, user: User, event: str) -> None:
    """Record at most one successful login/activity signal per local calendar day."""
    today = date.today()
    session.connection().exec_driver_sql(
        "INSERT OR IGNORE INTO loginaudit (user_id, event, day, occurred_at) "
        "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
        (user.id, event, today),
    )
    session.commit()


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, response: Response, session: Session = Depends(get_session)):
    user = auth.verify_login(session, body.username.strip(), body.password)
    if not user:
        return Response(status_code=401)
    record_login_audit(session, user, "login")
    auth.issue_session(response, user)
    return {"ok": True, "username": user.username}


class RegisterIn(BaseModel):
    username: str
    password: str
    invite_code: str
    level: str = "newgrad"       # newgrad | senior
    lang: str = "python"         # preferred language for examples


@router.post("/register")
def register(body: RegisterIn, response: Response, session: Session = Depends(get_session)):
    if not auth.ensure_invite_code() or body.invite_code.strip() != auth.ensure_invite_code():
        raise HTTPException(403, "Bad invite code")
    username = body.username.strip().lower()
    if not (3 <= len(username) <= 24) or not username.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(400, "Username: 3-24 chars, letters/digits/-/_")
    if len(body.password) < 6:
        raise HTTPException(400, "Passcode must be at least 6 characters")
    if session.exec(select(User).where(User.username == username)).first():
        raise HTTPException(409, "That username is taken")
    level = body.level if body.level in ("newgrad", "senior") else "newgrad"
    user = User(username=username, password_hash=auth.hash_password(body.password),
                level=level, lang=body.lang.strip().lower()[:20])
    session.add(user)
    session.commit()
    session.refresh(user)
    session.add(Settings(user_id=user.id))
    session.commit()
    service.sync_user_cards(session, user)
    record_login_audit(session, user, "login")
    auth.issue_session(response, user)
    return {"ok": True, "username": user.username}


@router.post("/logout")
def logout(response: Response):
    auth.clear_session(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request, session: Session = Depends(get_session)):
    try:
        user = auth.current_user(request)
    except Exception:
        return {"authenticated": False}
    record_login_audit(session, user, "active")
    out = {"authenticated": True, "username": user.username, "is_admin": user.is_admin}
    if user.is_admin:
        out["invite_code"] = auth.ensure_invite_code()
    return out


@router.get("/audit")
def login_audit(days: int = 30, user: User = auth.RequireUser,
                session: Session = Depends(get_session)):
    """Admin-only login and daily authenticated-activity summary."""
    if not user.is_admin:
        raise HTTPException(403, "Admin access required")
    window_days = max(1, min(days, 365))
    cutoff = date.today() - timedelta(days=window_days - 1)
    users = session.exec(select(User).order_by(User.username)).all()
    audits = session.exec(select(LoginAudit).order_by(LoginAudit.occurred_at)).all()
    daylogs = session.exec(select(DayLog).order_by(DayLog.day)).all()
    attempts = session.exec(select(Attempt).order_by(Attempt.created_at)).all()
    problem_statuses = session.exec(select(ProblemStatus)).all()
    concept_statuses = session.exec(select(ConceptStatus)).all()
    mock_sessions = session.exec(select(MockSession)).all()
    cards = session.exec(select(Card)).all()
    rows = []
    for account in users:
        own = [entry for entry in audits if entry.user_id == account.id]
        logins = [entry for entry in own if entry.event == "login"]
        activity = [entry for entry in own if entry.event == "active"]
        own_daylogs = [entry for entry in daylogs if entry.user_id == account.id]
        own_attempts = [entry for entry in attempts if entry.user_id == account.id]
        own_problems = [entry for entry in problem_statuses if entry.user_id == account.id]
        own_topics = [entry for entry in concept_statuses if entry.user_id == account.id]
        own_mocks = [entry for entry in mock_sessions if entry.user_id == account.id]
        own_cards = [entry for entry in cards if entry.user_id == account.id]

        progress_times = [entry.created_at for entry in own_attempts]
        progress_times.extend(entry.last_touched for entry in own_problems if entry.last_touched)
        progress_times.extend(entry.completed_at for entry in own_topics if entry.completed_at)
        progress_times.extend(entry.ended_at for entry in own_mocks if entry.ended_at)
        progress_times.extend(datetime.combine(entry.day, time.max) for entry in own_daylogs)

        study_dates = {entry.day for entry in own_daylogs}
        streak = 0
        cursor = date.today()
        if cursor not in study_dates:
            cursor -= timedelta(days=1)
        while cursor in study_dates:
            streak += 1
            cursor -= timedelta(days=1)

        correct = sum(entry.correct for entry in own_attempts)
        rows.append({
            "username": account.username,
            "level": account.level,
            "created_at": account.created_at,
            "last_login_at": logins[-1].occurred_at if logins else None,
            "last_active_at": activity[-1].occurred_at if activity else None,
            "login_days": sum(entry.day >= cutoff for entry in logins),
            "active_days": sum(entry.day >= cutoff for entry in activity),
            "recent_active_dates": [str(entry.day) for entry in activity if entry.day >= cutoff],
            "progress": {
                "last_progress_at": max(progress_times) if progress_times else None,
                "study_days": len(study_dates),
                "current_streak": streak,
                "reviews": len(own_attempts),
                "accuracy": correct / len(own_attempts) if own_attempts else None,
                "problems_solved": sum(entry.status == "solved" for entry in own_problems),
                "problems_attempted": sum(entry.status == "attempted" for entry in own_problems),
                "topics_completed": sum(entry.completed for entry in own_topics),
                "mocks_completed": sum(entry.status == "done" for entry in own_mocks),
                "cards_reviewed": sum(entry.last_reviewed is not None for entry in own_cards),
                "cards_total": len(own_cards),
            },
        })
    return {"window_days": window_days, "users": rows}
