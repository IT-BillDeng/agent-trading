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
        self.assertIn("factor-research-summary", html)
        self.assertIn("factor-validation-summary", html)
        self.assertIn("factor-validation-candidates", html)
        self.assertIn("factor-parity-summary", html)
        self.assertIn("factor-parity-mismatches", html)
        self.assertIn("factor-dual-run-summary", html)
        self.assertIn("factor-dual-run-mismatches", html)
        self.assertIn("diagnostic-factor-rules-summary", html)
        self.assertIn("real_universe_symbols_detected", html)
        self.assertIn("synthetic_fixture_symbols_detected", html)
        self.assertIn("latest_observation_path", html)
        self.assertIn("source_bar_session_summary", html)
        self.assertIn("production_path_unchanged", html)
        self.assertIn("readiness_status", html)
        self.assertIn("readiness_reasons", html)
        self.assertIn("artifact_age_seconds", html)
        self.assertIn("artifact_is_stale", html)
        self.assertIn("factor-sample-health", html)
        self.assertIn("renderFactorResearch(data)", html)
        self.assertIn("data?.factor_sample_health", html)
        self.assertIn("data?.factor_validation_summary", html)
        self.assertIn("data?.factor_parity_summary", html)
        self.assertIn("data?.factor_dual_run_summary", html)
        self.assertIn("data?.diagnostic_factor_rules_summary", html)
        self.assertIn("data?.diagnostic_factor_metrics_summary", html)
        self.assertIn("diagnostic-factor-metrics-summary", html)
        self.assertIn("Diagnostic Factor Metrics", html)
        self.assertIn("Factor Research Ops Summary", html)
        self.assertIn("factor-ops-summary", html)
        self.assertIn("data?.factor_ops_summary", html)
        self.assertIn("Historical Fact Replay Summary", html)
        self.assertIn("historical-fact-replay-section", html)
        self.assertIn("historical-fact-summary", html)
        self.assertIn("data?.historical_fact_summary", html)
        self.assertIn("leakage_warnings", html)
        self.assertIn("top_debug_scenarios", html)
        self.assertIn("python -m engine.factors.facts summarize", html)
        self.assertIn("promotion_readiness", html)
        self.assertIn("promotion_blockers", html)
        self.assertIn("missing_backfill_symbols", html)
        self.assertIn("top_diagnostic_rules", html)
        self.assertIn("label_join_summary", html)
        self.assertIn("top_label_join_blockers", html)
        self.assertIn("backfill_replay_available", html)
        self.assertIn("events_path", html)
        self.assertIn("events_summary_path", html)
        self.assertIn("Label Join Rate", html)
        self.assertIn("Label Join Blockers", html)
        self.assertIn("production_rules_modified=false", html)
        self.assertIn("actionable_enabled=false", html)
        self.assertIn("latest_diagnostic_rule_ids", html)
        self.assertIn("approval_decision_snapshot_present", html)
        self.assertIn("last_deployment_record_id", html)
        self.assertIn("real_apply_ready", html)
        self.assertIn("latest_approval_request_path", html)
        self.assertIn("latest_trial_mode", html)
        self.assertIn("latest_proposal_id", html)

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

    def test_historical_fact_section_is_read_only(self):
        html = STRATEGY_PAGE.read_text(encoding="utf-8")
        start = html.index('id="historical-fact-replay-section"')
        end = html.index("Factor Validation Summary", start)
        section = html[start:end].lower()

        self.assertNotIn("<button", section)
        self.assertNotIn("approveproposal", section)
        self.assertNotIn("rejectproposal", section)
        self.assertNotIn("applyhypothesis", section)
        self.assertNotIn("approvehypothesis", section)
        self.assertNotIn("editfactor", section)
        self.assertNotIn("linkfactorrule", section)


if __name__ == "__main__":
    unittest.main()
