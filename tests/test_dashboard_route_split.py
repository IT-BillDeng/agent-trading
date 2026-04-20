import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = ROOT / "dashboard" / "main.py"
PROPOSALS_FILE = ROOT / "dashboard" / "api" / "proposals.py"


class DashboardRouteSplitTests(unittest.TestCase):
    def test_proposals_module_exists(self):
        self.assertTrue(PROPOSALS_FILE.exists())

    def test_main_imports_proposal_route_handlers(self):
        content = MAIN_FILE.read_text(encoding="utf-8")
        self.assertIn("from .api.proposals import", content)
        self.assertIn("set_proposal_artifacts_root_getter", content)
        self.assertIn("api_strategy_proposals_route", content)
        self.assertIn("api_strategy_proposal_approve_route", content)
        self.assertIn("api_strategy_proposal_reject_route", content)


if __name__ == "__main__":
    unittest.main()
