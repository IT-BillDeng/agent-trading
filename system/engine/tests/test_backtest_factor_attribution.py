from __future__ import annotations

import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

sys.modules.setdefault("yfinance", types.SimpleNamespace(Ticker=None, download=None))

from engine.backtest import BacktestConfig, BacktestEngine, Bar


def _rules_file() -> Path:
    payload = {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "test_rule",
                "enabled": True,
                "priority": 1,
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "action": "BUY",
                    "conditions": {"type": "price", "field": "close", "operator": "above", "value": 999999},
                },
                "exit": {
                    "action": "EXIT",
                    "conditions": {"type": "price", "field": "close", "operator": "below", "value": -1},
                },
            }
        ],
    }
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    with handle:
        json.dump(payload, handle)
    return Path(handle.name)


def _bars(start: datetime, prices: list[float]) -> list[Bar]:
    return [
        Bar(
            timestamp=start + timedelta(minutes=30 * idx),
            open=price - 0.3,
            high=price + 0.5,
            low=price - 0.5,
            close=price,
            volume=1000 + idx * 10,
        )
        for idx, price in enumerate(prices)
    ]


class BacktestFactorAttributionTests(unittest.TestCase):
    def setUp(self):
        self.rules_path = _rules_file()
        self.addCleanup(lambda: self.rules_path.unlink(missing_ok=True))
        self.config = BacktestConfig(
            symbols=["AAPL"],
            start_date="2026-01-05",
            end_date="2026-01-06",
            timeframe="30min",
            initial_capital=100000.0,
        )

    def test_backtest_result_includes_factor_attribution_and_preserves_existing_metrics(self):
        engine = BacktestEngine(self.config, self.rules_path)
        start = datetime(2026, 1, 5, 9, 30)
        bars = _bars(start, [100.0, 101.5, 102.0, 101.0, 103.0, 104.0])

        def fake_load_data():
            engine.bars_by_symbol = {"AAPL": bars}
            engine.current_index = {"AAPL": -1}
            engine.data_coverage = {"AAPL": {"bars_count": len(bars), "has_sufficient_bars": True}}
            engine.data_warnings = []

        engine.load_data = fake_load_data
        engine.rule_engine.evaluate_symbol = lambda symbol, market, bars_history, position_dict: []

        factor_payload = {
            "enabled": True,
            "mode": "shadow",
            "registry_hash": "registry-hash-1",
            "horizons": [1, 2],
            "min_ic_samples": 3,
            "factors": {
                "rsi_14_30m": {
                    "coverage": 1.0,
                    "missing_rate": 0.0,
                    "ic_1bar": 0.25,
                    "ic_1bar_reason": None,
                }
            },
        }

        with patch("engine.backtest.build_factor_attribution", return_value=factor_payload) as mocked_builder:
            result = engine.run()

        mocked_builder.assert_called_once()
        self.assertEqual(result.factor_attribution, factor_payload)
        payload = result.to_dict()
        self.assertIn("factor_attribution", payload)
        self.assertIn("total_return_pct", payload)
        self.assertIn("sharpe_ratio", payload)
        self.assertIn("max_drawdown_pct", payload)
        self.assertIn("win_rate", payload)
        self.assertIn("fee_drag_pct", payload)


if __name__ == "__main__":
    unittest.main()
