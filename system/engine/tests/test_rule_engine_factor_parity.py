from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.factors.engine import FactorEngine
from engine.rule_engine import IndicatorCalculator, RuleEngine


def _registry_payload() -> dict:
    return {
        "schema_version": 1,
        "defaults": {
            "mode": "shadow",
            "allow_actionable_consumption": False,
            "regular_session_only_for_indicators": True,
            "default_timezone": "America/New_York",
        },
        "factors": {
            "rsi_14_30m": {
                "type": "technical",
                "implementation": "builtin:rsi",
                "inputs": ["regular_session_30m_bars"],
                "params": {"period": 14},
                "session": "regular",
                "timeframe": "30min",
                "output": "numeric",
                "usage": ["shadow", "rule_condition_candidate"],
                "actionable": False,
                "point_in_time": True,
                "required_bars": 14,
                "lookback_bars": 14,
                "horizon_bars": 1,
                "timezone": "America/New_York",
                "no_lookahead": True,
                "version": 1,
            },
            "bollinger_zscore_20_2_30m": {
                "type": "technical",
                "implementation": "builtin:bollinger_zscore",
                "inputs": ["regular_session_30m_bars"],
                "params": {"period": 20, "std_dev": 2.0},
                "session": "regular",
                "timeframe": "30min",
                "output": "numeric",
                "usage": ["shadow", "rule_condition_candidate"],
                "actionable": False,
                "point_in_time": True,
                "required_bars": 20,
                "lookback_bars": 20,
                "horizon_bars": 1,
                "timezone": "America/New_York",
                "no_lookahead": True,
                "version": 1,
            },
            "volume_ratio_20_30m": {
                "type": "technical",
                "implementation": "builtin:volume_ratio",
                "inputs": ["regular_session_30m_bars"],
                "params": {"period": 20},
                "session": "regular",
                "timeframe": "30min",
                "output": "numeric",
                "usage": ["shadow", "rule_condition_candidate"],
                "actionable": False,
                "point_in_time": True,
                "required_bars": 20,
                "lookback_bars": 20,
                "horizon_bars": 1,
                "timezone": "America/New_York",
                "no_lookahead": True,
                "version": 1,
            },
            "atr_pct_14_30m": {
                "type": "risk",
                "implementation": "builtin:atr_pct",
                "inputs": ["regular_session_30m_bars"],
                "params": {"period": 14},
                "session": "regular",
                "timeframe": "30min",
                "output": "numeric",
                "usage": ["shadow", "risk_hint_candidate"],
                "actionable": False,
                "point_in_time": True,
                "required_bars": 15,
                "lookback_bars": 15,
                "horizon_bars": 1,
                "timezone": "America/New_York",
                "no_lookahead": True,
                "version": 1,
            },
            "return_5_30m": {
                "type": "technical",
                "implementation": "builtin:return",
                "inputs": ["regular_session_30m_bars"],
                "params": {"period": 5},
                "session": "regular",
                "timeframe": "30min",
                "output": "numeric",
                "usage": ["shadow", "rule_condition_candidate"],
                "actionable": False,
                "point_in_time": True,
                "required_bars": 6,
                "lookback_bars": 6,
                "horizon_bars": 1,
                "timezone": "America/New_York",
                "no_lookahead": True,
                "version": 1,
            },
        },
    }


def _rules_payload() -> dict:
    return {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "factorized_momentum_entry",
                "name": "Factorized Momentum Entry",
                "enabled": True,
                "priority": 1,
                "timeframe": "30min",
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "conditions": {
                        "operator": "AND",
                        "items": [
                            {
                                "type": "indicator",
                                "indicator": "rsi",
                                "params": {"period": 14},
                                "compare": {"operator": "above", "value": 60},
                            },
                            {
                                "type": "indicator",
                                "indicator": "momentum",
                                "params": {"period": 5},
                                "compare": {"operator": "above", "value": 0.01},
                            },
                            {
                                "type": "indicator",
                                "indicator": "volume_ratio",
                                "params": {"period": 20},
                                "compare": {"operator": "above", "value": 0.95},
                            },
                        ],
                    },
                    "action": "BUY",
                    "order_type": "LMT",
                    "stop_loss_pct": 0.03,
                    "take_profit_pct": 0.06,
                },
            }
        ],
    }


