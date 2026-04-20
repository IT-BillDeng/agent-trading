import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.config import AppConfig
from engine.runtime import build_strategy_summary


def _ok_response(data):
    return {"http_status": 200, "body": {"code": 0, "data": data}}


def _error_response(message="provider failure", code=1):
    return {"http_status": 500, "body": {"code": code, "message": message, "data": []}}


def _make_bar(index: int) -> dict:
    close = 100 + index
    return {
        "time": f"2026-04-18 09:{index:02d}:00",
        "open": close - 0.2,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
        "volume": 1000000 + index * 1000,
    }


def _make_cycle_raw(symbol: str, *, bars_items, market_status="open", provider="yfinance"):
    return {
        "accounts": _ok_response({"items": []}),
        "assets": _ok_response({"items": []}),
        "positions": _ok_response({"items": []}),
        "active_orders": _ok_response({"items": []}),
        "quote_permissions": _ok_response([]),
        "market_state": {
            "US": _ok_response([{"status": market_status.upper(), "marketStatus": market_status}]),
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
                    {
                        "symbol": symbol,
                        "name": symbol,
                        "market": "US",
                        "secType": "STK",
                    }
                )
            }
        },
        "_provider": provider,
    }


class DataHealthReportTests(unittest.TestCase):
    def _app_config(self, tmpdir: str, *, symbols=None, use_rule_engine=False, rules_path=None):
        return AppConfig(
            raw={
                "mode": "paper",
                "markets": ["US"],
                "system": {
                    "state_dir": str(Path(tmpdir) / "runtime" / "state"),
                },
                "strategy": {
                    "timeframe": "30min",
                    "use_rule_engine": use_rule_engine,
                    "rules_path": str(rules_path) if rules_path else None,
                    "signal": {
                        "lookback_bars": 30,
                        "fast_sma": 5,
                        "slow_sma": 10,
                        "trend_sma": 20,
                    },
                    "symbols": symbols or [{"symbol": "AAPL", "market": "US", "name": "Apple"}],
                },
            }
        )

    def test_data_health_reports_market_closed_when_bars_are_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app = self._app_config(tmpdir)
            summary = build_strategy_summary(
                _make_cycle_raw("AAPL", bars_items=[], market_status="closed"),
                app,
            )

            health = summary["data_health"]["AAPL"]
            self.assertEqual(health["reason"], "market_closed")
            self.assertFalse(health["strategy_ready"])
            self.assertEqual(health["raw_bars_count"], 0)
            self.assertEqual(health["normalized_bars_count"], 0)
            self.assertEqual(health["contract_status"], "ok")

    def test_data_health_reports_insufficient_bars_with_required_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_path = Path(tmpdir) / "rules.json"
            rules_path.write_text(
                json.dumps(
                    {
                        "version": "1.0",
                        "rules": [
                            {
                                "rule_id": "slow_rsi_entry",
                                "enabled": True,
                                "priority": 1,
                                "timeframe": "30min",
                                "symbols": ["*"],
                                "markets": ["US"],
                                "entry": {
                                    "action": "BUY",
                                    "conditions": {
                                        "type": "indicator",
                                        "indicator": "rsi",
                                        "params": {"period": 20},
                                        "compare": {"operator": "cross_above", "value": 30},
                                    },
                                },
                                "exit": {"action": "EXIT", "conditions": {"type": "time"}},
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            )
            app = self._app_config(tmpdir, use_rule_engine=True, rules_path=rules_path)
            raw = _make_cycle_raw("AAPL", bars_items=[_make_bar(i) for i in range(12)], market_status="open")

            summary = build_strategy_summary(raw, app)

            health = summary["data_health"]["AAPL"]
            self.assertEqual(health["reason"], "insufficient_bars")
            self.assertFalse(health["strategy_ready"])
            self.assertEqual(health["required_bars"], 25)
            self.assertEqual(health["normalized_bars_count"], 12)
            self.assertEqual(health["latest_bar_time"], "2026-04-18 09:11:00")

    def test_data_health_reports_symbol_disabled_from_control_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "runtime" / "state"
            state_dir.mkdir(parents=True)
            (state_dir / "control_state.json").write_text(
                json.dumps(
                    {
                        "locked": False,
                        "global": {"enabled": True, "mode": "signal_only"},
                        "markets": {"US": True},
                        "symbols": {"AAPL": {"enabled": False}},
                        "risk": {},
                        "history": [],
                    },
                    ensure_ascii=False,
                )
            )
            app = self._app_config(tmpdir)
            raw = _make_cycle_raw("AAPL", bars_items=[_make_bar(i) for i in range(30)], market_status="open")

            summary = build_strategy_summary(raw, app)

            health = summary["data_health"]["AAPL"]
            self.assertEqual(health["reason"], "symbol_disabled")
            self.assertFalse(health["strategy_ready"])
            self.assertEqual(health["quote_status"], "delayed")


if __name__ == "__main__":
    unittest.main()
