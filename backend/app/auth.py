"""Single-user authentication with a signed session cookie."""
from __future__ import annotations

import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import settings, BASE_DIR

COOKIE = "prep_session"
MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _ensure_secret() -> str:
    """Load or lazily generate + persist the cookie-signing secret."""
    if settings.secret_key:
        return settings.secret_key
    settings.secret_key = secrets.token_urlsafe(48)
    _append_env("SECRET_KEY", settings.secret_key)
    return settings.secret_key


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


def set_password(pw: str) -> None:
    settings.password_hash = hash_password(pw)
    _append_env("PASSWORD_HASH", settings.password_hash)


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_ensure_secret(), salt="prep-session")


def verify_login(username: str, password: str) -> bool:
    if username != settings.username or not settings.password_hash:
        # Dummy check to keep timing roughly constant against user enumeration.
        _verify(password, hash_password("x"))
        return False
    return _verify(password, settings.password_hash)


def issue_session(response: Response) -> None:
    token = _serializer().dumps({"u": settings.username})
    response.set_cookie(
        COOKIE, token, max_age=MAX_AGE, httponly=True, samesite="lax"
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE)


def current_user(request: Request) -> str:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        data = _serializer().loads(token, max_age=MAX_AGE)
    except BadSignature:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")
    return data["u"]


RequireUser = Depends(current_user)
