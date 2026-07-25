"""Login / logout / session status."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from .. import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, response: Response):
    if not auth.verify_login(body.username, body.password):
        return Response(status_code=401)
    auth.issue_session(response)
    return {"ok": True, "username": body.username}


@router.post("/logout")
def logout(response: Response):
    auth.clear_session(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    try:
        user = auth.current_user(request)
        return {"authenticated": True, "username": user}
    except Exception:
        return {"authenticated": False}
