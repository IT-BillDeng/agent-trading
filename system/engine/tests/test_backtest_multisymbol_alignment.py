import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

sys.modules.setdefault("yfinance", types.SimpleNamespace(Ticker=None, download=None))

from engine.backtest import BacktestConfig, BacktestEngine, Bar, Position


def _make_rules_file() -> Path:
    payload = {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "noop_rule",
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


def _make_bars(symbol: str, count: int, *, start: datetime, base_price: float) -> list[Bar]:
    bars: list[Bar] = []
    for i in range(count):
        close = base_price + i
        bars.append(
            Bar(
                timestamp=start + timedelta(minutes=30 * i),
                open=close - 0.2,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume=1000 + i,
            )
        )
    return bars


class BacktestMultiSymbolAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.rules_path = _make_rules_file()
        self.config = BacktestConfig(
            symbols=["AAPL", "MSFT"],
            start_date="2026-01-01",
            end_date="2026-01-03",
            timeframe="30min",
            initial_capital=100000.0,
        )

    def tearDown(self):
        if self.rules_path.exists():
            self.rules_path.unlink()

    def test_multisymbol_backtest_aligns_on_timestamp_without_index_errors(self):
        engine = BacktestEngine(self.config, self.rules_path)
        start = datetime(2026, 1, 1, 9, 30)
        aapl_bars = _make_bars("AAPL", 100, start=start, base_price=100.0)
        msft_bars = _make_bars("MSFT", 60, start=start, base_price=200.0)

        def fake_load_data():
            engine.bars_by_symbol = {"AAPL": aapl_bars, "MSFT": msft_bars}
            engine.current_index = {symbol: -1 for symbol in engine.config.symbols}

        engine.load_data = fake_load_data
        engine.rule_engine.evaluate_symbol = lambda symbol, market, bars_history, position_dict: []
        engine.positions = {
            "AAPL": Position("AAPL", 1, 100.0, aapl_bars[0].timestamp, current_price=100.0),
            "MSFT": Position("MSFT", 1, 200.0, msft_bars[0].timestamp, current_price=200.0),
        }

        result = engine.run()

        self.assertGreater(len(result.equity_curve), 0)
        timestamps = [point["timestamp"] for point in result.equity_curve]
        self.assertEqual(timestamps, sorted(timestamps))
        self.assertEqual(engine.positions["AAPL"].current_price, aapl_bars[-1].close)
        self.assertEqual(engine.positions["MSFT"].current_price, msft_bars[-1].close)
        self.assertEqual(timestamps[-1], aapl_bars[-1].timestamp.isoformat())


if __name__ == "__main__":
    unittest.main()
