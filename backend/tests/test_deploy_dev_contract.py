from __future__ import annotations

import unittest
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / "deploy" / "deploy-dev.sh").read_text()
PREFLIGHT = ROOT / "deploy" / "check-dev-storage.py"


class DevelopmentDeployContractTests(unittest.TestCase):
    def assert_before(self, earlier: str, later: str) -> None:
        self.assertIn(earlier, SCRIPT)
        self.assertIn(later, SCRIPT)
        self.assertLess(SCRIPT.index(earlier), SCRIPT.index(later))

    def test_untracked_backend_or_frontend_source_is_rejected_before_build_and_sync(self):
        self.assertIn("ls-files --others --exclude-standard", SCRIPT)
        self.assertRegex(SCRIPT, r"-- backend frontend deploy")
        self.assertIn("untracked backend/frontend/deploy", SCRIPT)
        self.assert_before("ls-files --others --exclude-standard", "npm run build")
        self.assert_before("ls-files --others --exclude-standard", "rsync -az")

    def test_preserved_remote_env_is_attested_through_app_config_before_sync_or_reload(self):
        self.assertIn("check-dev-storage.py", SCRIPT)
        self.assertIn("--env-file", SCRIPT)
        self.assert_before("check-dev-storage.py", "rsync -az")
        self.assert_before("check-dev-storage.py", "launchctl unload")

    def test_post_restart_health_is_boolean_only_and_checks_the_isolated_service_surface(self):
        self.assertRegex(SCRIPT, r'd\.get\(\\?"environment\\?"\).*development')
        self.assertRegex(SCRIPT, r'd\.get\(\\?"scheduler_enabled\\?"\).*False')
        self.assertRegex(SCRIPT, r'd\.get\(\\?"dev_database_isolated\\?"\).*True')
        self.assertRegex(SCRIPT, r'd\.get\(\\?"dev_book_storage_isolated\\?"\).*True')
        self.assertIn("com.preppilot.dev", SCRIPT)
        self.assertIn("APP_PORT=8779", SCRIPT)
        self.assertIn("SERVE_PORT=10004", SCRIPT)
        self.assertNotIn('echo "$HEALTH <-', SCRIPT)

    def test_first_rollout_preflight_executes_without_new_app_settings_methods(self):
        with tempfile.TemporaryDirectory() as directory:
            backend = Path(directory) / "old-head" / "backend"
            data = backend / "data"
            (backend / "app").mkdir(parents=True)
            data.mkdir()
            (backend / "app" / "config.py").write_text("class Settings:\n    pass\n")
            env_file = backend / ".env"
            env_file.write_text(
                f"DATABASE_URL=sqlite:///{data / 'prep.db'}\n"
                f"BOOK_STORAGE_DIR={data / 'books'}\n"
            )

            result = subprocess.run(
                [sys.executable, str(PREFLIGHT), "--backend", str(backend), "--env-file", str(env_file)],
                text=True, capture_output=True, check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "development storage isolation attested")
            self.assertNotIn("require_dev_storage_isolation", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
