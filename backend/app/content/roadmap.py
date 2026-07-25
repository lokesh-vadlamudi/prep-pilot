"""The interview-prep flight plan.

Single source of truth for the roadmap: phase (leg) definitions, the weekly
rhythm, and today's mission. Consumed by the Flight Plan page, the dashboard
mission card, problem-of-the-day steering, and the Telegram reminder brief
(via /api/roadmap/brief).

The plan itself is data, not code: it loads from `backend/data/roadmap.json`
(personal, never committed) and falls back to `roadmap_example.json` next to
this file. Copy the example into data/ and edit to make the plan yours.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from ..config import DATA_DIR

_EXAMPLE = Path(__file__).with_name("roadmap_example.json")
_PERSONAL = DATA_DIR / "roadmap.json"


def _load() -> dict:
    path = _PERSONAL if _PERSONAL.exists() else _EXAMPLE
    return json.loads(path.read_text())


_plan = _load()

START = date.fromisoformat(_plan["start"])
END = date.fromisoformat(_plan["end"])
PHASE_DAYS = int(_plan.get("phase_days", 28))
PHASES = _plan["phases"]
WEEKDAY_TRACK = {i: t for i, t in enumerate(_plan["weekday_track"])}
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
    """The day's time slots, themed by the weekday's track."""
    ph = PHASES[phase_index(d)]
    track = WEEKDAY_TRACK[d.weekday()]
    if track == "deepwork":
        slots = [
            ("08:00", "Deep-work day: lab morning, timed coding afternoon"),
            ("10:00", f"Lab · {ph['dgx']}"),
            ("14:00", f"Read · {ph['read']}"),
            ("16:00", f"Timed set: 2 problems, 35 min each · {ph['code']}"),
            ("20:00", f"Behavioral · {ph['story']}"),
        ]
    elif track == "mock":
        slots = [
            ("10:00", f"45-min design mock OUT LOUD · {ph['design']}"),
            ("12:00", "Mock post-mortem: cost, latency, failure modes, evals"),
            ("14:00", f"Light coding · {ph['code']}"),
            ("16:00", f"Behavioral hour · {ph['story']}"),
            ("20:00", "WEEKLY RETRO: done vs planned; set next week's targets"),
        ]
    else:
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
