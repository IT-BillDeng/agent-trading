import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

sys.modules.setdefault("yfinance", types.SimpleNamespace(Ticker=None, download=None))

from engine.backtest import BacktestConfig, BacktestDataError, BacktestEngine, Bar, DataFetcher
from engine.rule_engine import RuleSignal


def _make_rules_file() -> Path:
    payload = {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "buy_then_exit",
                "enabled": True,
                "priority": 1,
                "timeframe": "30min",
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "action": "BUY",
                    "conditions": {"type": "price", "field": "close", "operator": "above", "value": 1},
                },
                "exit": {
                    "action": "EXIT",
                    "conditions": {"type": "price", "field": "close", "operator": "below", "value": 1},
                },
            }
        ],
    }
    handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    with handle:
        json.dump(payload, handle)
    return Path(handle.name)


def _make_bar_payload(start: datetime, count: int) -> list[dict]:
    payload: list[dict] = []
    for idx in range(count):
        ts = start + timedelta(minutes=30 * idx)
        payload.append(
            {
                "time": int(ts.timestamp() * 1000),
                "open": 100 + idx,
                "high": 101 + idx,
                "low": 99 + idx,
                "close": 100.5 + idx,
                "volume": 1000 + idx,
            }
        )
    return payload


def _make_bars(start: datetime, closes: list[float]) -> list[Bar]:
    return [
        Bar(
            timestamp=start + timedelta(minutes=30 * idx),
            open=close - 0.2,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            volume=1000 + idx,
        )
        for idx, close in enumerate(closes)
    ]


