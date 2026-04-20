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


class ColdApplyGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.artifacts_dir = Path(self._tmpdir.name) / "artifacts"
        self._old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
        os.environ["ENGINE_ARTIFACTS_DIR"] = str(self.artifacts_dir)
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        if self._old_env is None:
            os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
        else:
            os.environ["ENGINE_ARTIFACTS_DIR"] = self._old_env

    def test_cold_apply_keeps_proposal_approved_and_records_manual_action(self) -> None:
        queue_approval_request(
            "cold_manual",
            {
                "proposal_id": "cold_manual",
                "status": "approved",
                "target_files": ["system/engine/src/engine/strategy.py"],
                "recommended_update_mode": "cold",
            },
        )

        plan = build_apply_plan("cold_manual")
        result = apply_approved_proposal(
            "cold_manual",
            operator_type="agent",
            operator_id="applier",
        )

        queue_record = json.loads(
            (self.artifacts_dir / "strategist" / "approval_queue" / "cold_manual.json").read_text()
        )
        deployment_record = json.loads(
            (self.artifacts_dir / "strategist" / "deployment_records.jsonl").read_text().splitlines()[0]
        )

        self.assertEqual(plan["update_mode"], "cold")
        self.assertTrue(plan["requires_restart"])
        self.assertFalse(result["applied"])
        self.assertTrue(result["recorded"])
        self.assertTrue(result["manual_code_apply_required"])
        self.assertEqual(queue_record["status"], "approved")
        self.assertTrue(queue_record["manual_code_apply_required"])
        self.assertEqual(queue_record["apply_gate"]["apply_action"], "manual_code_apply_required")
        self.assertTrue(deployment_record["success"])
        self.assertFalse(deployment_record["code_applied"])
        self.assertEqual(deployment_record["apply_action"], "manual_code_apply_required")

    def test_cold_apply_still_requires_approved_status(self) -> None:
        queue_approval_request(
            "cold_unapproved",
            {
                "proposal_id": "cold_unapproved",
                "status": "awaiting_approval",
                "target_files": ["system/engine/src/engine/rule_engine.py"],
                "recommended_update_mode": "cold",
            },
        )

        with self.assertRaises(ValueError):
            apply_approved_proposal(
                "cold_unapproved",
                operator_type="agent",
                operator_id="applier",
            )


if __name__ == "__main__":
    unittest.main()
