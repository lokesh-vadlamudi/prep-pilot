"""Mock-interview logic: the DGX plays a senior interviewer, then scores you.

Turn-based: `open_interview` poses the problem, `next_turn` probes with follow-ups
in character (never hands over the answer), and `score` grades the full transcript
on a role-appropriate rubric.
"""
from __future__ import annotations

from .llm import chat, chat_json
from .tutor import USER_CONTEXT

_PERSONA = {
    "coding": (
        "You are a senior engineer running a CODING interview. Pose one interview-grade problem, "
        "then evaluate as a real interviewer would: expect the candidate to think aloud, clarify, "
        "state complexity, handle edge cases, and test. Probe with pointed follow-ups (‘what's the "
        "time complexity?’, ‘what breaks with an empty input?’, ‘can you do better than O(n^2)?’). "
        "Do NOT write the solution for them or reveal the optimal approach — nudge."
    ),
    "system_design": (
        "You are a staff engineer running a SYSTEM DESIGN interview. Pose one open-ended design "
        "prompt. Drive the standard flow (requirements, estimation, API, data model, high-level "
        "design, scaling, trade-offs). Push on scale, bottlenecks, consistency, and failure modes. "
        "Challenge hand-wavy answers and ask ‘why’. Do NOT design it for them."
    ),
    "behavioral": (
        "You are a hiring manager running a BEHAVIORAL interview appropriate to the candidate's level. Ask one "
        "behavioral question at a time (leadership, conflict, failure, ambiguity, impact). Probe for "
        "specifics: their exact role, the trade-offs, measurable results (STAR). Follow up on vague "
        "or ‘we’-heavy answers to surface individual contribution and scope."
    ),
}

_RUBRIC_DIMS = {
    "coding": "communication, problem_solving, technical_correctness, testing_edge_cases",
    "system_design": "requirements_clarification, high_level_design, scaling_and_bottlenecks, tradeoffs_and_communication",
    "behavioral": "structure_STAR, scope_and_impact, ownership, communication",
}


def _turns_to_messages(kind: str, transcript: list[dict]) -> list[dict]:
    """Map our transcript to chat messages (interviewer = assistant, candidate = user)."""
    msgs = []
    for t in transcript:
        role = "assistant" if t["role"] == "interviewer" else "user"
        msgs.append({"role": role, "content": t["content"]})
    return msgs


async def open_interview(kind: str, topic: str, difficulty: str, learner: str = "") -> str:
    persona = _PERSONA.get(kind, _PERSONA["coding"])
    sys = (
        persona + " " + (learner or USER_CONTEXT) +
        " Start the interview now: a one-line greeting, then pose ONE clear question"
        + (f" focused on: {topic}." if topic else " appropriate for the candidate's level.")
        + " Keep it to a few sentences — do not pre-answer or list hints. Stay in character throughout."
    )
    return await chat([{"role": "system", "content": sys},
                       {"role": "user", "content": "Begin the interview."}],
                      temperature=0.6, num_predict=500)


async def next_turn(kind: str, topic: str, difficulty: str, transcript: list[dict],
                    learner: str = "") -> str:
    persona = _PERSONA.get(kind, _PERSONA["coding"])
    sys = (
        persona + " " + (learner or USER_CONTEXT) +
        " Continue the interview. React to the candidate's latest answer with ONE short interviewer "
        "turn: acknowledge briefly, then either probe deeper or advance to the next aspect. Ask ONE "
        "thing at a time. If they've thoroughly covered the problem, you may pose a natural extension. "
        "Never dump the solution. Keep it to 1-3 sentences."
    )
    msgs = [{"role": "system", "content": sys}] + _turns_to_messages(kind, transcript)
    return await chat(msgs, temperature=0.5, num_predict=400)


async def score(kind: str, topic: str, transcript: list[dict], learner: str = "") -> dict:
    dims = _RUBRIC_DIMS.get(kind, _RUBRIC_DIMS["coding"])
    sys = (
        "You are a calibrated interview evaluator. " + (learner or USER_CONTEXT) +
        f" Score this {kind.replace('_', ' ')} interview transcript on each dimension ({dims}) "
        "from 1-5 (1 poor, 3 hire-bar, 5 outstanding). Be honest and specific — cite what the "
        "candidate actually did. Respond ONLY with JSON:\n"
        "{\n"
        f'  "dimensions": [{{"name": one of [{dims}], "score": 1-5, "note": "1 sentence evidence"}}],\n'
        '  "overall": 1-5,\n'
        '  "verdict": "strong hire | hire | lean hire | no hire",\n'
        '  "strengths": ["..."],\n'
        '  "improvements": ["the 2-3 most valuable things to work on"]\n'
        "}"
    )
    convo = "\n\n".join(f"{t['role'].upper()}: {t['content']}" for t in transcript)
    return await chat_json(
        [{"role": "system", "content": sys},
         {"role": "user", "content": f"TOPIC: {topic}\n\nTRANSCRIPT:\n{convo}"}],
        temperature=0.2, num_predict=1200,
    )
