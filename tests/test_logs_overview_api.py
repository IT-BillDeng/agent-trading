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


class LogsOverviewApiTests(unittest.TestCase):
    def test_build_logs_overview_syncs_latest_snapshots_and_status_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime_dir = root / "runtime"
            logs_root = root / "logs"
            audit_dir = logs_root / "audit"
            service_dir = logs_root / "service"
            latest_dir = logs_root / "latest"
            legacy_dir = runtime_dir / "logs"
            strategist_iterations_dir = logs_root / "agents" / "strategist" / "iterations"

            (runtime_dir / "state").mkdir(parents=True)
            (runtime_dir / "watcher").mkdir(parents=True)
            audit_dir.mkdir(parents=True)
            service_dir.mkdir(parents=True)
            legacy_dir.mkdir(parents=True)
            strategist_iterations_dir.mkdir(parents=True)

            (runtime_dir / ".last_execution_cycle.json").write_text(
                json.dumps({"cycle_id": "cycle_1", "market_state": {"US": {"state": "OPEN"}}}, ensure_ascii=False)
            )
            (runtime_dir / "market_context.json").write_text(
                json.dumps({"session": "regular", "tz": "America/New_York"}, ensure_ascii=False)
            )
            (runtime_dir / "state" / "control_state.json").write_text(
                json.dumps({"locked": False, "trading_mode": "signals"}, ensure_ascii=False)
            )
            (runtime_dir / "state" / "execution_state.json").write_text(
                json.dumps({"last_submit_at": "2026-04-16T10:00:00Z"}, ensure_ascii=False)
            )
            (runtime_dir / "watcher" / "latest.json").write_text(
                json.dumps({"generated_at": "2026-04-16T10:00:00Z", "summary": "healthy"}, ensure_ascii=False)
            )
            (runtime_dir / "watcher" / "history.jsonl").write_text(
                json.dumps({"generated_at": "2026-04-16T10:00:00Z"}) + "\n"
            )
            (runtime_dir / "newswire").mkdir(parents=True)
            (runtime_dir / "newswire" / "latest.json").write_text(json.dumps({"items": []}, ensure_ascii=False))
            (runtime_dir / "strategist_iterations").mkdir(parents=True)
            (runtime_dir / "strategy_plan_latest.json").write_text(json.dumps({"summary": "no change"}, ensure_ascii=False))

            (audit_dir / "execution.jsonl").write_text(
                json.dumps({"ts": "2026-04-16T10:01:00Z", "cycle_id": "cycle_1"}) + "\n"
            )
            (service_dir / "watcher.jsonl").write_text(
                json.dumps({"generated_at": "2026-04-16T10:02:00Z", "summary": "healthy"}) + "\n"
            )
            (legacy_dir / "execution.jsonl").write_text(
                json.dumps({"ts": "2026-04-15T10:01:00Z", "cycle_id": "legacy_cycle"}) + "\n"
            )

            with mock.patch.object(dashboard_main, "RUNTIME_DIR", runtime_dir), \
                mock.patch.object(dashboard_main, "LOGS_ROOT", logs_root), \
                mock.patch.object(dashboard_main, "AUDIT_LOG_DIR", audit_dir), \
                mock.patch.object(dashboard_main, "SERVICE_LOG_DIR", service_dir), \
                mock.patch.object(dashboard_main, "LATEST_LOG_DIR", latest_dir), \
                mock.patch.object(dashboard_main, "LEGACY_LOG_DIR", legacy_dir), \
                mock.patch.object(dashboard_main, "STRATEGIST_ITERATIONS_LOG_DIR", strategist_iterations_dir):
                overview = dashboard_main._build_logs_overview()

            self.assertEqual(overview["logs_root"], str(logs_root))
            self.assertIn("engine_cycle", overview["latest_snapshots"])
            self.assertTrue((latest_dir / "engine_cycle.json").exists())
            self.assertTrue((latest_dir / "market_context.json").exists())
            self.assertTrue((latest_dir / "control_state.json").exists())
            self.assertTrue((latest_dir / "execution_state.json").exists())
            self.assertTrue((latest_dir / "agents_status.json").exists())
            self.assertTrue((latest_dir / "logs_overview.json").exists())

            agent_status = json.loads((latest_dir / "agents_status.json").read_text())
            self.assertTrue(agent_status["agents"]["watcher"]["service_log"]["exists"])
            self.assertTrue(agent_status["agents"]["newswire"]["latest_output"]["exists"])

            audit_names = [Path(item["path"]).stem for item in overview["sections"]["audit"]]
            service_names = [Path(item["path"]).stem for item in overview["sections"]["service"]]
            self.assertIn("execution", audit_names)
            self.assertIn("watcher", service_names)


if __name__ == "__main__":
    unittest.main()
