from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.control import ControlPlane
from engine.risk import RiskManager


def _market_state_open():
    return {"US": [{"status": "TRADING", "marketStatus": "open"}]}


def _contracts():
    return {"US": {"AAPL": {"currency": "USD"}}}


def _buy_signal():
    return {
        "symbol": "AAPL",
        "market": "US",
        "action": "BUY",
        "last_close": 100.0,
    }


def _exit_signal():
    return {
        "symbol": "AAPL",
        "market": "US",
        "action": "EXIT",
        "last_close": 100.0,
    }


class ReduceOnlyAndEmergencyFlattenTests(unittest.TestCase):
    def _manager(self, state_dir: str) -> RiskManager:
        return RiskManager(
            {
                "risk": {
                    "daily_loss_limit_pct": 5,
                    "max_order_notional_usd": 10000,
                    "max_total_exposure_usd": 1000000,
                    "fx_rates_to_usd": {"USD": 1.0},
                    "disable_leverage": False,
                },
                "system": {"state_dir": state_dir},
            }
        )

    def _control(self, state_dir: str) -> ControlPlane:
        return ControlPlane(state_dir)

    def _evaluate(
        self,
        manager: RiskManager,
        *,
        signals: list[dict],
        positions_map: dict | None = None,
    ):
        return manager.evaluate(
            signals=signals,
            asset_snapshot={
                "netLiquidation": 100000.0,
                "trading_day": "2026-04-20",
                "timestamp": "2026-04-20T14:30:00+00:00",
            },
            market_state=_market_state_open(),
            contracts=_contracts(),
            positions_map=positions_map or {},
            active_orders_map={},
        )

    def test_reduce_only_blocks_buy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._control(tmpdir).update_risk(
                {"reduce_only": True, "reduce_only_reason": "manual_reduce_only"},
                updated_by="test",
                action="set_reduce_only",
            )
            decisions = self._evaluate(self._manager(tmpdir), signals=[_buy_signal()])

            self.assertFalse(decisions[0].allowed)
            self.assertIn("reduce_only_active", decisions[0].reasons)

    def test_reduce_only_does_not_block_exit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._control(tmpdir).update_risk(
                {"reduce_only": True, "reduce_only_reason": "manual_reduce_only"},
                updated_by="test",
                action="set_reduce_only",
            )
            decisions = self._evaluate(
                self._manager(tmpdir),
                signals=[_exit_signal()],
                positions_map={"AAPL": {"position": 5, "latestPrice": 100.0, "market": "US"}},
            )

            self.assertTrue(decisions[0].allowed)
            self.assertNotIn("reduce_only_active", decisions[0].reasons)

    def test_emergency_flatten_blocks_buy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._control(tmpdir).update_risk(
                {"emergency_flatten": True},
                updated_by="test",
                action="set_emergency_flatten",
            )
            decisions = self._evaluate(self._manager(tmpdir), signals=[_buy_signal()])

            self.assertFalse(decisions[0].allowed)
            self.assertIn("emergency_flatten_active", decisions[0].reasons)

    def test_emergency_flatten_does_not_block_exit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self._control(tmpdir).update_risk(
                {"emergency_flatten": True},
                updated_by="test",
                action="set_emergency_flatten",
            )
            decisions = self._evaluate(
                self._manager(tmpdir),
                signals=[_exit_signal()],
                positions_map={"AAPL": {"position": 5, "latestPrice": 100.0, "market": "US"}},
            )

            self.assertTrue(decisions[0].allowed)
            self.assertNotIn("emergency_flatten_active", decisions[0].reasons)


if __name__ == "__main__":
    unittest.main()
