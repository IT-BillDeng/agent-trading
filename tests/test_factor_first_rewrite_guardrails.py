from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ENGINE_SRC = ROOT / "system" / "engine" / "src"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ENGINE_SRC))

from dashboard.scheduler import SignalScheduler


class FactorFirstRewriteGuardrailTests(unittest.TestCase):
    def test_default_execution_guardrails_are_frozen(self):
        app_defaults = json.loads((ROOT / "config" / "app.defaults.json").read_text())
        execution = app_defaults.get("execution", {})

        self.assertEqual(execution.get("submit_mode"), "guarded")
        self.assertIs(execution.get("live_submit"), False)

    def test_default_factor_engine_guardrails_are_frozen(self):
        app_defaults = json.loads((ROOT / "config" / "app.defaults.json").read_text())
        factor_engine = app_defaults.get("factor_engine", {})
        registry = json.loads((ROOT / "factors" / "registry.json").read_text())
        registry_defaults = registry.get("defaults", {})
        factors = registry.get("factors", {})

        self.assertEqual(factor_engine.get("mode"), "shadow")
        self.assertIs(factor_engine.get("allow_actionable_consumption"), False)
        self.assertEqual(registry_defaults.get("mode"), "shadow")
        self.assertIs(registry_defaults.get("allow_actionable_consumption"), False)
        self.assertTrue(all(not bool(item.get("actionable", False)) for item in factors.values()))
        self.assertFalse(any("actionable" in (item.get("usage") or []) for item in factors.values()))

    def test_dashboard_scheduler_remains_preview_only(self):
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

            captured: dict[str, object] = {}

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

            fake_tiger_client = types.ModuleType("engine.tiger_client")
            fake_tiger_client.TigerClient = object

            fake_runtime = types.ModuleType("engine.runtime")
            fake_runtime.fetch_cycle_raw_with_provider = lambda **_kwargs: {}
            fake_runtime.build_strategy_summary = lambda _raw, _app: {"strategy": {"signals": []}}
            fake_runtime.build_execution_summary = lambda _raw, _app: {"strategy": {"signals": []}}

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
                scheduler._persist_cycle_outputs = lambda summary, app: captured.setdefault("summary", summary)
                scheduler._submit_orders = lambda summary, app: captured.__setitem__("submit_called", True)
                scheduler._run_cycle()

            summary = captured["summary"]
            assert isinstance(summary, dict)
            self.assertFalse(captured.get("submit_called", False))
            self.assertEqual(summary["execution_submit"]["count"], 0)
            self.assertTrue(summary["execution_submit"]["disabled"])
            self.assertEqual(summary["execution_submit"]["reason"], "dashboard_scheduler_preview_only")


if __name__ == "__main__":
    unittest.main()
