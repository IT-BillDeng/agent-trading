from __future__ import annotations

import json
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


class RiskDailyLossTests(unittest.TestCase):
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
                "system": {
                    "state_dir": state_dir,
                },
            }
        )

    def _control(self, state_dir: str) -> ControlPlane:
        return ControlPlane(state_dir)

    def _evaluate(
        self,
        manager: RiskManager,
        *,
        signals: list[dict],
        net_liq: float,
        trading_day: str,
        positions_map: dict | None = None,
    ):
        return manager.evaluate(
            signals=signals,
            asset_snapshot={
                "netLiquidation": net_liq,
                "trading_day": trading_day,
            },
            market_state=_market_state_open(),
            contracts=_contracts(),
            positions_map=positions_map or {},
            active_orders_map={},
        )

    def test_daily_loss_below_threshold_does_not_block_buy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._manager(tmpdir)

            self._evaluate(manager, signals=[], net_liq=100000.0, trading_day="2026-04-20")
            decisions = self._evaluate(
                manager,
                signals=[_buy_signal()],
                net_liq=96000.0,
                trading_day="2026-04-20",
            )

            self.assertTrue(decisions[0].allowed)
            self.assertNotIn("daily_loss_limit_exceeded", decisions[0].reasons)

            risk_state = self._control(tmpdir).status()["risk"]
            self.assertEqual(risk_state["trading_day"], "2026-04-20")
            self.assertAlmostEqual(risk_state["day_start_equity_usd"], 100000.0, places=6)
            self.assertAlmostEqual(risk_state["last_equity_usd"], 96000.0, places=6)
            self.assertAlmostEqual(risk_state["daily_loss_pct"], 4.0, places=6)
            self.assertFalse(risk_state["daily_loss_locked"])
            self.assertFalse(risk_state["reduce_only"])

    def test_daily_loss_at_threshold_blocks_buy_and_sets_reduce_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._manager(tmpdir)

            self._evaluate(manager, signals=[], net_liq=100000.0, trading_day="2026-04-20")
            decisions = self._evaluate(
                manager,
                signals=[_buy_signal()],
                net_liq=95000.0,
                trading_day="2026-04-20",
            )

            self.assertFalse(decisions[0].allowed)
            self.assertIn("daily_loss_limit_exceeded", decisions[0].reasons)

            risk_state = self._control(tmpdir).status()["risk"]
            self.assertEqual(risk_state["trading_day"], "2026-04-20")
            self.assertAlmostEqual(risk_state["day_start_equity_usd"], 100000.0, places=6)
            self.assertAlmostEqual(risk_state["last_equity_usd"], 95000.0, places=6)
            self.assertAlmostEqual(risk_state["daily_loss_pct"], 5.0, places=6)
            self.assertTrue(risk_state["daily_loss_locked"])
            self.assertTrue(risk_state["reduce_only"])

    def test_daily_loss_lock_does_not_auto_release_on_same_day_recovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._manager(tmpdir)

            self._evaluate(manager, signals=[], net_liq=100000.0, trading_day="2026-04-20")
            self._evaluate(manager, signals=[_buy_signal()], net_liq=95000.0, trading_day="2026-04-20")
            decisions = self._evaluate(
                manager,
                signals=[_buy_signal()],
                net_liq=99000.0,
                trading_day="2026-04-20",
            )

            self.assertFalse(decisions[0].allowed)
            self.assertIn("daily_loss_limit_exceeded", decisions[0].reasons)
            risk_state = self._control(tmpdir).status()["risk"]
            self.assertTrue(risk_state["daily_loss_locked"])
            self.assertTrue(risk_state["reduce_only"])

    def test_exit_remains_allowed_after_daily_loss_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._manager(tmpdir)

            self._evaluate(manager, signals=[], net_liq=100000.0, trading_day="2026-04-20")
            self._evaluate(manager, signals=[_buy_signal()], net_liq=95000.0, trading_day="2026-04-20")
            decisions = self._evaluate(
                manager,
                signals=[_exit_signal()],
                net_liq=94000.0,
                trading_day="2026-04-20",
                positions_map={"AAPL": {"position": 10, "latestPrice": 100.0, "market": "US"}},
            )

            self.assertTrue(decisions[0].allowed)
            self.assertNotIn("daily_loss_limit_exceeded", decisions[0].reasons)

    def test_new_trading_day_resets_daily_loss_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._manager(tmpdir)

            self._evaluate(manager, signals=[], net_liq=100000.0, trading_day="2026-04-20")
            self._evaluate(manager, signals=[_buy_signal()], net_liq=95000.0, trading_day="2026-04-20")
            decisions = self._evaluate(
                manager,
                signals=[_buy_signal()],
                net_liq=97000.0,
                trading_day="2026-04-21",
            )

            self.assertTrue(decisions[0].allowed)

            risk_state = self._control(tmpdir).status()["risk"]
            self.assertEqual(risk_state["trading_day"], "2026-04-21")
            self.assertAlmostEqual(risk_state["day_start_equity_usd"], 97000.0, places=6)
            self.assertAlmostEqual(risk_state["last_equity_usd"], 97000.0, places=6)
            self.assertAlmostEqual(risk_state["daily_loss_pct"], 0.0, places=6)
            self.assertFalse(risk_state["daily_loss_locked"])
            self.assertFalse(risk_state["reduce_only"])

    def test_manual_unlock_clears_daily_loss_lock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = self._manager(tmpdir)
            control = self._control(tmpdir)

            self._evaluate(manager, signals=[], net_liq=100000.0, trading_day="2026-04-20")
            self._evaluate(manager, signals=[_buy_signal()], net_liq=95000.0, trading_day="2026-04-20")
            control.unlock("manual_unlock", updated_by="operator")
            decisions = self._evaluate(
                manager,
                signals=[_buy_signal()],
                net_liq=99000.0,
                trading_day="2026-04-20",
            )

            self.assertTrue(decisions[0].allowed)
            risk_state = control.status()["risk"]
            self.assertFalse(risk_state["daily_loss_locked"])
            self.assertFalse(risk_state["reduce_only"])


if __name__ == "__main__":
    unittest.main()
