import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_FILE = ROOT / "agents" / "factor_researcher.yaml"
CRON_FILE = ROOT / "cron" / "factor-research-afterhours.json"
TASK_FILE = ROOT / "docs" / "tasks" / "cron" / "FACTOR_RESEARCH_AFTERHOURS.md"
ROLE_CONTRACT = ROOT / "docs" / "factor-researcher-role-contract.md"


def _extract_yaml_list(text: str, key: str) -> list[str]:
    items: list[str] = []
    capture = False
    prefix = f"{key}:"
    for line in text.splitlines():
        if not capture:
            if line.strip() == prefix:
                capture = True
            continue

        if line and not line.startswith(" "):
            break
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            items.append(stripped[2:].strip().strip('"').strip("'"))
    return items


class FactorResearcherStructureTests(unittest.TestCase):
    def test_factor_researcher_agent_yaml_exists_and_has_safe_write_scope(self):
        self.assertTrue(AGENT_FILE.exists())
        text = AGENT_FILE.read_text(encoding="utf-8")
        write_scopes = _extract_yaml_list(text, "write_scopes")
        protected_paths = _extract_yaml_list(text, "protected_paths")

        self.assertIn("/workspace/agent-trading/artifacts/factor_research/", write_scopes)
        self.assertIn("/workspace/agent-trading/artifacts/strategist/approval_queue/", write_scopes)
        self.assertIn("/workspace/agent-trading/rules/", protected_paths)
        self.assertIn("/workspace/agent-trading/factors/", protected_paths)
        self.assertIn("/workspace/agent-trading/system/engine/src/engine/live_execution.py", protected_paths)
        self.assertIn("/workspace/agent-trading/system/engine/src/engine/risk.py", protected_paths)
        for protected_path in protected_paths:
            self.assertNotIn(protected_path, write_scopes)
        for forbidden_fragment in (
            "/rules/",
            "/factors/",
            "/runtime/",
            "/logs/latest/",
            "/artifacts/broker/",
            "live_execution.py",
            "risk.py",
            "broker_client.py",
            "tiger_client.py",
            "dashboard/api/control.py",
            "dashboard/scheduler.py",
            "docker-compose.yml",
        ):
            self.assertFalse(any(forbidden_fragment in scope for scope in write_scopes), forbidden_fragment)

    def test_factor_research_afterhours_cron_points_to_taskfile(self):
        self.assertTrue(CRON_FILE.exists())
        payload = json.loads(CRON_FILE.read_text(encoding="utf-8"))
        self.assertEqual(payload["name"], "factor-research-afterhours")
        self.assertEqual(payload["sessionTarget"], "isolated")
        self.assertEqual(payload["delivery"]["mode"], "none")
        self.assertEqual(
            payload["payload"]["taskFile"],
            "/workspace/agent-trading/docs/tasks/cron/FACTOR_RESEARCH_AFTERHOURS.md",
        )

    def test_factor_research_taskfile_contains_no_submit_no_apply_no_secrets_constraints(self):
        self.assertTrue(TASK_FILE.exists())
        self.assertTrue(ROLE_CONTRACT.exists())
        text = TASK_FILE.read_text(encoding="utf-8")
        lowered = text.lower()

        self.assertIn("no submit", lowered)
        self.assertIn("no apply", lowered)
        self.assertIn("no secrets", lowered)
        self.assertIn("./artifacts/factor_research/latest.json", text)
        self.assertIn("./artifacts/factor_research/history.jsonl", text)
        self.assertIn("不得直接修改 `rules/rules.json`", text)
        self.assertIn("不得直接修改 `factors/registry.json`", text)


if __name__ == "__main__":
    unittest.main()
