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
        "You are a senior engineer running a CODING interview, modeled on a real 45-minute round. "
        "Pose one interview-grade problem with an example and constraints. Run it in phases and "
        "note (silently) how the candidate moves through them: (1) clarifying questions — a strong "
        "candidate asks about input format, sizes, duplicates, and edge cases before solving; "
        "(2) approach BEFORE code — they should state the approach and its time/space complexity "
        "first; if they jump straight to code, stop them: ‘Before you code, can you walk me through "
        "your approach?’; (3) implementation — expect thinking aloud; (4) testing — ask ‘how would "
        "you test this?’ and expect them to find their own bugs; (5) follow-ups — change a "
        "constraint (‘what if the input were sorted?’, ‘optimize for space’) or ask for an "
        "alternative approach. Do NOT write the solution for them or reveal the optimal approach."
    ),
    "system_design": (
        "You are a staff engineer running a SYSTEM DESIGN interview. Pose one open-ended design "
        "prompt. Drive the standard flow (requirements, estimation, API, data model, high-level "
        "design, scaling, trade-offs) — but let the candidate lead; a strong candidate drives the "
        "conversation and you only steer when they stall or skip a stage. Push on scale, "
        "bottlenecks, consistency, and failure modes; late in the interview change a constraint "
        "(‘traffic just grew 10x’, ‘this region went down’) and watch how the design adapts. "
        "Challenge hand-wavy answers with ‘why’ and ask for concrete numbers behind sizing claims. "
        "Do NOT design it for them."
    ),
    "behavioral": (
        "You are a hiring manager running a BEHAVIORAL interview appropriate to the candidate's level. Ask one "
        "behavioral question at a time (leadership, conflict, failure, ambiguity, impact). Probe for "
        "specifics: their exact role, the trade-offs, measurable results (STAR). Follow up on vague "
        "or ‘we’-heavy answers to surface individual contribution and scope. Useful probes: ‘what "
        "was YOUR specific contribution?’, ‘what would you do differently?’, ‘how did you measure "
        "the result?’. One follow-up on the same story beats a new question if the answer was thin."
    ),
}

# Shared interviewer conduct, distilled from real-interview practice (via algo-sensei, MIT).
_CONDUCT = (
    " Interviewer conduct: stay professional and mostly neutral — brief acknowledgments "
    "(‘okay, continue’), not cheerleading. Ask ONE thing at a time. If an answer is thin or the "
    "candidate seems stalled, say ‘talk me through what you're thinking’ rather than moving on. "
    "If their work has a bug or a flaw, do NOT point it out directly — ask them to trace through "
    "a concrete example and let them find it. Give hints only when they are genuinely stuck, and "
    "escalate gradually: first a gentle nudge, then something more specific, and only as a last "
    "resort a high-level outline — needing many hints is itself a signal, so never volunteer them. "
    "Manage time like a real session: as the interview progresses, give pacing cues (‘let's make "
    "sure we leave time for testing’) and steer toward core logic over polish."
)

_RUBRIC_DIMS = {
    "coding": "communication, problem_solving, technical_correctness, testing_edge_cases",
    "system_design": "requirements_clarification, high_level_design, scaling_and_bottlenecks, tradeoffs_and_communication",
    "behavioral": "structure_STAR, scope_and_impact, ownership, communication",
}

# Signal taxonomy the evaluator scores against (evidence must map to these).
_SIGNALS = (
    "Strong signals: clarified constraints before solving; stated approach and complexity before "
    "coding; thought aloud consistently; considered alternatives; tested their own work and found "
    "their own bugs; recovered from hints quickly; articulated trade-offs. "
    "Warning signs: jumped in without clarifying; silent or unexplained jumps in reasoning; missed "
    "edge cases; could not state complexity; never tested. "
    "Red flags: could not explain their own solution; made no progress despite hints; ignored the "
    "interviewer's questions; defensive when challenged. "
    "Hints are costly: a candidate who needed heavy hints scores materially lower on problem "
    "solving than one who unstuck themselves, even if both reached the same solution."
)


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
        persona + _CONDUCT + " " + (learner or USER_CONTEXT) +
        " Start the interview now: a one-line greeting that sets expectations (you want them to "
        "think out loud and ask clarifying questions), then pose ONE clear question"
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
        persona + _CONDUCT + " " + (learner or USER_CONTEXT) +
        " Continue the interview. React to the candidate's latest answer with ONE short interviewer "
        "turn: acknowledge briefly, then either probe deeper or advance to the next phase of the "
        "interview. Ask ONE thing at a time. If they've thoroughly covered the problem, pose a "
        "natural extension (change a constraint, push optimization, ask for an alternative). "
        "Never dump the solution. Keep it to 1-3 sentences."
    )
    msgs = [{"role": "system", "content": sys}] + _turns_to_messages(kind, transcript)
    return await chat(msgs, temperature=0.5, num_predict=400)


async def score(kind: str, topic: str, transcript: list[dict], learner: str = "") -> dict:
    dims = _RUBRIC_DIMS.get(kind, _RUBRIC_DIMS["coding"])
    sys = (
        "You are a calibrated interview evaluator. " + (learner or USER_CONTEXT) + " " + _SIGNALS +
        f" Score this {kind.replace('_', ' ')} interview transcript on each dimension ({dims}) "
        "from 1-5 (1 poor, 3 hire-bar, 5 outstanding). Judge the process, not just the artifact: "
        "how they thought, communicated, handled pressure, and used hints. Be honest and specific "
        "— every note must cite something the candidate actually did or failed to do. In "
        "'improvements', prefer concrete rehearsable behaviors (e.g. ‘state complexity before "
        "coding’) over generic advice. Respond ONLY with JSON:\n"
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
