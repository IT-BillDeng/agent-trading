from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.rule_engine import RuleEngine, RuleSignal
from engine.signal_arbiter import SignalArbiter


class SignalArbiterTests(unittest.TestCase):
    def setUp(self):
        self.arbiter = SignalArbiter()

    def _signal(self, *, rule_id: str, action: str, priority: int, score: int = 1) -> RuleSignal:
        return RuleSignal(
            rule_id=rule_id,
            symbol="AAPL",
            market="US",
            action=action,
            order_type="LMT",
            score=score,
            reason="test",
            priority=priority,
            stop_loss=None,
            take_profit=None,
            last_close=100.0,
            diagnostics={},
        )

    def test_exit_wins_over_buy(self):
        result = self.arbiter.choose(
            [
                self._signal(rule_id="buy_rule", action="BUY", priority=1),
                self._signal(rule_id="exit_rule", action="EXIT", priority=5),
            ]
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.action, "EXIT")
        self.assertEqual(result.rule_id, "exit_rule")
        self.assertEqual(result.diagnostics["arbiter"]["resolution"], "exit_over_buy")
        self.assertEqual(result.diagnostics["arbiter"]["suppressed"], ["buy_rule"])

    def test_multiple_buys_choose_lower_priority_value(self):
        result = self.arbiter.choose(
            [
                self._signal(rule_id="buy_slow", action="BUY", priority=5),
                self._signal(rule_id="buy_fast", action="BUY", priority=2),
            ]
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.action, "BUY")
        self.assertEqual(result.rule_id, "buy_fast")
        self.assertEqual(result.diagnostics["arbiter"]["resolution"], "priority")

    def test_same_priority_uses_score(self):
        result = self.arbiter.choose(
            [
                self._signal(rule_id="rule_low_score", action="BUY", priority=2, score=1),
                self._signal(rule_id="rule_high_score", action="BUY", priority=2, score=5),
            ]
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.rule_id, "rule_high_score")
        self.assertEqual(result.diagnostics["arbiter"]["resolution"], "score")

    def test_hold_selected_when_only_hold_signals_exist(self):
        result = self.arbiter.choose(
            [
                self._signal(rule_id="hold_a", action="HOLD", priority=3),
                self._signal(rule_id="hold_b", action="HOLD", priority=1),
            ]
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.action, "HOLD")
        self.assertEqual(result.rule_id, "hold_b")
        self.assertEqual(result.diagnostics["arbiter"]["resolution"], "priority")


class RuleEngineArbiterIntegrationTests(unittest.TestCase):
    def _bars(self):
        closes = [100 + i for i in range(30)]
        return [
            {
                "open": close - 0.2,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1000000,
            }
            for close in closes
        ]

    def test_rule_engine_returns_single_final_signal_per_symbol(self):
        rules_config = {
            "version": "1.0",
            "rules": [
                {
                    "rule_id": "buy_rule",
                    "enabled": True,
                    "priority": 5,
                    "symbols": ["*"],
                    "markets": ["US"],
                    "entry": {
                        "conditions": {
                            "type": "indicator",
                            "indicator": "sma",
                            "params": {"period": 3},
                            "compare": {"field": "close", "operator": "below"},
                        },
                        "action": "BUY",
                        "order_type": "LMT",
                    },
                },
                {
                    "rule_id": "hold_rule",
                    "enabled": True,
                    "priority": 1,
                    "symbols": ["*"],
                    "markets": ["US"],
                    "entry": {
                        "conditions": {
                            "type": "indicator",
                            "indicator": "rsi",
                            "params": {"period": 14},
                            "compare": {"operator": "below", "value": 5},
                        },
                        "action": "BUY",
                        "order_type": "LMT",
                    },
                },
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(rules_config, f)
            rules_path = f.name

        try:
            engine = RuleEngine(rules_path)
            signals = engine.evaluate_symbol("AAPL", "US", self._bars(), None)
        finally:
            Path(rules_path).unlink()

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].action, "BUY")
        self.assertEqual(signals[0].rule_id, "buy_rule")
        self.assertIn("arbiter", signals[0].diagnostics)
        self.assertEqual(signals[0].diagnostics["arbiter"]["selected_rule_id"], "buy_rule")
        self.assertEqual(signals[0].diagnostics["arbiter"]["suppressed"], ["hold_rule"])


if __name__ == "__main__":
    unittest.main()
