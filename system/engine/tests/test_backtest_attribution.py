from __future__ import annotations

import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

sys.modules.setdefault("yfinance", types.SimpleNamespace(Ticker=None, download=None))

from engine.backtest import BacktestConfig, BacktestEngine, Bar
from engine.rule_engine import RuleSignal


def _rules_file() -> Path:
    payload = {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "rsi_reversal",
                "enabled": True,
                "priority": 1,
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "action": "BUY",
                    "conditions": {"type": "price", "field": "close", "operator": "above", "value": 1},
                },
                "exit": {
                    "action": "EXIT",
                    "conditions": {"type": "price", "field": "close", "operator": "below", "value": 1},
                },
            },
            {
                "rule_id": "bollinger_breakout",
                "enabled": True,
                "priority": 2,
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "action": "BUY",
                    "conditions": {"type": "price", "field": "close", "operator": "above", "value": 1},
                },
                "exit": {
                    "action": "EXIT",
                    "conditions": {"type": "price", "field": "close", "operator": "below", "value": 1},
                },
            },
        ],
        "symbol_profile_templates": {
            "default_shared_30m": {
                "description": "default",
                "enabled_rules": {},
                "rule_overrides": {},
            }
        },
        "symbol_profiles": {
            "AAPL": {"profile": "default_shared_30m", "enabled_rules": {}, "rule_overrides": {}},
            "MSFT": {"profile": "default_shared_30m", "enabled_rules": {}, "rule_overrides": {}},
        },
    }
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    with handle:
        json.dump(payload, handle)
    return Path(handle.name)


def _bars(start: datetime, prices: list[float]) -> list[Bar]:
    return [
        Bar(
            timestamp=start + timedelta(minutes=30 * idx),
            open=price - 0.2,
            high=price + 0.5,
            low=price - 0.5,
            close=price,
            volume=1000 + idx,
        )
        for idx, price in enumerate(prices)
    ]


class BacktestAttributionTests(unittest.TestCase):
    def setUp(self):
        self.rules_path = _rules_file()
        self.addCleanup(lambda: self.rules_path.unlink(missing_ok=True))
        self.config = BacktestConfig(
            symbols=["AAPL", "MSFT"],
            start_date="2026-01-01",
            end_date="2026-01-02",
            timeframe="30min",
            initial_capital=100000.0,
        )

    def test_backtest_outputs_symbol_rule_attribution_and_preserves_metrics(self):
        engine = BacktestEngine(self.config, self.rules_path)
        start = datetime(2026, 1, 1, 9, 30)
        aapl_bars = _bars(start, [100.0, 103.0, 105.0])
        msft_bars = _bars(start, [200.0, 201.0, 202.0])

        def fake_load_data():
            engine.bars_by_symbol = {"AAPL": aapl_bars, "MSFT": msft_bars}
            engine.current_index = {symbol: -1 for symbol in engine.config.symbols}

        def fake_evaluate(symbol, market, bars_history, position_dict):
            idx = engine.current_index[symbol]
            if symbol == "AAPL" and idx == 0:
                return [
                    RuleSignal(
                        rule_id="rsi_reversal",
                        symbol=symbol,
                        market=market,
                        action="BUY",
                        order_type="LMT",
                        score=1,
                        reason="entry",
                        priority=1,
                        stop_loss=98.0,
                        take_profit=104.0,
                        last_close=bars_history[-1]["close"],
                        base_rule_id="rsi_reversal",
                        primary_rule_id="rsi_reversal",
                        source_rule_ids=["rsi_reversal"],
                        symbol_profile="default_shared_30m",
                        effective_config_hash="hash-rsi-aapl",
                        effective_config_hashes=["hash-rsi-aapl"],
                        overrides_applied={},
                    )
                ]
            if symbol == "AAPL" and idx == 2 and position_dict:
                return [
                    RuleSignal(
                        rule_id="bollinger_breakout",
                        symbol=symbol,
                        market=market,
                        action="EXIT",
                        order_type="MKT",
                        score=1,
                        reason="exit",
                        priority=2,
                        stop_loss=None,
                        take_profit=None,
                        last_close=bars_history[-1]["close"],
                        base_rule_id="bollinger_breakout",
                        primary_rule_id="bollinger_breakout",
                        source_rule_ids=["bollinger_breakout"],
                        symbol_profile="default_shared_30m",
                        effective_config_hash="hash-bb-aapl",
                        effective_config_hashes=["hash-bb-aapl"],
                        overrides_applied={},
                    )
                ]
            return []

        engine.load_data = fake_load_data
        engine.rule_engine.evaluate_symbol = fake_evaluate

        result = engine.run()

        self.assertEqual(result.winning_trades, 1)
        self.assertEqual(result.losing_trades, 0)
        self.assertEqual(result.win_rate, 1.0)

        attribution = result.attribution
        self.assertIn("symbols", attribution)
        self.assertIn("rules", attribution)

        aapl_rsi = attribution["symbols"]["AAPL"]["rules"]["rsi_reversal"]
        aapl_bollinger = attribution["symbols"]["AAPL"]["rules"]["bollinger_breakout"]
        msft_rsi = attribution["symbols"]["MSFT"]["rules"]["rsi_reversal"]

        self.assertEqual(aapl_rsi["signals"], 1)
        self.assertEqual(aapl_rsi["entries"], 1)
        self.assertEqual(aapl_rsi["closed_trades"], 1)
        self.assertEqual(aapl_rsi["winning_closed_trades"], 1)
        self.assertGreater(aapl_rsi["net_return_pct"], 0.0)

        self.assertEqual(aapl_bollinger["signals"], 1)
        self.assertEqual(aapl_bollinger["entries"], 0)
        self.assertEqual(aapl_bollinger["exits"], 1)
        self.assertEqual(aapl_bollinger["closed_trades"], 0)

        self.assertEqual(msft_rsi["signals"], 0)
        self.assertEqual(msft_rsi["closed_trades"], 0)
        self.assertIsNone(msft_rsi["win_rate"])

        self.assertEqual(attribution["rules"]["rsi_reversal"]["closed_trades"], 1)
        self.assertIn("AAPL", attribution["rules"]["rsi_reversal"]["symbols"])
        self.assertIn("MSFT", attribution["rules"]["rsi_reversal"]["symbols"])
        self.assertEqual(attribution["rules"]["bollinger_breakout"]["closed_trades"], 0)


if __name__ == "__main__":
    unittest.main()