class BacktestTigerPaginationTests(unittest.TestCase):
    def test_tiger_fetch_paginates_past_500_bars_and_advances_cursor(self):
        start = datetime(2026, 1, 1, 9, 30)
        page1 = _make_bar_payload(start, 500)
        page2 = _make_bar_payload(start + timedelta(minutes=30 * 500), 120)
        requested_begins: list[str] = []

        class FakeTigerClient:
            def __init__(self, _props):
                pass

            def get_bars(self, symbols, period="30min", limit=500, begin_time=None, end_time=None):
                requested_begins.append(begin_time)
                items = page1 if len(requested_begins) == 1 else page2
                return {
                    "http_status": 200,
                    "body": {"code": 0, "data": [{"symbol": symbols[0], "items": items}]},
                }

        fake_config = types.ModuleType("engine.config")
        fake_config.load_tiger_props = lambda _path: object()
        fake_tiger_client = types.ModuleType("engine.tiger_client")
        fake_tiger_client.TigerClient = FakeTigerClient

        with tempfile.TemporaryDirectory() as tmpdir:
            props_dir = Path(tmpdir)
            (props_dir / "tiger_openapi_config.properties").write_text("ok", encoding="utf-8")
            with mock.patch.dict(sys.modules, {"engine.config": fake_config, "engine.tiger_client": fake_tiger_client}):
                with mock.patch.dict("os.environ", {"BROKER_PROPERTIES_DIR": str(props_dir)}, clear=False):
                    bars = DataFetcher._fetch_from_tiger("AAPL", "2026-01-01", "2026-03-01", "30min")

        self.assertEqual(len(bars), 620)
        self.assertEqual(requested_begins[0], "2026-01-01 00:00:00")
        self.assertNotEqual(requested_begins[0], requested_begins[1])
        self.assertGreater(bars[-1].timestamp, bars[0].timestamp)

    def test_tiger_pagination_stall_falls_back_to_yfinance(self):
        start = datetime(2026, 1, 1, 9, 30)
        duplicate_page = _make_bar_payload(start, 500)

        class FakeTigerClient:
            def __init__(self, _props):
                pass

            def get_bars(self, symbols, period="30min", limit=500, begin_time=None, end_time=None):
                return {
                    "http_status": 200,
                    "body": {"code": 0, "data": [{"symbol": symbols[0], "items": duplicate_page}]},
                }

        fake_config = types.ModuleType("engine.config")
        fake_config.load_tiger_props = lambda _path: object()
        fake_tiger_client = types.ModuleType("engine.tiger_client")
        fake_tiger_client.TigerClient = FakeTigerClient
        fallback_bars = _make_bars(start, [100.0, 101.0, 102.0])

        with tempfile.TemporaryDirectory() as tmpdir:
            props_dir = Path(tmpdir)
            (props_dir / "tiger_openapi_config.properties").write_text("ok", encoding="utf-8")
            with mock.patch.dict(sys.modules, {"engine.config": fake_config, "engine.tiger_client": fake_tiger_client}):
                with mock.patch.dict("os.environ", {"BROKER_PROPERTIES_DIR": str(props_dir)}, clear=False):
                    with mock.patch.object(DataFetcher, "_fetch_from_yfinance", return_value=fallback_bars):
                        bars, meta = DataFetcher.fetch_with_metadata(
                            "AAPL",
                            "2026-01-01",
                            "2026-03-01",
                            interval="30min",
                            source="tiger",
                        )

        self.assertEqual(len(bars), 3)
        self.assertEqual(meta["data_source"], "yfinance")
        self.assertTrue(meta["fallback_used"])
        self.assertIn("tiger_fetch_failed_fallback_to_yfinance", meta["warnings"])

    def test_full_universe_with_empty_symbol_does_not_zero_out_valid_symbol(self):
        rules_path = _make_rules_file()
        self.addCleanup(lambda: rules_path.unlink(missing_ok=True))
        start = datetime(2026, 1, 1, 9, 30)
        valid_bars = _make_bars(start, [100.0 + i for i in range(20)])

        def fake_load_data(engine):
            engine.bars_by_symbol = {"AAPL": valid_bars, "EMPTY": []}
            engine.data_coverage = {
                "AAPL": {
                    "symbol": "AAPL",
                    "bars_count": 20,
                    "first_bar_time": valid_bars[0].timestamp.isoformat(),
                    "last_bar_time": valid_bars[-1].timestamp.isoformat(),
                    "data_source": "tiger",
                    "requested_start": "2026-01-01 00:00:00",
                    "requested_end": "2026-01-03 23:59:59",
                    "requested_interval": "30min",
                    "fallback_used": False,
                    "status": "ok",
                    "warnings": [],
                    "error": None,
                    "required_bars": 10,
                    "has_sufficient_bars": True,
                },
                "EMPTY": {
                    "symbol": "EMPTY",
                    "bars_count": 0,
                    "first_bar_time": None,
                    "last_bar_time": None,
                    "data_source": "tiger",
                    "requested_start": "2026-01-01 00:00:00",
                    "requested_end": "2026-01-03 23:59:59",
                    "requested_interval": "30min",
                    "fallback_used": False,
                    "status": "error",
                    "warnings": [],
                    "error": "bars_empty",
                    "required_bars": 10,
                    "has_sufficient_bars": False,
                },
            }
            engine.data_warnings = ["EMPTY: bars_empty"]
            engine.current_index = {symbol: -1 for symbol in engine.config.symbols}

        config = BacktestConfig(
            symbols=["AAPL", "EMPTY"],
            start_date="2026-01-01",
            end_date="2026-01-03",
            timeframe="30min",
            initial_capital=100000.0,
        )
        engine = BacktestEngine(config, rules_path)
        engine.load_data = lambda: fake_load_data(engine)

        def fake_evaluate(symbol, market, bars_history, position_dict):
            idx = engine.current_index[symbol]
            if symbol == "AAPL" and idx == 0:
                return [
                    RuleSignal(
                        rule_id="buy_then_exit",
                        symbol=symbol,
                        market=market,
                        action="BUY",
                        order_type="LMT",
                        score=1,
                        reason="entry",
                        priority=1,
                        stop_loss=None,
                        take_profit=None,
                        last_close=bars_history[-1]["close"],
                    )
                ]
            if symbol == "AAPL" and idx == 2 and position_dict:
                return [
                    RuleSignal(
                        rule_id="buy_then_exit",
                        symbol=symbol,
                        market=market,
                        action="EXIT",
                        order_type="MKT",
                        score=1,
                        reason="exit",
                        priority=1,
                        stop_loss=None,
                        take_profit=None,
                        last_close=bars_history[-1]["close"],
                    )
                ]
            return []

        engine.rule_engine.evaluate_symbol = fake_evaluate
        result = engine.run()

        self.assertEqual(result.total_trades, 2)
        self.assertIn("EMPTY: bars_empty", result.data_warnings)
        self.assertEqual(result.data_coverage["EMPTY"]["bars_count"], 0)

    def test_run_raises_explicit_error_when_no_symbols_have_valid_bars(self):
        rules_path = _make_rules_file()
        self.addCleanup(lambda: rules_path.unlink(missing_ok=True))
        config = BacktestConfig(
            symbols=["AAPL", "MSFT"],
            start_date="2026-01-01",
            end_date="2026-01-03",
            timeframe="30min",
            initial_capital=100000.0,
        )
        engine = BacktestEngine(config, rules_path)
        engine.load_data = lambda: (_ for _ in ()).throw(
            BacktestDataError(
                "No valid bars loaded for any symbol in backtest window",
                diagnostics={"symbols": {"AAPL": {"bars_count": 0}, "MSFT": {"bars_count": 0}}},
            )
        )

        with self.assertRaises(BacktestDataError) as ctx:
            engine.run()

        self.assertIn("No valid bars loaded for any symbol", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
