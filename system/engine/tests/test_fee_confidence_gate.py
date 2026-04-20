from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ENGINE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from engine.applier import apply_approved_proposal, build_apply_plan  # noqa: E402
from engine.strategist_artifacts import queue_approval_request  # noqa: E402


class FeeConfidenceGateTests(unittest.TestCase):
    def _write_fee_summary(self, artifacts_dir: Path, *, trust_level: str | None):
        broker_dir = artifacts_dir / "broker"
        broker_dir.mkdir(parents=True, exist_ok=True)
        if trust_level is None:
            return
        payload = {
            "count": 5,
            "avg_delta": 0.1,
            "max_abs_delta": 0.2,
            "trust": {
                "level": trust_level,
                "label": {
                    "high": "可信",
                    "observe": "观察",
                    "low": "不可信",
                }.get(trust_level, "缺失"),
                "reason": f"trust={trust_level}",
            },
        }
        (broker_dir / "fee_calibration_summary.json").write_text(json.dumps(payload, ensure_ascii=False))

    def test_low_confidence_blocks_hot_enable_new_buy_rule(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                self._write_fee_summary(artifacts_dir, trust_level="low")
                queue_approval_request(
                    "prop_fee_low",
                    {
                        "proposal_id": "prop_fee_low",
                        "status": "approved",
                        "target_files": ["rules/rules.json"],
                        "recommended_update_mode": "hot",
                        "change_intent": "enable_new_buy_rule",
                        "turnover_profile": "high",
                    },
                )
                with self.assertRaisesRegex(ValueError, "fee confidence gate blocked apply"):
                    build_apply_plan("prop_fee_low")
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

    def test_missing_confidence_allows_reduce_risk_hot_apply(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                queue_approval_request(
                    "prop_reduce_risk",
                    {
                        "proposal_id": "prop_reduce_risk",
                        "status": "approved",
                        "target_files": ["rules/rules.json"],
                        "recommended_update_mode": "hot",
                        "change_intent": "reduce_risk",
                    },
                )
                plan = build_apply_plan("prop_reduce_risk")
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertEqual(plan["fee_confidence_snapshot"]["confidence"], "missing")
            self.assertTrue(plan["fee_confidence_gate"]["allowed"])

    def test_medium_confidence_allows_low_turnover_enablement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                self._write_fee_summary(artifacts_dir, trust_level="observe")
                queue_approval_request(
                    "prop_medium_low_turnover",
                    {
                        "proposal_id": "prop_medium_low_turnover",
                        "status": "approved",
                        "target_files": ["rules/rules.json"],
                        "recommended_update_mode": "hot",
                        "change_intent": "enable_new_buy_rule",
                        "turnover_profile": "low",
                    },
                )
                plan = build_apply_plan("prop_medium_low_turnover")
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertEqual(plan["fee_confidence_snapshot"]["confidence"], "medium")
            self.assertTrue(plan["fee_confidence_gate"]["allowed"])

    def test_deployment_record_contains_fee_confidence_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                self._write_fee_summary(artifacts_dir, trust_level="high")
                queue_approval_request(
                    "prop_apply_high",
                    {
                        "proposal_id": "prop_apply_high",
                        "status": "approved",
                        "target_files": ["rules/rules.json"],
                        "recommended_update_mode": "hot",
                        "change_intent": "enable_new_buy_rule",
                        "turnover_profile": "high",
                    },
                )
                apply_approved_proposal(
                    "prop_apply_high",
                    operator_type="agent",
                    operator_id="applier",
                )
                deployment_record = json.loads((artifacts_dir / "strategist" / "deployment_records.jsonl").read_text().splitlines()[0])
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            snapshot = deployment_record["fee_confidence_snapshot"]
            self.assertEqual(snapshot["confidence"], "high")
            self.assertEqual(snapshot["label"], "可信")


if __name__ == "__main__":
    unittest.main()
