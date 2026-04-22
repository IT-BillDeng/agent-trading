from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ENGINE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from engine.applier import apply_approved_proposal  # noqa: E402
from engine.strategist_artifacts import queue_approval_request  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_FILE = REPO_ROOT / "rules" / "rules.json"
FACTOR_REGISTRY_FILE = REPO_ROOT / "factors" / "registry.json"


class FactorApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.repo_root = Path(self._tmpdir.name)
        self.artifacts_dir = self.repo_root / "artifacts"
        self.rules_path = self.repo_root / "rules" / "rules.json"
        self.factor_registry_path = self.repo_root / "factors" / "registry.json"

        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        self.factor_registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.original_rules = json.loads(RULES_FILE.read_text())
        self.original_registry = json.loads(FACTOR_REGISTRY_FILE.read_text())
        self.rules_path.write_text(json.dumps(self.original_rules, ensure_ascii=False, indent=2))
        self.factor_registry_path.write_text(json.dumps(self.original_registry, ensure_ascii=False, indent=2))

        self.live_execution_path = self.repo_root / "system" / "engine" / "src" / "engine" / "live_execution.py"
        self.risk_path = self.repo_root / "system" / "engine" / "src" / "engine" / "risk.py"
        self.broker_path = self.repo_root / "system" / "engine" / "src" / "engine" / "broker_client.py"
        self.factor_impl_path = self.repo_root / "system" / "engine" / "src" / "engine" / "factors" / "builtins.py"
        for path, text in (
            (self.live_execution_path, "LIVE_SENTINEL = 1\n"),
            (self.risk_path, "RISK_SENTINEL = 1\n"),
            (self.broker_path, "BROKER_SENTINEL = 1\n"),
            (self.factor_impl_path, "FACTOR_SENTINEL = 1\n"),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        self._old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
        os.environ["ENGINE_ARTIFACTS_DIR"] = str(self.artifacts_dir)
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        if self._old_env is None:
            os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
        else:
            os.environ["ENGINE_ARTIFACTS_DIR"] = self._old_env

    def _base_factor_record(
        self,
        proposal_id: str,
        *,
        proposal_type: str,
        factor_id: str,
        target_files: list[str],
        recommended_update_mode: str,
    ) -> dict:
        return {
            "proposal_id": proposal_id,
            "proposal_type": proposal_type,
            "status": "approved",
            "recommended_update_mode": recommended_update_mode,
            "target_files": target_files,
            "factor_id": factor_id,
            "hypothesis": "validate factor governance path",
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
            "ic": 0.12,
            "coverage": 0.95,
            "missing_rate": 0.05,
            "correlation_with_existing": None,
            "backtest_delta": None,
            "fee_cost_impact": None,
            "paper_shadow_required_days": 5,
            "risk_notes": ["shadow only"],
            "rollback_plan": "restore previous file from backup",
        }

    def _read_queue_record(self, proposal_id: str) -> dict:
        path = self.artifacts_dir / "strategist" / "approval_queue" / f"{proposal_id}.json"
        return json.loads(path.read_text())

    def _read_deployment_records(self) -> list[dict]:
        path = self.artifacts_dir / "strategist" / "deployment_records.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def _read_failure_records(self) -> list[dict]:
        path = self.artifacts_dir / "strategist" / "failure_records.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_approved_factor_config_hot_apply_succeeds(self) -> None:
        updated_registry = copy.deepcopy(self.original_registry)
        updated_registry["factors"]["rsi_14_30m"]["version"] = 2
        proposal_id = "factor_config_hot"
        before_live = self.live_execution_path.read_text()
        before_risk = self.risk_path.read_text()
        before_broker = self.broker_path.read_text()

        record = self._base_factor_record(
            proposal_id,
            proposal_type="factor_config",
            factor_id="rsi_14_30m",
            target_files=["factors/registry.json"],
            recommended_update_mode="hot",
        )
        record["target_contents"] = {"factors/registry.json": updated_registry}
        queue_approval_request(proposal_id, record)

        result = apply_approved_proposal(
            proposal_id,
            operator_type="agent",
            operator_id="applier",
        )

        deployment_record = self._read_deployment_records()[0]
        queue_record = self._read_queue_record(proposal_id)
        applied_registry = json.loads(self.factor_registry_path.read_text())

        self.assertTrue(result["applied"])
        self.assertEqual(queue_record["status"], "applied")
        self.assertEqual(applied_registry["factors"]["rsi_14_30m"]["version"], 2)
        self.assertEqual(deployment_record["proposal_type"], "factor_config")
        self.assertEqual(deployment_record["changed_factors"], ["rsi_14_30m"])
        self.assertEqual(deployment_record["changed_rules"], [])
        self.assertTrue(deployment_record["registry_hash"])
        self.assertTrue(deployment_record["validation_summary"]["factor_registry"]["valid"])
        self.assertEqual(before_live, self.live_execution_path.read_text())
        self.assertEqual(before_risk, self.risk_path.read_text())
        self.assertEqual(before_broker, self.broker_path.read_text())

    def test_invalid_factor_registry_hot_apply_fails_and_records_failure_reason(self) -> None:
        invalid_registry = copy.deepcopy(self.original_registry)
        invalid_registry["defaults"]["allow_actionable_consumption"] = "yes"
        proposal_id = "factor_config_invalid"
        before_bytes = self.factor_registry_path.read_bytes()

        record = self._base_factor_record(
            proposal_id,
            proposal_type="factor_config",
            factor_id="rsi_14_30m",
            target_files=["factors/registry.json"],
            recommended_update_mode="hot",
        )
        record["target_contents"] = {"factors/registry.json": invalid_registry}
        queue_approval_request(proposal_id, record)

        with self.assertRaisesRegex(ValueError, "invalid factor registry payload"):
            apply_approved_proposal(
                proposal_id,
                operator_type="agent",
                operator_id="applier",
            )

        self.assertEqual(before_bytes, self.factor_registry_path.read_bytes())
        deployment_record = self._read_deployment_records()[0]
        failure_record = self._read_failure_records()[0]
        queue_record = self._read_queue_record(proposal_id)

        self.assertEqual(queue_record["status"], "approved")
        self.assertFalse(deployment_record["success"])
        self.assertIn("allow_actionable_consumption", deployment_record["error"])
        self.assertIn("allow_actionable_consumption", failure_record["reason"])
        self.assertEqual(failure_record["proposal_type"], "factor_config")

    def test_factor_code_is_marked_manual_code_apply_required(self) -> None:
        proposal_id = "factor_code_manual"
        before_bytes = self.factor_impl_path.read_bytes()

        record = self._base_factor_record(
            proposal_id,
            proposal_type="factor_code",
            factor_id="rsi_14_30m",
            target_files=["system/engine/src/engine/factors/builtins.py"],
            recommended_update_mode="cold",
        )
        queue_approval_request(proposal_id, record)

        result = apply_approved_proposal(
            proposal_id,
            operator_type="agent",
            operator_id="applier",
        )

        deployment_record = self._read_deployment_records()[0]
        queue_record = self._read_queue_record(proposal_id)

        self.assertFalse(result["applied"])
        self.assertTrue(result["manual_code_apply_required"])
        self.assertEqual(before_bytes, self.factor_impl_path.read_bytes())
        self.assertEqual(queue_record["status"], "approved")
        self.assertTrue(queue_record["manual_code_apply_required"])
        self.assertEqual(deployment_record["apply_action"], "manual_code_apply_required")
        self.assertFalse(deployment_record["code_applied"])
        self.assertEqual(deployment_record["changed_factors"], ["rsi_14_30m"])

    def test_factor_rule_link_unknown_factor_reference_fails(self) -> None:
        updated_rules = copy.deepcopy(self.original_rules)
        updated_rules["rules"].append(
            {
                "rule_id": "factor_missing_rule",
                "enabled": True,
                "priority": 999,
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "action": "BUY",
                    "conditions": {
                        "type": "indicator",
                        "indicator": "factor",
                        "factor_id": "missing_factor",
                        "compare": {"operator": "above", "value": 1},
                    },
                },
            }
        )
        proposal_id = "factor_rule_link_unknown"
        before_bytes = self.rules_path.read_bytes()

        record = self._base_factor_record(
            proposal_id,
            proposal_type="factor_rule_link",
            factor_id="missing_factor",
            target_files=["rules/rules.json"],
            recommended_update_mode="hot",
        )
        record["target_contents"] = {"rules/rules.json": updated_rules}
        queue_approval_request(proposal_id, record)

        with self.assertRaisesRegex(ValueError, "unknown factor_id"):
            apply_approved_proposal(
                proposal_id,
                operator_type="agent",
                operator_id="applier",
            )

        self.assertEqual(before_bytes, self.rules_path.read_bytes())
        failure_record = self._read_failure_records()[0]
        self.assertIn("unknown factor_id", failure_record["reason"])
        self.assertEqual(failure_record["proposal_type"], "factor_rule_link")

    def test_factor_apply_does_not_modify_live_execution_or_broker_files(self) -> None:
        updated_registry = copy.deepcopy(self.original_registry)
        updated_registry["factors"]["bollinger_zscore_20_2_30m"]["version"] = 2
        proposal_id = "factor_config_safe_targets"
        before_live = self.live_execution_path.read_text()
        before_risk = self.risk_path.read_text()
        before_broker = self.broker_path.read_text()

        record = self._base_factor_record(
            proposal_id,
            proposal_type="factor_config",
            factor_id="bollinger_zscore_20_2_30m",
            target_files=["factors/registry.json"],
            recommended_update_mode="hot",
        )
        record["target_contents"] = {"factors/registry.json": updated_registry}
        queue_approval_request(proposal_id, record)

        apply_approved_proposal(
            proposal_id,
            operator_type="agent",
            operator_id="applier",
        )

        self.assertEqual(before_live, self.live_execution_path.read_text())
        self.assertEqual(before_risk, self.risk_path.read_text())
        self.assertEqual(before_broker, self.broker_path.read_text())


if __name__ == "__main__":
    unittest.main()
