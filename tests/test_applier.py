import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ENGINE_SRC = Path(__file__).resolve().parents[1] / "system" / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from engine.applier import apply_approved_proposal, build_apply_plan  # noqa: E402
from engine.strategist_artifacts import queue_approval_request  # noqa: E402


class ApplierTests(unittest.TestCase):
    def test_build_apply_plan_for_hot_update(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                queue_approval_request(
                    "prop_hot",
                    {
                        "proposal_id": "prop_hot",
                        "status": "approved",
                        "target_files": ["rules/rules.json"],
                        "recommended_update_mode": "hot",
                    },
                )
                plan = build_apply_plan("prop_hot")
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertEqual(plan["update_mode"], "hot")
            self.assertFalse(plan["requires_restart"])
            self.assertEqual(plan["apply_action"], "apply_rules_only")

    def test_apply_approved_proposal_records_manual_cold_apply(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                queue_approval_request(
                    "prop_cold",
                    {
                        "proposal_id": "prop_cold",
                        "status": "approved",
                        "target_files": ["system/engine/src/engine/strategy.py"],
                        "recommended_update_mode": "cold",
                    },
                )
                result = apply_approved_proposal(
                    "prop_cold",
                    operator_type="agent",
                    operator_id="applier",
                )
                queue_record = json.loads((artifacts_dir / "strategist" / "approval_queue" / "prop_cold.json").read_text())
                deployment_record = json.loads((artifacts_dir / "strategist" / "deployment_records.jsonl").read_text().splitlines()[0])
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertFalse(result["applied"])
            self.assertTrue(result["recorded"])
            self.assertTrue(result["manual_code_apply_required"])
            self.assertEqual(result["update_mode"], "cold")
            self.assertTrue(result["requires_restart"])
            self.assertEqual(queue_record["status"], "approved")
            self.assertTrue(queue_record["manual_code_apply_required"])
            self.assertEqual(deployment_record["operator_id"], "applier")
            self.assertEqual(deployment_record["apply_action"], "manual_code_apply_required")
            self.assertFalse(deployment_record["code_applied"])


if __name__ == "__main__":
    unittest.main()
