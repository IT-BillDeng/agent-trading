from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.proposal_schema import (  # noqa: E402
    FACTOR_PROPOSAL_QUALITY_THRESHOLDS,
    validate_proposal_record,
)


def _valid_factor_proposal() -> dict:
    return {
        "proposal_id": "factor_prop_quality",
        "proposal_type": "factor_config",
        "status": "approved",
        "recommended_update_mode": "hot",
        "target_files": ["factors/registry.json"],
        "factor_id": "rsi_14_30m",
        "hypothesis": "quality gate should pass",
        "input_data": ["regular_session_30m_bars"],
        "session": "regular",
        "usage": ["shadow", "rule_condition_candidate"],
        "lookback_bars": 14,
        "horizon_bars": 1,
        "validation_results": {
            "ic": 0.12,
            "coverage": 0.95,
            "missing_rate": 0.05,
        },
        "correlation_with_existing": 0.35,
        "backtest_delta": {"sharpe": 0.08},
        "fee_cost_impact": {"bps": 1.2},
        "paper_shadow_required_days": 5,
        "risk_notes": ["shadow only"],
        "rollback_plan": "restore previous file from backup",
    }


def _valid_factor_rule_link_proposal() -> dict:
    payload = _valid_factor_proposal()
    payload["proposal_type"] = "factor_rule_link"
    payload["target_files"] = ["rules/rules.json"]
    payload["paper_shadow_required_days"] = 20
    return payload


class FactorProposalSchemaTests(unittest.TestCase):
    def test_valid_quality_gate_passes_and_records_summary(self) -> None:
        result = validate_proposal_record(_valid_factor_proposal())

        self.assertTrue(result["valid"])
        self.assertEqual(result["quality_summary"]["failed_checks"], [])
        self.assertEqual(
            result["quality_summary"]["thresholds"]["min_abs_ic"],
            FACTOR_PROPOSAL_QUALITY_THRESHOLDS["min_abs_ic"],
        )

    def test_low_ic_is_rejected(self) -> None:
        payload = _valid_factor_proposal()
        payload["validation_results"]["ic"] = 0.01

        result = validate_proposal_record(payload)

        self.assertFalse(result["valid"])
        self.assertTrue(any("abs(ic)" in error for error in result["errors"]))

    def test_high_missing_rate_is_rejected(self) -> None:
        payload = _valid_factor_proposal()
        payload["validation_results"]["missing_rate"] = 0.4

        result = validate_proposal_record(payload)

        self.assertFalse(result["valid"])
        self.assertTrue(any("missing_rate" in error for error in result["errors"]))

    def test_insufficient_shadow_days_is_rejected(self) -> None:
        payload = _valid_factor_proposal()
        payload["paper_shadow_required_days"] = 2

        result = validate_proposal_record(payload)

        self.assertFalse(result["valid"])
        self.assertTrue(any("paper_shadow_required_days" in error for error in result["errors"]))

    def test_null_optional_analysis_fields_emit_warnings(self) -> None:
        payload = _valid_factor_proposal()
        payload["correlation_with_existing"] = None
        payload["backtest_delta"] = None
        payload["fee_cost_impact"] = None

        result = validate_proposal_record(payload)

        self.assertTrue(result["valid"])
        self.assertTrue(any("correlation_with_existing" in warning for warning in result["warnings"]))
        self.assertTrue(any("backtest_delta" in warning for warning in result["warnings"]))
        self.assertTrue(any("fee/cost impact" in warning for warning in result["warnings"]))

    def test_factor_rule_link_requires_non_null_quality_fields(self) -> None:
        payload = _valid_factor_rule_link_proposal()
        payload["correlation_with_existing"] = None
        payload["backtest_delta"] = None
        payload["fee_cost_impact"] = None

        result = validate_proposal_record(payload)

        self.assertFalse(result["valid"])
        self.assertTrue(any("factor_rule_link proposals require non-null correlation_with_existing" in error for error in result["errors"]))
        self.assertTrue(any("factor_rule_link proposals require non-null backtest_delta" in error for error in result["errors"]))
        self.assertTrue(any("factor_rule_link proposals require non-null fee_cost_impact" in error for error in result["errors"]))

    def test_factor_rule_link_requires_longer_shadow_observation(self) -> None:
        payload = _valid_factor_rule_link_proposal()
        payload["paper_shadow_required_days"] = 10

        result = validate_proposal_record(payload)

        self.assertFalse(result["valid"])
        self.assertEqual(
            result["quality_summary"]["thresholds"]["min_paper_shadow_required_days"],
            20,
        )
        self.assertTrue(any("paper_shadow_required_days=10 < 20" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
