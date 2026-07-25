"""Mock-interview endpoints: start → reply (turn-based) → finish (rubric) → history."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..auth import RequireUser
from ..db import get_session
from ..models import MockSession
from .. import mock

router = APIRouter(prefix="/api/mock", tags=["mock"], dependencies=[RequireUser])

VALID_KINDS = {"coding", "system_design", "behavioral"}


def _load(m: MockSession) -> list[dict]:
    return json.loads(m.transcript_json) if m.transcript_json else []


class StartIn(BaseModel):
    kind: str = "coding"
    topic: str = ""
    difficulty: str = "senior"
    duration_min: int = 40


@router.post("/start")
async def start(body: StartIn, session: Session = Depends(get_session)):
    if body.kind not in VALID_KINDS:
        raise HTTPException(400, "Invalid interview kind")
    opening = await mock.open_interview(body.kind, body.topic, body.difficulty)
    transcript = [{"role": "interviewer", "content": opening}]
    m = MockSession(
        kind=body.kind, topic=body.topic, difficulty=body.difficulty,
        duration_min=body.duration_min, transcript_json=json.dumps(transcript),
    )
    session.add(m)
    session.commit()
    session.refresh(m)
    return {"id": m.id, "kind": m.kind, "topic": m.topic, "duration_min": m.duration_min,
            "message": opening}


class ReplyIn(BaseModel):
    message: str


@router.post("/{sid}/reply")
async def reply(sid: int, body: ReplyIn, session: Session = Depends(get_session)):
    m = session.get(MockSession, sid)
    if not m:
        raise HTTPException(404, "Session not found")
    if m.status == "done":
        raise HTTPException(400, "This interview has ended")
    transcript = _load(m)
    transcript.append({"role": "candidate", "content": body.message})
    interviewer = await mock.next_turn(m.kind, m.topic, m.difficulty, transcript)
    transcript.append({"role": "interviewer", "content": interviewer})
    m.transcript_json = json.dumps(transcript)
    session.add(m)
    session.commit()
    return {"message": interviewer}


@router.post("/{sid}/finish")
async def finish(sid: int, session: Session = Depends(get_session)):
    m = session.get(MockSession, sid)
    if not m:
        raise HTTPException(404, "Session not found")
    transcript = _load(m)
    if m.status != "done":
        rubric = await mock.score(m.kind, m.topic, transcript)
        m.rubric_json = json.dumps(rubric)
        m.status = "done"
        m.ended_at = datetime.utcnow()
        session.add(m)
        session.commit()
    return json.loads(m.rubric_json) if m.rubric_json else {}


@router.get("/history")
def history(session: Session = Depends(get_session)):
    rows = session.exec(select(MockSession).order_by(MockSession.started_at.desc()).limit(30)).all()
    out = []
    for m in rows:
        rubric = json.loads(m.rubric_json) if m.rubric_json else None
        out.append({
            "id": m.id, "kind": m.kind, "topic": m.topic, "status": m.status,
            "started_at": m.started_at.isoformat(),
            "overall": rubric.get("overall") if rubric else None,
            "verdict": rubric.get("verdict") if rubric else None,
        })
    return out


@router.get("/{sid}")
def get_session_detail(sid: int, session: Session = Depends(get_session)):
    m = session.get(MockSession, sid)
    if not m:
        raise HTTPException(404, "Session not found")
    return {
        "id": m.id, "kind": m.kind, "topic": m.topic, "duration_min": m.duration_min,
        "status": m.status, "transcript": _load(m),
        "rubric": json.loads(m.rubric_json) if m.rubric_json else None,
    }
