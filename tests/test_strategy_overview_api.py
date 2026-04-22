import json
import sys
import tempfile
import types
import unittest
import asyncio
from pathlib import Path
from unittest import mock


class _FakeFastAPI:
    def __init__(self, *args, **kwargs):
        self.routes = []

    def middleware(self, *args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    def mount(self, *args, **kwargs):
        return None

    def get(self, *args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    post = get
    put = get
    patch = get
    delete = get


class _FakeUploadFile:
    filename = ""

    async def read(self):
        return b""


class _FakeJSONResponse(dict):
    def __init__(self, content, status_code=200):
        super().__init__(content)
        self.status_code = status_code


class _FakeStaticFiles:
    def __init__(self, *args, **kwargs):
        pass


fake_fastapi = types.ModuleType("fastapi")
fake_fastapi.FastAPI = _FakeFastAPI
fake_fastapi.Form = lambda default=None, **kwargs: default
fake_fastapi.File = lambda default=None, **kwargs: default
fake_fastapi.UploadFile = _FakeUploadFile

fake_fastapi_responses = types.ModuleType("fastapi.responses")
fake_fastapi_responses.FileResponse = object
fake_fastapi_responses.JSONResponse = _FakeJSONResponse

fake_fastapi_staticfiles = types.ModuleType("fastapi.staticfiles")
fake_fastapi_staticfiles.StaticFiles = _FakeStaticFiles

fake_pydantic = types.ModuleType("pydantic")
fake_pydantic.BaseModel = object

fake_broker_client = types.ModuleType("dashboard.broker_client")
fake_broker_client.BrokerClient = type("BrokerClient", (), {})

fake_tiger_client = types.ModuleType("dashboard.tiger_client")
fake_tiger_client.TigerClient = object

fake_data_cache = types.ModuleType("dashboard.data_cache")
fake_data_cache.DataCache = object

fake_quote_provider = types.ModuleType("dashboard.quote_provider")
fake_quote_provider.get_quote_provider = lambda *args, **kwargs: None

fake_scheduler = types.ModuleType("dashboard.scheduler")
fake_scheduler.SignalScheduler = object

fake_normalize = types.ModuleType("dashboard.normalize")
fake_normalize.get_normalizer = lambda *args, **kwargs: None
fake_normalize.available_brokers = lambda: []

fake_service_logs = types.ModuleType("dashboard.service_logs")
fake_service_logs.append_service_log = lambda *args, **kwargs: None

fake_trading_day = types.ModuleType("dashboard.trading_day")
fake_trading_day.get_us_trading_day_status = lambda *args, **kwargs: {}

with mock.patch.dict(
    sys.modules,
    {
        "fastapi": fake_fastapi,
        "fastapi.responses": fake_fastapi_responses,
        "fastapi.staticfiles": fake_fastapi_staticfiles,
        "pydantic": fake_pydantic,
        "dashboard.broker_client": fake_broker_client,
        "dashboard.tiger_client": fake_tiger_client,
        "dashboard.data_cache": fake_data_cache,
        "dashboard.quote_provider": fake_quote_provider,
        "dashboard.scheduler": fake_scheduler,
        "dashboard.normalize": fake_normalize,
        "dashboard.service_logs": fake_service_logs,
        "dashboard.trading_day": fake_trading_day,
    },
):
    from dashboard import main as dashboard_main
    from dashboard.api import strategy as dashboard_strategy_api


class StrategyOverviewApiTests(unittest.TestCase):
    def test_build_strategy_overview_aggregates_rules_signals_and_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            runtime_dir = root / "runtime" / "engine"
            rules_dir = root / "rules"
            logs_root = root / "logs"
            latest_dir = logs_root / "latest"
            strategist_logs_dir = logs_root / "agents" / "strategist" / "iterations"
            broker_artifacts_dir = root / "artifacts" / "broker"
            factor_artifacts_dir = root / "artifacts" / "factors"
            strategist_artifacts_dir = root / "artifacts" / "strategist"
            registry_path = root / "factor-registry.json"

            (config_dir).mkdir(parents=True)
            (runtime_dir / "state").mkdir(parents=True)
            (runtime_dir / "strategist_iterations").mkdir(parents=True)
            (rules_dir).mkdir(parents=True)
            latest_dir.mkdir(parents=True)
            strategist_logs_dir.mkdir(parents=True)
            broker_artifacts_dir.mkdir(parents=True)
            (factor_artifacts_dir / "history").mkdir(parents=True)
            strategist_artifacts_dir.mkdir(parents=True)
            (strategist_artifacts_dir / "deployment_records.jsonl").write_text(
                json.dumps(
                    {
                        "proposal_id": "factor_config_hot_1",
                        "proposal_type": "factor_config",
                        "apply_action": "apply_factor_registry_only",
                        "success": True,
                        "applied_at": "2026-04-16T10:05:00",
                        "registry_hash": "registry-hash-1",
                        "changed_factors": ["rsi_14_30m"],
                    },
                    ensure_ascii=False,
                ) + "\n"
            )

            registry_path.write_text(json.dumps({
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
                        "version": 1,
                    }
                },
            }, ensure_ascii=False))

            (config_dir / "app_config.docker.json").write_text(json.dumps({
                "mode": "paper",
                "markets": ["US"],
                "strategy": {
                    "timeframe": "30min",
                    "watchlist_file": "/app/data/watchlist.json",
                    "rules_path": "/app/rules/rules.json",
                    "symbols": [
                        {"symbol": "AAPL", "name": "Apple"},
                        {"symbol": "MSFT", "name": "Microsoft"},
                    ],
                },
                "factor_engine": {
                    "enabled": True,
                    "mode": "shadow",
                    "registry_path": str(registry_path),
                    "allow_actionable_consumption": False,
                },
            }, ensure_ascii=False))

            (rules_dir / "rules.json").write_text(json.dumps({
                "version": "1.0",
                "updated_at": "2026-04-16T10:00:00",
                "rules": [
                    {
                        "rule_id": "rsi_reversal",
                        "name": "RSI反转策略",
                        "description": "RSI 超卖反弹",
                        "enabled": True,
                        "priority": 2,
                        "timeframe": "30min",
                        "symbols": ["*"],
                        "markets": ["US"],
                        "entry": {"action": "BUY"},
                        "exit": {"action": "EXIT"},
                    },
                    {
                        "rule_id": "bollinger_breakout",
                        "name": "布林带突破策略",
                        "description": "价格突破上轨",
                        "enabled": False,
                        "priority": 3,
                        "timeframe": "30min",
                        "symbols": ["*"],
                        "markets": ["US"],
                        "entry": {"action": "BUY"},
                        "exit": {"action": "EXIT"},
                    },
                ],
                "global_settings": {"min_score": 4},
            }, ensure_ascii=False, indent=2))

            (runtime_dir / ".last_execution_cycle.json").write_text(json.dumps({
                "cycle_id": "cycle_1",
                "trading_mode": "signals",
                "strategy": {
                    "timeframe": "30min",
                    "signals": [
                        {"rule_id": "rsi_reversal", "symbol": "AAPL", "market": "US", "action": "BUY", "score": 3, "reason": "entry_condition_met", "order_type": "LMT", "last_close": 266.37},
                        {"rule_id": "bollinger_breakout", "symbol": "MSFT", "market": "US", "action": "EXIT", "score": 1, "reason": "exit_condition_met", "order_type": "MKT", "last_close": 411.27},
                        {"rule_id": "rsi_reversal", "symbol": "MSFT", "market": "US", "action": "HOLD", "score": 0, "reason": "no_condition_met", "order_type": "LMT", "last_close": 411.27},
                    ],
                },
                "data_health": {
                    "AAPL": {
                        "market": "US",
                        "provider": "yfinance",
                        "quote_status": "delayed",
                        "contract_status": "ok",
                        "raw_bars_count": 0,
                        "normalized_bars_count": 0,
                        "required_bars": 25,
                        "latest_bar_time": None,
                        "timeframe": "30min",
                        "strategy_ready": False,
                        "reason": "bars_empty",
                    }
                },
                "quote_access": {"US": True},
                "market_state": {"US": {"state": "OPEN"}},
                "factor_engine": {
                    "enabled": True,
                    "mode": "shadow",
                    "allow_actionable_consumption": False,
                    "registry_hash": "registry-hash-1",
                    "registry_hash_source": "runtime_registry",
                    "schema_valid": True,
                    "schema_errors": [],
                    "schema_warnings": [],
                    "implementation_summary": {
                        "available_count": 1,
                        "total_count": 1,
                        "missing_count": 0,
                    },
                    "symbols": {
                        "AAPL": {
                            "factors_ready": 1,
                            "factors_total": 1,
                            "blocking": False,
                            "reasons": [],
                        }
                    },
                },
            }, ensure_ascii=False))

            (factor_artifacts_dir / "latest.json").write_text(json.dumps({
                "timestamp": "2026-04-16T10:00:00+00:00",
                "registry_hash": "registry-hash-1",
                "registry_hash_source": "runtime_registry",
                "schema_valid": True,
                "schema_errors": [],
                "schema_warnings": [],
                "implementation_summary": {
                    "available_count": 1,
                    "total_count": 1,
                    "missing_count": 0
                },
                "mode": "shadow",
                "symbols": {
                    "AAPL": {
                        "symbol": "AAPL",
                        "timestamp": "2026-04-16T10:00:00-04:00",
                        "registry_hash": "registry-hash-1",
                        "mode": "shadow",
                        "factors": {
                            "rsi_14_30m": {
                                "value": 42.1,
                                "ready": True,
                                "actionable": False,
                                "reason": "ok",
                                "source": "regular_session_completed_bars",
                                "config_hash": "factor-hash-1",
                                "implementation_available": True,
                            }
                        },
                    }
                },
            }, ensure_ascii=False))

            (runtime_dir / "strategy_plan_latest.json").write_text(json.dumps({
                "plan_id": "plan-1",
                "generated_at": "2026-04-16T10:00:00",
                "generator": "tiger-strategist",
                "data_quality": "ok",
                "summary": "继续跟踪 MSFT / AAPL",
                "fee_model_confidence": {
                    "level": "observe",
                    "label": "观察",
                    "reason": "真实费用记录不足",
                },
                "risk_notes": ["净收益回测可信度下降"],
                "strategy_recommendations": [{"priority": 1, "action": "WAIT", "detail": "market closed"}],
                "action_items": [{"owner": "operator", "task": "recheck on open"}],
            }, ensure_ascii=False))

            (runtime_dir / "strategy_plan_history.jsonl").write_text(
                json.dumps({"plan_id": "plan-1", "generated_at": "2026-04-16T10:00:00", "summary": "继续跟踪 MSFT / AAPL"}, ensure_ascii=False) + "\n"
            )

            iter_payload = {
                "iteration_id": "iter_20260416_100000",
                "timestamp": "2026-04-16T10:00:00",
                "symbols": ["AAPL"],
                "period": "2026-01-07 ~ 2026-04-07",
                "results": [{"label": "base", "params": {}, "trades": 4, "return_pct": 2.5}],
                "best": {"label": "base", "return_pct": 2.5},
            }
            (runtime_dir / "strategist_iterations" / "iter_20260416_100000.json").write_text(json.dumps(iter_payload, ensure_ascii=False))
            (strategist_logs_dir / "iter_20260416_100000.json").write_text(json.dumps(iter_payload, ensure_ascii=False))

            (runtime_dir / "state" / "control_state.json").write_text(json.dumps({
                "locked": False,
                "trading_mode": "signals",
                "reason": "manual",
            }, ensure_ascii=False))

            (broker_artifacts_dir / "fee_calibration_summary.json").write_text(json.dumps({
                "count": 1,
                "avg_delta": -0.04,
                "max_abs_delta": 0.04,
                "trust": {"level": "observe", "label": "观察", "reason": "真实费用记录不足"},
                "recent": [{
                    "broker_platform": "tiger",
                    "market": "US",
                    "symbol": "AAPL",
                    "side": "SELL",
                    "price": 100.0,
                    "quantity": 10.0,
                    "estimated_total": 2.05,
                    "actual_total": 2.01,
                    "delta": -0.04,
                }],
            }, ensure_ascii=False))

            with mock.patch.object(dashboard_main, "CONFIG_DIR_PATH", config_dir), \
                mock.patch.object(dashboard_main, "RULES_DIR", rules_dir), \
                mock.patch.object(dashboard_main, "RULES_FILE", rules_dir / "rules.json"), \
                mock.patch.object(dashboard_main, "RUNTIME_DIR", runtime_dir), \
                mock.patch.object(dashboard_main, "LOGS_ROOT", logs_root), \
                mock.patch.object(dashboard_main, "LATEST_LOG_DIR", latest_dir), \
                mock.patch.object(dashboard_main, "BROKER_ARTIFACTS_DIR", broker_artifacts_dir), \
                mock.patch.object(dashboard_main, "FACTOR_ARTIFACTS_DIR", factor_artifacts_dir), \
                mock.patch.object(dashboard_main, "STRATEGIST_ARTIFACTS_DIR", strategist_artifacts_dir), \
                mock.patch.object(dashboard_main, "STRATEGIST_MEMORY_DIR", strategist_artifacts_dir / "memory"), \
                mock.patch.object(dashboard_main, "STRATEGIST_ITERATIONS_ARTIFACT_DIR", strategist_artifacts_dir / "iterations"), \
                mock.patch.object(dashboard_main, "STRATEGIST_ITERATIONS_LOG_DIR", strategist_logs_dir):
                overview = dashboard_main._build_strategy_overview()

            self.assertEqual(overview["latest_cycle"]["signal_count"], 3)
            self.assertEqual(overview["latest_cycle"]["buy_count"], 1)
            self.assertEqual(overview["latest_cycle"]["exit_count"], 1)
            self.assertEqual(overview["latest_cycle"]["hold_count"], 1)
            self.assertEqual(len(overview["rules_summary"]), 2)
            self.assertEqual(overview["rules_summary"][0]["rule_id"], "rsi_reversal")
            self.assertEqual(len(overview["signal_records"]), 3)
            self.assertEqual(overview["signal_records"][0]["action"], "BUY")
            self.assertEqual(overview["latest_plan"]["plan_id"], "plan-1")
            self.assertEqual(overview["latest_plan"]["fee_model_confidence"]["label"], "观察")
            self.assertEqual(overview["latest_plan"]["risk_notes"][0], "净收益回测可信度下降")
            self.assertEqual(len(overview["plan_history"]), 1)
            self.assertEqual(len(overview["iterations"]), 1)
            self.assertEqual(overview["fee_calibration"]["count"], 1)
            self.assertAlmostEqual(overview["fee_calibration"]["avg_delta"], -0.04, places=6)
            self.assertEqual(overview["fee_calibration"]["trust"]["label"], "观察")
            self.assertIn("AAPL", overview["data_health"])
            self.assertEqual(overview["data_health"]["AAPL"]["reason"], "bars_empty")
            self.assertIn("factor_engine", overview)
            self.assertTrue(overview["factor_engine"]["enabled"])
            self.assertEqual(overview["factor_engine"]["mode"], "shadow")
            self.assertFalse(overview["factor_engine"]["allow_actionable_consumption"])
            self.assertEqual(overview["latest_cycle"]["factor_engine"]["registry_hash"], "registry-hash-1")
            self.assertEqual(overview["factor_engine"]["registry_hash_source"], "runtime_registry")
            self.assertTrue(overview["factor_engine"]["schema_valid"])
            self.assertEqual(overview["factor_engine"]["implementation_summary"]["missing_count"], 0)
            self.assertEqual(overview["factor_engine"]["symbols"]["AAPL"]["factors_ready"], 1)
            self.assertEqual(overview["factor_engine"]["symbols"]["AAPL"]["factors"]["rsi_14_30m"]["session"], "regular")
            self.assertTrue(overview["factor_engine"]["symbols"]["AAPL"]["factors"]["rsi_14_30m"]["implementation_available"])
            self.assertEqual(len(overview["factor_engine"]["factor_rows"]), 1)
            self.assertEqual(overview["factor_engine"]["factor_rows"][0]["source"], "regular_session_completed_bars")
            self.assertEqual(overview["factor_engine"]["last_apply"]["proposal_id"], "factor_config_hot_1")
            self.assertEqual(overview["control"]["legacy_mode"], "signals")
            self.assertEqual(overview["control"]["canonical_mode"], "signal_only")
            self.assertTrue(overview["control"]["signal_generation_enabled"])
            self.assertFalse(overview["control"]["paper_execution_enabled"])
            self.assertFalse(overview["control"]["live_execution_enabled"])
            self.assertFalse(overview["control"]["live_submission_ready"])
            self.assertTrue((latest_dir / "strategy_overview.json").exists())

    def test_strategy_api_returns_factor_engine_field(self):
        expected = {"factor_engine": {"enabled": True, "mode": "shadow"}}
        with mock.patch.object(dashboard_main, "_build_strategy_overview", return_value=expected):
            dashboard_strategy_api.set_dashboard_main_module(dashboard_main)
            result = asyncio.run(dashboard_strategy_api.api_strategy_overview())
        self.assertEqual(result["factor_engine"]["mode"], "shadow")
        self.assertTrue(result["factor_engine"]["enabled"])


if __name__ == "__main__":
    unittest.main()
