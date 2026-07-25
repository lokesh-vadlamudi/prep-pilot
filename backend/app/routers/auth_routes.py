"""Login / logout / registration / session status."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import auth, service
from ..db import get_session
from ..models import Settings, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, response: Response, session: Session = Depends(get_session)):
    user = auth.verify_login(session, body.username.strip(), body.password)
    if not user:
        return Response(status_code=401)
    auth.issue_session(response, user)
    return {"ok": True, "username": user.username}


class RegisterIn(BaseModel):
    username: str
    password: str
    invite_code: str


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
    user = User(username=username, password_hash=auth.hash_password(body.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    session.add(Settings(user_id=user.id))
    session.commit()
    service.sync_user_cards(session, user.id)
    auth.issue_session(response, user)
    return {"ok": True, "username": user.username}


@router.post("/logout")
def logout(response: Response):
    auth.clear_session(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    try:
        user = auth.current_user(request)
    except Exception:
        return {"authenticated": False}
    out = {"authenticated": True, "username": user.username, "is_admin": user.is_admin}
    if user.is_admin:
        out["invite_code"] = auth.ensure_invite_code()
    return out
