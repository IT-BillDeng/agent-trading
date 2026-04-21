import json
import sys
import tempfile
import types
import unittest
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


class StrategyProfileApiTests(unittest.TestCase):
    def test_strategy_overview_includes_symbol_profiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_dir = root / "config"
            rules_dir = root / "rules"
            runtime_dir = root / "runtime" / "engine"
            logs_root = root / "logs"
            latest_dir = logs_root / "latest"

            config_dir.mkdir(parents=True)
            rules_dir.mkdir(parents=True)
            (runtime_dir / "state").mkdir(parents=True)
            latest_dir.mkdir(parents=True)

            (config_dir / "app.defaults.json").write_text(json.dumps({
                "mode": "paper",
                "markets": ["US"],
                "strategy": {
                    "timeframe": "30min",
                    "symbols": [
                        {"symbol": "AAPL", "market": "US", "name": "Apple"},
                        {"symbol": "NVDA", "market": "US", "name": "NVIDIA"},
                    ],
                },
            }, ensure_ascii=False))
            (config_dir / "app_config.docker.json").write_text(json.dumps({
                "extends": "./app.defaults.json",
            }, ensure_ascii=False))

            (rules_dir / "rules.json").write_text(json.dumps({
                "version": "1.0",
                "rules": [
                    {
                        "rule_id": "rsi_reversal",
                        "enabled": True,
                        "priority": 1,
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
                    },
                    {
                        "rule_id": "bollinger_breakout",
                        "enabled": True,
                        "priority": 2,
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
                    },
                ],
                "symbol_profile_templates": {
                    "default_shared_30m": {
                        "description": "default",
                        "enabled_rules": {},
                        "rule_overrides": {},
                    },
                    "high_beta_guarded": {
                        "description": "guarded",
                        "enabled_rules": {"rsi_reversal": False},
                        "rule_overrides": {},
                    },
                },
                "symbol_profiles": {
                    "AAPL": {
                        "profile": "default_shared_30m",
                        "enabled_rules": {},
                        "rule_overrides": {
                            "bollinger_breakout": {"risk": {"stop_loss_pct": 0.02}},
                        },
                    },
                    "NVDA": {
                        "profile": "high_beta_guarded",
                        "enabled_rules": {"rsi_reversal": False},
                        "rule_overrides": {},
                    },
                },
            }, ensure_ascii=False, indent=2))

            (runtime_dir / ".last_execution_cycle.json").write_text(json.dumps({
                "cycle_id": "cycle_profile",
                "strategy": {
                    "timeframe": "30min",
                    "signals": [
                        {
                            "rule_id": "bollinger_breakout",
                            "primary_rule_id": "bollinger_breakout",
                            "base_rule_id": "bollinger_breakout",
                            "symbol": "AAPL",
                            "market": "US",
                            "action": "BUY",
                            "symbol_profile": "default_shared_30m",
                            "effective_config_hash": "hash-aapl-bb",
                            "overrides_applied": {"risk": {"stop_loss_pct": 0.02}},
                        }
                    ],
                },
                "data_health": {},
            }, ensure_ascii=False))

            with mock.patch.object(dashboard_main, "CONFIG_DIR_PATH", config_dir), \
                mock.patch.object(dashboard_main, "RULES_DIR", rules_dir), \
                mock.patch.object(dashboard_main, "RULES_FILE", rules_dir / "rules.json"), \
                mock.patch.object(dashboard_main, "RUNTIME_DIR", runtime_dir), \
                mock.patch.object(dashboard_main, "LOGS_ROOT", logs_root), \
                mock.patch.object(dashboard_main, "LATEST_LOG_DIR", latest_dir), \
                mock.patch.object(dashboard_main, "BROKER_ARTIFACTS_DIR", root / "artifacts" / "broker"), \
                mock.patch.object(dashboard_main, "STRATEGIST_ARTIFACTS_DIR", root / "artifacts" / "strategist"), \
                mock.patch.object(dashboard_main, "STRATEGIST_MEMORY_DIR", root / "artifacts" / "strategist" / "memory"), \
                mock.patch.object(dashboard_main, "STRATEGIST_ITERATIONS_ARTIFACT_DIR", root / "artifacts" / "strategist" / "iterations"), \
                mock.patch.object(dashboard_main, "STRATEGIST_ITERATIONS_LOG_DIR", root / "logs" / "agents" / "strategist" / "iterations"):
                overview = dashboard_main._build_strategy_overview()

            self.assertIn("symbol_profiles", overview)
            self.assertEqual(overview["symbol_profiles"]["AAPL"]["profile"], "default_shared_30m")
            self.assertIn("bollinger_breakout", overview["symbol_profiles"]["AAPL"]["rules_with_overrides"])
            self.assertIn("rsi_reversal", overview["symbol_profiles"]["NVDA"]["disabled_rules"])
            self.assertEqual(overview["signal_records"][0]["symbol_profile"], "default_shared_30m")
            self.assertEqual(overview["signal_records"][0]["effective_config_hash"], "hash-aapl-bb")


if __name__ == "__main__":
    unittest.main()
