import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
ENGINE_SRC = ROOT / "system" / "engine" / "src"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ENGINE_SRC))

from dashboard.scheduler import SignalScheduler


class SchedulerSafetyTests(unittest.TestCase):
    def test_scheduler_reads_canonical_signal_only_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime_dir = root / "runtime"
            state_dir = runtime_dir / "state"
            runtime_dir.mkdir(parents=True)
            state_dir.mkdir(parents=True)
            (state_dir / "control_state.json").write_text(
                json.dumps(
                    {
                        "locked": False,
                        "global": {"enabled": True, "mode": "signal_only"},
                        "markets": {"US": True},
                        "symbols": {},
                        "risk": {
                            "reduce_only": False,
                            "emergency_flatten": False,
                            "daily_loss_locked": False,
                        },
                        "history": [],
                    },
                    ensure_ascii=False,
                )
            )

            scheduler = SignalScheduler(
                app_config_path=str(root / "app_config.json"),
                runtime_dir=str(runtime_dir),
                provider_name="yfinance",
                interval_seconds=60,
            )

            self.assertTrue(scheduler._check_trading_mode())
            self.assertEqual(scheduler._get_trading_mode(), "signal_only")

    def test_trade_mode_must_not_escalate_guarded_execution_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runtime_dir = root / "runtime"
            state_dir = runtime_dir / "state"
            config_file = root / "app_config.json"
            runtime_dir.mkdir(parents=True)
            state_dir.mkdir(parents=True)
            config_file.write_text(json.dumps({"system": {}}, ensure_ascii=False))
            (state_dir / "control_state.json").write_text(
                json.dumps(
                    {
                        "locked": False,
                        "global": {"enabled": True, "mode": "paper_trade"},
                        "markets": {"US": True},
                        "symbols": {},
                        "risk": {
                            "reduce_only": False,
                            "emergency_flatten": False,
                            "daily_loss_locked": False,
                        },
                        "history": [],
                    },
                    ensure_ascii=False,
                )
            )

            scheduler = SignalScheduler(
                app_config_path=str(config_file),
                runtime_dir=str(runtime_dir),
                provider_name="yfinance",
                interval_seconds=60,
            )

            captured = {}

            class FakeApp:
                def __init__(self):
                    self.raw = {
                        "execution": {
                            "submit_mode": "guarded",
                            "live_submit": False,
                        },
                        "system": {},
                    }

            def fake_load_app_config(_path):
                return FakeApp()

            fake_config = types.ModuleType("engine.config")
            fake_config.load_app_config = fake_load_app_config
            fake_config.load_tiger_props = lambda _path: object()

            fake_data_provider = types.ModuleType("engine.data_provider")
            fake_data_provider.create_data_provider = lambda _name: object()

            class FakeTigerClient:
                def __init__(self, _props):
                    pass

            fake_tiger_client = types.ModuleType("engine.tiger_client")
            fake_tiger_client.TigerClient = FakeTigerClient

            fake_runtime = types.ModuleType("engine.runtime")
            fake_runtime.fetch_cycle_raw_with_provider = lambda **_kwargs: {}

            def fake_build_strategy_summary(_raw, _app):
                return {"strategy": {"signals": []}}

            def fake_build_execution_summary(_raw, app):
                captured["submit_mode"] = app.raw["execution"]["submit_mode"]
                captured["live_submit"] = app.raw["execution"]["live_submit"]
                return {"strategy": {"signals": []}}

            fake_runtime.build_strategy_summary = fake_build_strategy_summary
            fake_runtime.build_execution_summary = fake_build_execution_summary

            fake_engine = types.ModuleType("engine")
            fake_engine.__path__ = []

            with patch.dict(
                sys.modules,
                {
                    "engine": fake_engine,
                    "engine.config": fake_config,
                    "engine.data_provider": fake_data_provider,
                    "engine.tiger_client": fake_tiger_client,
                    "engine.runtime": fake_runtime,
                },
            ):
                scheduler._submit_orders = lambda summary, app: None
                scheduler._persist_cycle_outputs = lambda summary, app: None
                scheduler._run_cycle()

            self.assertEqual(captured["submit_mode"], "guarded")
            self.assertFalse(captured["live_submit"])


if __name__ == "__main__":
    unittest.main()
