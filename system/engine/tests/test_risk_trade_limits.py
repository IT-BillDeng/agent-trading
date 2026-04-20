from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.risk import RiskManager
from engine.state import TradeLimitStore


def _market_state_open():
    return {"US": [{"status": "TRADING", "marketStatus": "open"}]}


def _contracts():
    return {
        "US": {
            "AAPL": {"currency": "USD"},
            "MSFT": {"currency": "USD"},
        }
    }


def _buy_signal(symbol: str = "AAPL"):
    return {
        "symbol": symbol,
        "market": "US",
        "action": "BUY",
        "last_close": 100.0,
    }


def _exit_signal(symbol: str = "AAPL"):
    return {
        "symbol": symbol,
        "market": "US",
        "action": "EXIT",
        "last_close": 100.0,
    }


class RiskTradeLimitTests(unittest.TestCase):
    def _manager(self, state_dir: str) -> RiskManager:
        return RiskManager(
            {
                "risk": {
                    "daily_loss_limit_pct": 5,
                    "max_order_notional_usd": 10000,
                    "max_total_exposure_usd": 1000000,
                    "max_trades_per_day": 3,
                    "max_trades_per_symbol_per_day": 2,
                    "symbol_cooldown_minutes_after_order": 30,
                    "symbol_cooldown_minutes_after_loss": 120,
                    "fx_rates_to_usd": {"USD": 1.0},
                    "disable_leverage": False,
                },
                "system": {"state_dir": state_dir},
            }
        )

    def _evaluate(
        self,
        manager: RiskManager,
        *,
        signals: list[dict],
        timestamp: str,
        positions_map: dict | None = None,
    ):
        return manager.evaluate(
            signals=signals,
            asset_snapshot={
                "netLiquidation": 100000.0,
                "trading_day": "2026-04-20",
                "timestamp": timestamp,
            },
            market_state=_market_state_open(),
            contracts=_contracts(),
            positions_map=positions_map or {},
            active_orders_map={},
        )

    def test_global_trade_limit_blocks_new_buy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TradeLimitStore(tmpdir)
            store.record_trade("2026-04-20", symbol="AAPL", side="BUY", ts="2026-04-20T09:30:00+00:00")
            store.record_trade("2026-04-20", symbol="MSFT", side="BUY", ts="2026-04-20T10:00:00+00:00")
            store.record_trade("2026-04-20", symbol="AAPL", side="SELL", ts="2026-04-20T10:30:00+00:00")

            manager = self._manager(tmpdir)
            decisions = self._evaluate(manager, signals=[_buy_signal("AAPL")], timestamp="2026-04-20T11:00:00+00:00")

            self.assertFalse(decisions[0].allowed)
            self.assertIn("max_trades_per_day_exceeded", decisions[0].reasons)

    def test_symbol_trade_limit_blocks_only_that_symbol(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TradeLimitStore(tmpdir)
            store.record_trade("2026-04-20", symbol="AAPL", side="BUY", ts="2026-04-20T09:30:00+00:00")
            store.record_trade("2026-04-20", symbol="AAPL", side="SELL", ts="2026-04-20T10:30:00+00:00")

            manager = self._manager(tmpdir)
            blocked = self._evaluate(manager, signals=[_buy_signal("AAPL")], timestamp="2026-04-20T12:00:00+00:00")
            allowed = self._evaluate(manager, signals=[_buy_signal("MSFT")], timestamp="2026-04-20T12:00:00+00:00")

            self.assertFalse(blocked[0].allowed)
            self.assertIn("max_trades_per_symbol_exceeded:AAPL", blocked[0].reasons)
            self.assertTrue(allowed[0].allowed)

    def test_symbol_cooldown_blocks_buy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TradeLimitStore(tmpdir)
            store.record_trade("2026-04-20", symbol="AAPL", side="BUY", ts="2026-04-20T10:00:00+00:00")

            manager = self._manager(tmpdir)
            decisions = self._evaluate(manager, signals=[_buy_signal("AAPL")], timestamp="2026-04-20T10:10:00+00:00")

            self.assertFalse(decisions[0].allowed)
            self.assertIn("symbol_cooldown_active:AAPL", decisions[0].reasons)

    def test_exit_not_blocked_by_cooldown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TradeLimitStore(tmpdir)
            store.record_trade("2026-04-20", symbol="AAPL", side="BUY", ts="2026-04-20T10:00:00+00:00")

            manager = self._manager(tmpdir)
            decisions = self._evaluate(
                manager,
                signals=[_exit_signal("AAPL")],
                timestamp="2026-04-20T10:10:00+00:00",
                positions_map={"AAPL": {"position": 10, "latestPrice": 100.0, "market": "US"}},
            )

            self.assertTrue(decisions[0].allowed)
            self.assertNotIn("symbol_cooldown_active:AAPL", decisions[0].reasons)

    def test_new_day_resets_trade_limit_counters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = TradeLimitStore(tmpdir)
            store.record_trade("2026-04-20", symbol="AAPL", side="BUY", ts="2026-04-20T10:00:00+00:00")
            store.record_trade("2026-04-20", symbol="AAPL", side="SELL", ts="2026-04-20T11:00:00+00:00")

            manager = self._manager(tmpdir)
            decisions = manager.evaluate(
                signals=[_buy_signal("AAPL")],
                asset_snapshot={
                    "netLiquidation": 100000.0,
                    "trading_day": "2026-04-21",
                    "timestamp": "2026-04-21T10:00:00+00:00",
                },
                market_state=_market_state_open(),
                contracts=_contracts(),
                positions_map={},
                active_orders_map={},
            )

            self.assertTrue(decisions[0].allowed)
            self.assertEqual(store.snapshot("2026-04-21")["total_trades"], 0)


if __name__ == "__main__":
    unittest.main()
