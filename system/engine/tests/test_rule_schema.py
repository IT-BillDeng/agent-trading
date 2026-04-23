from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.rule_engine import RuleEngine
from engine.rule_schema import validate_rules_config


class RuleSchemaValidationTests(unittest.TestCase):
    def test_unknown_factor_id_is_rejected(self):
        rules_data = {
            "rules": [
                {
                    "rule_id": "factor_rule",
                    "enabled": True,
                    "priority": 1,
                    "symbols": ["*"],
                    "markets": ["US"],
                    "entry": {
                        "action": "BUY",
                        "conditions": {
                            "type": "indicator",
                            "indicator": "factor",
                            "factor_id": "missing_factor",
                            "compare": {"operator": "above", "value": 30},
                        },
                    },
                }
            ]
        }
        registry_payload = {
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
                }
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            json.dump(registry_payload, handle)
            registry_path = handle.name

        try:
            result = validate_rules_config(rules_data, factor_registry=registry_path)
        finally:
            Path(registry_path).unlink()

        self.assertFalse(result["valid"])
        self.assertTrue(any("unknown factor_id" in item for item in result["errors"]))

    def test_current_rules_file_is_schema_valid(self):
        rules_path = Path(__file__).resolve().parents[3] / "rules" / "rules.json"
        rules_data = json.loads(rules_path.read_text())

        result = validate_rules_config(rules_data)

        self.assertTrue(result["valid"])
        self.assertEqual(result["errors"], [])

    def test_duplicate_rule_id_is_rejected(self):
        rules_data = {
            "rules": [
                {"rule_id": "dup", "enabled": True, "priority": 1, "entry": {"action": "BUY", "conditions": {"type": "price", "field": "close", "operator": "above", "value": 1}}},
                {"rule_id": "dup", "enabled": True, "priority": 2, "entry": {"action": "BUY", "conditions": {"type": "price", "field": "close", "operator": "above", "value": 2}}},
            ]
        }

        result = validate_rules_config(rules_data)

        self.assertFalse(result["valid"])
        self.assertTrue(any("duplicate rule_id" in item for item in result["errors"]))

    def test_invalid_entry_action_is_rejected(self):
        rules_data = {
            "rules": [
                {
                    "rule_id": "bad_entry_action",
                    "enabled": True,
                    "priority": 1,
                    "entry": {
                        "action": "EXIT",
                        "conditions": {"type": "price", "field": "close", "operator": "above", "value": 1},
                    },
                }
            ]
        }

        result = validate_rules_config(rules_data)

        self.assertFalse(result["valid"])
        self.assertTrue(any("entry.action" in item for item in result["errors"]))

    def test_invalid_indicator_and_operator_are_rejected(self):
        rules_data = {
            "rules": [
                {
                    "rule_id": "bad_indicator",
                    "enabled": True,
                    "priority": 1,
                    "entry": {
                        "action": "BUY",
                        "conditions": {
                            "type": "indicator",
                            "indicator": "does_not_exist",
                            "compare": {"operator": "sideways", "value": 1},
                        },
                    },
                }
            ]
        }

        result = validate_rules_config(rules_data)

        self.assertFalse(result["valid"])
        self.assertTrue(any("unsupported indicator" in item for item in result["errors"]))
        self.assertTrue(any("unsupported operator" in item for item in result["errors"]))

    def test_cross_operator_requires_compare_target(self):
        rules_data = {
            "rules": [
                {
                    "rule_id": "bad_cross",
                    "enabled": True,
                    "priority": 1,
                    "entry": {
                        "action": "BUY",
                        "conditions": {
                            "type": "indicator",
                            "indicator": "rsi",
                            "params": {"period": 14},
                            "compare": {"operator": "cross_above"},
                        },
                    },
                }
            ]
        }

        result = validate_rules_config(rules_data)

        self.assertFalse(result["valid"])
        self.assertTrue(any("cross operator requires" in item for item in result["errors"]))

    def test_search_space_path_must_resolve(self):
        rules_data = {
            "rules": [
                {
                    "rule_id": "bad_search_space",
                    "enabled": True,
                    "priority": 1,
                    "entry": {
                        "action": "BUY",
                        "conditions": {"type": "price", "field": "close", "operator": "above", "value": 1},
                    },
                    "search_space": {
                        "threshold": {
                            "min": 1,
                            "max": 2,
                            "step": 1,
                            "path": "entry.conditions.items[0].compare.value",
                        }
                    },
                }
            ]
        }

        result = validate_rules_config(rules_data)

        self.assertFalse(result["valid"])
        self.assertTrue(any("search_space path" in item for item in result["errors"]))

    def test_rule_engine_ignores_invalid_rules_on_load(self):
        rules_data = {
            "rules": [
                {
                    "rule_id": "valid_buy",
                    "enabled": True,
                    "priority": 1,
                    "symbols": ["*"],
                    "markets": ["US"],
                    "entry": {
                        "action": "BUY",
                        "conditions": {"type": "price", "field": "close", "operator": "above", "value": 1},
                    },
                },
                {
                    "rule_id": "invalid_buy",
                    "enabled": True,
                    "priority": "high",
                    "symbols": ["*"],
                    "markets": ["US"],
                    "entry": {
                        "action": "BUY",
                        "conditions": {"type": "indicator", "indicator": "bad_indicator", "compare": {"operator": "above", "value": 1}},
                    },
                },
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(rules_data, f)
            rules_path = f.name

        try:
            engine = RuleEngine(rules_path)
            enabled_rules = engine.get_enabled_rules()
        finally:
            Path(rules_path).unlink()

        self.assertEqual([rule["rule_id"] for rule in enabled_rules], ["valid_buy"])
        self.assertIn("__validation__", engine.rules_config)
        self.assertFalse(engine.rules_config["__validation__"]["valid"])


if __name__ == "__main__":
    unittest.main()
