"""PrepPilot API + static frontend host."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Session

from .config import settings, BASE_DIR
from .db import engine, init_db
from .content.seed import seed_database, seed_problems
from .scheduler import start_scheduler
from . import auth
from .routers import auth_routes, study_routes, ask_routes, problem_routes, mock_routes, roadmap_routes

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
    _scheduler = start_scheduler()
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


# ---- First-run password setup (only allowed while no password is set) ----
class SetupIn(BaseModel):
    password: str


@app.get("/api/needs-setup")
def needs_setup():
    return {"needs_setup": not bool(settings.password_hash), "username": settings.username}


@app.post("/api/setup")
def setup(body: SetupIn, response: Response):
    if settings.password_hash:
        return Response(status_code=409)  # already configured
    if len(body.password) < 6:
        return Response(status_code=400)
    auth.set_password(body.password)
    auth.issue_session(response)
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"ok": True}


# ---- Serve the built React app (SPA fallback) ----
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    def no_frontend():
        return {"message": "PrepPilot API up. Frontend not built yet (run: npm run build)."}
