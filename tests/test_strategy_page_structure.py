import unittest
from pathlib import Path


STRATEGY_PAGE = Path(__file__).resolve().parents[1] / "dashboard" / "static" / "strategy.html"


class StrategyPageStructureTests(unittest.TestCase):
    def test_strategy_page_contains_proposal_review_section(self):
        html = STRATEGY_PAGE.read_text(encoding="utf-8")
        self.assertIn("🧾 Proposal Review", html)
        self.assertIn("proposal-review-body", html)
        self.assertIn("refreshProposals()", html)

    def test_strategy_page_wires_review_api_endpoints(self):
        html = STRATEGY_PAGE.read_text(encoding="utf-8")
        self.assertIn("/api/strategy/proposals", html)
        self.assertIn("/approve", html)
        self.assertIn("/reject", html)
        self.assertIn("approveProposal(", html)
        self.assertIn("rejectProposal(", html)

    def test_strategy_page_prefers_canonical_mode_display(self):
        html = STRATEGY_PAGE.read_text(encoding="utf-8")
        self.assertIn("data.control.canonical_mode", html)
        self.assertIn("paper_trade", html)
        self.assertIn("live_trade", html)

    def test_strategy_page_contains_symbol_profile_and_attribution_sections(self):
        html = STRATEGY_PAGE.read_text(encoding="utf-8")
        self.assertIn("Symbol Profiles", html)
        self.assertIn("Symbol × Rule Attribution", html)
        self.assertIn("symbol-profiles-body", html)
        self.assertIn("attribution-body", html)

    def test_strategy_page_contains_factor_shadow_sections(self):
        html = STRATEGY_PAGE.read_text(encoding="utf-8")
        self.assertIn("Factor Engine Shadow", html)
        self.assertIn("Factor Health Matrix", html)
        self.assertIn("Registry Validation", html)
        self.assertIn("Last Apply", html)
        self.assertIn("factor-engine-meta", html)
        self.assertIn("factor-health-body", html)

    def test_strategy_page_does_not_expose_direct_rules_edit_controls(self):
        html = STRATEGY_PAGE.read_text(encoding="utf-8")
        self.assertNotIn("updateRules(", html)
        self.assertNotIn("fetch(API_BASE + '/api/rules'", html)
        self.assertIn("proposal / hot apply only", html)

    def test_strategy_page_does_not_expose_direct_factor_registry_write_controls(self):
        html = STRATEGY_PAGE.read_text(encoding="utf-8")
        self.assertNotIn("updateFactorRegistry(", html)
        self.assertNotIn("/api/factor-registry", html)
        self.assertNotIn("factors/registry.json", html)
        self.assertNotIn("rules/rules.json", html)


if __name__ == "__main__":
    unittest.main()
