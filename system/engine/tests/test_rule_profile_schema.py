from __future__ import annotations

import copy
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.rule_schema import validate_rules_config


def _rules_payload() -> dict:
    return {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "trend_follow_30m",
                "enabled": False,
                "priority": 1,
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
            },
            {
                "rule_id": "rsi_reversal",
                "enabled": True,
                "priority": 2,
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "action": "BUY",
                    "stop_loss_pct": 0.02,
                    "take_profit_pct": 0.04,
                    "conditions": {
                        "operator": "AND",
                        "items": [
                            {
                                "type": "indicator",
                                "indicator": "rsi",
                                "params": {"period": 14},
                                "compare": {"operator": "cross_above", "value": 30},
                            }
                        ],
                    },
                },
                "exit": {
                    "action": "EXIT",
                    "conditions": {
                        "operator": "OR",
                        "items": [
                            {
                                "type": "indicator",
                                "indicator": "rsi",
                                "params": {"period": 14},
                                "compare": {"operator": "above", "value": 75},
                            },
                            {"type": "stop_loss", "threshold_pct": 0.02},
                        ],
                    },
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
        "symbol_profiles": {},
    }


class RuleProfileSchemaTests(unittest.TestCase):
    def test_unknown_profile_name_is_rejected(self):
        payload = _rules_payload()
        payload["symbol_profiles"]["AAPL"] = {
            "profile": "missing_profile",
            "enabled_rules": {},
            "rule_overrides": {},
        }

        result = validate_rules_config(payload, symbol_universe={"AAPL"})

        self.assertFalse(result["valid"])
        self.assertTrue(any("unknown profile" in error for error in result["errors"]))

    def test_unknown_rule_id_and_forbidden_key_are_rejected(self):
        payload = _rules_payload()
        payload["symbol_profiles"]["AAPL"] = {
            "profile": "default_shared_30m",
            "enabled_rules": {"missing_rule": False},
            "rule_overrides": {
                "rsi_reversal": {
                    "execution": {"live_submit": True},
                }
            },
        }

        result = validate_rules_config(payload, symbol_universe={"AAPL"})

        self.assertFalse(result["valid"])
        self.assertTrue(any("unknown rule_id 'missing_rule'" in error for error in result["errors"]))
        self.assertTrue(any(".execution is forbidden" in error or ".execution is not allowed" in error for error in result["errors"]))

    def test_invalid_numeric_range_is_rejected(self):
        payload = _rules_payload()
        payload["symbol_profiles"]["AAPL"] = {
            "profile": "default_shared_30m",
            "enabled_rules": {},
            "rule_overrides": {
                "rsi_reversal": {
                    "entry": {
                        "conditions": {
                            "operator": "AND",
                            "items": [
                                {
                                    "type": "indicator",
                                    "indicator": "rsi",
                                    "params": {"period": 14},
                                    "compare": {"operator": "cross_above", "value": 130},
                                }
                            ],
                        }
                    }
                }
            },
        }

        result = validate_rules_config(payload, symbol_universe={"AAPL"})

        self.assertFalse(result["valid"])
        self.assertTrue(any("out of range" in error for error in result["errors"]))

    def test_cannot_enable_base_disabled_rule(self):
        payload = _rules_payload()
        payload["symbol_profiles"]["AAPL"] = {
            "profile": "default_shared_30m",
            "enabled_rules": {"trend_follow_30m": True},
            "rule_overrides": {},
        }

        result = validate_rules_config(payload, symbol_universe={"AAPL"})

        self.assertFalse(result["valid"])
        self.assertTrue(any("cannot enable base disabled rule" in error for error in result["errors"]))

    def test_symbol_outside_current_universe_is_rejected(self):
        payload = _rules_payload()
        payload["symbol_profiles"]["TSLA"] = {
            "profile": "default_shared_30m",
            "enabled_rules": {},
            "rule_overrides": {},
        }

        result = validate_rules_config(payload, symbol_universe={"AAPL", "MSFT"})

        self.assertFalse(result["valid"])
        self.assertTrue(any("outside current universe" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
