"""Free-form 'ask the tutor' + on-demand content generation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..auth import RequireUser
from ..models import User
from ..ratelimit import require_shared_ai_rate
from .. import tutor, scheduler, llm

router = APIRouter(prefix="/api", tags=["ask"], dependencies=[RequireUser])


class AskIn(BaseModel):
    question: str = Field(max_length=4000)
    context: str = Field(default="", max_length=2000)
    history: list[dict] = Field(default_factory=list, max_length=20)


@router.post("/ask", dependencies=[Depends(require_shared_ai_rate)])
async def ask(body: AskIn, user: User = RequireUser):
    answer = await tutor.answer_question(
        body.question, body.context, body.history, learner=tutor.learner_context(user))
    return {"answer": answer}


@router.post("/generate-now")
async def generate_now(per_track: int = Query(1, ge=1, le=5), user: User = RequireUser):
    """Manually trigger content generation, authored for the requesting user's level.

    Capped at 5 per track (20 LLM generations max) so a manual trigger can't
    be used to DoS the DGX brain or flood the content bank."""
    added = await scheduler.generate_new_concepts(per_track=per_track, audience=user.level)
    return {"added": added}


@router.get("/brain-health")
async def brain_health():
    online, model = await llm.model_status()
    return {"online": online, "model": model}
