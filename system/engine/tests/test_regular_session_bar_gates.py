import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.config import AppConfig
from engine.runtime import build_execution_summary, build_strategy_summary
from engine.state import TradeLimitStore


def _ok_response(data):
    return {"http_status": 200, "body": {"code": 0, "data": data}}


def _make_bar(ts: str, close: float, volume: int = 1000) -> dict:
    return {
        "time": ts,
        "open": close - 0.2,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": volume,
    }


def _make_prev_day_regular_bars() -> list[dict]:
    bars: list[dict] = []
    hour = 10
    minute = 0
    close = 100.0
    for _ in range(10):
        bars.append(_make_bar(f"2026-04-17 {hour:02d}:{minute:02d}:00", close))
        close += 1.0
        minute += 30
        if minute >= 60:
            minute = 0
            hour += 1
    return bars


def _rule_doc():
    return {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "session_gate_buy",
                "enabled": True,
                "priority": 1,
                "timeframe": "30min",
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "action": "BUY",
                    "conditions": {
                        "type": "indicator",
                        "indicator": "sma",
                        "params": {"period": 2},
                        "compare": {"field": "close", "operator": "below"},
                    },
                    "order_type": "LMT",
                },
                "exit": {
                    "action": "EXIT",
                    "conditions": {"type": "time"},
                },
            }
        ],
    }


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


class RegularSessionBarGateTests(unittest.TestCase):
    def _app(self, tmpdir: str, rules_path: Path) -> AppConfig:
        return AppConfig(
            raw={
                "mode": "paper",
                "markets": ["US"],
                "broker": {"platform": "tiger"},
                "execution": {"submit_mode": "guarded", "live_submit": False},
                "notify": {"telegram_preview_only": True},
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
                    "use_rule_engine": True,
                    "rules_path": str(rules_path),
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
            }
        )

    def test_0930_previous_day_latest_bar_can_be_diagnostic_but_not_actionable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.json"
            rules_path.write_text(json.dumps(_rule_doc(), ensure_ascii=False))
            app = self._app(tmpdir, rules_path)
            raw = _make_cycle_raw(
                "AAPL",
                _make_prev_day_regular_bars(),
                timestamp="2026-04-20T13:30:00+00:00",
            )

            strategy = build_strategy_summary(raw, app)
            self.assertEqual(strategy["strategy"]["signals"][0]["action"], "BUY")
            self.assertFalse(strategy["strategy"]["signals"][0]["actionable"])

            summary = build_execution_summary(raw, app)
            self.assertEqual(summary["execution_preview"]["count"], 0)
            self.assertEqual(summary["order_intents"]["count"], 0)
            self.assertIn(
                summary["risk"]["decisions"][0]["reasons"][0],
                {"first_30m_bar_not_closed", "latest_regular_bar_stale"},
            )
            snapshot = TradeLimitStore(Path(tmpdir) / "runtime" / "state").snapshot("2026-04-20")
            self.assertEqual(snapshot["total_trades"], 0)

    def test_0945_partial_first_bar_does_not_count_as_completed_regular_bar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.json"
            rules_path.write_text(json.dumps(_rule_doc(), ensure_ascii=False))
            app = self._app(tmpdir, rules_path)
            raw = _make_cycle_raw(
                "AAPL",
                _make_prev_day_regular_bars() + [_make_bar("2026-04-20 09:30:00", 120.0)],
                timestamp="2026-04-20T13:45:00+00:00",
            )

            strategy = build_strategy_summary(raw, app)
            health = strategy["data_health"]["AAPL"]
            self.assertFalse(health["latest_regular_bar_is_complete"])
            self.assertFalse(health["actionable_ready"])
            self.assertEqual(health["actionable_block_reason"], "first_30m_bar_not_closed")

            summary = build_execution_summary(raw, app)
            self.assertEqual(summary["execution_preview"]["count"], 0)
            self.assertEqual(summary["order_intents"]["count"], 0)
            snapshot = TradeLimitStore(Path(tmpdir) / "runtime" / "state").snapshot("2026-04-20")
            self.assertEqual(snapshot["total_trades"], 0)

    def test_1001_completed_first_bar_allows_buy_to_reach_normal_risk_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.json"
            rules_path.write_text(json.dumps(_rule_doc(), ensure_ascii=False))
            app = self._app(tmpdir, rules_path)
            raw = _make_cycle_raw(
                "AAPL",
                _make_prev_day_regular_bars()
                + [
                    _make_bar("2026-04-20 09:30:00", 120.0),
                    _make_bar("2026-04-20 10:00:00", 121.0),
                ],
                timestamp="2026-04-20T14:01:00+00:00",
            )

            strategy = build_strategy_summary(raw, app)
            health = strategy["data_health"]["AAPL"]
            self.assertTrue(health["first_regular_30m_bar_completed"])
            self.assertTrue(health["actionable_ready"])

            summary = build_execution_summary(raw, app)
            self.assertEqual(summary["execution_preview"]["count"], 1)
            self.assertEqual(summary["order_intents"]["count"], 1)
            self.assertTrue(summary["risk"]["decisions"][0]["allowed"])


if __name__ == "__main__":
    unittest.main()
