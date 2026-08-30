#!/usr/bin/env python3
"""Require line and branch coverage for every touched backend app module."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

THRESHOLD = 95.0


def git(root: Path, *args: str) -> list[str]:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def touched_modules(root: Path, base: str) -> list[str]:
    tracked = git(root, "diff", "--name-only", "-z", "--diff-filter=ACMR", base, "--", "backend/app")
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", "backend/app")
    return sorted({path for path in tracked + untracked if path.endswith(".py") and "/__pycache__/" not in path})


def report_entries(root: Path, report: dict) -> dict[str, dict]:
    entries: dict[str, dict] = {}
    for name, data in report.get("files", {}).items():
        path = Path(name)
        candidates = [path] if path.is_absolute() else [root / path, root / "backend" / path]
        for candidate in candidates:
            try:
                key = candidate.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                continue
            entries[key] = data
    return entries


def percent(covered: int, total: int) -> float:
    return covered * 100 / total if total else 100.0


def metrics(data: dict, module: str) -> tuple[float, float]:
    summary = data.get("summary") if isinstance(data, dict) else None
    required = ("covered_lines", "num_statements", "covered_branches", "num_branches")
    if not isinstance(summary, dict) or any(not isinstance(summary.get(key), int) for key in required):
        raise ValueError(f"{module}: incomplete line or branch coverage data")
    return percent(summary["covered_lines"], summary["num_statements"]), percent(summary["covered_branches"], summary["num_branches"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--coverage", default="backend/coverage.json")
    options = parser.parse_args()
    root = Path(options.root).resolve()
    report = json.loads(Path(options.coverage).read_text())
    entries = report_entries(root, report)
    failures: list[str] = []
    for module in touched_modules(root, options.base):
        if module not in entries:
            failures.append(f"{module}: missing coverage")
            continue
        lines, branches = metrics(entries[module], module)
        result = f"{module}: lines {lines:.2f}%; branches {branches:.2f}%"
        if min(lines, branches) < THRESHOLD:
            failures.append(result)
        else:
            print(f"PASS {result}")
    if failures:
        print("Backend touched-module coverage gate failed:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"Backend touched-module coverage gate failed: {error}", file=sys.stderr)
        raise SystemExit(1)
