from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.config import AppConfig
from engine.runtime import build_execution_summary


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


def _ok_response(data):
    return {"http_status": 200, "body": {"code": 0, "data": data}}


def _make_bar(ts: str, close: float, *, volume: int = 1000) -> dict:
    return {
        "time": ts,
        "open": close - 0.2,
        "high": close + 0.5,
        "low": close - 0.5,
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
                volume=volume_base + index * 100,
            )
        )
        close += 0.6
        minute += 30
        if minute >= 60:
            hour += 1
            minute -= 60
    return bars


def _make_cycle_raw(symbol: str, bars_items, *, timestamp: str, trading_day: str = "2026-04-20"):
    return {
        "accounts": _ok_response({"items": []}),
        "assets": _ok_response(
            {
                "items": [
                    {
                        "account": "paper",
                        "netLiquidation": 100000.0,
                        "cashValue": 100000.0,
                        "buyingPower": 100000.0,
                        "grossPositionValue": 0.0,
                        "unrealizedPnL": 0.0,
                        "realizedPnL": 0.0,
                        "timestamp": timestamp,
                        "trading_day": trading_day,
                    }
                ]
            }
        ),
        "positions": _ok_response({"items": []}),
        "active_orders": _ok_response({"items": []}),
        "quote_permissions": _ok_response([]),
        "market_state": {
            "US": _ok_response([{"status": "TRADING", "marketStatus": "open"}]),
        },
        "delay_quotes": {
            "US": _ok_response({"items": [{"symbol": symbol, "latestPrice": 101.0}]}),
        },
        "briefs": {
            "US": _ok_response({"items": [{"symbol": symbol, "latestPrice": 101.0}]}),
        },
        "bars": {
            "US": _ok_response([{"symbol": symbol, "items": bars_items}]),
        },
        "contracts": {
            "US": {
                symbol: _ok_response(
                    {"symbol": symbol, "market": "US", "currency": "USD", "secType": "STK", "tickSizes": []}
                )
            }
        },
        "_provider": "yfinance",
    }


