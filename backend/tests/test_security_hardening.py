"""Regression tests for the security-hardening fixes on this branch.

Covered:
  1. SPA catch-all path traversal (main.py) — `..` segments must not leak files
     outside frontend/dist (the .env → SECRET_KEY → session-forgery chain).
  2. Code-execution sandbox denies reads of app secrets (.env, data dir, books)
     while leaving interpreter files readable.
  3. Auth rate limiting (login/register/setup).
  4. /generate-now per_track cap + free-text input length caps.
"""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
from starlette.requests import Request

from app import auth, executor
from app import main as main_module
from app.config import BASE_DIR, settings
from app.main import app as full_app
from app.routers import ask_routes, auth_routes, mock_routes, study_routes
from app.ratelimit import _login, _register, _setup


def memory_session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def user(session: Session, name: str, password: str = "correct-pass") -> "object":
    from app.models import User
    value = User(username=name, password_hash=auth.hash_password(password))
    session.add(value); session.commit(); session.refresh(value)
    return value


class SpaTraversalTests(unittest.TestCase):
    """The catch-all must never serve files outside the frontend build dir."""

    @classmethod
    def setUpClass(cls):
        cls.route = next(
            (r for r in full_app.router.routes
             if getattr(r, "path", "") == "/{full_path:path}" and r.endpoint.__name__ == "spa"),
            None,
        )
        if cls.route is None:
            raise unittest.SkipTest("frontend/dist not built; SPA route not registered")

    def test_dotdot_returns_index_not_adjacent_file(self):
        resp = self.route.endpoint("../package.json")
        self.assertEqual(Path(resp.path).resolve(),
                         (Path(main_module.FRONTEND_DIST) / "index.html").resolve())

    def test_deep_dotdot_into_backend_returns_index(self):
        resp = self.route.endpoint("../../backend/.env")
        self.assertEqual(Path(resp.path).resolve(),
                         (Path(main_module.FRONTEND_DIST) / "index.html").resolve())

    def test_encoded_dotdot_over_http_returns_index(self):
        client = TestClient(full_app)
        expected = (Path(main_module.FRONTEND_DIST) / "index.html").read_text()
        self.assertEqual(client.get("/..%2Fpackage.json").text, expected)
        self.assertEqual(client.get("/..%2F..%2Fbackend%2F.env").text, expected)

    def test_in_dist_file_still_served(self):
        assets = sorted((Path(main_module.FRONTEND_DIST) / "assets").glob("*.js"))
        if not assets:
            self.skipTest("no built assets present")
        resp = self.route.endpoint(f"assets/{assets[0].name}")
        self.assertEqual(Path(resp.path).resolve(), assets[0].resolve())


class ExecutorSandboxTests(unittest.TestCase):
    def test_profile_denies_app_secrets_but_not_interpreter_paths(self):
        profile = executor._SANDBOX_PROFILE.format(work="/tmp/x", work_raw="/tmp/x",
                                                   **executor._secret_paths())
        self.assertIn(f'(literal "{(BASE_DIR / ".env").resolve()}")', profile)
        self.assertIn(f'(subpath "{executor.DATA_DIR.resolve()}")', profile)
        # The interpreter's own venv must stay readable or execution breaks.
        self.assertNotIn(f'(subpath "{(BASE_DIR / ".venv").resolve()}")', profile)

    @unittest.skipUnless(shutil.which("sandbox-exec"), "macOS only")
    def test_sandboxed_python_still_runs(self):
        res = executor.run_code("python", "print('ok')", timeout=15)
        self.assertTrue(res["ok"], res["stderr"])
        self.assertIn("ok", res["stdout"])

    @unittest.skipUnless(shutil.which("sandbox-exec"), "macOS only")
    def test_sandboxed_code_cannot_read_env_or_db(self):
        targets = [BASE_DIR / ".env", executor.DATA_DIR / "prep.db"]
        targets = [t for t in targets if t.exists()]
        if not targets:
            self.skipTest("no secret files present on this host")
        for target in targets:
            res = executor.run_code(
                "python", f"print(open({str(target)!r}, 'rb').read(16))", timeout=15)
            self.assertFalse(res["ok"],
                             f"sandbox allowed reading {target}: {res['stdout']}")


def _auth_app() -> tuple[FastAPI, TestClient, Session]:
    app_ = FastAPI()
    app_.include_router(auth_routes.router)
    session = memory_session()

    def _override_session():
        yield session

    app_.dependency_overrides[auth_routes.get_session] = _override_session
    return app_, TestClient(app_), session


class AuthRateLimitTests(unittest.TestCase):
    def setUp(self):
        _login.reset(); _register.reset()

    def test_login_throttles_at_limit(self):
        _, client, session = _auth_app()
        user(session, "throttle_alice")
        statuses = [
            client.post("/api/auth/login",
                        json={"username": "throttle_alice", "password": "correct-pass"}).status_code
            for _ in range(11)
        ]
        self.assertEqual(statuses[:10], [200] * 10)
        self.assertEqual(statuses[10], 429)

    def test_register_throttles_at_limit(self):
        code = "test-invite-code"
        saved, settings.invite_code = settings.invite_code, code
        try:
            app_, client, session = _auth_app()
            for i in range(6):
                r = client.post("/api/auth/register", json={
                    "username": f"reg{i}", "password": "pass123", "invite_code": code})
                if i < 5:
                    self.assertEqual(r.status_code, 200, r.text)
                else:
                    self.assertEqual(r.status_code, 429)
        finally:
            settings.invite_code = saved

    def test_setup_window_allows_three(self):
        def _req():
            return Request({"type": "http", "method": "POST", "path": "/api/setup",
                            "headers": [], "client": ("10.0.0.1", 5555), "server": ("h", 80)})

        _setup.reset()
        from fastapi import HTTPException
        for _ in range(3):
            _setup.check(_req().client.host)
        with self.assertRaises(HTTPException) as caught:
            _setup.check("10.0.0.1")
        self.assertEqual(caught.exception.status_code, 429)


class InputCapTests(unittest.TestCase):
    def test_ask_question_length_capped(self):
        ask_routes.AskIn(question="x" * 4000)
        with self.assertRaises(ValidationError):
            ask_routes.AskIn(question="x" * 4001)

    def test_self_grade_capped_to_sm2_scale(self):
        study_routes.SubmitIn(card_id=1, self_grade=5)
        with self.assertRaises(ValidationError):
            study_routes.SubmitIn(card_id=1, self_grade=6)
        with self.assertRaises(ValidationError):
            study_routes.SubmitIn(card_id=1, self_grade=-1)

    def test_mock_duration_capped(self):
        mock_routes.StartIn(duration_min=40)
        with self.assertRaises(ValidationError):
            mock_routes.StartIn(duration_min=999)

    def test_generate_now_per_track_capped(self):
        from unittest.mock import AsyncMock, patch
        app_ = FastAPI()
        app_.include_router(ask_routes.router)
        session = memory_session()
        me = user(session, "cap_user")
        app_.dependency_overrides[auth.current_user] = lambda: me
        client = TestClient(app_)
        with patch("app.scheduler.generate_new_concepts", new=AsyncMock(return_value=0)):
            self.assertEqual(client.post("/api/generate-now", params={"per_track": 99}).status_code, 422)
            self.assertEqual(client.post("/api/generate-now", params={"per_track": 0}).status_code, 422)
            self.assertEqual(client.post("/api/generate-now", params={"per_track": 5}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
