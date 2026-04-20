import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.control import ControlPlane
from engine.control import canonical_mode_to_legacy_ui_mode, legacy_ui_mode_to_canonical_mode


def _ready_live_readiness():
    return {
        "checklist_id": "live-readiness-v1",
        "status": "ready",
        "confirm_live": True,
        "items": {
            "p0_safety_tests_passed": True,
            "p1_risk_tests_passed": True,
            "paper_shadow_20d_stable": True,
            "fee_model_confidence_ok": True,
            "recent_data_health_ok": True,
            "broker_no_unknown_open_orders": True,
            "execution_state_reconciled": True,
            "operator_confirmed": True,
        },
        "failed_items": [],
        "updated_at": "2026-04-20T00:00:00+00:00",
        "updated_by": "test",
    }


class ControlPlaneSafetyTests(unittest.TestCase):
    def _write_state(self, tmpdir: str, payload: dict) -> ControlPlane:
        state_path = Path(tmpdir) / "control_state.json"
        state_path.write_text(json.dumps(payload, ensure_ascii=False))
        return ControlPlane(tmpdir)

    def test_default_state_allows_trade_when_unlocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = ControlPlane(tmpdir)

            ok, reason = control.can_trade("US", "AAPL")

            self.assertFalse(ok)
            self.assertEqual(reason, "mode:off")

    def test_locked_control_blocks_trade(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = ControlPlane(tmpdir)
            control.lock("manual test lock", updated_by="test")

            ok, reason = control.can_trade("US", "AAPL")

            self.assertFalse(ok)
            self.assertEqual(reason, "manual_lock_active")

    def test_default_state_file_is_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = ControlPlane(tmpdir)

            payload = json.loads(Path(control.path).read_text())

            self.assertIn("global", payload)
            self.assertEqual(payload["global"]["mode"], "off")
            self.assertTrue(payload["global"]["enabled"])
            self.assertIn("risk", payload)
            self.assertEqual(
                payload["risk"],
                {
                    "reduce_only": False,
                    "reduce_only_reason": None,
                    "emergency_flatten": False,
                    "daily_loss_locked": False,
                    "trading_day": None,
                    "day_start_equity_usd": None,
                    "last_equity_usd": None,
                    "daily_loss_pct": 0.0,
                },
            )
            self.assertIn("live_readiness", payload)
            self.assertEqual(payload["live_readiness"]["status"], "missing")
            self.assertIsNone(payload["live_readiness"]["checklist_id"])

    def test_legacy_trading_mode_trade_normalizes_to_paper_trade(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "control_state.json"
            state_path.write_text(
                json.dumps({"locked": False, "trading_mode": "trade"}, ensure_ascii=False)
            )

            control = ControlPlane(tmpdir)
            payload = control.status()

            self.assertEqual(payload["global"]["mode"], "paper_trade")
            self.assertEqual(control.mode(), "paper_trade")
            self.assertTrue(control.paper_execution_enabled())
            self.assertFalse(control.live_execution_enabled())

    def test_legacy_global_trade_mode_paper_live_normalizes_to_paper_trade(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "control_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "locked": False,
                        "global": {"enabled": True, "trade_mode": "paper_live"},
                    },
                    ensure_ascii=False,
                )
            )

            control = ControlPlane(tmpdir)
            payload = control.status()

            self.assertEqual(payload["global"]["mode"], "paper_trade")
            self.assertEqual(control.mode(), "paper_trade")

    def test_symbol_suspended_blocks_trade(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = self._write_state(
                tmpdir,
                {
                    "locked": False,
                    "global": {"enabled": True, "mode": "paper_trade"},
                    "markets": {"US": True},
                    "symbols": {
                        "AAPL": {"enabled": True, "suspended": True},
                    },
                },
            )

            ok, reason = control.can_trade("US", "AAPL")

            self.assertFalse(ok)
            self.assertEqual(reason, "symbol_suspended:AAPL")

    def test_symbol_suspended_blocks_build_order_intents(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = self._write_state(
                tmpdir,
                {
                    "locked": False,
                    "global": {"enabled": True, "mode": "paper_trade"},
                    "markets": {"US": True},
                    "symbols": {
                        "SMCI": {"enabled": True, "suspended": True, "reason": "manual_suspend"},
                    },
                },
            )

            ok, reason = control.can_build_order_intents("US", "SMCI")

            self.assertFalse(ok)
            self.assertEqual(reason, "symbol_suspended:SMCI")

    def test_symbol_suspended_blocks_live_submit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = self._write_state(
                tmpdir,
                {
                    "locked": False,
                    "global": {"enabled": True, "mode": "live_trade"},
                    "markets": {"US": True},
                    "symbols": {
                        "SMCI": {"enabled": True, "suspended": True, "reason": "manual_suspend"},
                    },
                    "live_readiness": _ready_live_readiness(),
                },
            )

            ok, reason = control.can_live_submit("US", "SMCI")

            self.assertFalse(ok)
            self.assertEqual(reason, "symbol_suspended:SMCI")

    def test_symbol_disabled_dict_blocks_with_distinct_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = self._write_state(
                tmpdir,
                {
                    "locked": False,
                    "global": {"enabled": True, "mode": "paper_trade"},
                    "markets": {"US": True},
                    "symbols": {
                        "SMCI": {"enabled": False},
                    },
                },
            )

            ok, reason = control.can_build_order_intents("US", "SMCI")

            self.assertFalse(ok)
            self.assertEqual(reason, "symbol_disabled:SMCI")

    def test_legacy_symbol_false_is_compatible_with_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = self._write_state(
                tmpdir,
                {
                    "locked": False,
                    "global": {"enabled": True, "mode": "paper_trade"},
                    "markets": {"US": True},
                    "symbols": {
                        "SMCI": False,
                    },
                },
            )

            ok, reason = control.can_build_order_intents("US", "SMCI")

            self.assertFalse(ok)
            self.assertEqual(reason, "symbol_disabled:SMCI")

    def test_enabled_symbol_without_suspension_does_not_block_symbol_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paper_control = self._write_state(
                tmpdir,
                {
                    "locked": False,
                    "global": {"enabled": True, "mode": "paper_trade"},
                    "markets": {"US": True},
                    "symbols": {
                        "SMCI": {"enabled": True, "suspended": False},
                    },
                },
            )

            ok, reason = paper_control.can_build_order_intents("US", "SMCI")

            self.assertTrue(ok)
            self.assertIsNone(reason)

        with tempfile.TemporaryDirectory() as tmpdir:
            live_control = self._write_state(
                tmpdir,
                {
                    "locked": False,
                    "global": {"enabled": True, "mode": "live_trade"},
                    "markets": {"US": True},
                    "symbols": {
                        "SMCI": {"enabled": True, "suspended": False},
                    },
                    "live_readiness": _ready_live_readiness(),
                },
            )

            ok, reason = live_control.can_live_submit("US", "SMCI")

            self.assertTrue(ok)
            self.assertIsNone(reason)

    def test_live_submit_requires_readiness_status_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = self._write_state(
                tmpdir,
                {
                    "locked": False,
                    "global": {"enabled": True, "mode": "live_trade"},
                    "markets": {"US": True},
                    "symbols": {"SMCI": {"enabled": True, "suspended": False}},
                    "live_readiness": {
                        "checklist_id": "live-readiness-v1",
                        "status": "blocked",
                        "confirm_live": True,
                        "items": {"operator_confirmed": True},
                        "failed_items": ["paper_shadow_20d_stable"],
                    },
                },
            )

            ok, reason = control.can_live_submit("US", "SMCI")

            self.assertFalse(ok)
            self.assertEqual(reason, "live_readiness:blocked")

    def test_manual_unlock_does_not_clear_daily_loss_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = self._write_state(
                tmpdir,
                {
                    "locked": True,
                    "reason": "daily loss",
                    "global": {"enabled": True, "mode": "paper_trade"},
                    "markets": {"US": True},
                    "symbols": {},
                    "risk": {
                        "reduce_only": True,
                        "reduce_only_reason": "daily_loss_limit_exceeded",
                        "emergency_flatten": False,
                        "daily_loss_locked": True,
                        "trading_day": "2026-04-20",
                        "day_start_equity_usd": 100000.0,
                        "last_equity_usd": 95000.0,
                        "daily_loss_pct": 5.0,
                    },
                },
            )

            state = control.unlock("manual_unlock", updated_by="operator")

            self.assertFalse(state["locked"])
            self.assertTrue(state["risk"]["daily_loss_locked"])
            self.assertTrue(state["risk"]["reduce_only"])

    def test_explicit_daily_loss_override_clears_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = self._write_state(
                tmpdir,
                {
                    "locked": False,
                    "global": {"enabled": True, "mode": "paper_trade"},
                    "markets": {"US": True},
                    "symbols": {},
                    "risk": {
                        "reduce_only": True,
                        "reduce_only_reason": "daily_loss_limit_exceeded",
                        "emergency_flatten": False,
                        "daily_loss_locked": True,
                        "trading_day": "2026-04-20",
                        "day_start_equity_usd": 100000.0,
                        "last_equity_usd": 95000.0,
                        "daily_loss_pct": 5.0,
                    },
                },
            )

            state = control.clear_daily_loss_lock("audited_override", updated_by="operator")

            self.assertFalse(state["risk"]["daily_loss_locked"])
            self.assertFalse(state["risk"]["reduce_only"])
            self.assertIsNone(state["risk"]["reduce_only_reason"])

    def test_legacy_ui_mode_mapping_never_auto_upgrades_to_live_trade(self):
        self.assertEqual(legacy_ui_mode_to_canonical_mode("off"), "off")
        self.assertEqual(legacy_ui_mode_to_canonical_mode("signals"), "signal_only")
        self.assertEqual(legacy_ui_mode_to_canonical_mode("trade"), "paper_trade")

    def test_canonical_mode_maps_back_to_legacy_ui_shape(self):
        self.assertEqual(canonical_mode_to_legacy_ui_mode("off"), "off")
        self.assertEqual(canonical_mode_to_legacy_ui_mode("signal_only"), "signals")
        self.assertEqual(canonical_mode_to_legacy_ui_mode("paper_trade"), "trade")
        self.assertEqual(canonical_mode_to_legacy_ui_mode("live_trade"), "trade")

    def test_live_trade_requires_checklist_id_and_confirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = ControlPlane(tmpdir)

            with self.assertRaisesRegex(ValueError, "readiness_checklist_id is required"):
                control.set_mode("live_trade", updated_by="test", confirm_live=True)

            with self.assertRaisesRegex(ValueError, "confirm_live must be true"):
                control.set_mode(
                    "live_trade",
                    updated_by="test",
                    readiness_checklist_id="live-readiness-v1",
                    checklist={},
                )

    def test_live_trade_requires_all_checklist_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = ControlPlane(tmpdir)

            with self.assertRaisesRegex(ValueError, "live readiness checklist failed"):
                control.set_mode(
                    "live_trade",
                    updated_by="test",
                    confirm_live=True,
                    readiness_checklist_id="live-readiness-v1",
                    checklist={
                        "p0_safety_tests_passed": True,
                        "p1_risk_tests_passed": True,
                    },
                )

            payload = control.status()
            self.assertEqual(payload["live_readiness"]["status"], "blocked")
            self.assertEqual(payload["live_readiness"]["checklist_id"], "live-readiness-v1")
            self.assertIn("paper_shadow_20d_stable", payload["live_readiness"]["failed_items"])

    def test_live_trade_can_be_enabled_when_checklist_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            control = ControlPlane(tmpdir)
            state = control.set_mode(
                "live_trade",
                updated_by="test",
                confirm_live=True,
                readiness_checklist_id="live-readiness-v1",
                checklist={
                    "p0_safety_tests_passed": True,
                    "p1_risk_tests_passed": True,
                    "paper_shadow_20d_stable": True,
                    "fee_model_confidence_ok": True,
                    "recent_data_health_ok": True,
                    "broker_no_unknown_open_orders": True,
                    "execution_state_reconciled": True,
                },
            )

            self.assertEqual(state["global"]["mode"], "live_trade")
            self.assertEqual(state["live_readiness"]["status"], "ready")
            self.assertTrue(state["live_readiness"]["items"]["operator_confirmed"])
            self.assertEqual(state["live_readiness"]["failed_items"], [])


if __name__ == "__main__":
    unittest.main()
