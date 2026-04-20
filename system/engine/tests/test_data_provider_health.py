import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from engine.config import AppConfig
from engine.runtime import build_strategy_summary, fetch_cycle_raw_with_provider


def _ok_response(data):
    return {"http_status": 200, "body": {"code": 0, "data": data}}


class _FakePrimaryProvider:
    name = "yfinance"

    def __init__(self, bars_by_symbol):
        self._bars_by_symbol = bars_by_symbol

    def get_market_state(self, market="US"):
        return _ok_response([{"status": "OPEN", "marketStatus": "open"}])

    def get_delay_quotes(self, symbols, market="US"):
        return _ok_response({"items": [{"symbol": s, "latestPrice": 101.0} for s in symbols]})

    def get_briefs(self, symbols, market="US"):
        return _ok_response({"items": [{"symbol": s, "latestPrice": 101.0} for s in symbols]})

    def get_bars(self, symbols, period="30min", limit=30):
        return _ok_response(
            [{"symbol": s, "items": list(self._bars_by_symbol.get(s, []))} for s in symbols]
        )

    def get_contract(self, symbol, market):
        return _ok_response({"symbol": symbol, "market": market, "secType": "STK"})


class _FakeBrokerClient:
    def __init__(self, bars_by_symbol):
        self._bars_by_symbol = bars_by_symbol

    @property
    def account(self):
        return "paper"

    def get_accounts(self):
        return _ok_response({"items": []})

    def get_assets(self):
        return _ok_response({"items": []})

    def get_positions(self):
        return _ok_response({"items": []})

    def get_active_orders(self):
        return _ok_response({"items": []})

    def get_quote_permission(self):
        return _ok_response([])

    def get_market_state(self, market="US"):
        return _ok_response([{"status": "OPEN", "marketStatus": "open"}])

    def get_delay_quotes(self, symbols, market="US"):
        return _ok_response({"items": [{"symbol": s, "latestPrice": 101.0} for s in symbols]})

    def get_briefs(self, symbols, market="US"):
        return _ok_response({"items": [{"symbol": s, "latestPrice": 101.0} for s in symbols]})

    def get_bars(self, symbols, period="30min", limit=30, begin_time=None, end_time=None):
        return _ok_response(
            [{"symbol": s, "items": list(self._bars_by_symbol.get(s, []))} for s in symbols]
        )

    def get_contract(self, symbol, market):
        return _ok_response({"symbol": symbol, "market": market, "secType": "STK"})


def _make_bar(i):
    return {
        "time": f"2026-04-20 10:{i:02d}:00",
        "open": 100 + i,
        "high": 101 + i,
        "low": 99 + i,
        "close": 100.5 + i,
        "volume": 1000 + i,
    }


class DataProviderFallbackTests(unittest.TestCase):
    def _app(self, tmpdir, *, fail_on_empty_bars=False):
        return AppConfig(
            raw={
                "mode": "paper",
                "markets": ["US"],
                "broker": {"platform": "tiger"},
                "system": {"state_dir": str(Path(tmpdir) / "runtime" / "state")},
                "strategy": {
                    "timeframe": "30min",
                    "use_rule_engine": False,
                    "data_provider": {
                        "primary": "yfinance",
                        "fallback": "tiger",
                        "fail_on_empty_bars": fail_on_empty_bars,
                    },
                    "signal": {
                        "lookback_bars": 30,
                        "fast_sma": 5,
                        "slow_sma": 10,
                        "trend_sma": 20,
                    },
                    "symbols": [{"symbol": "AAPL", "market": "US", "name": "Apple"}],
                },
            }
        )

    def test_fetch_cycle_raw_uses_fallback_provider_when_primary_bars_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app = self._app(tmpdir)
            raw = fetch_cycle_raw_with_provider(
                client=_FakeBrokerClient({"AAPL": [_make_bar(i) for i in range(30)]}),
                data=_FakePrimaryProvider({"AAPL": []}),
                app=app,
            )

            bars_entry = raw["bars"]["US"]["body"]["data"][0]
            self.assertEqual(len(bars_entry["items"]), 30)

            meta = raw["_bars_meta"]["US"]["symbols"]["AAPL"]
            self.assertEqual(meta["status"], "fallback_ok")
            self.assertTrue(meta["fallback_used"])
            self.assertEqual(meta["provider"], "tiger")
            self.assertEqual(meta["provider_path"], "yfinance->tiger")

    def test_strategy_summary_marks_bars_empty_when_fallback_also_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app = self._app(tmpdir)
            raw = fetch_cycle_raw_with_provider(
                client=_FakeBrokerClient({"AAPL": []}),
                data=_FakePrimaryProvider({"AAPL": []}),
                app=app,
            )

            summary = build_strategy_summary(raw, app)
            health = summary["data_health"]["AAPL"]

            self.assertFalse(health["strategy_ready"])
            self.assertEqual(health["reason"], "bars_empty")
            self.assertTrue(health["fallback_used"])
            self.assertEqual(health["provider_path"], "yfinance->tiger")
            self.assertEqual(health["provider_status"], "failed")

    def test_fail_on_empty_bars_marks_bars_response_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app = self._app(tmpdir, fail_on_empty_bars=True)
            raw = fetch_cycle_raw_with_provider(
                client=_FakeBrokerClient({"AAPL": []}),
                data=_FakePrimaryProvider({"AAPL": []}),
                app=app,
            )

            self.assertNotEqual(raw["bars"]["US"]["body"]["code"], 0)
            self.assertIn("bars_unavailable", raw["bars"]["US"]["body"].get("message", ""))


if __name__ == "__main__":
    unittest.main()