def _make_bar(ts: str, close: float, *, volume: int) -> dict:
    return {
        "time": ts,
        "open": close - 0.2,
        "high": close + 0.6,
        "low": close - 0.4,
        "close": close,
        "volume": volume,
    }


def _make_regular_day(date: str, *, start_close: float, volume_base: int) -> list[dict]:
    bars: list[dict] = []
    hour = 9
    minute = 30
    close = start_close
    for index in range(13):
        bars.append(
            _make_bar(
                f"{date} {hour:02d}:{minute:02d}:00",
                close,
                volume=volume_base + index * 150,
            )
        )
        close += 0.7
        minute += 30
        if minute >= 60:
            hour += 1
            minute -= 60
    return bars


class RuleEngineFactorParityTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.registry_path = root / "registry.json"
        self.rules_path = root / "rules.json"
        self.registry_path.write_text(json.dumps(_registry_payload(), ensure_ascii=False))
        self.rules_path.write_text(json.dumps(_rules_payload(), ensure_ascii=False))
        self.rule_engine = RuleEngine(self.rules_path, factor_registry=self.registry_path)
        self.factor_engine = FactorEngine(self.registry_path)
        self.calc = IndicatorCalculator()
        self.bars = _make_regular_day("2026-04-20", start_close=100.0, volume_base=1000) + _make_regular_day(
            "2026-04-21",
            start_close=109.5,
            volume_base=3000,
        )
        self.snapshot = self.factor_engine.evaluate_symbol(
            "AAPL",
            self.bars,
            evaluation_time="2026-04-21T21:00:00+00:00",
            market="US",
            provider="yfinance",
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_rsi_parity(self):
        resolved = self.rule_engine.condition_eval.factor_accessor.resolve_numeric_indicator(
            "rsi",
            {"period": 14},
            self.bars,
            factor_snapshot=self.snapshot,
        )
        expected = self.calc.calculate("rsi", {"period": 14}, self.bars)
        self.assertEqual(resolved["source"], "factor_snapshot")
        self.assertAlmostEqual(resolved["value"], expected, places=9)

    def test_bollinger_parity(self):
        resolved = self.rule_engine.condition_eval.factor_accessor.resolve_bollinger_zscore(
            {"period": 20, "std_dev": 2.0},
            self.bars,
            factor_snapshot=self.snapshot,
        )
        bands = self.calc.calculate("bollinger", {"period": 20, "std_dev": 2.0}, self.bars)
        self.assertIsNotNone(bands)
        band_std = (bands["upper"] - bands["middle"]) / 2.0
        expected = (float(self.bars[-1]["close"]) - bands["middle"]) / band_std
        self.assertEqual(resolved["source"], "factor_snapshot")
        self.assertAlmostEqual(resolved["value"], expected, places=9)

    def test_volume_ratio_parity(self):
        resolved = self.rule_engine.condition_eval.factor_accessor.resolve_numeric_indicator(
            "volume_ratio",
            {"period": 20},
            self.bars,
            factor_snapshot=self.snapshot,
        )
        expected = self.calc.calculate("volume_ratio", {"period": 20}, self.bars)
        self.assertEqual(resolved["source"], "factor_snapshot")
        self.assertAlmostEqual(resolved["value"], expected, places=9)

    def test_atr_parity(self):
        resolved = self.rule_engine.condition_eval.factor_accessor.resolve_numeric_indicator(
            "atr",
            {"period": 14},
            self.bars,
            factor_snapshot=self.snapshot,
        )
        expected = self.calc.calculate("atr", {"period": 14}, self.bars)
        self.assertEqual(resolved["source"], "factor_snapshot")
        self.assertAlmostEqual(resolved["value"], expected, places=9)

    def test_return_parity(self):
        resolved = self.rule_engine.condition_eval.factor_accessor.resolve_numeric_indicator(
            "momentum",
            {"period": 5},
            self.bars,
            factor_snapshot=self.snapshot,
        )
        expected = self.calc.calculate("momentum", {"period": 5}, self.bars)
        self.assertEqual(resolved["source"], "factor_snapshot")
        self.assertAlmostEqual(resolved["value"], expected, places=9)

    def test_missing_snapshot_uses_compatibility_fallback(self):
        factor_def = self.rule_engine.condition_eval.factor_accessor._synthetic_factor_definition(
            "momentum",
            {"period": 3},
        )
        payload = self.rule_engine.condition_eval.factor_accessor.factor_engine.evaluate_factor_definition(
            factor_def,
            self.bars,
            evaluation_time=self.snapshot["timestamp"],
        )
        expected, reason = self.rule_engine.condition_eval.factor_accessor._payload_to_numeric_value(
            "momentum",
            payload,
            self.bars,
        )

        resolved = self.rule_engine.condition_eval.factor_accessor.resolve_numeric_indicator(
            "momentum",
            {"period": 3},
            self.bars,
            factor_snapshot=self.snapshot,
        )
        self.assertEqual(resolved["source"], "factor_engine_compatibility")
        self.assertEqual(resolved["reason"], reason)
        self.assertAlmostEqual(resolved["value"], expected, places=9)

    def test_default_rules_use_factor_engine_compatibility_without_snapshot(self):
        baseline = self.rule_engine.evaluate_symbol("AAPL", "US", self.bars, None)

        self.assertEqual(len(baseline), 1)
        entry_diagnostics = baseline[0].diagnostics["entry"]["diagnostics"]
        feature_sources = {
            item.get("feature_source")
            for item in entry_diagnostics
            if isinstance(item, dict)
        }

        self.assertIn("factor_engine_compatibility", feature_sources)
        self.assertNotIn("legacy_indicator_calculator", feature_sources)

    def test_default_buy_signal_is_unchanged_with_factor_snapshot(self):
        baseline = self.rule_engine.evaluate_symbol("AAPL", "US", self.bars, None)
        with_snapshot = self.rule_engine.evaluate_symbol(
            "AAPL",
            "US",
            self.bars,
            None,
            factor_snapshot=self.snapshot,
            previous_factor_snapshot=self.factor_engine.evaluate_symbol(
                "AAPL",
                self.bars[:-1],
                evaluation_time="2026-04-21T21:00:00+00:00",
                market="US",
                provider="yfinance",
            ),
        )
        self.assertEqual(len(baseline), len(with_snapshot))
        self.assertEqual([item.action for item in baseline], [item.action for item in with_snapshot])
        self.assertEqual([item.reason for item in baseline], [item.reason for item in with_snapshot])
        self.assertEqual([item.rule_id for item in baseline], [item.rule_id for item in with_snapshot])
        self.assertEqual(
            [item.suggested_quantity for item in baseline],
            [item.suggested_quantity for item in with_snapshot],
        )

    def test_factor_failure_is_fail_open(self):
        baseline = self.rule_engine.evaluate_symbol("AAPL", "US", self.bars, None)
        broken_snapshot = {
            "symbol": "AAPL",
            "factors": {
                "rsi_14_30m": {
                    "value": None,
                    "ready": False,
                    "reason": "synthetic_failure",
                    "source": "factor_snapshot",
                    "config_hash": "broken",
                }
            },
        }
        fail_open = self.rule_engine.evaluate_symbol(
            "AAPL",
            "US",
            self.bars,
            None,
            factor_snapshot=broken_snapshot,
            previous_factor_snapshot=None,
        )
        self.assertEqual([item.to_dict() for item in baseline], [item.to_dict() for item in fail_open])


if __name__ == "__main__":
    unittest.main()
