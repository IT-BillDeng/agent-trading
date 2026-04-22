from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.factors.builtins import compute_builtin_factor
from engine.factors.registry import load_factor_registry
from engine.indicators import bollinger, rsi, volume_ratio
from engine.market_sessions import analyze_symbol_bars


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


def _app_config() -> dict:
    return {
        "strategy": {
            "market_data": {
                "include_extended_hours": True,
                "extended_hours_usage": "context_only",
                "regular_session_only_for_indicators": True,
                "require_completed_bar_for_actionable_signal": True,
            },
            "sessions": {
                "US": {
                    "regular_start": "09:30",
                    "regular_end": "16:00",
                    "entry_window_start": "10:00",
                    "entry_window_end": "15:15",
                    "timezone": "America/New_York",
                }
            },
        }
    }


class FactorBuiltinsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            json.dump(_registry_payload(), handle)
            cls._registry_path = Path(handle.name)
        cls.registry = load_factor_registry(cls._registry_path)

    @classmethod
    def tearDownClass(cls):
        cls._registry_path.unlink(missing_ok=True)

    def _analysis(self, bars: list[dict], *, evaluation_time: str) -> dict:
        return analyze_symbol_bars(
            bars,
            asset_snapshot={"timestamp": evaluation_time},
            market="US",
            timeframe="30min",
            app_config=_app_config(),
            provider="yfinance",
        )

    def test_rsi_matches_indicator_module_and_ignores_premarket_bars(self):
        regular_bars = _make_regular_day("2026-04-17", start_close=100.0) + _make_regular_day(
            "2026-04-18",
            start_close=110.0,
        )
        premarket_bars = [
            _make_bar("2026-04-20 08:00:00", 250.0, volume=5000),
            _make_bar("2026-04-20 08:30:00", 251.0, volume=6000),
            _make_bar("2026-04-20 09:00:00", 252.0, volume=7000),
        ]
        analysis = self._analysis(regular_bars + premarket_bars, evaluation_time="2026-04-20T13:15:00+00:00")

        result = compute_builtin_factor(self.registry.factors["rsi_14_30m"], analysis=analysis)

        expected = rsi([float(bar["close"]) for bar in regular_bars], 14)
        self.assertTrue(result.ready)
        self.assertEqual(result.reason, "ok")
        self.assertEqual(result.source, "regular_session_completed_bars")
        self.assertAlmostEqual(float(result.value), float(expected), places=8)

    def test_bollinger_zscore_matches_formula(self):
        regular_bars = _make_regular_day("2026-04-17", start_close=100.0) + _make_regular_day(
            "2026-04-18",
            start_close=111.0,
        )
        analysis = self._analysis(regular_bars, evaluation_time="2026-04-20T14:30:00+00:00")

        result = compute_builtin_factor(self.registry.factors["bollinger_zscore_20_2_30m"], analysis=analysis)

        closes = [float(bar["close"]) for bar in regular_bars]
        upper, middle, _lower = bollinger(closes, 20, 2.0)
        expected = (closes[-1] - middle) / ((upper - middle) / 2.0)
        self.assertTrue(result.ready)
        self.assertAlmostEqual(float(result.value), float(expected), places=8)

    def test_volume_ratio_matches_indicator_logic(self):
        regular_bars = _make_regular_day("2026-04-17", start_close=100.0, volume_base=1000) + _make_regular_day(
            "2026-04-18",
            start_close=109.0,
            volume_base=1500,
        )
        analysis = self._analysis(regular_bars, evaluation_time="2026-04-20T14:30:00+00:00")

        result = compute_builtin_factor(self.registry.factors["volume_ratio_20_30m"], analysis=analysis)

        expected = volume_ratio([float(bar["volume"]) for bar in regular_bars], 20)
        self.assertTrue(result.ready)
        self.assertAlmostEqual(float(result.value), float(expected), places=8)

    def test_premarket_gap_pct_uses_context_only_and_stays_non_actionable(self):
        regular_bars = _make_regular_day("2026-04-17", start_close=100.0) + _make_regular_day(
            "2026-04-18",
            start_close=108.0,
        )
        previous_close = float(regular_bars[-1]["close"])
        premarket_bars = [
            _make_bar("2026-04-20 08:00:00", previous_close * 1.02, volume=5000),
            _make_bar("2026-04-20 08:30:00", previous_close * 1.03, volume=6000),
            _make_bar("2026-04-20 09:00:00", previous_close * 1.04, volume=7000),
        ]
        analysis = self._analysis(regular_bars + premarket_bars, evaluation_time="2026-04-20T13:15:00+00:00")

        result = compute_builtin_factor(self.registry.factors["premarket_gap_pct"], analysis=analysis)

        self.assertTrue(result.ready)
        self.assertFalse(result.actionable)
        self.assertEqual(result.source, "extended_hours_context")
        self.assertAlmostEqual(float(result.value), 0.04, places=8)


if __name__ == "__main__":
    unittest.main()
