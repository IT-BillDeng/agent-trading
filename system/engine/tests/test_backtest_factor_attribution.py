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
        engine.rule_engine.evaluate_symbol = (
            lambda symbol, market, bars_history, position_dict, **kwargs: []
        )

        factor_payload = {
            "enabled": True,
            "mode": "shadow",
            "registry_hash": "registry-hash-1",
            "horizons": [1, 2],
            "min_ic_samples": 3,
            "symbol_coverage": {"AAPL": {"coverage": 1.0, "missing_rate": 0.0}},
            "factor_correlation": {
                "status": "placeholder",
                "matrix": None,
                "reason": "factor_correlation_not_computed_in_v1",
            },
            "factors": {
                "rsi_14_30m": {
                    "coverage": 1.0,
                    "missing_rate": 0.0,
                    "ic_1bar": 0.25,
                    "ic_1bar_reason": None,
                    "rank_ic_1bar": 0.25,
                    "rank_ic_1bar_reason": None,
                    "decay_basis": {
                        "status": "ok",
                        "base_horizon": 1,
                        "by_horizon": {
                            "1bar": {"ic": 0.25, "rank_ic": 0.25},
                            "2bar": {"ic": 0.1, "rank_ic": 0.1},
                        },
                    },
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

    def test_backtest_uses_factor_snapshots_by_default_and_keeps_fail_open(self):
        start = datetime(2026, 1, 5, 9, 30)
        bars = _bars(start, [100.0, 100.8, 101.6, 102.4, 103.2, 104.0])

        def make_load_data(target_engine):
            def fake_load_data():
                target_engine.bars_by_symbol = {"AAPL": bars}
                target_engine.current_index = {"AAPL": -1}
                target_engine.data_coverage = {"AAPL": {"bars_count": len(bars), "has_sufficient_bars": True}}
                target_engine.data_warnings = []

            return fake_load_data

        engine = BacktestEngine(self.config, self.rules_path)
        class StubFactorEngine:
            def __init__(self):
                self.calls = []

            def evaluate_symbol(self, symbol, bars_history, **kwargs):
                self.calls.append(len(bars_history))
                return {
                    "symbol": symbol,
                    "mode": "shadow",
                    "registry_hash": "registry-hash-1",
                    "factors": {
                        "return_5_30m": {
                            "value": 0.05,
                            "ready": True,
                            "reason": "ok",
                            "source": "stub",
                            "config_hash": "factor-hash-1",
                        }
                    },
                }

        engine.load_data = make_load_data(engine)
        engine.factor_engine = StubFactorEngine()
        captured = []

        def fake_evaluate(symbol, market, bars_history, position_dict, **kwargs):
            captured.append(kwargs)
            return []

        engine.rule_engine.evaluate_symbol = fake_evaluate

        with patch("engine.backtest.build_factor_attribution", return_value={"enabled": False, "factors": {}, "reason": "stubbed"}):
            result = engine.run()

        self.assertEqual(result.total_trades, 0)
        self.assertEqual(len(captured), len(bars))
        self.assertTrue(all(item.get("factor_snapshot") is not None for item in captured))
        self.assertTrue(any(item.get("previous_factor_snapshot") is not None for item in captured[1:]))
        self.assertEqual(engine.factor_runtime_diagnostics["symbols"]["AAPL"]["status"], "ok")

        failing_engine = BacktestEngine(self.config, self.rules_path)
        failing_engine.load_data = make_load_data(failing_engine)

        class RaisingFactorEngine:
            def evaluate_symbol(self, symbol, bars_history, **kwargs):
                raise RuntimeError("factor failed")

        failing_engine.factor_engine = RaisingFactorEngine()
        failing_captured = []

        def fail_open_evaluate(symbol, market, bars_history, position_dict, **kwargs):
            failing_captured.append(kwargs)
            return []

        failing_engine.rule_engine.evaluate_symbol = fail_open_evaluate

        with patch("engine.backtest.build_factor_attribution", return_value={"enabled": False, "factors": {}, "reason": "stubbed"}):
            fail_open_result = failing_engine.run()

        self.assertEqual(fail_open_result.total_trades, 0)
        self.assertEqual(len(failing_captured), len(bars))
        self.assertTrue(all(item.get("factor_snapshot") is None for item in failing_captured))
        self.assertTrue(all(item.get("previous_factor_snapshot") is None for item in failing_captured))
        self.assertEqual(failing_engine.factor_runtime_diagnostics["symbols"]["AAPL"]["status"], "error")


if __name__ == "__main__":
    unittest.main()
