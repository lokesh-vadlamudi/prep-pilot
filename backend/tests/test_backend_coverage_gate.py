from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_backend_module_coverage.py"


class BackendCoverageGateTests(unittest.TestCase):
    def fixture(self, line_percent: float, branch_percent: float) -> tuple[Path, Path]:
        root = Path(tempfile.mkdtemp(prefix="backend-coverage-gate-"))
        source = root / "backend" / "app" / "reader.py"
        source.parent.mkdir(parents=True)
        source.write_text("def page():\n    return 1\n")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "coverage@example.invalid"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Coverage Gate"], cwd=root, check=True)
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "baseline"], cwd=root, check=True)
        source.write_text("def page():\n    return 2\n")
        report = root / "coverage.json"
        report.write_text(json.dumps({"files": {"backend/app/reader.py": {"summary": {
            "num_statements": 100,
            "covered_lines": round(line_percent),
            "num_branches": 20,
            "covered_branches": round(branch_percent / 5),
        }}}}))
        return root, report

    def run_gate(self, root: Path, report: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            sys.executable, str(CHECKER), "--root", str(root), "--base", "HEAD",
            "--coverage", str(report),
        ], text=True, capture_output=True)

    def test_fails_a_touched_module_below_line_or_branch_threshold(self):
        root, report = self.fixture(94, 95)
        result = self.run_gate(root, report)
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stderr, r"reader\.py.*lines 94\.00%.*branches 95\.00%")

    def test_passes_each_touched_module_at_exactly_95_percent(self):
        root, report = self.fixture(95, 95)
        result = self.run_gate(root, report)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"PASS backend/app/reader\.py: lines 95\.00%; branches 95\.00%")

    def test_fails_closed_when_touched_module_is_missing_from_report(self):
        root, report = self.fixture(100, 100)
        report.write_text('{"files": {}}')
        result = self.run_gate(root, report)
        self.assertNotEqual(result.returncode, 0)
        self.assertRegex(result.stderr, r"reader\.py.*missing coverage")


if __name__ == "__main__":
    unittest.main()
