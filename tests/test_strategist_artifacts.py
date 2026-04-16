import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ENGINE_SRC = Path(__file__).resolve().parents[1] / "system" / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from engine.strategist_artifacts import (  # noqa: E402
    approve_request,
    ensure_strategist_dirs,
    infer_update_mode,
    load_approval_request,
    mark_request_applied,
    queue_approval_request,
    reject_request,
    record_approval_decision,
    record_code_change_proposal,
    record_code_change_result,
    record_deployment_record,
    record_rollback_note,
    resolve_apply_gate,
    strategist_paths,
    transition_approval_status,
)


class StrategistArtifactTests(unittest.TestCase):
    def test_ensure_dirs_creates_l3a_layout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                paths = ensure_strategist_dirs()
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertTrue(paths["root"].exists())
            self.assertTrue(paths["memory_dir"].exists())
            self.assertTrue(paths["iterations_dir"].exists())
            self.assertTrue(paths["experiments_dir"].exists())
            self.assertTrue(paths["approval_queue_dir"].exists())
            self.assertEqual(paths["code_change_proposals"], artifacts_dir / "strategist" / "code_change_proposals.jsonl")

    def test_l3a_records_append_to_canonical_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                proposal_path = record_code_change_proposal(
                    {
                        "proposal_id": "prop_001",
                        "hypothesis": "narrow false positives",
                        "target_files": ["system/engine/src/engine/rule_engine.py"],
                    }
                )
                result_path = record_code_change_result(
                    {
                        "proposal_id": "prop_001",
                        "tests_passed": True,
                        "dry_run_passed": False,
                    }
                )
                rollback_path = record_rollback_note(
                    {
                        "proposal_id": "prop_001",
                        "rollback_trigger": "backtest regression",
                    }
                )
                paths = strategist_paths()
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertEqual(proposal_path, paths["code_change_proposals"])
            self.assertEqual(result_path, paths["code_change_results"])
            self.assertEqual(rollback_path, paths["rollback_notes"])

            proposal_record = json.loads(proposal_path.read_text().splitlines()[0])
            result_record = json.loads(result_path.read_text().splitlines()[0])
            rollback_record = json.loads(rollback_path.read_text().splitlines()[0])

            self.assertEqual(proposal_record["proposal_id"], "prop_001")
            self.assertTrue(result_record["tests_passed"])
            self.assertEqual(rollback_record["rollback_trigger"], "backtest regression")

    def test_l3b_records_write_to_canonical_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                queue_path = queue_approval_request(
                    "prop_002",
                    {
                        "proposal_id": "prop_002",
                        "status": "awaiting_approval",
                        "recommended_update_mode": "cold",
                        "requires_restart": True,
                    },
                )
                decision_path = record_approval_decision(
                    {
                        "proposal_id": "prop_002",
                        "decision": "approved",
                        "decider_type": "human",
                    }
                )
                deployment_path = record_deployment_record(
                    {
                        "proposal_id": "prop_002",
                        "update_mode": "cold",
                        "success": True,
                    }
                )
                paths = strategist_paths()
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertEqual(queue_path, paths["approval_queue_dir"] / "prop_002.json")
            self.assertEqual(decision_path, paths["approval_decisions"])
            self.assertEqual(deployment_path, paths["deployment_records"])

            queue_record = json.loads(queue_path.read_text())
            decision_record = json.loads(decision_path.read_text().splitlines()[0])
            deployment_record = json.loads(deployment_path.read_text().splitlines()[0])

            self.assertEqual(queue_record["status"], "awaiting_approval")
            self.assertEqual(queue_record["recommended_update_mode"], "cold")
            self.assertEqual(decision_record["decision"], "approved")
            self.assertTrue(deployment_record["success"])

    def test_l3b_state_machine_happy_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                queue_approval_request(
                    "prop_003",
                    {
                        "proposal_id": "prop_003",
                        "status": "validated",
                        "target_files": ["system/engine/src/engine/strategy.py"],
                        "recommended_update_mode": "cold",
                    },
                )
                transition_approval_status("prop_003", "awaiting_approval")
                queue_path, decision_path = approve_request(
                    "prop_003",
                    {
                        "decider_type": "human",
                        "decider_id": "teacher",
                    },
                )
                applied_queue_path, deployment_path = mark_request_applied(
                    "prop_003",
                    {
                        "update_mode": "cold",
                        "success": True,
                    },
                )
                final_record = load_approval_request("prop_003")
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertEqual(queue_path, applied_queue_path)
            self.assertEqual(final_record["status"], "applied")
            self.assertEqual(final_record["decision"], "approved")
            self.assertTrue(final_record["applied"])
            self.assertEqual(json.loads(decision_path.read_text().splitlines()[0])["decision"], "approved")
            self.assertTrue(json.loads(deployment_path.read_text().splitlines()[0])["success"])

    def test_l3b_state_machine_rejects_invalid_transition(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                queue_approval_request(
                    "prop_004",
                    {
                        "proposal_id": "prop_004",
                        "status": "awaiting_approval",
                        "target_files": ["rules/rules.json"],
                        "recommended_update_mode": "hot",
                    },
                )
                with self.assertRaises(ValueError):
                    mark_request_applied(
                        "prop_004",
                        {
                            "update_mode": "cold",
                            "success": True,
                        },
                    )
                queue_path, decision_path = reject_request(
                    "prop_004",
                    {
                        "decider_type": "agent",
                        "decider_id": "yuuka",
                        "reason": "insufficient evidence",
                    },
                )
                final_record = load_approval_request("prop_004")
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertEqual(final_record["status"], "rejected")
            self.assertEqual(final_record["decision"], "rejected")
            self.assertEqual(json.loads(queue_path.read_text())["reason"], "insufficient evidence")
            self.assertEqual(json.loads(decision_path.read_text().splitlines()[0])["decision"], "rejected")

    def test_apply_gate_infers_hot_for_rules_only(self):
        record = {
            "proposal_id": "prop_hot",
            "target_files": ["rules/rules.json"],
        }
        self.assertEqual(infer_update_mode(record), "hot")

    def test_apply_gate_infers_cold_for_strategy_code(self):
        record = {
            "proposal_id": "prop_cold",
            "target_files": ["system/engine/src/engine/strategy.py"],
        }
        self.assertEqual(infer_update_mode(record), "cold")

    def test_resolve_apply_gate_requires_approved_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                queue_approval_request(
                    "prop_005",
                    {
                        "proposal_id": "prop_005",
                        "status": "awaiting_approval",
                        "target_files": ["rules/rules.json"],
                    },
                )
                with self.assertRaises(ValueError):
                    resolve_apply_gate("prop_005")
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

    def test_resolve_apply_gate_blocks_hot_for_code_change(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                queue_approval_request(
                    "prop_006",
                    {
                        "proposal_id": "prop_006",
                        "status": "approved",
                        "target_files": ["system/engine/src/engine/rule_engine.py"],
                        "recommended_update_mode": "hot",
                    },
                )
                with self.assertRaises(ValueError):
                    resolve_apply_gate("prop_006")
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

    def test_mark_request_applied_rejects_mode_mismatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                queue_approval_request(
                    "prop_007",
                    {
                        "proposal_id": "prop_007",
                        "status": "approved",
                        "target_files": ["rules/rules.json"],
                        "recommended_update_mode": "hot",
                    },
                )
                with self.assertRaises(ValueError):
                    mark_request_applied(
                        "prop_007",
                        {
                            "update_mode": "cold",
                            "success": True,
                        },
                    )
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env


if __name__ == "__main__":
    unittest.main()
