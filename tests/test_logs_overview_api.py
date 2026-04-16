import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dashboard import main as dashboard_main


class LogsOverviewApiTests(unittest.TestCase):
    def test_build_logs_overview_syncs_latest_snapshots_and_status_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime_dir = root / "runtime"
            logs_root = root / "logs"
            audit_dir = logs_root / "audit"
            service_dir = logs_root / "service"
            latest_dir = logs_root / "latest"
            legacy_dir = runtime_dir / "logs"
            strategist_iterations_dir = logs_root / "agents" / "strategist" / "iterations"

            (runtime_dir / "state").mkdir(parents=True)
            (runtime_dir / "watcher").mkdir(parents=True)
            audit_dir.mkdir(parents=True)
            service_dir.mkdir(parents=True)
            legacy_dir.mkdir(parents=True)
            strategist_iterations_dir.mkdir(parents=True)

            (runtime_dir / ".last_execution_cycle.json").write_text(
                json.dumps({"cycle_id": "cycle_1", "market_state": {"US": {"state": "OPEN"}}}, ensure_ascii=False)
            )
            (runtime_dir / "market_context.json").write_text(
                json.dumps({"session": "regular", "tz": "America/New_York"}, ensure_ascii=False)
            )
            (runtime_dir / "state" / "control_state.json").write_text(
                json.dumps({"locked": False, "trading_mode": "signals"}, ensure_ascii=False)
            )
            (runtime_dir / "state" / "execution_state.json").write_text(
                json.dumps({"last_submit_at": "2026-04-16T10:00:00Z"}, ensure_ascii=False)
            )
            (runtime_dir / "watcher" / "latest.json").write_text(
                json.dumps({"generated_at": "2026-04-16T10:00:00Z", "summary": "healthy"}, ensure_ascii=False)
            )
            (runtime_dir / "watcher" / "history.jsonl").write_text(
                json.dumps({"generated_at": "2026-04-16T10:00:00Z"}) + "\n"
            )
            (runtime_dir / "newswire").mkdir(parents=True)
            (runtime_dir / "newswire" / "latest.json").write_text(json.dumps({"items": []}, ensure_ascii=False))
            (runtime_dir / "strategist_iterations").mkdir(parents=True)
            (runtime_dir / "strategy_plan_latest.json").write_text(json.dumps({"summary": "no change"}, ensure_ascii=False))

            (audit_dir / "execution.jsonl").write_text(
                json.dumps({"ts": "2026-04-16T10:01:00Z", "cycle_id": "cycle_1"}) + "\n"
            )
            (service_dir / "watcher.jsonl").write_text(
                json.dumps({"generated_at": "2026-04-16T10:02:00Z", "summary": "healthy"}) + "\n"
            )
            (legacy_dir / "execution.jsonl").write_text(
                json.dumps({"ts": "2026-04-15T10:01:00Z", "cycle_id": "legacy_cycle"}) + "\n"
            )

            with mock.patch.object(dashboard_main, "RUNTIME_DIR", runtime_dir), \
                mock.patch.object(dashboard_main, "LOGS_ROOT", logs_root), \
                mock.patch.object(dashboard_main, "AUDIT_LOG_DIR", audit_dir), \
                mock.patch.object(dashboard_main, "SERVICE_LOG_DIR", service_dir), \
                mock.patch.object(dashboard_main, "LATEST_LOG_DIR", latest_dir), \
                mock.patch.object(dashboard_main, "LEGACY_LOG_DIR", legacy_dir), \
                mock.patch.object(dashboard_main, "STRATEGIST_ITERATIONS_LOG_DIR", strategist_iterations_dir):
                overview = dashboard_main._build_logs_overview()

            self.assertEqual(overview["logs_root"], str(logs_root))
            self.assertIn("engine_cycle", overview["latest_snapshots"])
            self.assertTrue((latest_dir / "engine_cycle.json").exists())
            self.assertTrue((latest_dir / "market_context.json").exists())
            self.assertTrue((latest_dir / "control_state.json").exists())
            self.assertTrue((latest_dir / "execution_state.json").exists())
            self.assertTrue((latest_dir / "agents_status.json").exists())
            self.assertTrue((latest_dir / "logs_overview.json").exists())

            agent_status = json.loads((latest_dir / "agents_status.json").read_text())
            self.assertTrue(agent_status["agents"]["watcher"]["service_log"]["exists"])
            self.assertTrue(agent_status["agents"]["newswire"]["latest_output"]["exists"])

            audit_names = [Path(item["path"]).stem for item in overview["sections"]["audit"]]
            service_names = [Path(item["path"]).stem for item in overview["sections"]["service"]]
            self.assertIn("execution", audit_names)
            self.assertIn("watcher", service_names)


if __name__ == "__main__":
    unittest.main()
