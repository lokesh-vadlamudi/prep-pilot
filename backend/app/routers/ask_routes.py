"""Free-form 'ask the tutor' + on-demand content generation."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from ..auth import RequireUser
from .. import tutor, scheduler, llm

router = APIRouter(prefix="/api", tags=["ask"], dependencies=[RequireUser])


class AskIn(BaseModel):
    question: str
    context: str = ""
    history: list[dict] = []


@router.post("/ask")
async def ask(body: AskIn):
    answer = await tutor.answer_question(body.question, body.context, body.history)
    return {"answer": answer}


@router.post("/generate-now")
async def generate_now(per_track: int = 1):
    """Manually trigger the nightly generation (adds `per_track` concepts per track)."""
    added = await scheduler.generate_new_concepts(per_track=per_track)
    return {"added": added}


@router.get("/brain-health")
async def brain_health():
    return {"online": await llm.health(), "model": llm.settings.model}
