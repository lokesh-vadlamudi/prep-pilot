"""PrepPilot API + static frontend host."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Session

from .config import settings, BASE_DIR
from .db import engine, init_db
from .content.seed import seed_database, seed_problems
from .scheduler import start_scheduler
from .ratelimit import require_setup_rate
from . import auth
from .routers import (
    ask_routes, auth_routes, book_routes, course_routes, mock_routes,
    problem_routes, roadmap_routes, study_routes,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("prep")

FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    init_db()
    with Session(engine) as session:
        added = seed_database(session)
        p_added, p_updated = seed_problems(session)
        log.info("seeded %d new concepts; problems +%d new, %d updated", added, p_added, p_updated)
    # Book imports must progress in every environment. The setting only controls
    # optional nightly curriculum generation (disabled in development).
    _scheduler = start_scheduler(enable_nightly=settings.scheduler_enabled)
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="PrepPilot", lifespan=lifespan)
app.include_router(auth_routes.router)
app.include_router(study_routes.router)
app.include_router(ask_routes.router)
app.include_router(problem_routes.router)
app.include_router(mock_routes.router)
app.include_router(roadmap_routes.router)
app.include_router(book_routes.router)
app.include_router(course_routes.router)


# ---- First-run setup (only allowed while no account exists) ----
class SetupIn(BaseModel):
    password: str
    username: str = ""


def _no_users() -> bool:
    from sqlmodel import select
    from .models import User
    with Session(engine) as session:
        return session.exec(select(User)).first() is None


@app.get("/api/needs-setup")
def needs_setup():
    return {"needs_setup": _no_users(), "username": settings.username}


@app.post("/api/setup", dependencies=[Depends(require_setup_rate)])
def setup(body: SetupIn, response: Response):
    from .models import Settings as UserSettings, User
    if not _no_users():
        return Response(status_code=409)  # already configured
    if len(body.password) < 6:
        return Response(status_code=400)
    username = (body.username.strip().lower() or settings.username)
    with Session(engine) as session:
        user = User(username=username, password_hash=auth.hash_password(body.password),
                    is_admin=True)
        session.add(user)
        session.commit()
        session.refresh(user)
        session.add(UserSettings(user_id=user.id))
        session.commit()
        from . import service
        service.sync_user_cards(session, user)
        auth.issue_session(response, user)
    return {"ok": True, "username": username}


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "environment": settings.environment,
        "release": settings.release,
        "scheduler_enabled": settings.scheduler_enabled,
    }


# ---- Serve the built React app (SPA fallback) ----
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    _dist_root = FRONTEND_DIST.resolve()

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        # Containment: reject any path that escapes the frontend build dir
        # (`..` segments survive percent-decoding, so check the resolved path).
        candidate = (_dist_root / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(_dist_root):
            return FileResponse(candidate)
        return FileResponse(_dist_root / "index.html")
else:
    @app.get("/")
    def no_frontend():
        return {"message": "PrepPilot API up. Frontend not built yet (run: npm run build)."}
