from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.factors.builtins import available_builtin_implementations
from engine.factors.catalog import BUILTIN_FACTOR_IMPLEMENTATIONS
from engine.factors.registry import FactorRegistryValidationError, load_factor_registry
from engine.factors.schema import SUPPORTED_IMPLEMENTATIONS, validate_factor_registry


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
            "premarket_gap_pct": {
                "type": "session",
                "implementation": "builtin:premarket_gap_pct",
                "inputs": ["extended_hours_bars", "previous_regular_close"],
                "params": {},
                "session": "premarket",
                "timeframe": "30min",
                "output": "numeric",
                "usage": ["shadow", "context_only", "risk_hint_candidate"],
                "actionable": False,
                "point_in_time": True,
                "required_bars": 1,
                "lookback_bars": 1,
                "horizon_bars": 1,
                "timezone": "America/New_York",
                "no_lookahead": True,
                "version": 1,
            },
            "afterhours_move_pct": {
                "type": "session",
                "implementation": "builtin:afterhours_move_pct",
                "inputs": ["extended_hours_bars", "latest_regular_close"],
                "params": {},
                "session": "afterhours",
                "timeframe": "30min",
                "output": "numeric",
                "usage": ["shadow", "context_only", "risk_hint_candidate"],
                "actionable": False,
                "point_in_time": True,
                "required_bars": 1,
                "lookback_bars": 1,
                "horizon_bars": 1,
                "timezone": "America/New_York",
                "no_lookahead": True,
                "version": 1,
            },
            "overnight_return_pct": {
                "type": "session",
                "implementation": "builtin:overnight_return_pct",
                "inputs": ["extended_hours_bars", "previous_regular_close", "current_regular_open"],
                "params": {},
                "session": "premarket",
                "timeframe": "30min",
                "output": "numeric",
                "usage": ["shadow", "context_only", "risk_hint_candidate"],
                "actionable": False,
                "point_in_time": True,
                "required_bars": 1,
                "lookback_bars": 1,
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


def _valid_registry_payload() -> dict:
    return _registry_payload()


class FactorRegistrySchemaTests(unittest.TestCase):
    def test_schema_supported_implementations_match_builtin_catalog(self):
        self.assertEqual(set(SUPPORTED_IMPLEMENTATIONS), set(BUILTIN_FACTOR_IMPLEMENTATIONS))
        self.assertEqual(set(SUPPORTED_IMPLEMENTATIONS), set(available_builtin_implementations()))

    def test_current_registry_file_loads_successfully(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            json.dump(_valid_registry_payload(), handle)
            registry_path = Path(handle.name)

        try:
            registry = load_factor_registry(registry_path)
        finally:
            registry_path.unlink()

        self.assertEqual(registry.schema_version, 1)
        self.assertEqual(registry.defaults["mode"], "shadow")
        self.assertFalse(registry.defaults["allow_actionable_consumption"])
        self.assertTrue(registry.config_hash)
        self.assertIn("rsi_14_30m", registry.factors)
        self.assertEqual(registry.factors["rsi_14_30m"].factor_id, "rsi_14_30m")
        self.assertTrue(registry.factors["rsi_14_30m"].config_hash)
        self.assertTrue(
            set(factor.implementation for factor in registry.factors.values()).issubset(
                set(available_builtin_implementations())
            )
        )

    def test_missing_required_field_is_rejected(self):
        payload = _valid_registry_payload()
        del payload["factors"]["rsi_14_30m"]["output"]

        result = validate_factor_registry(payload)

        self.assertFalse(result["valid"])
        self.assertTrue(any("missing required field 'output'" in error for error in result["errors"]))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            registry_path = Path(handle.name)

        try:
            with self.assertRaises(FactorRegistryValidationError):
                load_factor_registry(registry_path)
        finally:
            registry_path.unlink()

    def test_unknown_implementation_is_rejected(self):
        payload = _valid_registry_payload()
        payload["factors"]["rsi_14_30m"]["implementation"] = "builtin:not_real"

        result = validate_factor_registry(payload)

        self.assertFalse(result["valid"])
        self.assertTrue(any("unsupported implementation" in error for error in result["errors"]))

    def test_extended_hours_actionable_factor_is_rejected(self):
        payload = _valid_registry_payload()
        payload["defaults"]["allow_actionable_consumption"] = True
        payload["factors"]["premarket_gap_pct"]["actionable"] = True
        payload["factors"]["premarket_gap_pct"]["usage"] = ["shadow", "context_only", "actionable"]

        result = validate_factor_registry(payload)

        self.assertFalse(result["valid"])
        self.assertTrue(any("extended-hours factor cannot be actionable" in error for error in result["errors"]))
        self.assertTrue(any("extended-hours factor usage cannot include 'actionable'" in error for error in result["errors"]))

    def test_actionable_factor_is_rejected_when_defaults_forbid_it(self):
        payload = _valid_registry_payload()
        payload["factors"]["rsi_14_30m"]["actionable"] = True
        payload["factors"]["rsi_14_30m"]["usage"] = ["shadow", "actionable"]

        result = validate_factor_registry(payload)

        self.assertFalse(result["valid"])
        self.assertTrue(
            any("defaults.allow_actionable_consumption=false" in error for error in result["errors"])
        )

    def test_invalid_indicator_params_are_rejected(self):
        cases = [
            ("rsi_14_30m", {"period": 0}, "params.period"),
            ("bollinger_zscore_20_2_30m", {"period": 20, "std_dev": 0}, "params.std_dev"),
            ("volume_ratio_20_30m", {"period": 0}, "params.period"),
            ("atr_pct_14_30m", {"period": 0}, "params.period"),
            ("return_5_30m", {"period": 0}, "params.period"),
        ]

        for factor_id, params, expected_fragment in cases:
            with self.subTest(factor_id=factor_id):
                payload = _valid_registry_payload()
                payload["factors"][factor_id]["params"] = copy.deepcopy(params)

                result = validate_factor_registry(payload)

                self.assertFalse(result["valid"])
                self.assertTrue(any(expected_fragment in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
