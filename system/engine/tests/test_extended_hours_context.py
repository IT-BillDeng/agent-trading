import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.config import AppConfig
from engine.runtime import build_execution_summary, build_strategy_summary


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


def _make_regular_bars() -> list[dict]:
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
                "rule_id": "extended_context_buy",
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
                        "params": {"period": 3},
                        "compare": {"field": "close", "operator": "below"},
                    },
                    "order_type": "LMT",
                },
                "exit": {"action": "EXIT", "conditions": {"type": "time"}},
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


class ExtendedHoursContextTests(unittest.TestCase):
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

    def test_premarket_bars_are_context_only_and_do_not_change_indicator_value(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.json"
            rules_path.write_text(json.dumps(_rule_doc(), ensure_ascii=False))
            app = self._app(tmpdir, rules_path)

            regular_only = _make_regular_bars()
            with_extended = regular_only + [
                _make_bar("2026-04-20 08:30:00", 200.0, volume=5000),
                _make_bar("2026-04-20 09:00:00", 201.0, volume=6000),
                _make_bar("2026-04-20 09:15:00", 202.0, volume=7000),
            ]

            summary_regular = build_strategy_summary(
                _make_cycle_raw("AAPL", regular_only, timestamp="2026-04-20T13:15:00+00:00"),
                app,
            )
            summary_extended = build_strategy_summary(
                _make_cycle_raw("AAPL", with_extended, timestamp="2026-04-20T13:15:00+00:00"),
                app,
            )

            signal_regular = summary_regular["strategy"]["signals"][0]
            signal_extended = summary_extended["strategy"]["signals"][0]
            self.assertEqual(signal_regular["action"], signal_extended["action"])
            self.assertEqual(
                signal_regular["diagnostics"]["entry"]["value"],
                signal_extended["diagnostics"]["entry"]["value"],
            )
            health = summary_extended["data_health"]["AAPL"]
            self.assertGreater(health["extended_bars_count"], 0)
            self.assertEqual(health["extended_context"]["premarket_bars_count"], 3)
            self.assertTrue(health["extended_context"]["has_extended_data"])

    def test_afterhours_bars_do_not_create_actionable_buy_and_are_kept_as_context(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.json"
            rules_path.write_text(json.dumps(_rule_doc(), ensure_ascii=False))
            app = self._app(tmpdir, rules_path)
            bars = _make_regular_bars() + [
                _make_bar("2026-04-20 16:30:00", 123.0, volume=9000),
                _make_bar("2026-04-20 17:00:00", 124.0, volume=10000),
            ]
            raw = _make_cycle_raw("AAPL", bars, timestamp="2026-04-20T21:00:00+00:00")

            summary = build_execution_summary(raw, app)
            health = summary["data_health"]["AAPL"]

            self.assertEqual(summary["execution_preview"]["count"], 0)
            self.assertEqual(summary["order_intents"]["count"], 0)
            self.assertIn("entry_window_closed", summary["risk"]["decisions"][0]["reasons"])
            self.assertTrue(health["extended_context"]["has_extended_data"])
            self.assertEqual(health["extended_context"]["afterhours_bars_count"], 2)
            self.assertIsNotNone(health["extended_context"]["afterhours_move_pct"])


if __name__ == "__main__":
    unittest.main()
