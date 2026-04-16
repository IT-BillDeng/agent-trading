import json
import os
import tempfile
import unittest
from pathlib import Path

from dashboard.scheduler import SignalScheduler


class SchedulerAuditLogTests(unittest.TestCase):
    def test_persist_cycle_outputs_writes_runtime_snapshot_and_audit_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime_dir = root / "runtime"
            logs_root = root / "logs"
            config_file = root / "app_config.json"
            runtime_dir.mkdir(parents=True)
            logs_root.mkdir(parents=True)
            config_file.write_text(json.dumps({"system": {}}, ensure_ascii=False))

            scheduler = SignalScheduler(
                app_config_path=str(config_file),
                runtime_dir=str(runtime_dir),
                provider_name="yfinance",
                interval_seconds=60,
            )
            summary = {
                "cycle_id": "20260416_180000",
                "account_ok": True,
                "assets_ok": True,
                "positions_ok": True,
                "active_orders_ok": True,
                "quote_access": {"US": {"quote_delay": {"ok": True}}},
                "asset_snapshot": {"netLiquidation": 1000},
                "position_count": 1,
                "active_order_count": 0,
                "strategy": {"signals": [{"symbol": "AAPL", "action": "BUY"}]},
                "risk": {"decisions": [], "allowed_count": 1, "preview_blockers": []},
                "order_intents": {"items": [], "count": 0},
                "notification_preview": {"items": [], "count": 0},
                "notification_dispatch": {"items": [], "count": 0},
                "execution_preview_check": {"items": []},
                "execution_submit": {"items": [], "count": 0},
                "order_sync": {"items": [], "count": 0},
            }
            app = type("App", (), {"raw": {"system": {}}})()

            old_logs_dir = os.environ.get("ENGINE_LOGS_DIR")
            os.environ["ENGINE_LOGS_DIR"] = str(logs_root)
            try:
                scheduler._persist_cycle_outputs(summary, app)
            finally:
                if old_logs_dir is None:
                    os.environ.pop("ENGINE_LOGS_DIR", None)
                else:
                    os.environ["ENGINE_LOGS_DIR"] = old_logs_dir

            cycle_file = runtime_dir / ".last_execution_cycle.json"
            execution_log = logs_root / "audit" / "execution.jsonl"
            cycles_log = logs_root / "audit" / "cycles.jsonl"
            scheduler_log = logs_root / "service" / "scheduler.jsonl"

            self.assertTrue(cycle_file.exists())
            self.assertTrue(execution_log.exists())
            self.assertTrue(cycles_log.exists())
            self.assertTrue(scheduler_log.exists())

            cycle_data = json.loads(cycle_file.read_text())
            self.assertEqual(cycle_data["cycle_id"], "20260416_180000")

            execution_entry = json.loads(execution_log.read_text().strip().splitlines()[-1])
            cycles_entry = json.loads(cycles_log.read_text().strip().splitlines()[-1])
            scheduler_entry = json.loads(scheduler_log.read_text().strip().splitlines()[-1])
            self.assertEqual(execution_entry["cycle_id"], "20260416_180000")
            self.assertEqual(cycles_entry["cycle_id"], "20260416_180000")
            self.assertEqual(scheduler_entry["cycle_id"], "20260416_180000")
            self.assertEqual(scheduler_entry["kind"], "cycle_complete")
            self.assertIn("audit_logs", summary)


if __name__ == "__main__":
    unittest.main()
