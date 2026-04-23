from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.factors.engine import FactorEngine
from engine.factors.registry import load_factor_registry
from engine.rule_engine import RuleEngine


def _bars_from_closes(closes: list[float]) -> list[dict]:
    bars: list[dict] = []
    for index, close in enumerate(closes):
        day = 17 + (index // 13)
        slot = index % 13
        total_minutes = 9 * 60 + 30 + slot * 30
        hour = total_minutes // 60
        minute = total_minutes % 60
        bars.append(
            {
                "time": f"2026-04-{day:02d} {hour:02d}:{minute:02d}:00",
                "open": close - 0.2,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1000 + index * 10,
            }
        )
    return bars


def _registry_payload(*, allow_actionable: bool = False, actionable: bool = False, usage: list[str] | None = None) -> dict:
    if usage is None:
        usage = ["shadow", "rule_condition_candidate"]
    return {
        "schema_version": 1,
        "defaults": {
            "mode": "shadow",
            "allow_actionable_consumption": allow_actionable,
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
                "usage": usage,
                "actionable": actionable,
                "point_in_time": True,
                "required_bars": 14,
                "lookback_bars": 14,
                "horizon_bars": 1,
                "timezone": "America/New_York",
                "no_lookahead": True,
                "version": 1,
            }
        },
    }


def _factor_rule_payload(
    *,
    rule_id: str = "factor_rule",
    include_price_rule: bool = False,
    intent_action: str = "BUY",
) -> dict:
    rule = {
        "rule_id": rule_id,
        "name": "Factor Rule",
        "enabled": True,
        "priority": 1,
        "symbols": ["*"],
        "markets": ["US"],
    }
    factor_condition = {
        "type": "indicator",
        "indicator": "factor",
        "factor_id": "rsi_14_30m",
        "compare": {"operator": "cross_above", "value": 30},
    }
    if intent_action == "EXIT":
        rule["exit"] = {
            "action": "EXIT",
            "conditions": factor_condition,
        }
    else:
        rule["entry"] = {
            "action": "BUY",
            "conditions": factor_condition,
        }

    rules = [rule]
    if include_price_rule:
        rules.append(
            {
                "rule_id": "price_backup",
                "name": "Price Backup",
                "enabled": True,
                "priority": 2,
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "action": "BUY",
                    "conditions": {
                        "type": "price",
                        "field": "close",
                        "operator": "above",
                        "value": 1,
                    },
                },
            }
        )
    return {"version": "1.0", "rules": rules}


