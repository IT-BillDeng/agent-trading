import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


class SafeHandoffScriptTests(unittest.TestCase):
    def test_make_safe_handoff_creates_filtered_zip(self):
        repo_root = Path(tempfile.mkdtemp())
        output_dir = repo_root / "handoff-out"

        # Allowed content
        (repo_root / "docs").mkdir(parents=True)
        (repo_root / "docs" / "guide.md").write_text("guide")
        (repo_root / "rules").mkdir(parents=True)
        (repo_root / "rules" / "rule.md").write_text("rule")
        (repo_root / "config").mkdir(parents=True)
        (repo_root / "config" / "app.defaults.json").write_text("{}")
        (repo_root / "config" / "app_config.docker.json").write_text("{}")
        (repo_root / "config" / "user.settings.example.json").write_text("{}")
        (repo_root / "agents").mkdir(parents=True)
        (repo_root / "agents" / "strategist.yaml").write_text("model: test")
        (repo_root / "cron").mkdir(parents=True)
        (repo_root / "cron" / "job.json").write_text("{}")
        (repo_root / "system" / "engine" / "src" / "engine").mkdir(parents=True)
        (repo_root / "system" / "engine" / "src" / "engine" / "rule_engine.py").write_text("pass")
        (repo_root / "system" / "engine" / "tests").mkdir(parents=True)
        (repo_root / "system" / "engine" / "tests" / "test_rule_engine.py").write_text("pass")
        (repo_root / "dashboard").mkdir(parents=True)
        (repo_root / "dashboard" / "main.py").write_text("pass")

        # Sensitive or disallowed content
        (repo_root / ".env").write_text("SECRET=1")
        (repo_root / ".env.local").write_text("LOCAL=1")
        (repo_root / "properties").mkdir(parents=True)
        (repo_root / "properties" / "tiger_openapi_config.properties").write_text("secret")
        (repo_root / "runtime" / "state").mkdir(parents=True)
        (repo_root / "runtime" / "state" / "control_state.json").write_text("{}")
        (repo_root / "logs" / "latest").mkdir(parents=True)
        (repo_root / "logs" / "latest" / "execution_state.json").write_text("{}")
        (repo_root / "logs" / "latest" / "control_state.json").write_text("{}")
        (repo_root / "artifacts" / "broker").mkdir(parents=True)
        (repo_root / "artifacts" / "broker" / "fee_calibration.jsonl").write_text("{}")
        (repo_root / "docs" / "secret-notes.md").write_text("do not ship")
        (repo_root / "dashboard" / "api_token.txt").write_text("do not ship")
        (repo_root / "system" / "engine" / "src" / "engine" / "__pycache__").mkdir(parents=True)
        (repo_root / "system" / "engine" / "src" / "engine" / "__pycache__" / "rule_engine.pyc").write_bytes(b"pyc")

        script_path = (
            Path("/Users/openclaw/.openclaw/workspace-yuuka/agent-trading")
            / "scripts"
            / "make_safe_handoff.sh"
        )
        result = subprocess.run(
            ["bash", str(script_path), str(repo_root), str(output_dir)],
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertIn("Safe handoff zip:", result.stdout)
        self.assertIn("Exclude rules:", result.stdout)

        zip_files = list(output_dir.glob("*.zip"))
        self.assertEqual(len(zip_files), 1)

        with zipfile.ZipFile(zip_files[0]) as zf:
            names = set(zf.namelist())

        self.assertIn("docs/guide.md", names)
        self.assertIn("rules/rule.md", names)
        self.assertIn("config/app.defaults.json", names)
        self.assertIn("config/app_config.docker.json", names)
        self.assertIn("config/user.settings.example.json", names)
        self.assertIn("agents/strategist.yaml", names)
        self.assertIn("cron/job.json", names)
        self.assertIn("system/engine/src/engine/rule_engine.py", names)
        self.assertIn("system/engine/tests/test_rule_engine.py", names)
        self.assertIn("dashboard/main.py", names)

        self.assertNotIn(".env", names)
        self.assertNotIn(".env.local", names)
        self.assertNotIn("properties/tiger_openapi_config.properties", names)
        self.assertNotIn("runtime/state/control_state.json", names)
        self.assertNotIn("logs/latest/execution_state.json", names)
        self.assertNotIn("logs/latest/control_state.json", names)
        self.assertNotIn("artifacts/broker/fee_calibration.jsonl", names)
        self.assertNotIn("docs/secret-notes.md", names)
        self.assertNotIn("dashboard/api_token.txt", names)
        self.assertNotIn("system/engine/src/engine/__pycache__/rule_engine.pyc", names)


if __name__ == "__main__":
    unittest.main()
