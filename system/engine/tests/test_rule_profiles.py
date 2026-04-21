from __future__ import annotations

import copy
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.rule_profiles import (
    DEFAULT_SYMBOL_PROFILE_ID,
    build_symbol_profile_overview,
    resolve_effective_rule,
)


def _base_rules() -> dict:
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
    }


class RuleProfileResolverTests(unittest.TestCase):
    def test_backward_compatible_default_profile_keeps_base_behavior(self):
        rules = _base_rules()

        effective = resolve_effective_rule(rules, "AAPL", "rsi_reversal", market="US")

        self.assertIsNotNone(effective)
        self.assertEqual(effective["entry"]["take_profit_pct"], 0.04)
        self.assertEqual(effective["entry"]["stop_loss_pct"], 0.02)
        self.assertEqual(effective["entry"]["conditions"]["items"][0]["compare"]["value"], 30)
        self.assertEqual(effective["__rule_profile__"]["profile_id"], DEFAULT_SYMBOL_PROFILE_ID)
        self.assertEqual(effective["__rule_profile__"]["overrides_applied"], {})

    def test_symbol_level_parameter_override_does_not_mutate_base_rule(self):
        rules = _base_rules()
        original = copy.deepcopy(rules["rules"][1])
        rules["symbol_profiles"] = {
            "AAPL": {
                "profile": DEFAULT_SYMBOL_PROFILE_ID,
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
                                        "compare": {"operator": "cross_above", "value": 35},
                                    }
                                ],
                            }
                        },
                        "risk": {"stop_loss_pct": 0.025},
                    }
                },
            }
        }

        aapl_rule = resolve_effective_rule(rules, "AAPL", "rsi_reversal", market="US")
        msft_rule = resolve_effective_rule(rules, "MSFT", "rsi_reversal", market="US")

        self.assertEqual(aapl_rule["entry"]["conditions"]["items"][0]["compare"]["value"], 35)
        self.assertEqual(aapl_rule["entry"]["stop_loss_pct"], 0.025)
        self.assertEqual(aapl_rule["exit"]["conditions"]["items"][1]["threshold_pct"], 0.025)
        self.assertEqual(msft_rule["entry"]["conditions"]["items"][0]["compare"]["value"], 30)
        self.assertEqual(msft_rule["entry"]["stop_loss_pct"], 0.02)
        self.assertEqual(rules["rules"][1], original)

    def test_profile_template_inheritance_and_symbol_level_priority(self):
        rules = _base_rules()
        rules["symbol_profile_templates"] = {
            "default_shared_30m": {
                "description": "default",
                "enabled_rules": {},
                "rule_overrides": {},
            },
            "high_beta_guarded": {
                "description": "guarded",
                "enabled_rules": {"rsi_reversal": False},
                "rule_overrides": {
                    "rsi_reversal": {"risk": {"stop_loss_pct": 0.03}},
                },
            },
        }
        rules["symbol_profiles"] = {
            "NVDA": {
                "profile": "high_beta_guarded",
                "enabled_rules": {"rsi_reversal": False},
                "rule_overrides": {
                    "rsi_reversal": {"risk": {"stop_loss_pct": 0.015}},
                },
            }
        }

        overview = build_symbol_profile_overview(rules, ["NVDA"], market_by_symbol={"NVDA": "US"})

        self.assertEqual(overview["NVDA"]["profile"], "high_beta_guarded")
        self.assertIn("rsi_reversal", overview["NVDA"]["disabled_rules"])
        self.assertIn("rsi_reversal", overview["NVDA"]["rules_with_overrides"])
        self.assertEqual(
            overview["NVDA"]["overrides"]["rsi_reversal"]["risk"]["stop_loss_pct"],
            0.015,
        )


if __name__ == "__main__":
    unittest.main()
