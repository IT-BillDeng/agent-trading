from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ENGINE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from engine.applier import apply_approved_proposal  # noqa: E402
from engine.strategist_artifacts import queue_approval_request  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_FILE = REPO_ROOT / "rules" / "rules.json"


def _checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class HotApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.repo_root = Path(self._tmpdir.name)
        self.artifacts_dir = self.repo_root / "artifacts"
        self.rules_path = self.repo_root / "rules" / "rules.json"
        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        self.original_rules = json.loads(RULES_FILE.read_text())
        self.rules_path.write_text(json.dumps(self.original_rules, ensure_ascii=False, indent=2))

        self._old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
        os.environ["ENGINE_ARTIFACTS_DIR"] = str(self.artifacts_dir)
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        if self._old_env is None:
            os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
        else:
            os.environ["ENGINE_ARTIFACTS_DIR"] = self._old_env

    def _queue_hot_proposal(self, proposal_id: str, payload: dict) -> None:
        queue_approval_request(
            proposal_id,
            {
                "proposal_id": proposal_id,
                "status": "approved",
                "target_files": ["rules/rules.json"],
                "recommended_update_mode": "hot",
                "target_contents": {"rules/rules.json": payload},
            },
        )

    def _read_queue_record(self, proposal_id: str) -> dict:
        path = self.artifacts_dir / "strategist" / "approval_queue" / f"{proposal_id}.json"
        return json.loads(path.read_text())

    def _read_deployment_records(self) -> list[dict]:
        path = self.artifacts_dir / "strategist" / "deployment_records.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_hot_apply_updates_rules_file_and_records_checksums(self) -> None:
        updated_rules = json.loads(json.dumps(self.original_rules))
        updated_rules["rules"][0]["enabled"] = not updated_rules["rules"][0]["enabled"]
        before_bytes = self.rules_path.read_bytes()

        self._queue_hot_proposal("hot_success", updated_rules)
        result = apply_approved_proposal(
            "hot_success",
            operator_type="agent",
            operator_id="applier",
        )

        after_bytes = self.rules_path.read_bytes()
        queue_record = self._read_queue_record("hot_success")
        deployment_record = self._read_deployment_records()[0]
        target_record = deployment_record["targets"][0]

        self.assertTrue(result["applied"])
        self.assertNotEqual(before_bytes, after_bytes)
        self.assertEqual(queue_record["status"], "applied")
        self.assertEqual(target_record["target_file"], "rules/rules.json")
        self.assertEqual(target_record["before_checksum"], _checksum(before_bytes))
        self.assertEqual(target_record["after_checksum"], _checksum(after_bytes))
        self.assertTrue(target_record["validation_result"]["valid"])
        self.assertEqual(deployment_record["operator_id"], "applier")
        self.assertTrue(deployment_record["success"])

    def test_hot_apply_invalid_rules_does_not_modify_file(self) -> None:
        invalid_rules = json.loads(json.dumps(self.original_rules))
        invalid_rules["rules"][0]["entry"]["action"] = "SELL"
        before_bytes = self.rules_path.read_bytes()

        self._queue_hot_proposal("hot_invalid", invalid_rules)

        with self.assertRaises(ValueError):
            apply_approved_proposal(
                "hot_invalid",
                operator_type="agent",
                operator_id="applier",
            )

        after_bytes = self.rules_path.read_bytes()
        queue_record = self._read_queue_record("hot_invalid")
        deployment_record = self._read_deployment_records()[0]

        self.assertEqual(before_bytes, after_bytes)
        self.assertEqual(queue_record["status"], "approved")
        self.assertFalse(deployment_record["success"])
        self.assertTrue(deployment_record["rollback_performed"])
        self.assertEqual(deployment_record["targets"], [])

    def test_hot_apply_rolls_back_when_finalize_step_fails(self) -> None:
        updated_rules = json.loads(json.dumps(self.original_rules))
        updated_rules["rules"][0]["priority"] = updated_rules["rules"][0]["priority"] + 1
        before_bytes = self.rules_path.read_bytes()

        self._queue_hot_proposal("hot_rollback", updated_rules)

        with patch("engine.applier.mark_request_applied", side_effect=RuntimeError("finalize failed")):
            with self.assertRaises(RuntimeError):
                apply_approved_proposal(
                    "hot_rollback",
                    operator_type="agent",
                    operator_id="applier",
                )

        after_bytes = self.rules_path.read_bytes()
        queue_record = self._read_queue_record("hot_rollback")
        deployment_record = self._read_deployment_records()[0]
        target_record = deployment_record["targets"][0]

        self.assertEqual(before_bytes, after_bytes)
        self.assertEqual(queue_record["status"], "approved")
        self.assertFalse(deployment_record["success"])
        self.assertTrue(deployment_record["rollback_performed"])
        self.assertEqual(target_record["before_checksum"], _checksum(before_bytes))
        self.assertNotEqual(target_record["before_checksum"], target_record["after_checksum"])

    def test_hot_apply_missing_payload_records_failure_with_fee_confidence_snapshot(self) -> None:
        broker_dir = self.artifacts_dir / "broker"
        broker_dir.mkdir(parents=True, exist_ok=True)
        (broker_dir / "fee_calibration_summary.json").write_text(
            json.dumps(
                {
                    "count": 3,
                    "avg_delta": 0.1,
                    "max_abs_delta": 0.2,
                    "trust": {
                        "level": "high",
                        "label": "可信",
                        "reason": "calibrated",
                    },
                },
                ensure_ascii=False,
            )
        )
        queue_approval_request(
            "hot_missing_payload",
            {
                "proposal_id": "hot_missing_payload",
                "status": "approved",
                "target_files": ["rules/rules.json"],
                "recommended_update_mode": "hot",
            },
        )

        with self.assertRaisesRegex(ValueError, "target_contents or single-file content"):
            apply_approved_proposal(
                "hot_missing_payload",
                operator_type="agent",
                operator_id="applier",
            )

        deployment_record = self._read_deployment_records()[0]
        self.assertFalse(deployment_record["success"])
        self.assertEqual(deployment_record["targets"], [])
        self.assertEqual(
            deployment_record["fee_confidence_snapshot"]["confidence"],
            "high",
        )
        self.assertIn("target_contents or single-file content", deployment_record["error"])


if __name__ == "__main__":
    unittest.main()
