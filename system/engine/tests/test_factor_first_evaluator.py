from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.factors.engine import FactorEngine
from engine.rule_engine import RuleEngine
from engine.strategy.evaluator import normalize_rule_to_factor_binding_view


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


def _legacy_rule_payload() -> dict:
    return {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "legacy_entry",
                "name": "Legacy Entry",
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


def _factor_rule_payload() -> dict:
    return {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "factor_entry",
                "name": "Factor Entry",
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
                                "indicator": "factor",
                                "factor_id": "rsi_14_30m",
                                "compare": {"operator": "above", "value": 60},
                            },
                            {
                                "type": "indicator",
                                "indicator": "factor",
                                "factor_id": "return_5_30m",
                                "compare": {"operator": "above", "value": 0.01},
                            },
                            {
                                "type": "indicator",
                                "indicator": "factor",
                                "factor_id": "volume_ratio_20_30m",
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


def _mixed_rules_payload() -> dict:
    legacy = _legacy_rule_payload()["rules"][0]
    factor = _factor_rule_payload()["rules"][0]
    legacy["rule_id"] = "legacy_buy"
    legacy["priority"] = 3
    factor["rule_id"] = "factor_buy"
    factor["priority"] = 1
    return {"version": "1.0", "rules": [legacy, factor]}


def _legacy_exit_rule_payload() -> dict:
    return {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "legacy_exit",
                "name": "Legacy Exit",
                "enabled": True,
                "priority": 1,
                "timeframe": "30min",
                "symbols": ["*"],
                "markets": ["US"],
                "exit": {
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
                        ],
                    },
                    "action": "EXIT",
                    "order_type": "MKT",
                },
            }
        ],
    }


def _factor_exit_rule_payload() -> dict:
    return {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "factor_exit",
                "name": "Factor Exit",
                "enabled": True,
                "priority": 1,
                "timeframe": "30min",
                "symbols": ["*"],
                "markets": ["US"],
                "exit": {
                    "conditions": {
                        "operator": "AND",
                        "items": [
                            {
                                "type": "indicator",
                                "indicator": "factor",
                                "factor_id": "rsi_14_30m",
                                "compare": {"operator": "above", "value": 60},
                            },
                            {
                                "type": "indicator",
                                "indicator": "factor",
                                "factor_id": "return_5_30m",
                                "compare": {"operator": "above", "value": 0.01},
                            },
                        ],
                    },
                    "action": "EXIT",
                    "order_type": "MKT",
                },
            }
        ],
    }


def _mixed_exit_rules_payload() -> dict:
    legacy = _legacy_exit_rule_payload()["rules"][0]
    factor = _factor_exit_rule_payload()["rules"][0]
    legacy["rule_id"] = "legacy_exit_low_priority"
    legacy["priority"] = 3
    factor["rule_id"] = "factor_exit_high_priority"
    factor["priority"] = 1
    return {"version": "1.0", "rules": [legacy, factor]}


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


class FactorFirstEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.registry_path = self.root / "registry.json"
        self.registry_path.write_text(json.dumps(_registry_payload(), ensure_ascii=False))
        self.bars = _make_regular_day("2026-04-20", start_close=100.0, volume_base=1000) + _make_regular_day(
            "2026-04-21",
            start_close=109.5,
            volume_base=3000,
        )
        self.factor_engine = FactorEngine(self.registry_path)
        self.current_factor = self.factor_engine.evaluate_symbol(
            "AAPL",
            self.bars,
            evaluation_time="2026-04-21T21:00:00+00:00",
            market="US",
            provider="yfinance",
        )
        self.previous_factor = self.factor_engine.evaluate_symbol(
            "AAPL",
            self.bars[:-1],
            evaluation_time="2026-04-21T21:00:00+00:00",
            market="US",
            provider="yfinance",
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _write_rules(self, filename: str, payload: dict) -> Path:
        path = self.root / filename
        path.write_text(json.dumps(payload, ensure_ascii=False))
        return path

    def test_migration_tool_normalizes_legacy_conditions_to_factor_binding_view(self):
        legacy_rule = {
            "rule_id": "legacy_migration_view",
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
                            "indicator": "bollinger",
                            "params": {"period": 20, "std_dev": 2},
                            "compare": {"operator": "above_middle"},
                        },
                        {
                            "type": "volume",
                            "operator": "above_avg",
                            "ratio": 0.95,
                        },
                    ],
                }
            },
        }
        engine = RuleEngine(self._write_rules("legacy_rules.json", _legacy_rule_payload()), factor_registry=self.registry_path)

        view = normalize_rule_to_factor_binding_view(
            legacy_rule,
            factor_accessor=engine.condition_eval.factor_only_accessor,
        )

        self.assertEqual(view["rule_id"], "legacy_migration_view")
        self.assertEqual(sorted(view["factor_ids"]), [
            "bollinger_zscore_20_2_30m",
            "rsi_14_30m",
            "volume_ratio_20_30m",
        ])
        entry_view = view["entry"]
        self.assertEqual(entry_view.kind, "structural_condition")
        item_views = entry_view.metadata["item_views"]
        self.assertEqual([item.kind for item in item_views], [
            "factor_condition",
            "factor_condition",
            "factor_condition",
        ])

    def test_factor_based_rule_and_legacy_rule_match_on_equivalent_conditions(self):
        legacy_rules = self._write_rules("legacy_exit_rules.json", _legacy_exit_rule_payload())
        factor_rules = self._write_rules("factor_exit_rules.json", _factor_exit_rule_payload())
        legacy_engine = RuleEngine(legacy_rules, factor_registry=self.registry_path)
        factor_engine = RuleEngine(factor_rules, factor_registry=self.registry_path)
        position = {"avg_cost": 100.0, "quantity": 10}

        legacy_signals = legacy_engine.evaluate_symbol(
            "AAPL",
            "US",
            self.bars,
            position,
            factor_snapshot=self.current_factor,
            previous_factor_snapshot=self.previous_factor,
        )
        factor_signals = factor_engine.evaluate_symbol(
            "AAPL",
            "US",
            self.bars,
            position,
            factor_snapshot=self.current_factor,
            previous_factor_snapshot=self.previous_factor,
        )

        self.assertEqual(len(legacy_signals), 1)
        self.assertEqual(len(factor_signals), 1)
        self.assertEqual(legacy_signals[0].action, factor_signals[0].action)
        self.assertEqual(legacy_signals[0].reason, factor_signals[0].reason)
        self.assertEqual(legacy_signals[0].suggested_quantity, factor_signals[0].suggested_quantity)
        self.assertEqual(legacy_signals[0].stop_loss, factor_signals[0].stop_loss)
        self.assertEqual(legacy_signals[0].take_profit, factor_signals[0].take_profit)

    def test_signal_arbiter_behavior_is_stable_with_mixed_factor_and_legacy_rules(self):
        mixed_rules = self._write_rules("mixed_exit_rules.json", _mixed_exit_rules_payload())
        engine = RuleEngine(mixed_rules, factor_registry=self.registry_path)
        position = {"avg_cost": 100.0, "quantity": 10}

        signals = engine.evaluate_symbol(
            "AAPL",
            "US",
            self.bars,
            position,
            factor_snapshot=self.current_factor,
            previous_factor_snapshot=self.previous_factor,
        )

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.rule_id, "factor_exit_high_priority")
        self.assertEqual(signal.diagnostics["arbiter"]["resolution"], "priority")
        self.assertEqual(signal.diagnostics["arbiter"]["suppressed"], ["legacy_exit_low_priority"])


if __name__ == "__main__":
    unittest.main()
