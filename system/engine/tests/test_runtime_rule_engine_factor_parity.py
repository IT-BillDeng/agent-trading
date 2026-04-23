from __future__ import annotations

import json
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


def _rules_payload() -> dict:
    return {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "runtime_factorized_entry",
                "name": "Runtime Factorized Entry",
                "enabled": True,
                "priority": 1,
                "timeframe": "30min",
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "conditions": {
                        "operator": "AND",
                        "items": [
                            {
                                "type": "indicator",
                                "indicator": "rsi",
                                "params": {"period": 14},
                                "compare": {"operator": "above", "value": 60},
                            },
                            {
                                "type": "indicator",
                                "indicator": "momentum",
                                "params": {"period": 5},
                                "compare": {"operator": "above", "value": 0.01},
                            },
                            {
                                "type": "indicator",
                                "indicator": "volume_ratio",
                                "params": {"period": 20},
                                "compare": {"operator": "above", "value": 0.95},
                            },
                        ],
                    },
                    "action": "BUY",
                    "order_type": "LMT",
                    "stop_loss_pct": 0.03,
                    "take_profit_pct": 0.06,
                },
            }
        ],
    }


def _ok_response(data):
    return {"http_status": 200, "body": {"code": 0, "data": data}}


def _make_bar(ts: str, close: float, *, volume: int) -> dict:
    return {
        "time": ts,
        "open": close - 0.2,
        "high": close + 0.6,
        "low": close - 0.4,
        "close": close,
        "volume": volume,
    }


def _make_regular_day(date: str, *, start_close: float, volume_base: int) -> list[dict]:
    bars: list[dict] = []
    hour = 9
    minute = 30
    close = start_close
    for index in range(13):
        bars.append(
            _make_bar(
                f"{date} {hour:02d}:{minute:02d}:00",
                close,
                volume=volume_base + index * 150,
            )
        )
        close += 0.7
        minute += 30
        if minute >= 60:
            hour += 1
            minute -= 60
    return bars


def _make_cycle_raw(symbol: str, bars_items: list[dict], *, timestamp: str):
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
                        "trading_day": "2026-04-21",
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


class RuntimeRuleEngineFactorParityTests(unittest.TestCase):
    def _app(
        self,
        tmpdir: str,
        *,
        registry_path: str,
        rules_path: str,
        factor_enabled: bool,
        debug_factor_parity: bool,
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
                "system": {
                    "state_dir": str(Path(tmpdir) / "runtime" / "state"),
                    "debug_factor_parity": debug_factor_parity,
                },
                "strategy": {
                    "timeframe": "30min",
                    "use_rule_engine": True,
                    "rules_path": rules_path,
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
                    "enabled": factor_enabled,
                    "mode": "shadow",
                    "registry_path": registry_path,
                    "write_artifacts": False,
                    "allow_actionable_consumption": False,
                    "regular_session_only_for_indicators": True,
                },
            }
        )

    def _bars(self) -> list[dict]:
        return _make_regular_day("2026-04-20", start_close=100.0, volume_base=1000) + _make_regular_day(
            "2026-04-21",
            start_close=109.5,
            volume_base=3000,
        )

    def test_runtime_debug_includes_factor_parity_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            rules_path = root / "rules.json"
            registry_path.write_text(json.dumps(_registry_payload(), ensure_ascii=False))
            rules_path.write_text(json.dumps(_rules_payload(), ensure_ascii=False))
            raw = _make_cycle_raw("AAPL", self._bars(), timestamp="2026-04-21T21:00:00+00:00")
            app = self._app(
                tmpdir,
                registry_path=str(registry_path),
                rules_path=str(rules_path),
                factor_enabled=True,
                debug_factor_parity=True,
            )

            with patch("engine.runtime._cycle_id", return_value="20260421T193000Z"):
                summary = build_execution_summary(raw, app)

            parity = summary["factor_engine"]["parity"]["symbols"]["AAPL"]["entries"]
            self.assertAlmostEqual(parity["rsi_14_30m"]["diff"], 0.0, places=9)
            self.assertAlmostEqual(parity["bollinger_zscore_20_2_30m"]["diff"], 0.0, places=9)
            self.assertAlmostEqual(parity["volume_ratio_20_30m"]["diff"], 0.0, places=9)
            self.assertAlmostEqual(parity["atr_pct_14_30m"]["diff"], 0.0, places=9)
            self.assertAlmostEqual(parity["return_5_30m"]["diff"], 0.0, places=9)

    def test_runtime_factor_failure_remains_fail_open_for_rule_engine(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            registry_path = root / "registry.json"
            rules_path = root / "rules.json"
            registry_path.write_text(json.dumps(_registry_payload(), ensure_ascii=False))
            rules_path.write_text(json.dumps(_rules_payload(), ensure_ascii=False))
            raw = _make_cycle_raw("AAPL", self._bars(), timestamp="2026-04-21T21:00:00+00:00")
            baseline_app = self._app(
                str(root / "baseline"),
                registry_path=str(registry_path),
                rules_path=str(rules_path),
                factor_enabled=False,
                debug_factor_parity=False,
            )
            failure_app = self._app(
                str(root / "failure"),
                registry_path=str(root / "missing_registry.json"),
                rules_path=str(rules_path),
                factor_enabled=True,
                debug_factor_parity=False,
            )

            with patch("engine.runtime._cycle_id", return_value="20260421T193000Z"):
                baseline = build_execution_summary(raw, baseline_app)
            with patch("engine.runtime._cycle_id", return_value="20260421T193000Z"):
                failure = build_execution_summary(raw, failure_app)

            self.assertEqual(baseline["strategy"]["signals"], failure["strategy"]["signals"])
            self.assertEqual(baseline["risk"]["decisions"], failure["risk"]["decisions"])
            self.assertEqual(baseline["execution_preview"], failure["execution_preview"])
            self.assertEqual(baseline["order_intents"]["items"], failure["order_intents"]["items"])


if __name__ == "__main__":
    unittest.main()
