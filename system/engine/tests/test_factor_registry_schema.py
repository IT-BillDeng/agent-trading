from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.factors.registry import FactorRegistryValidationError, load_factor_registry
from engine.factors.schema import validate_factor_registry


def _valid_registry_payload() -> dict:
    registry_path = Path(__file__).resolve().parents[3] / "factors" / "registry.json"
    return json.loads(registry_path.read_text())


class FactorRegistrySchemaTests(unittest.TestCase):
    def test_current_registry_file_loads_successfully(self):
        registry_path = Path(__file__).resolve().parents[3] / "factors" / "registry.json"

        registry = load_factor_registry(registry_path)

        self.assertEqual(registry.schema_version, 1)
        self.assertEqual(registry.defaults["mode"], "shadow")
        self.assertFalse(registry.defaults["allow_actionable_consumption"])
        self.assertTrue(registry.config_hash)
        self.assertIn("rsi_14_30m", registry.factors)
        self.assertEqual(registry.factors["rsi_14_30m"].factor_id, "rsi_14_30m")
        self.assertTrue(registry.factors["rsi_14_30m"].config_hash)

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
