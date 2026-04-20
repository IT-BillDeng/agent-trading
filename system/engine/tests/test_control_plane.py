import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.control import ControlPlane
from engine.control import canonical_mode_to_legacy_ui_mode, legacy_ui_mode_to_canonical_mode


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
                    "emergency_flatten": False,
                    "daily_loss_locked": False,
                },
            )

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
                },
            )

            ok, reason = live_control.can_live_submit("US", "SMCI")

            self.assertTrue(ok)
            self.assertIsNone(reason)

    def test_legacy_ui_mode_mapping_never_auto_upgrades_to_live_trade(self):
        self.assertEqual(legacy_ui_mode_to_canonical_mode("off"), "off")
        self.assertEqual(legacy_ui_mode_to_canonical_mode("signals"), "signal_only")
        self.assertEqual(legacy_ui_mode_to_canonical_mode("trade"), "paper_trade")

    def test_canonical_mode_maps_back_to_legacy_ui_shape(self):
        self.assertEqual(canonical_mode_to_legacy_ui_mode("off"), "off")
        self.assertEqual(canonical_mode_to_legacy_ui_mode("signal_only"), "signals")
        self.assertEqual(canonical_mode_to_legacy_ui_mode("paper_trade"), "trade")
        self.assertEqual(canonical_mode_to_legacy_ui_mode("live_trade"), "trade")


if __name__ == "__main__":
    unittest.main()
