import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ENGINE_SRC = Path(__file__).resolve().parents[1] / "system" / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from engine.closer import CloserSummary, TigerCloser, run_closer
from engine.watcher import AlertLevel, HealthCheck, WatcherReport, TigerWatcher, run_watcher_check
from engine.watcher_api import TigerWatcherAPI, run_watcher_check as run_watcher_api_check


class AgentArtifactWriteTests(unittest.TestCase):
    def test_watcher_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime_dir = root / "runtime"
            config_dir = root / "config"
            artifacts_dir = root / "artifacts"
            runtime_dir.mkdir(parents=True)
            config_dir.mkdir(parents=True)

            report = WatcherReport(
                timestamp="2026-04-17T09:00:00",
                level=AlertLevel.INFO,
                checks=[HealthCheck(name="health", status="ok", message="ok")],
                alerts=[],
                summary="ok",
            )

            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                with mock.patch.object(TigerWatcher, "run_all_checks", return_value=report):
                    result = run_watcher_check(runtime_dir, config_dir)
                with mock.patch.object(TigerWatcherAPI, "run_all_checks", return_value=report):
                    api_result = run_watcher_api_check()
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertEqual(result["summary"], "ok")
            self.assertEqual(api_result["summary"], "ok")
            latest = artifacts_dir / "watcher" / "latest.json"
            history = artifacts_dir / "watcher" / "history.jsonl"
            self.assertTrue(latest.exists())
            self.assertTrue(history.exists())
            self.assertEqual(json.loads(latest.read_text())["summary"], "ok")
            self.assertGreaterEqual(len(history.read_text().splitlines()), 1)

    def test_closer_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifacts_dir = root / "artifacts"
            artifacts_dir.mkdir(parents=True)

            summary = CloserSummary(
                market="US",
                date="2026-04-17",
                cycle_count=1,
                signals={"buy": 1, "exit": 0, "hold": 3},
                orders={"filled": 1, "pending": 0},
                account={"net_liquidation": 1000, "unrealized_pnl": 10, "cash": 990},
                positions=[],
                risk_blockers=[],
                focus_symbols=["AAPL"],
            )

            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                with mock.patch.object(TigerCloser, "generate_summary", return_value=summary), \
                    mock.patch.object(TigerCloser, "format_report", return_value="report"), \
                    mock.patch("engine.closer.check_has_trading_data", return_value=True):
                    result = run_closer("US")
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertEqual(result["status"], "ok")
            latest = artifacts_dir / "closer" / "summary_latest.json"
            history = artifacts_dir / "closer" / "summary_history.jsonl"
            self.assertTrue(latest.exists())
            self.assertTrue(history.exists())
            self.assertEqual(json.loads(latest.read_text())["status"], "ok")
            self.assertGreaterEqual(len(history.read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
