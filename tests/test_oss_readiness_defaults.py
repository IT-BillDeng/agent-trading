from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OssReadinessDefaultsTests(unittest.TestCase):
    def test_committed_defaults_are_paper_first_and_guarded(self):
        config = json.loads((ROOT / "config" / "app.defaults.json").read_text())
        execution = config.get("execution", {})
        factor_engine = config.get("factor_engine", {})
        notify = config.get("notify", {})

        self.assertEqual(config.get("mode"), "paper")
        self.assertEqual(execution.get("submit_mode"), "guarded")
        self.assertIs(execution.get("live_submit"), False)
        self.assertIs(execution.get("live_cancel"), False)
        self.assertEqual(factor_engine.get("mode"), "shadow")
        self.assertIs(factor_engine.get("allow_actionable_consumption"), False)
        self.assertIs(notify.get("telegram"), False)
        self.assertIs(notify.get("telegram_preview_only"), True)
        self.assertIs(notify.get("telegram_send_enabled"), False)

    def test_dashboard_default_host_and_upload_gate_are_local_safe(self):
        dashboard_main = (ROOT / "dashboard" / "main.py").read_text()
        env_example = (ROOT / ".env.example").read_text()
        compose = (ROOT / "docker-compose.yml").read_text()

        self.assertIn('os.environ.get("DASHBOARD_HOST", "127.0.0.1")', dashboard_main)
        self.assertIn("DASHBOARD_ENABLE_CONFIG_UPLOAD=false", env_example)
        self.assertIn("127.0.0.1:8088:8088", compose)

    def test_tracked_runtime_sensitive_paths_are_not_present(self):
        tracked_paths = (ROOT / ".gitignore").read_text()
        self.assertRegex(tracked_paths, re.compile(r"^runtime/$", re.MULTILINE))
        self.assertRegex(tracked_paths, re.compile(r"^rules/\*$", re.MULTILINE))
        self.assertRegex(tracked_paths, re.compile(r"^properties/tiger_openapi_config\.properties$", re.MULTILINE))


if __name__ == "__main__":
    unittest.main()
