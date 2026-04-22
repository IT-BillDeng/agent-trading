from __future__ import annotations

import types
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.factors.attribution import build_factor_attribution, summarize_factor_observations


class FactorAttributionTests(unittest.TestCase):
    def test_build_factor_attribution_uses_future_returns_without_lookahead(self):
        bars = [
            {"timestamp": "2026-01-05T09:30:00", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000},
            {"timestamp": "2026-01-05T10:00:00", "open": 110.0, "high": 111.0, "low": 109.0, "close": 110.0, "volume": 1000},
            {"timestamp": "2026-01-05T10:30:00", "open": 99.0, "high": 100.0, "low": 98.0, "close": 99.0, "volume": 1000},
            {"timestamp": "2026-01-05T11:00:00", "open": 118.8, "high": 119.0, "low": 118.0, "close": 118.8, "volume": 1000},
        ]
        factor_values = [1.0, -1.0, 2.0, 0.0]

        factor_definition = types.SimpleNamespace(
            factor_id="test_factor",
            type="technical",
            session="regular",
            timeframe="30min",
            output="numeric",
            usage=("shadow",),
            actionable=False,
            config_hash="factor-hash-1",
        )
        registry = types.SimpleNamespace(
            config_hash="registry-hash-1",
            factors={"test_factor": factor_definition},
        )

        class StubFactorEngine:
            mode = "shadow"

            def evaluate_symbol(self, symbol, bars, *, evaluation_time=None, market="US", asset_snapshot=None, provider=None):
                index = len(bars) - 1
                return {
                    "symbol": symbol,
                    "mode": self.mode,
                    "registry_hash": self.registry.config_hash,
                    "factors": {
                        "test_factor": {
                            "value": factor_values[index],
                            "ready": True,
                            "reason": "ok",
                            "source": "stub",
                            "config_hash": factor_definition.config_hash,
                        }
                    },
                }

        StubFactorEngine.registry = registry

        attribution = build_factor_attribution(
            {"AAPL": bars},
            factor_engine=StubFactorEngine(),
            timeframe="30min",
        )

        factor_summary = attribution["factors"]["test_factor"]
        self.assertAlmostEqual(factor_summary["ic_1bar"], 1.0, places=9)
        self.assertIsNone(factor_summary["ic_1bar_reason"])
        self.assertEqual(factor_summary["ic_1bar_sample_count"], 3)

    def test_insufficient_samples_return_null_ic_with_reason(self):
        summary = summarize_factor_observations(
            [
                {"value": 1.0, "ready": True, "reason": "ok", "future_returns": {1: 0.1}},
                {"value": 2.0, "ready": True, "reason": "ok", "future_returns": {1: 0.2}},
            ],
            horizons=(1,),
            min_ic_samples=3,
        )

        self.assertIsNone(summary["ic_1bar"])
        self.assertEqual(summary["ic_1bar_reason"], "insufficient_samples")
        self.assertEqual(summary["ic_1bar_sample_count"], 2)

    def test_missing_factor_values_are_counted_in_missing_rate(self):
        summary = summarize_factor_observations(
            [
                {"value": 1.0, "ready": True, "reason": "ok", "future_returns": {1: 0.1}},
                {"value": None, "ready": False, "reason": "insufficient_bars", "future_returns": {1: 0.2}},
                {"value": 2.0, "ready": True, "reason": "ok", "future_returns": {1: 0.3}},
            ],
            horizons=(1,),
            min_ic_samples=2,
        )

        self.assertEqual(summary["sample_count"], 3)
        self.assertEqual(summary["valid_count"], 2)
        self.assertEqual(summary["missing_count"], 1)
        self.assertAlmostEqual(summary["missing_rate"], 1 / 3, places=9)
        self.assertEqual(summary["not_ready_reasons"], {"insufficient_bars": 1})


if __name__ == "__main__":
    unittest.main()
