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
    def test_scheduler_status_is_read_only_and_control_mutations_are_disabled(self):
        class _FakeScheduler:
            def get_state(self):
                return {"running": True, "cycle_count": 7}

        with mock.patch.object(dashboard_main, "scheduler", _FakeScheduler()):
            status = asyncio.run(dashboard_main.api_scheduler_status())
            interval_result = asyncio.run(dashboard_main.api_scheduler_interval({"interval": 30}))
            run_result = asyncio.run(dashboard_main.api_scheduler_run())

        self.assertTrue(status["running"])
        self.assertEqual(status["cycle_count"], 7)
        self.assertTrue(status["read_only"])
        self.assertTrue(status["mutable_controls_disabled"])

        self.assertEqual(interval_result.status_code, 403)
        self.assertEqual(interval_result["error"], "scheduler control disabled from dashboard")
        self.assertTrue(interval_result["read_only"])

        self.assertEqual(run_result.status_code, 403)
        self.assertEqual(run_result["error"], "scheduler control disabled from dashboard")
        self.assertTrue(run_result["read_only"])

    def test_broker_config_upload_is_disabled_by_default(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            result = asyncio.run(dashboard_main.api_broker_config_upload_file(_FakeUploadFile()))

        self.assertEqual(result.status_code, 403)
        self.assertEqual(result["error"], "broker config upload disabled")
        self.assertIn("DASHBOARD_ENABLE_CONFIG_UPLOAD", result["reason"])

    def test_rules_validate_returns_errors_and_direct_rules_write_is_disabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rules_dir = Path(tmpdir) / "rules"
            rules_dir.mkdir(parents=True)
            rules_file = rules_dir / "rules.json"
            rules_file.write_text(json.dumps({"version": "1.0", "rules": []}, ensure_ascii=False))

            invalid_rules = {
                "rules": [
                    {
                        "rule_id": "bad_rule",
                        "enabled": "yes",
                        "priority": "high",
                        "entry": {
                            "action": "SELL",
                            "conditions": {
                                "type": "indicator",
                                "indicator": "not_supported",
                                "compare": {"operator": "cross_above"},
                            },
                        },
                    }
                ]
            }

            with mock.patch.object(dashboard_main, "RULES_DIR", rules_dir), mock.patch.object(dashboard_main, "RULES_FILE", rules_file):
                validate_result = asyncio.run(dashboard_main.api_rules_validate(invalid_rules))
                update_result = asyncio.run(dashboard_main.api_rules_update(invalid_rules))

            self.assertFalse(validate_result["valid"])
            self.assertGreater(len(validate_result["errors"]), 0)
            self.assertEqual(validate_result["warnings"], [])

            self.assertEqual(update_result.status_code, 403)
            self.assertEqual(
                update_result["reason"],
                "direct_rules_write_disabled_use_proposal_applier",
            )
            self.assertTrue(update_result["read_only"])

            persisted = json.loads(rules_file.read_text())
            self.assertEqual(persisted, {"version": "1.0", "rules": []})

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
            self.assertEqual(result["legacy_mode"], "trade")
            self.assertEqual(result["canonical_mode"], "paper_trade")
            self.assertTrue(result["reduce_only"])
            self.assertEqual(result["reduce_only_reason"], "manual_reduce_only")
            self.assertTrue(result["emergency_flatten"])
            self.assertEqual(result["risk_state"], "emergency_flatten")
            self.assertTrue(result["signal_generation_enabled"])
            self.assertTrue(result["paper_execution_enabled"])
            self.assertFalse(result["live_execution_enabled"])
            self.assertFalse(result["live_submission_ready"])
            self.assertFalse(result["order_submission"])
            self.assertIn("live_readiness", result)

    def test_live_trade_requires_readiness_checklist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_dir = Path(tmpdir) / "runtime" / "engine"
            state_dir = runtime_dir / "state"
            state_dir.mkdir(parents=True)

            with mock.patch.object(dashboard_main, "RUNTIME_DIR", runtime_dir):
                missing_id = asyncio.run(
                    dashboard_main.api_trading_mode_set(
                        {
                            "mode": "live_trade",
                            "confirm_live": True,
                        }
                    )
                )
                blocked = asyncio.run(
                    dashboard_main.api_trading_mode_set(
                        {
                            "mode": "live_trade",
                            "confirm_live": True,
                            "readiness_checklist_id": "live-readiness-v1",
                            "checklist": {
                                "p0_safety_tests_passed": True,
                                "p1_risk_tests_passed": True,
                            },
                        }
                    )
                )

            self.assertEqual(missing_id.status_code, 400)
            self.assertIn("readiness_checklist_id is required", missing_id["error"])

            self.assertEqual(blocked.status_code, 400)
            self.assertIn("live readiness checklist failed", blocked["error"])

            state = json.loads((state_dir / "control_state.json").read_text())
            self.assertEqual(state["live_readiness"]["status"], "blocked")
            self.assertEqual(state["global"]["mode"], "off")

    def test_live_trade_can_be_enabled_with_passing_checklist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime_dir = Path(tmpdir) / "runtime" / "engine"
            state_dir = runtime_dir / "state"
            state_dir.mkdir(parents=True)

            with mock.patch.object(dashboard_main, "RUNTIME_DIR", runtime_dir):
                result = asyncio.run(
                    dashboard_main.api_trading_mode_set(
                        {
                            "mode": "live_trade",
                            "confirm_live": True,
                            "readiness_checklist_id": "live-readiness-v1",
                            "checklist": {
                                "p0_safety_tests_passed": True,
                                "p1_risk_tests_passed": True,
                                "paper_shadow_20d_stable": True,
                                "fee_model_confidence_ok": True,
                                "recent_data_health_ok": True,
                                "broker_no_unknown_open_orders": True,
                                "execution_state_reconciled": True,
                            },
                        }
                    )
                )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["canonical_mode"], "live_trade")
            self.assertEqual(result["mode"], "trade")
            self.assertEqual(result["live_readiness"]["status"], "ready")
            self.assertEqual(result["live_readiness"]["checklist_id"], "live-readiness-v1")

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
