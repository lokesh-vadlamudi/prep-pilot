"""Login / logout / registration / session status."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import auth, service
from ..db import get_session
from ..models import LoginAudit, Settings, User

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
    rows = []
    for account in users:
        own = [entry for entry in audits if entry.user_id == account.id]
        logins = [entry for entry in own if entry.event == "login"]
        activity = [entry for entry in own if entry.event == "active"]
        rows.append({
            "username": account.username,
            "last_login_at": logins[-1].occurred_at if logins else None,
            "last_active_at": activity[-1].occurred_at if activity else None,
            "login_days": sum(entry.day >= cutoff for entry in logins),
            "active_days": sum(entry.day >= cutoff for entry in activity),
            "recent_active_dates": [str(entry.day) for entry in activity if entry.day >= cutoff],
        })
    return {"window_days": window_days, "users": rows}