class RuleEngineFactorConditionTests(unittest.TestCase):
    def _write_json(self, root: Path, name: str, payload: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(payload, ensure_ascii=False))
        return path

    def _factor_snapshots(
        self,
        registry_path: Path,
        closes: list[float],
    ) -> tuple[dict, dict]:
        registry = load_factor_registry(registry_path)
        engine = FactorEngine(registry)
        current_bars = _bars_from_closes(closes)
        previous_bars = _bars_from_closes(closes[:-1])
        current = engine.evaluate_symbol(
            "AAPL",
            current_bars,
            evaluation_time="2026-04-20T14:30:00+00:00",
        )
        previous = engine.evaluate_symbol(
            "AAPL",
            previous_bars,
            evaluation_time="2026-04-20T14:00:00+00:00",
        )
        return current, previous

    def test_factor_condition_is_shadow_only_and_preserves_diagnostics(self):
        closes = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 86, 87, 91]
        bars = _bars_from_closes(closes)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = self._write_json(
                root,
                "registry.json",
                _registry_payload(),
            )
            rules_path = self._write_json(root, "rules.json", _factor_rule_payload())
            current_factor, previous_factor = self._factor_snapshots(registry_path, closes)
            engine = RuleEngine(rules_path, factor_registry=registry_path)

            signals = engine.evaluate_symbol(
                "AAPL",
                "US",
                bars,
                None,
                factor_snapshot=current_factor,
                previous_factor_snapshot=previous_factor,
            )

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.rule_id, "factor_rule")
        self.assertEqual(signal.action, "HOLD")
        self.assertEqual(signal.reason, "no_condition_met")
        self.assertEqual(signal.diagnostics["used_factors"], ["rsi_14_30m"])
        self.assertTrue(signal.diagnostics["factor_readiness"]["rsi_14_30m"])
        self.assertAlmostEqual(
            signal.diagnostics["factor_values"]["rsi_14_30m"],
            current_factor["factors"]["rsi_14_30m"]["value"],
            places=6,
        )
        self.assertIn("arbiter", signal.diagnostics)
        self.assertEqual(signal.diagnostics["entry"]["factor_id"], "rsi_14_30m")
        self.assertEqual(signal.diagnostics["entry"]["reason"], "factor_actionable_consumption_disabled")
        self.assertEqual(
            signal.diagnostics["entry"]["source"],
            current_factor["factors"]["rsi_14_30m"]["source"],
        )
        self.assertEqual(
            signal.diagnostics["entry"]["config_hash"],
            current_factor["factors"]["rsi_14_30m"]["config_hash"],
        )

    def test_factor_not_ready_returns_false_condition_and_reason(self):
        closes = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91]
        bars = _bars_from_closes(closes)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = self._write_json(
                root,
                "registry.json",
                _registry_payload(),
            )
            rules_path = self._write_json(
                root,
                "rules.json",
                _factor_rule_payload(intent_action="EXIT"),
            )
            current_factor, _ = self._factor_snapshots(registry_path, closes)
            engine = RuleEngine(rules_path, factor_registry=registry_path)

            signals = engine.evaluate_symbol(
                "AAPL",
                "US",
                bars,
                {"quantity": 10, "avg_price": closes[-1]},
                factor_snapshot=current_factor,
            )

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.action, "HOLD")
        self.assertEqual(signal.reason, "no_condition_met")
        self.assertEqual(signal.diagnostics["exit"]["reason"], "factor_not_ready")
        self.assertEqual(signal.diagnostics["exit"]["factor_reason"], "insufficient_bars")
        self.assertEqual(signal.diagnostics["used_factors"], ["rsi_14_30m"])
        self.assertFalse(signal.diagnostics["factor_readiness"]["rsi_14_30m"])

    def test_context_only_or_non_actionable_factor_cannot_trigger_buy_when_actionable_consumption_disabled(self):
        closes = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 86, 87, 91]
        bars = _bars_from_closes(closes)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = self._write_json(
                root,
                "registry.json",
                _registry_payload(
                    allow_actionable=False,
                    actionable=False,
                    usage=["shadow", "context_only"],
                ),
            )
            rules_path = self._write_json(root, "rules.json", _factor_rule_payload())
            current_factor, previous_factor = self._factor_snapshots(registry_path, closes)
            engine = RuleEngine(rules_path, factor_registry=registry_path)

            signals = engine.evaluate_symbol(
                "AAPL",
                "US",
                bars,
                None,
                factor_snapshot=current_factor,
                previous_factor_snapshot=previous_factor,
            )

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.action, "HOLD")
        self.assertEqual(signal.diagnostics["entry"]["reason"], "factor_actionable_consumption_disabled")
        self.assertEqual(signal.diagnostics["used_factors"], ["rsi_14_30m"])

    def test_current_rules_without_factor_conditions_keep_same_behavior(self):
        closes = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 86, 87, 91]
        bars = _bars_from_closes(closes)
        rules_path = Path(__file__).resolve().parents[3] / "rules" / "rules.json"

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = self._write_json(
                root,
                "registry.json",
                _registry_payload(),
            )
            current_factor, previous_factor = self._factor_snapshots(registry_path, closes)
            engine = RuleEngine(rules_path)

            baseline = [signal.to_dict() for signal in engine.evaluate_symbol("AAPL", "US", bars, None)]
            with_factor = [
                signal.to_dict()
                for signal in engine.evaluate_symbol(
                    "AAPL",
                    "US",
                    bars,
                    None,
                    factor_snapshot=current_factor,
                    previous_factor_snapshot=previous_factor,
                )
            ]

        self.assertEqual(baseline, with_factor)


if __name__ == "__main__":
    unittest.main()
