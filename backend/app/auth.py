"""Multi-user authentication with a signed session cookie."""
from __future__ import annotations

import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlmodel import Session, select

from .config import settings, BASE_DIR
from .db import engine
from .models import User

COOKIE = settings.cookie_name
MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _ensure_secret() -> str:
    """Load or lazily generate + persist the cookie-signing secret."""
    if settings.secret_key:
        return settings.secret_key
    settings.secret_key = secrets.token_urlsafe(48)
    _append_env("SECRET_KEY", settings.secret_key)
    return settings.secret_key


def ensure_invite_code() -> str:
    """Shared code new users must present to register (admin hands it out)."""
    if not settings.invite_code:
        settings.invite_code = secrets.token_urlsafe(9)
        _append_env("INVITE_CODE", settings.invite_code)
    return settings.invite_code


def _append_env(key: str, value: str) -> None:
    env = BASE_DIR / ".env"
    lines = env.read_text().splitlines() if env.exists() else []
    lines = [ln for ln in lines if not ln.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    env.write_text("\n".join(lines) + "\n")


def hash_password(pw: str) -> str:
    # bcrypt operates on the first 72 bytes; truncate defensively.
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def _verify(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_ensure_secret(), salt="prep-session")


def verify_login(session: Session, username: str, password: str) -> User | None:
    user = session.exec(select(User).where(User.username == username)).first()
    if not user or not user.password_hash:
        # Dummy check to keep timing roughly constant against user enumeration.
        _verify(password, hash_password("x"))
        return None
    return user if _verify(password, user.password_hash) else None


def issue_session(response: Response, user: User) -> None:
    token = _serializer().dumps({"uid": user.id, "u": user.username})
    response.set_cookie(
        COOKIE, token, max_age=MAX_AGE, httponly=True, samesite="lax"
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE)


def current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        data = _serializer().loads(token, max_age=MAX_AGE)
    except BadSignature:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    with Session(engine) as session:
        user = None
        if data.get("uid") is not None:
            user = session.get(User, data["uid"])
        elif data.get("u"):  # legacy single-user cookie from before multi-user
            user = session.exec(select(User).where(User.username == data["u"])).first()
        if not user:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
        return user


RequireUser = Depends(current_user)


def admin_user(session: Session) -> User | None:
    """The primary account — target of legacy data and the reminder brief."""
    return session.exec(
        select(User).where(User.is_admin == True).order_by(User.id)  # noqa: E712
    ).first()
