import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = ROOT / "dashboard"


class DashboardDirectoryCleanupTests(unittest.TestCase):
    def test_services_exist_and_legacy_provider_files_are_removed(self):
        self.assertTrue((DASHBOARD_DIR / "services" / "__init__.py").exists())
        self.assertTrue((DASHBOARD_DIR / "services" / "broker.py").exists())
        self.assertTrue((DASHBOARD_DIR / "services" / "market_data.py").exists())
        self.assertTrue((DASHBOARD_DIR / "services" / "runtime.py").exists())

        self.assertFalse((DASHBOARD_DIR / "tiger_quote_provider.py").exists())
        self.assertFalse((DASHBOARD_DIR / "yfinance_provider.py").exists())

    def test_compatibility_wrappers_delegate_to_services(self):
        broker_text = (DASHBOARD_DIR / "broker_client.py").read_text(encoding="utf-8")
        tiger_text = (DASHBOARD_DIR / "tiger_client.py").read_text(encoding="utf-8")
        quote_text = (DASHBOARD_DIR / "quote_provider.py").read_text(encoding="utf-8")

        self.assertIn("from .services.broker import BrokerClient", broker_text)
        self.assertIn("from .services.broker import ET_ZONE, TigerClient", tiger_text)
        self.assertIn("from .services.market_data import", quote_text)
        self.assertNotIn("tiger_quote_provider", quote_text)
        self.assertNotIn("yfinance_provider", quote_text)

    def test_main_and_market_apis_route_through_runtime_services(self):
        main_text = (DASHBOARD_DIR / "main.py").read_text(encoding="utf-8")
        config_text = (DASHBOARD_DIR / "api" / "config.py").read_text(encoding="utf-8")
        market_text = (DASHBOARD_DIR / "api" / "market.py").read_text(encoding="utf-8")

        self.assertIn("from .services.runtime import create_dashboard_bindings", main_text)
        self.assertIn("create_dashboard_bindings(", main_text)
        self.assertIn("from dashboard.services.runtime import create_dashboard_bindings, get_broker_account_info", config_text)
        self.assertIn("from dashboard.services.runtime import replace_quote_provider", market_text)
        self.assertIn("replace_quote_provider(", market_text)


if __name__ == "__main__":
    unittest.main()
