from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ENGINE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from engine.factors.facts import (  # noqa: E402
    collect_historical_facts,
    is_point_in_time_safe,
    normalize_fact,
    validate_fact,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


class FactorFactSchemaTests(unittest.TestCase):
    def _fact(self, **overrides) -> dict:
        payload = {
            "fact_type": "dual_run_readiness",
            "event_time": "2026-04-30T16:00:00+00:00",
            "available_at": "2026-04-30T16:00:01+00:00",
            "source": "unit-test",
            "usage": "debug_only",
            "payload": {"readiness_status": "ready"},
        }
        payload.update(overrides)
        return normalize_fact(payload)

    def test_valid_debug_fact(self) -> None:
        result = validate_fact(self._fact())
        self.assertTrue(result["valid"], result)

    def test_valid_research_context_fact(self) -> None:
        result = validate_fact(self._fact(
            fact_type="factor_observation",
            usage="research_context",
            symbol="AAPL",
            payload={"factor_id": "rsi_14_30m", "value": 42.0},
        ))
        self.assertTrue(result["valid"], result)

    def test_valid_label_fact(self) -> None:
        result = validate_fact(self._fact(
            fact_type="diagnostic_label",
            usage="label",
            payload={"forward_return_1bar": 0.01},
        ))
        self.assertTrue(result["valid"], result)

    def test_invalid_missing_available_at(self) -> None:
        fact = self._fact(usage="research_context", available_at=None)
        result = validate_fact(fact)
        self.assertFalse(result["valid"])
        self.assertIn("available_at", " ".join(result["errors"]))

    def test_debug_missing_available_at_requires_reason(self) -> None:
        fact = self._fact(available_at=None, missing_available_at_reason="legacy decision artifact lacked timestamp")
        result = validate_fact(fact)
        self.assertTrue(result["valid"], result)

    def test_label_fact_is_not_factor_usable(self) -> None:
        fact = self._fact(fact_type="diagnostic_label", usage="label", payload={"forward_return_1bar": 0.02})
        self.assertFalse(is_point_in_time_safe(fact, "2026-04-30T16:05:00+00:00"))

    def test_available_after_decision_is_not_factor_usable(self) -> None:
        candidate = self._fact(
            fact_type="factor_observation",
            usage="factor_candidate",
            available_at="2026-04-30T16:10:00+00:00",
            payload={"factor_id": "rsi_14_30m", "value": 40.0},
        )
        self.assertFalse(is_point_in_time_safe(candidate, "2026-04-30T16:05:00+00:00"))
        self.assertTrue(is_point_in_time_safe(candidate, "2026-04-30T16:10:00+00:00"))


class FactorFactCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.root = Path(self._tmpdir.name)
        self.artifacts = self.root / "artifacts"
        self.logs = self.root / "logs"

    def _write_baseline_sources(self, *, approval_blocked: bool = False) -> None:
        _append_jsonl(self.artifacts / "factors" / "history" / "2026-04-30.jsonl", {
            "timestamp": "2026-04-30T16:00:00+00:00",
            "generated_at": "2026-04-30T16:00:00+00:00",
            "sample_source": "live_shadow",
            "symbols": {
                "AAPL": {
                    "factors": {
                        "rsi_14_30m": {
                            "value": 58.1,
                            "ready": True,
                            "actionable": False,
                            "source_bar_time": "2026-04-30T15:30:00+00:00",
                            "sample_source": "live_shadow",
                            "observation_id": "AAPL|rsi|2026-04-30T15:30:00+00:00|hash|live_shadow",
                        }
                    }
                }
            },
        })
        _append_jsonl(self.artifacts / "factor_research" / "dual_run" / "observations" / "history.jsonl", {
            "observed_at": "2026-04-30T16:01:00+00:00",
            "readiness_status": "ready",
            "readiness_reasons": [],
            "compared_symbols": ["AAPL"],
            "compared_rules": ["rsi_reversal"],
            "compared_count": 1,
            "matched_count": 1,
            "blocking_mismatch_count": 0,
            "top_mismatches": [],
            "diagnostic_only": True,
            "apply_allowed": False,
        })
        _write_json(self.artifacts / "factor_research" / "diagnostic_metrics" / "latest.json", {
            "generated_at": "2026-04-30T16:02:00+00:00",
            "top_label_join_blockers": [{"reason": "insufficient_live_shadow_days", "count": 1}],
            "label_join_summary": {"reasons_count": {"insufficient_live_shadow_days": 1}},
        })
        _write_json(self.artifacts / "factor_research" / "diagnostic_metrics" / "events" / "summary.json", {
            "generated_at": "2026-04-30T16:02:00+00:00",
            "label_join_summary": {"reasons_count": {"insufficient_live_shadow_days": 1}},
        })
        _append_jsonl(self.artifacts / "factor_research" / "diagnostic_metrics" / "events" / "latest.jsonl", {
            "event_id": "diag|AAPL|2026-04-30T15:30:00+00:00|BUY|live_shadow",
            "event_time": "2026-04-30T15:30:00+00:00",
            "symbol": "AAPL",
            "rule_id": "diag_rsi_reversal_rsi_14_30m",
            "source_rule_id": "rsi_reversal",
            "label_join_status": "unjoined",
            "label_join_reason": "insufficient_live_shadow_days",
            "sample_source": "live_shadow",
            "diagnostic_only": True,
            "entered_risk": False,
            "entered_order_intents": False,
        })
        _append_jsonl(self.artifacts / "factor_research" / "diagnostic_metrics" / "events" / "latest.jsonl", {
            "event_id": "diag|MSFT|2026-04-30T15:30:00+00:00|BUY|historical_backfill",
            "event_time": "2026-04-30T15:30:00+00:00",
            "symbol": "MSFT",
            "rule_id": "diag_rsi_reversal_rsi_14_30m",
            "label_join_status": "joined",
            "sample_source": "historical_backfill",
            "forward_return_1bar": 0.01,
        })
        _append_jsonl(self.artifacts / "strategist" / "approval_decisions.jsonl", {
            "proposal_id": "frule_diag_1",
            "decision": "approved",
            "decider_type": "main_agent",
            "decided_at": "2026-04-30T16:03:00+00:00",
        })
        deployment = {
            "proposal_id": "frule_diag_1",
            "proposal_type": "factor_rule_link",
            "target_file": "rules/diagnostic_factor_rules.json",
            "apply_mode": "hot_diagnostic_only",
            "success": True,
            "applied_at": "2026-04-30T16:04:00+00:00",
            "production_rules_modified": False,
            "actionable_enabled": False,
        }
        if not approval_blocked:
            deployment["approval_decision_snapshot"] = {"decision": "approved", "decider_type": "main_agent"}
        _append_jsonl(self.artifacts / "strategist" / "deployment_records.jsonl", deployment)
        _write_json(self.logs / "latest" / "strategy_overview.json", {
            "generated_at": "2026-04-30T16:05:00+00:00",
            "data_health": {
                "AAPL": {
                    "strategy_ready": False,
                    "reason": "bars_empty",
                    "actionable_block_reason": "bars_empty",
                }
            },
        })

    def test_collector_generates_expected_fact_types(self) -> None:
        self._write_baseline_sources()
        result = collect_historical_facts(
            artifacts_root=self.artifacts,
            logs_root=self.logs,
            generated_at="2026-04-30T16:06:00+00:00",
        )

        self.assertEqual(result["status"], "ok")
        fact_types = result["fact_type_counts"]
        self.assertIn("factor_observation", fact_types)
        self.assertIn("dual_run_readiness", fact_types)
        self.assertIn("diagnostic_signal_event", fact_types)
        self.assertIn("diagnostic_label", fact_types)
        self.assertIn("label_join_blocker", fact_types)
        self.assertIn("approval_decision", fact_types)
        self.assertIn("deployment_record", fact_types)
        self.assertIn("data_quality_blocker", fact_types)
        self.assertNotIn("factor_candidate", result["usage_counts"])
        self.assertTrue((self.artifacts / "factor_research" / "facts" / "latest.json").exists())
        self.assertTrue((self.artifacts / "factor_research" / "scenarios" / "latest.json").exists())

    def test_scenario_generation_and_history_dedupe(self) -> None:
        self._write_baseline_sources(approval_blocked=True)
        first = collect_historical_facts(
            artifacts_root=self.artifacts,
            logs_root=self.logs,
            generated_at="2026-04-30T16:06:00+00:00",
        )
        second = collect_historical_facts(
            artifacts_root=self.artifacts,
            logs_root=self.logs,
            generated_at="2026-04-30T16:06:00+00:00",
        )
        scenarios = first["scenarios"]["scenario_type_counts"]

        self.assertIn("dual_run_ready", scenarios)
        self.assertIn("label_join_blocker", scenarios)
        self.assertIn("diagnostic_signal_unlabeled", scenarios)
        self.assertIn("approval_integrity_blocked", scenarios)
        self.assertIn("data_health_blocker", scenarios)
        self.assertGreater(first["scenario_count"], 0)
        self.assertEqual(second["writes"]["facts"]["history_appended"], 0)
        self.assertEqual(second["writes"]["scenarios"]["history_appended"], 0)

    def test_no_facts_fail_soft(self) -> None:
        result = collect_historical_facts(
            artifacts_root=self.artifacts,
            logs_root=self.logs,
            generated_at="2026-04-30T16:06:00+00:00",
        )
        self.assertEqual(result["fact_count"], 0)
        self.assertEqual(result["scenario_count"], 0)
        self.assertEqual(result["scenarios"]["scenarios"], [])

    def test_fact_outputs_remain_out_of_execution_paths(self) -> None:
        self._write_baseline_sources()
        result = collect_historical_facts(
            artifacts_root=self.artifacts,
            logs_root=self.logs,
            generated_at="2026-04-30T16:06:00+00:00",
        )
        safety = result["facts"]["safety"]

        self.assertFalse(safety["entered_risk"])
        self.assertFalse(safety["entered_execution"])
        self.assertFalse(safety["entered_execution_preview"])
        self.assertFalse(safety["entered_order_intents"])
        self.assertFalse(safety["broker_submit"])
        self.assertFalse(safety["approve"])
        self.assertFalse(safety["apply"])


if __name__ == "__main__":
    unittest.main()