class RuntimeFactorShadowTests(unittest.TestCase):
    maxDiff = None

    def _app(
        self,
        tmpdir: str,
        *,
        registry_path: str,
        enabled: bool,
        write_artifacts: bool,
    ) -> AppConfig:
        return AppConfig(
            raw={
                "mode": "paper",
                "markets": ["US"],
                "broker": {"platform": "tiger"},
                "execution": {"submit_mode": "guarded", "live_submit": False},
                "notify": {"telegram_preview_only": True, "telegram_send_enabled": False},
                "risk": {
                    "daily_loss_limit_pct": 5,
                    "max_order_notional_usd": 10000,
                    "max_total_exposure_usd": 1000000,
                    "max_trades_per_day": 10,
                    "max_trades_per_symbol_per_day": 3,
                    "symbol_cooldown_minutes_after_order": 30,
                    "symbol_cooldown_minutes_after_loss": 120,
                    "fx_rates_to_usd": {"USD": 1.0},
                },
                "system": {"state_dir": str(Path(tmpdir) / "runtime" / "state")},
                "strategy": {
                    "timeframe": "30min",
                    "use_rule_engine": False,
                    "signal": {
                        "fast_sma": 5,
                        "slow_sma": 10,
                        "trend_sma": 20,
                        "min_momentum_3bars": 0.003,
                        "max_bar_range_pct": 0.04,
                    },
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
                    "symbols": [{"symbol": "AAPL", "market": "US", "name": "Apple"}],
                },
                "factor_engine": {
                    "enabled": enabled,
                    "mode": "shadow",
                    "registry_path": registry_path,
                    "write_artifacts": write_artifacts,
                    "allow_actionable_consumption": False,
                    "regular_session_only_for_indicators": True,
                },
            }
        )

    def _bars(self) -> list[dict]:
        previous_regular = _make_regular_day("2026-04-17", start_close=100.0) + _make_regular_day(
            "2026-04-18",
            start_close=108.0,
        )
        previous_close = float(previous_regular[-1]["close"])
        afterhours = [
            _make_bar("2026-04-18 16:00:00", previous_close * 1.01, volume=3500),
            _make_bar("2026-04-18 16:30:00", previous_close * 1.02, volume=3750),
            _make_bar("2026-04-18 17:00:00", previous_close * 1.03, volume=4000),
        ]
        premarket = [
            _make_bar("2026-04-20 08:00:00", previous_close * 1.03, volume=5000),
            _make_bar("2026-04-20 08:30:00", previous_close * 1.04, volume=6000),
            _make_bar("2026-04-20 09:00:00", previous_close * 1.05, volume=7000),
        ]
        return previous_regular + afterhours + premarket

    def test_runtime_shadow_writes_factor_summary_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            registry_path.write_text(json.dumps(_registry_payload(), ensure_ascii=False))
            artifacts_dir = root / "artifacts"
            raw = _make_cycle_raw("AAPL", self._bars(), timestamp="2026-04-20T13:15:00+00:00")
            app = self._app(tmpdir, registry_path=str(registry_path), enabled=True, write_artifacts=True)

            with patch.dict(os.environ, {"ENGINE_ARTIFACTS_DIR": str(artifacts_dir)}, clear=False), \
                patch("engine.runtime._cycle_id", return_value="20260420T143000Z"):
                summary = build_execution_summary(raw, app)

            factor_engine = summary["factor_engine"]
            self.assertTrue(factor_engine["enabled"])
            self.assertEqual(factor_engine["mode"], "shadow")
            self.assertFalse(factor_engine["allow_actionable_consumption"])
            self.assertTrue(factor_engine["registry_hash"])
            self.assertEqual(factor_engine["registry_hash_source"], "runtime_registry")
            self.assertTrue(factor_engine["schema_valid"])
            self.assertEqual(factor_engine["schema_errors"], [])
            self.assertEqual(factor_engine["implementation_summary"]["missing_count"], 0)
            self.assertEqual(factor_engine["symbols"]["AAPL"]["factors_total"], 8)
            self.assertEqual(factor_engine["symbols"]["AAPL"]["factors_ready"], 8)

            latest = artifacts_dir / "factors" / "latest.json"
            history = artifacts_dir / "factors" / "history" / "2026-04-20.jsonl"
            self.assertTrue(latest.exists())
            self.assertTrue(history.exists())
            latest_payload = json.loads(latest.read_text())
            self.assertEqual(latest_payload["mode"], "shadow")
            self.assertEqual(latest_payload["registry_hash_source"], "runtime_registry")
            self.assertTrue(latest_payload["schema_valid"])
            self.assertEqual(latest_payload["implementation_summary"]["missing_count"], 0)
            self.assertIn("AAPL", latest_payload["symbols"])
            self.assertTrue(
                latest_payload["symbols"]["AAPL"]["factors"]["rsi_14_30m"]["implementation_available"]
            )

    def test_shadow_factor_failure_does_not_change_trading_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            valid_registry = root / "valid_registry.json"
            valid_registry.write_text(json.dumps(_registry_payload(), ensure_ascii=False))
            raw = _make_cycle_raw("AAPL", self._bars(), timestamp="2026-04-20T13:15:00+00:00")
            baseline_app = self._app(
                str(root / "baseline"),
                registry_path=str(valid_registry),
                enabled=False,
                write_artifacts=False,
            )
            failure_app = self._app(
                str(root / "failure"),
                registry_path=str(root / "missing_registry.json"),
                enabled=True,
                write_artifacts=True,
            )

            with patch("engine.runtime._cycle_id", return_value="20260420T143000Z"):
                baseline = build_execution_summary(raw, baseline_app)
            with patch("engine.runtime._cycle_id", return_value="20260420T143000Z"):
                failure = build_execution_summary(raw, failure_app)

            self.assertEqual(baseline["strategy"]["signals"], failure["strategy"]["signals"])
            self.assertEqual(baseline["risk"]["decisions"], failure["risk"]["decisions"])
            self.assertEqual(baseline["execution_preview"], failure["execution_preview"])
            baseline_intents = self._normalize_order_intents(baseline["order_intents"])
            failure_intents = self._normalize_order_intents(failure["order_intents"])
            self.assertEqual(baseline_intents, failure_intents)
            self.assertIn("factor_engine", failure)
            self.assertIn("error", failure["factor_engine"])

    def _normalize_order_intents(self, payload: dict) -> dict:
        normalized = dict(payload)
        normalized["items"] = [
            {
                key: value
                for key, value in item.items()
                if key != "created_at"
            }
            for item in payload.get("items", [])
        ]
        return normalized


if __name__ == "__main__":
    unittest.main()
