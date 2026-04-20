import asyncio
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


class DashboardApiStructureTests(unittest.TestCase):
    def test_trading_mode_get_exposes_reduce_only_and_emergency_flags(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_dir = Path(tmpdir) / "runtime" / "engine"
            state_dir = runtime_dir / "state"
            state_dir.mkdir(parents=True)

            (state_dir / "control_state.json").write_text(
                json.dumps(
                    {
                        "locked": False,
                        "reason": None,
                        "global": {"enabled": True, "mode": "paper_trade"},
                        "markets": {"US": True},
                        "symbols": {},
                        "risk": {
                            "reduce_only": True,
                            "reduce_only_reason": "manual_reduce_only",
                            "emergency_flatten": True,
                            "daily_loss_locked": False,
                        },
                        "history": [],
                    },
                    ensure_ascii=False,
                )
            )

            with mock.patch.object(dashboard_main, "RUNTIME_DIR", runtime_dir):
                result = asyncio.run(dashboard_main.api_trading_mode_get())

            self.assertEqual(result["mode"], "trade")
            self.assertEqual(result["canonical_mode"], "paper_trade")
            self.assertTrue(result["reduce_only"])
            self.assertEqual(result["reduce_only_reason"], "manual_reduce_only")
            self.assertTrue(result["emergency_flatten"])
            self.assertEqual(result["risk_state"], "emergency_flatten")

    def test_api_control_only_handles_lock_and_unlock(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_dir = Path(tmpdir) / "runtime" / "engine"
            state_dir = runtime_dir / "state"
            state_dir.mkdir(parents=True)

            execution_state = state_dir / "execution_state.json"
            execution_state.write_text(
                json.dumps(
                    {
                        "submitted": {"intent-1": {"symbol": "AAPL"}},
                        "previews": {"preview-1": {"symbol": "AAPL"}},
                        "sync": {"order-1": {"status": "Initial"}},
                        "history": [{"symbol": "AAPL"}],
                    },
                    ensure_ascii=False,
                )
            )

            with mock.patch.object(dashboard_main, "RUNTIME_DIR", runtime_dir):
                result = asyncio.run(dashboard_main.api_control("lock"))
                self.assertEqual(result, {"status": "ok", "action": "locked"})

                locked_state = json.loads((state_dir / "control_state.json").read_text())
                self.assertTrue(locked_state["locked"])
                self.assertEqual(locked_state["reason"], "manual_lock")

                execution_after_lock = json.loads(execution_state.read_text())
                self.assertEqual(len(execution_after_lock["submitted"]), 1)
                self.assertEqual(len(execution_after_lock["previews"]), 1)
                self.assertEqual(len(execution_after_lock["sync"]), 1)
                self.assertEqual(len(execution_after_lock["history"]), 1)

                result = asyncio.run(dashboard_main.api_control("unlock"))
                self.assertEqual(result, {"status": "ok", "action": "unlocked"})

                unlocked_state = json.loads((state_dir / "control_state.json").read_text())
                self.assertFalse(unlocked_state["locked"])
                self.assertEqual(unlocked_state["reason"], "manual_unlock")

    def test_execution_state_reset_is_independent_and_locks_engine(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_dir = Path(tmpdir) / "runtime" / "engine"
            state_dir = runtime_dir / "state"
            state_dir.mkdir(parents=True)

            execution_state = state_dir / "execution_state.json"
            execution_state.write_text(
                json.dumps(
                    {
                        "submitted": {
                            "intent-1": {"symbol": "AAPL"},
                            "intent-2": {"symbol": "MSFT"},
                        },
                        "previews": {"preview-1": {"symbol": "AAPL"}},
                        "sync": {"order-1": {"status": "Initial"}},
                        "history": [{"symbol": "AAPL"}, {"symbol": "MSFT"}],
                    },
                    ensure_ascii=False,
                )
            )

            with mock.patch.object(dashboard_main, "RUNTIME_DIR", runtime_dir):
                result = asyncio.run(dashboard_main.api_execution_state_reset())

            self.assertEqual(result["status"], "ok")
            self.assertEqual(
                result["cleared"],
                {
                    "submitted": 2,
                    "previews": 1,
                    "sync": 1,
                    "history": 2,
                },
            )
            self.assertTrue(result["engine_locked"])
            self.assertIsInstance(result["backup"], str)
            self.assertTrue(result["backup"].startswith("execution_state.bak."))

            backup_file = state_dir / result["backup"]
            self.assertTrue(backup_file.exists())

            cleared_state = json.loads(execution_state.read_text())
            self.assertEqual(cleared_state["submitted"], {})
            self.assertEqual(cleared_state["previews"], {})
            self.assertEqual(cleared_state["sync"], {})
            self.assertEqual(cleared_state["history"], [])

            control_state = json.loads((state_dir / "control_state.json").read_text())
            self.assertTrue(control_state["locked"])
            self.assertEqual(control_state["reason"], "execution_state_reset")
            self.assertEqual(control_state["updated_by"], "dashboard")


if __name__ == "__main__":
    unittest.main()
