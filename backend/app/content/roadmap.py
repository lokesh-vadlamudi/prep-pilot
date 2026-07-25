"""The 6-month interview-prep flight plan (Jul 2026 → Jan 2027).

Single source of truth for the roadmap: phase (leg) definitions, the weekly
rhythm, and today's mission. Consumed by the Flight Plan page, the dashboard
mission card, problem-of-the-day steering, and Alfred's Telegram reminders
(via /api/roadmap/brief).
"""
from __future__ import annotations

from datetime import date, timedelta

START = date(2026, 7, 27)   # week 1 Monday
END = date(2027, 1, 24)     # interviews land here
PHASE_DAYS = 28             # one leg ≈ a month; the final leg absorbs the tail

# Legs of the flight. `categories` are NeetCode-150 categories owned by the
# leg — they drive per-leg coding progress and problem-of-the-day steering.
# An empty list = every category (endgame legs sweep the whole board).
PHASES = [
    dict(
        key="takeoff", callsign="TAKEOFF", name="Foundations",
        motto="Wheels up. Build the habit before the ambition.",
        code="Arrays & hashing, two pointers, sliding window, stack, binary search",
        design="Handbook meta-guidance: how interviews are graded, clarify→approach→code→test",
        dgx="vLLM on the DGX: serve a 7–8B model, baseline benchmark (tok/s, TTFT vs batch size)",
        read="Ubicloud 'Life of an inference request (vLLM V1)'",
        story="Draft 2 STAR stories per week until you have 10",
        categories=["Arrays & Hashing", "Two Pointers", "Sliding Window", "Stack",
                    "Binary Search", "Linked List"],
    ),
    dict(
        key="climb", callsign="CLIMB", name="Core I",
        motto="Gaining altitude — trees, heaps, and your first real designs.",
        code="Trees, tries, heaps / priority queues",
        design="Alex Xu vol 1 classics: rate limiter, URL shortener, news feed — one/week on paper",
        dgx="KV cache deep-dive: PagedAttention paper + measure cache growth vs context length",
        read="The PagedAttention paper (vLLM)",
        story="Rehearse 1 STAR story out loud weekly",
        categories=["Trees", "Tries", "Heap / Priority Queue"],
    ),
    dict(
        key="cruise", callsign="CRUISE", name="Core II",
        motto="Steady state. Graphs below, quantization ahead.",
        code="Graphs, advanced graphs, backtracking",
        design="Alex Xu vol 2 + HelloInterview ML System Design intro",
        dgx="Quantization experiments: FP8 / INT8 / AWQ — quality vs throughput curves",
        read="HelloInterview 'ML System Design in a Hurry'",
        story="Rehearse 1 STAR story out loud weekly",
        categories=["Backtracking", "Graphs", "Advanced Graphs"],
    ),
    dict(
        key="longhaul", callsign="LONG HAUL", name="Flagship build",
        motto="The leg that shows up on your resume.",
        code="1-D/2-D dynamic programming, greedy, intervals",
        design="GenAI designs: RAG pipeline, LLM API w/ rate limiting, eval + guardrails",
        dgx="FLAGSHIP: serving stack — router, continuous batching, metrics dashboard, public writeup",
        read="Your own benchmark notes — turn them into writeup sections",
        story="Rehearse 1 STAR story out loud weekly",
        categories=["1-D DP", "2-D DP", "Greedy", "Intervals"],
    ),
    dict(
        key="turbulence", callsign="TURBULENCE", name="Mocks & depth",
        motto="Shake the airframe on purpose. Better here than in the loop.",
        code="Timed mediums (35-min cap) + redo weak topics; math & bit manipulation",
        design="WEEKLY MOCK out loud — alternate classic SD and ML-SD",
        dgx="Speculative decoding experiment + first Triton kernel (wafer-ai curriculum)",
        read="wafer-ai gpu-perf-engineering-resources",
        story="Mock behavioral answers — record yourself",
        categories=["Math & Geometry", "Bit Manipulation"],
    ),
    dict(
        key="final", callsign="FINAL APPROACH", name="Loop-ready",
        motto="Gear down. Applications out. Cleared to land.",
        code="Company-tagged problems for your target list",
        design="Full mock loops: SD + ML-SD back-to-back",
        dgx="Polish the flagship writeup into interview talking points",
        read="Target companies' engineering blogs",
        story="APPLICATIONS OUT — 3–5/week + follow-ups",
        categories=[],  # everything
    ),
]

# Mon/Wed=coding, Tue/Thu=design, Fri=DGX lab, Sat=deep work, Sun=mock+retro.
WEEKDAY_TRACK = {0: "code", 1: "design", 2: "code", 3: "design", 4: "dgx",
                 5: "deepwork", 6: "mock"}
TRACK_LABEL = {
    "code": "🧩 Coding", "design": "📐 System design", "dgx": "⚡ DGX inference lab",
    "deepwork": "⚡🧩 Deep-work Saturday", "mock": "📐🗣️ Mock + retro Sunday",
}


def phase_index(d: date) -> int:
    return max(0, min((d - START).days // PHASE_DAYS, len(PHASES) - 1))


def week_of(d: date) -> int:
    return max(1, (d - START).days // 7 + 1)


def total_weeks() -> int:
    return (END - START).days // 7 + 1


def phase_range(i: int) -> tuple[date, date]:
    start = START + timedelta(days=i * PHASE_DAYS)
    end = END if i == len(PHASES) - 1 else start + timedelta(days=PHASE_DAYS - 1)
    return start, end


def today_mission(d: date) -> dict:
    """The day's slots (mirrors Alfred's 2-hour cadence, 8am–10pm)."""
    ph = PHASES[phase_index(d)]
    track = WEEKDAY_TRACK[d.weekday()]
    if track == "deepwork":  # Saturday
        slots = [
            ("08:00", "Deep-work day: DGX lab morning, timed coding afternoon"),
            ("10:00", f"DGX lab · {ph['dgx']}"),
            ("14:00", f"Read · {ph['read']}"),
            ("16:00", f"Timed set: 2 problems, 35 min each · {ph['code']}"),
            ("20:00", f"Behavioral · {ph['story']}"),
        ]
    elif track == "mock":  # Sunday
        slots = [
            ("10:00", f"45-min design mock OUT LOUD · {ph['design']}"),
            ("12:00", "Mock post-mortem: cost, latency, failure modes, evals"),
            ("14:00", f"Light coding · {ph['code']}"),
            ("16:00", f"Behavioral hour · {ph['story']}"),
            ("20:00", "WEEKLY RETRO: done vs planned; set next week's targets"),
        ]
    else:  # weekday
        second = "design" if track == "code" else "code"
        slots = [
            ("08:00", f"Brief: tonight's main block is {TRACK_LABEL[track]}"),
            ("12:00", f"Lunch rep: one problem · {ph['code']}"),
            ("14:00", f"15-min read · {ph['read']}"),
            ("18:00", f"Main block · {ph[track]}"),
            ("20:00", f"Checkpoint, then 30 min of {TRACK_LABEL[second]}"),
            ("22:00", "Wrap: log progress, clear reviews, note tomorrow's first task"),
        ]
    return {
        "track": track,
        "track_label": TRACK_LABEL[track],
        "slots": [{"time": t, "title": s} for t, s in slots],
    }
