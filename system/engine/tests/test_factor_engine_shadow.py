from __future__ import annotations

import json
import tempfile
import copy
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.factors.engine import FactorEngine
from engine.factors.registry import load_factor_registry


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


def _make_bar(ts: str, close: float, *, volume: int = 1000) -> dict:
    return {
        "time": ts,
        "open": close - 0.4,
        "high": close + 0.8,
        "low": close - 0.6,
        "close": close,
        "volume": volume,
    }


def _make_regular_day(date: str, *, start_close: float, volume_base: int = 1000) -> list[dict]:
    bars: list[dict] = []
    hour = 9
    minute = 30
    close = start_close
    for index in range(13):
        bars.append(
            _make_bar(
                f"{date} {hour:02d}:{minute:02d}:00",
                close,
                volume=volume_base + index * 50,
            )
        )
        close += 0.7
        minute += 30
        if minute >= 60:
            hour += 1
            minute -= 60
    return bars


def _make_afterhours_session(date: str, *, start_close: float, volume_base: int = 3000) -> list[dict]:
    bars: list[dict] = []
    hour = 16
    minute = 0
    close = start_close
    for index in range(3):
        bars.append(
            _make_bar(
                f"{date} {hour:02d}:{minute:02d}:00",
                close,
                volume=volume_base + index * 250,
            )
        )
        close += 0.5
        minute += 30
        if minute >= 60:
            hour += 1
            minute -= 60
    return bars


def _make_premarket_session(date: str, *, start_close: float, volume_base: int = 5000) -> list[dict]:
    bars: list[dict] = []
    hour = 8
    minute = 0
    close = start_close
    for index in range(3):
        bars.append(
            _make_bar(
                f"{date} {hour:02d}:{minute:02d}:00",
                close,
                volume=volume_base + index * 500,
            )
        )
        close += 0.5
        minute += 30
        if minute >= 60:
            hour += 1
            minute -= 60
    return bars


class FactorEngineShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            json.dump(_registry_payload(), handle)
            cls._registry_path = Path(handle.name)
        cls.registry = load_factor_registry(cls._registry_path)
        cls.engine = FactorEngine(cls.registry)

    @classmethod
    def tearDownClass(cls):
        cls._registry_path.unlink(missing_ok=True)

    def test_shadow_engine_returns_expected_envelope_and_metadata(self):
        bars = _make_regular_day("2026-04-17", start_close=100.0) + _make_regular_day(
            "2026-04-18",
            start_close=109.0,
        )
        previous_close = float(bars[-1]["close"])
        bars = bars + _make_afterhours_session("2026-04-18", start_close=previous_close * 1.02)
        bars = bars + _make_premarket_session("2026-04-20", start_close=previous_close * 1.04)
        result = self.engine.evaluate_symbol(
            "AAPL",
            bars,
            evaluation_time="2026-04-20T13:15:00+00:00",
        )

        self.assertEqual(result["symbol"], "AAPL")
        self.assertEqual(result["mode"], "shadow")
        self.assertEqual(result["registry_hash"], self.registry.config_hash)
        self.assertTrue(result["timestamp"])
        self.assertIn("rsi_14_30m", result["factors"])
        self.assertIn("afterhours_move_pct", result["factors"])
        self.assertIn("overnight_return_pct", result["factors"])
        self.assertIn("atr_pct_14_30m", result["factors"])
        self.assertIn("return_5_30m", result["factors"])
        rsi_factor = result["factors"]["rsi_14_30m"]
        self.assertIn("ready", rsi_factor)
        self.assertIn("reason", rsi_factor)
        self.assertIn("source", rsi_factor)
        self.assertIn("config_hash", rsi_factor)
        self.assertEqual(rsi_factor["config_hash"], self.registry.factors["rsi_14_30m"].config_hash)
        self.assertTrue(result["factors"]["afterhours_move_pct"]["ready"])
        self.assertTrue(result["factors"]["overnight_return_pct"]["ready"])
        for factor_id, payload in result["factors"].items():
            self.assertNotEqual(
                payload["reason"],
                "implementation_not_available",
                msg=f"{factor_id} unexpectedly missing builtin handler",
            )

    def test_engine_does_not_mutate_input_bars(self):
        bars = _make_regular_day("2026-04-17", start_close=100.0) + _make_regular_day(
            "2026-04-18",
            start_close=109.0,
        )
        original = copy.deepcopy(bars)

        self.engine.evaluate_symbol(
            "AAPL",
            bars,
            evaluation_time="2026-04-20T14:30:00+00:00",
        )

        self.assertEqual(bars, original)

    def test_missing_required_bars_returns_not_ready(self):
        bars = _make_regular_day("2026-04-18", start_close=100.0)[:5]

        result = self.engine.evaluate_symbol(
            "AAPL",
            bars,
            evaluation_time="2026-04-20T14:30:00+00:00",
        )

        self.assertFalse(result["factors"]["rsi_14_30m"]["ready"])
        self.assertEqual(result["factors"]["rsi_14_30m"]["reason"], "insufficient_bars")
        self.assertFalse(result["factors"]["bollinger_zscore_20_2_30m"]["ready"])
        self.assertFalse(result["factors"]["volume_ratio_20_30m"]["ready"])
        self.assertFalse(result["factors"]["atr_pct_14_30m"]["ready"])
        self.assertFalse(result["factors"]["return_5_30m"]["ready"])

    def test_incomplete_regular_bar_is_excluded_from_technical_factor_input(self):
        base_bars = _make_regular_day("2026-04-17", start_close=100.0) + _make_regular_day(
            "2026-04-18",
            start_close=109.0,
        )
        with_incomplete_opening_bar = base_bars + [_make_bar("2026-04-20 09:30:00", 400.0, volume=9000)]

        base_result = self.engine.evaluate_symbol(
            "AAPL",
            base_bars,
            evaluation_time="2026-04-20T13:45:00+00:00",
        )
        with_incomplete_result = self.engine.evaluate_symbol(
            "AAPL",
            with_incomplete_opening_bar,
            evaluation_time="2026-04-20T13:45:00+00:00",
        )

        self.assertEqual(
            base_result["factors"]["rsi_14_30m"]["value"],
            with_incomplete_result["factors"]["rsi_14_30m"]["value"],
        )
        self.assertEqual(
            base_result["factors"]["bollinger_zscore_20_2_30m"]["value"],
            with_incomplete_result["factors"]["bollinger_zscore_20_2_30m"]["value"],
        )
        self.assertEqual(
            base_result["factors"]["volume_ratio_20_30m"]["value"],
            with_incomplete_result["factors"]["volume_ratio_20_30m"]["value"],
        )
        self.assertEqual(
            base_result["factors"]["atr_pct_14_30m"]["value"],
            with_incomplete_result["factors"]["atr_pct_14_30m"]["value"],
        )
        self.assertEqual(
            base_result["factors"]["return_5_30m"]["value"],
            with_incomplete_result["factors"]["return_5_30m"]["value"],
        )


if __name__ == "__main__":
    unittest.main()
