import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = ROOT / "dashboard" / "main.py"
API_DIR = ROOT / "dashboard" / "api"
MODULES = {
    "market": API_DIR / "market.py",
    "control": API_DIR / "control.py",
    "config": API_DIR / "config.py",
    "strategy": API_DIR / "strategy.py",
    "backtest": API_DIR / "backtest.py",
    "logs": API_DIR / "logs.py",
    "proposals": API_DIR / "proposals.py",
}
REGISTER_NAMES = {
    "market": "register_market_routes",
    "control": "register_control_routes",
    "config": "register_config_routes",
    "strategy": "register_strategy_routes",
    "backtest": "register_backtest_routes",
    "logs": "register_logs_routes",
    "proposals": "register_proposal_routes",
}


class DashboardRouteSplitTests(unittest.TestCase):
    def test_route_modules_exist(self):
        for name, path in MODULES.items():
            with self.subTest(module=name):
                self.assertTrue(path.exists())

    def test_main_imports_and_registers_split_route_modules(self):
        content = MAIN_FILE.read_text(encoding="utf-8")
        for name in MODULES:
            with self.subTest(module=name):
                self.assertIn(f"from .api.{name} import", content)
                self.assertIn(REGISTER_NAMES[name], content)

        self.assertIn("set_proposal_artifacts_root_getter", content)
        self.assertIn("set_market_dashboard_main_module", content)
        self.assertIn("set_control_dashboard_main_module", content)
        self.assertIn("set_config_dashboard_main_module", content)
        self.assertIn("set_strategy_dashboard_main_module", content)
        self.assertIn("set_backtest_dashboard_main_module", content)
        self.assertIn("set_logs_dashboard_main_module", content)


if __name__ == "__main__":
    unittest.main()
