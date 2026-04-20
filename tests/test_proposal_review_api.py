import asyncio
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ENGINE_SRC = Path(__file__).resolve().parents[1] / "system" / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))


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

from engine.strategist_artifacts import queue_approval_request


class ProposalReviewApiTests(unittest.TestCase):
    def _write_fee_summary(self, artifacts_dir: Path):
        broker_dir = artifacts_dir / "broker"
        broker_dir.mkdir(parents=True, exist_ok=True)
        (broker_dir / "fee_calibration_summary.json").write_text(
            json.dumps(
                {
                    "count": 4,
                    "avg_delta": 0.02,
                    "max_abs_delta": 0.08,
                    "trust": {
                        "level": "high",
                        "label": "可信",
                        "reason": "recent deltas acceptable",
                    },
                },
                ensure_ascii=False,
            )
        )

    def test_proposal_list_and_detail_expose_review_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                self._write_fee_summary(artifacts_dir)
                queue_approval_request(
                    "prop_review_1",
                    {
                        "proposal_id": "prop_review_1",
                        "status": "awaiting_approval",
                        "target_files": ["rules/rules.json"],
                        "recommended_update_mode": "hot",
                        "requires_restart": False,
                        "diff_summary": "enable low-turnover buy rule",
                        "validation": {
                            "tests": [{"name": "unit", "passed": True}],
                            "backtest": {"return_pct": 3.2},
                            "risk": {"notes": ["low turnover only"]},
                            "fee_confidence": "high",
                        },
                    },
                    base_dir=artifacts_dir,
                )

                with mock.patch.object(dashboard_main, "ARTIFACTS_ROOT", artifacts_dir):
                    listing = asyncio.run(dashboard_main.api_strategy_proposals())
                    detail = asyncio.run(dashboard_main.api_strategy_proposal_detail("prop_review_1"))
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertEqual(len(listing["items"]), 1)
            item = listing["items"][0]
            self.assertEqual(item["proposal_id"], "prop_review_1")
            self.assertEqual(item["status"], "awaiting_approval")
            self.assertEqual(item["recommended_update_mode"], "hot")
            self.assertFalse(item["requires_restart"])
            self.assertEqual(item["validation"]["fee_confidence"], "high")

            self.assertEqual(detail["proposal_id"], "prop_review_1")
            self.assertEqual(detail["diff_summary"], "enable low-turnover buy rule")
            self.assertEqual(detail["validation"]["backtest"]["return_pct"], 3.2)

    def test_approve_and_reject_write_decision_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                queue_approval_request(
                    "prop_approve",
                    {
                        "proposal_id": "prop_approve",
                        "status": "awaiting_approval",
                        "target_files": ["rules/rules.json"],
                        "recommended_update_mode": "hot",
                    },
                    base_dir=artifacts_dir,
                )
                queue_approval_request(
                    "prop_reject",
                    {
                        "proposal_id": "prop_reject",
                        "status": "awaiting_approval",
                        "target_files": ["rules/rules.json"],
                        "recommended_update_mode": "hot",
                    },
                    base_dir=artifacts_dir,
                )

                with mock.patch.object(dashboard_main, "ARTIFACTS_ROOT", artifacts_dir):
                    approve_result = asyncio.run(
                        dashboard_main.api_strategy_proposal_approve(
                            "prop_approve",
                            {"decider_type": "human", "decider_id": "teacher"},
                        )
                    )
                    reject_result = asyncio.run(
                        dashboard_main.api_strategy_proposal_reject(
                            "prop_reject",
                            {"decider_type": "agent", "decider_id": "main-agent", "reason": "insufficient evidence"},
                        )
                    )
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertEqual(approve_result["decision"], "approved")
            self.assertEqual(reject_result["decision"], "rejected")

            queue_approved = json.loads((artifacts_dir / "strategist" / "approval_queue" / "prop_approve.json").read_text())
            queue_rejected = json.loads((artifacts_dir / "strategist" / "approval_queue" / "prop_reject.json").read_text())
            decisions = [
                json.loads(line)
                for line in (artifacts_dir / "strategist" / "approval_decisions.jsonl").read_text().splitlines()
            ]

            self.assertEqual(queue_approved["status"], "approved")
            self.assertEqual(queue_rejected["status"], "rejected")
            self.assertEqual(decisions[0]["decision"], "approved")
            self.assertEqual(decisions[1]["decision"], "rejected")

    def test_invalid_transition_returns_400(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifacts_dir = Path(tmpdir) / "artifacts"
            old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
            os.environ["ENGINE_ARTIFACTS_DIR"] = str(artifacts_dir)
            try:
                queue_approval_request(
                    "prop_draft",
                    {
                        "proposal_id": "prop_draft",
                        "status": "draft",
                        "target_files": ["rules/rules.json"],
                        "recommended_update_mode": "hot",
                    },
                    base_dir=artifacts_dir,
                )
                with mock.patch.object(dashboard_main, "ARTIFACTS_ROOT", artifacts_dir):
                    result = asyncio.run(
                        dashboard_main.api_strategy_proposal_approve(
                            "prop_draft",
                            {"decider_type": "human", "decider_id": "teacher"},
                        )
                    )
            finally:
                if old_env is None:
                    os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
                else:
                    os.environ["ENGINE_ARTIFACTS_DIR"] = old_env

            self.assertEqual(result.status_code, 400)
            self.assertIn("invalid approval transition", result["error"])


if __name__ == "__main__":
    unittest.main()
