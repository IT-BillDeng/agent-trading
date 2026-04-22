from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.watcher_api import AlertLevel, TigerWatcherAPI


class FakeDashboardClient:
    def __init__(self, responses):
        self.responses = responses

    def get(self, endpoint: str, timeout: int = 10):
        return self.responses.get(endpoint, {"error": f"unexpected endpoint: {endpoint}"})


def _engine_payload(*, locked: bool, reason: str = "unknown"):
    return {
        "control_state": {
            "locked": locked,
            "reason": reason,
            "canonical_mode": "paper_trade",
            "trading_mode": "trade",
        },
        "last_cycle": {
            "cycle_id": "cycle-1",
            "strategy": {"signals": []},
            "risk": {"preview_blockers": []},
        },
    }


def _responses(*, locked: bool, reason: str = "unknown"):
    return {
        "/health": {"status": "ok"},
        "/api/engine": _engine_payload(locked=locked, reason=reason),
        "/api/signals": {"signals": []},
        "/api/risk": {"allowed_count": 0, "preview_blockers": []},
        "/api/account": {"net_liquidation": 1000.0},
    }


class WatcherAPILockHandlingTests(unittest.TestCase):
    def _build_watcher(self, *, locked: bool, reason: str) -> TigerWatcherAPI:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        watcher = TigerWatcherAPI(state_file=Path(tmpdir.name) / "watcher_state.json")
        watcher.client = FakeDashboardClient(_responses(locked=locked, reason=reason))
        return watcher

    def test_manual_lock_is_warning_not_error(self):
        watcher = self._build_watcher(locked=True, reason="manual_lock")

        report = watcher.run_all_checks()
        engine_state = next(check for check in report.checks if check.name == "engine_state")

        self.assertEqual(engine_state.status, "warning")
        self.assertEqual(engine_state.details["lock_kind"], "manual")
        self.assertFalse(engine_state.details["fault"])
        self.assertEqual(report.level, AlertLevel.WARNING)
        self.assertEqual(watcher.state["consecutive_errors"], 0)

    def test_manual_lock_does_not_escalate_to_emergency_across_runs(self):
        watcher = self._build_watcher(locked=True, reason="manual_lock")

        reports = [watcher.run_all_checks() for _ in range(6)]

        self.assertTrue(all(report.level != AlertLevel.EMERGENCY for report in reports))
        self.assertEqual(watcher.state["consecutive_errors"], 0)
        self.assertFalse(any(alert.action_taken == "建议自动锁定引擎" for report in reports for alert in report.alerts))

    def test_already_locked_state_does_not_recommend_relocking(self):
        watcher = self._build_watcher(locked=True, reason="daily_loss_limit_exceeded")

        reports = [watcher.run_all_checks() for _ in range(5)]
        emergency_report = reports[-1]
        emergency_alert = next(alert for alert in emergency_report.alerts if alert.level == AlertLevel.EMERGENCY)

        self.assertEqual(emergency_report.level, AlertLevel.EMERGENCY)
        self.assertEqual(emergency_alert.action_taken, "引擎已锁定，无需重复锁定")

    def test_non_manual_lock_remains_strict_error(self):
        watcher = self._build_watcher(locked=True, reason="risk_auto_lock")

        report = watcher.run_all_checks()
        engine_state = next(check for check in report.checks if check.name == "engine_state")

        self.assertEqual(engine_state.status, "error")
        self.assertEqual(engine_state.details["lock_kind"], "abnormal")
        self.assertTrue(engine_state.details["fault"])
        self.assertEqual(report.level, AlertLevel.CRITICAL)
        self.assertEqual(watcher.state["consecutive_errors"], 1)


if __name__ == "__main__":
    unittest.main()
