import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import types

sys.modules.setdefault("yfinance", types.SimpleNamespace(Ticker=None, download=None))

from engine.backtest import BacktestConfig, BacktestEngine, Trade


def _make_rules_file() -> Path:
    payload = {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "test_rule",
                "enabled": True,
                "priority": 1,
                "timeframe": "30min",
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "action": "BUY",
                    "conditions": {
                        "type": "indicator",
                        "indicator": "sma",
                        "params": {"period": 5},
                        "compare": {"field": "close", "operator": "above"},
                    },
                },
                "exit": {
                    "action": "EXIT",
                    "conditions": {
                        "type": "indicator",
                        "indicator": "sma",
                        "params": {"period": 5},
                        "compare": {"field": "close", "operator": "below"},
                    },
                },
            }
        ],
    }
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    with handle:
        json.dump(payload, handle)
    return Path(handle.name)


class BacktestMetricsTests(unittest.TestCase):
    def setUp(self):
        self.rules_path = _make_rules_file()
        self.config = BacktestConfig(
            symbols=["AAPL"],
            start_date="2026-01-01",
            end_date="2026-01-02",
            timeframe="30min",
            initial_capital=100000.0,
        )

    def tearDown(self):
        if self.rules_path.exists():
            self.rules_path.unlink()

    def _engine(self) -> BacktestEngine:
        engine = BacktestEngine(self.config, self.rules_path)
        engine.equity_curve = [
            {"timestamp": "2026-01-01T09:30:00", "cash": 100000.0, "positions_value": 0.0, "total_value": 100000.0},
            {"timestamp": "2026-01-01T10:00:00", "cash": 100010.0, "positions_value": 0.0, "total_value": 100010.0},
        ]
        return engine

    def test_win_rate_uses_closed_trades_for_profitable_round_trip(self):
        engine = self._engine()
        start = datetime(2026, 1, 1, 9, 30)
        engine.trades = [
            Trade("AAPL", "BUY", 10, 100.0, start, commission=0.0, slippage=0.0),
            Trade("AAPL", "SELL", 10, 101.0, start + timedelta(minutes=30), commission=0.0, slippage=0.0),
        ]

        result = engine.calculate_performance(start, start + timedelta(hours=1), 100010.0)

        self.assertEqual(result.total_trades, 2)
        self.assertEqual(result.winning_trades, 1)
        self.assertEqual(result.losing_trades, 0)
        self.assertEqual(result.win_rate, 1.0)

    def test_win_rate_is_zero_for_losing_round_trip(self):
        engine = self._engine()
        start = datetime(2026, 1, 1, 9, 30)
        engine.trades = [
            Trade("AAPL", "BUY", 10, 100.0, start, commission=0.0, slippage=0.0),
            Trade("AAPL", "SELL", 10, 99.0, start + timedelta(minutes=30), commission=0.0, slippage=0.0),
        ]

        result = engine.calculate_performance(start, start + timedelta(hours=1), 99990.0)

        self.assertEqual(result.winning_trades, 0)
        self.assertEqual(result.losing_trades, 1)
        self.assertEqual(result.win_rate, 0.0)

    def test_open_buy_without_close_keeps_win_rate_zero(self):
        engine = self._engine()
        start = datetime(2026, 1, 1, 9, 30)
        engine.trades = [
            Trade("AAPL", "BUY", 10, 100.0, start, commission=0.0, slippage=0.0),
        ]

        result = engine.calculate_performance(start, start + timedelta(hours=1), 100000.0)

        self.assertEqual(result.total_trades, 1)
        self.assertEqual(result.winning_trades, 0)
        self.assertEqual(result.losing_trades, 0)
        self.assertEqual(result.win_rate, 0.0)


if __name__ == "__main__":
    unittest.main()
