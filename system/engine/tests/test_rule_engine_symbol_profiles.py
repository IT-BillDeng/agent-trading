from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.rule_engine import RuleEngine


def _bars() -> list[dict]:
    return [
        {
            "open": 99.5 + i,
            "high": 100.5 + i,
            "low": 99.0 + i,
            "close": 100.0 + i,
            "volume": 1000 + i,
        }
        for i in range(30)
    ]


def _rules_payload(*, with_profiles: bool = False) -> dict:
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
                    "order_type": "LMT",
                    "conditions": {"type": "price", "field": "close", "operator": "above", "value": 1},
                },
                "exit": {
                    "action": "EXIT",
                    "order_type": "MKT",
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
                    "order_type": "LMT",
                    "conditions": {"type": "price", "field": "close", "operator": "above", "value": 1},
                },
                "exit": {
                    "action": "EXIT",
                    "order_type": "MKT",
                    "conditions": {"type": "price", "field": "close", "operator": "below", "value": 1},
                },
            },
        ],
    }
    if with_profiles:
        payload["symbol_profile_templates"] = {
            "default_shared_30m": {
                "description": "default",
                "enabled_rules": {},
                "rule_overrides": {},
            }
        }
        payload["symbol_profiles"] = {
            "AAPL": {"profile": "default_shared_30m", "enabled_rules": {}, "rule_overrides": {}},
            "NVDA": {"profile": "default_shared_30m", "enabled_rules": {}, "rule_overrides": {}},
        }
    return payload


class RuleEngineSymbolProfileTests(unittest.TestCase):
    def _write_engine(self, payload: dict) -> RuleEngine:
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        with handle:
            json.dump(payload, handle)
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return RuleEngine(handle.name, symbol_universe=["AAPL", "NVDA"])

    def test_neutral_profile_preserves_signal_behavior(self):
        base_engine = self._write_engine(_rules_payload(with_profiles=False))
        profiled_engine = self._write_engine(_rules_payload(with_profiles=True))

        base_signal = base_engine.evaluate_symbol("AAPL", "US", _bars(), None)[0]
        profiled_signal = profiled_engine.evaluate_symbol("AAPL", "US", _bars(), None)[0]

        self.assertEqual(base_signal.action, profiled_signal.action)
        self.assertEqual(base_signal.rule_id, profiled_signal.rule_id)
        self.assertEqual(profiled_signal.symbol_profile, "default_shared_30m")

    def test_per_symbol_disable_blocks_only_that_rule(self):
        payload = _rules_payload(with_profiles=True)
        payload["symbol_profiles"]["NVDA"]["enabled_rules"] = {"rsi_reversal": False}
        engine = self._write_engine(payload)

        evaluated: list[str] = []
        original = engine._evaluate_rule

        def record(rule, symbol, market, bars, position):
            evaluated.append(f"{symbol}:{rule['rule_id']}")
            return original(rule, symbol, market, bars, position)

        engine._evaluate_rule = record  # type: ignore[method-assign]

        engine.evaluate_symbol("AAPL", "US", _bars(), None)
        engine.evaluate_symbol("NVDA", "US", _bars(), None)

        self.assertIn("AAPL:rsi_reversal", evaluated)
        self.assertIn("AAPL:bollinger_breakout", evaluated)
        self.assertNotIn("NVDA:rsi_reversal", evaluated)
        self.assertIn("NVDA:bollinger_breakout", evaluated)

    def test_signal_metadata_and_arbiter_source_ids_are_preserved(self):
        engine = self._write_engine(_rules_payload(with_profiles=True))

        signals = engine.evaluate_symbol("AAPL", "US", _bars(), None)

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal.primary_rule_id, "rsi_reversal")
        self.assertEqual(signal.source_rule_ids, ["rsi_reversal", "bollinger_breakout"])
        self.assertEqual(signal.base_rule_id, "rsi_reversal")
        self.assertEqual(signal.symbol_profile, "default_shared_30m")
        self.assertTrue(signal.effective_config_hash)
        self.assertEqual(len(signal.effective_config_hashes), 2)


if __name__ == "__main__":
    unittest.main()
