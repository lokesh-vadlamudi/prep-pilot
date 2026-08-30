"""Simple in-memory per-IP sliding-window rate limit for auth endpoints.

Single-uvicorn-worker personal tool: a process-local window is sufficient —
no persistence, no external dependency. Thresholds are generous for real
humans but slow overnight brute-force to a crawl (bcrypt already slows it).
"""
from __future__ import annotations

import time
from collections import deque

from fastapi import HTTPException, Request


class _SlidingWindow:
    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window = window_s
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> None:
        now = time.monotonic()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            retry_in = self.window if not hits else max(1.0, self.window - (now - hits[0]))
            raise HTTPException(
                429,
                "Too many attempts — try again later.",
                headers={"Retry-After": str(int(retry_in + 1))},
            )
        hits.append(now)

    def reset(self) -> None:
        self._hits.clear()


# Login: 10 attempts / 5 min per IP.
_login = _SlidingWindow(limit=10, window_s=300)
# Register: 5 attempts / 10 min per IP (invite code is the real gate).
_register = _SlidingWindow(limit=5, window_s=600)
# One-time setup: 3 attempts / 10 min per IP.
_setup = _SlidingWindow(limit=3, window_s=600)
# Course persistence: generous for normal autosave/retry, bounded against floods.
_course_mutation = _SlidingWindow(limit=60, window_s=60)
# Course AI boundary: deliberately tighter than deterministic persistence.
_course_ai = _SlidingWindow(limit=12, window_s=60)
# Shared AI entry points outside the course-specific tutor window.
_shared_ai = _SlidingWindow(limit=20, window_s=60)


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def require_login_rate(request: Request) -> None:
    _login.check(_ip(request))


def require_register_rate(request: Request) -> None:
    _register.check(_ip(request))


def require_setup_rate(request: Request) -> None:
    _setup.check(_ip(request))


def require_course_mutation_rate(request: Request) -> None:
    _course_mutation.check(_ip(request))


def require_course_ai_rate(request: Request) -> None:
    _course_ai.check(_ip(request))


def require_shared_ai_rate(request: Request) -> None:
    _shared_ai.check(_ip(request))
