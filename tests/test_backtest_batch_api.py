import asyncio
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from dashboard import main as dashboard_main


def _build_rules_fixture() -> dict:
    return {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "trend_follow_30m",
                "enabled": False,
                "entry": {
                    "conditions": {
                        "items": [
                            {"params": {"period": 5}},
                            {"params": {"period": 10}},
                            {"params": {"period": 20}},
                            {"params": {"period": 3}, "compare": {"value": 0.003}},
                            {"compare": {"value": 0.04}},
                        ]
                    }
                },
            },
            {
                "rule_id": "rsi_reversal",
                "enabled": True,
                "entry": {
                    "conditions": {
                        "items": [
                            {"params": {"period": 14}, "compare": {"value": 30}},
                        ]
                    }
                },
                "exit": {
                    "conditions": {
                        "items": [
                            {"compare": {"value": 70}},
                            {"threshold_pct": 0.02},
                        ]
                    }
                },
            },
            {
                "rule_id": "bollinger_breakout",
                "enabled": True,
                "entry": {
                    "conditions": {
                        "items": [
                            {"params": {"period": 20, "std_dev": 2}},
                            {"ratio": 1.2},
                        ]
                    }
                },
                "exit": {
                    "conditions": {
                        "items": [
                            {"compare": {"value": 0}},
                            {"threshold_pct": 0.03},
                        ]
                    }
                },
            },
        ],
    }


class FakeBacktestConfig:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeBacktestResult:
    def __init__(self, total_return_pct: float, total_trades: int = 3):
        self.total_return_pct = total_return_pct
        self.total_trades = total_trades

    def to_dict(self):
        return {
            "total_trades": self.total_trades,
            "total_return_pct": self.total_return_pct,
            "win_rate": 0.5,
            "sharpe_ratio": 1.2,
            "max_drawdown_pct": 4.2,
            "winning_trades": 2,
            "losing_trades": 1,
        }


class BacktestBatchApiTests(unittest.TestCase):
    def test_apply_param_overrides_updates_enabled_and_nested_fields(self):
        rules = _build_rules_fixture()

        dashboard_main._apply_param_overrides(
            rules,
            {
                "trend_follow_enabled": True,
                "rsi_enabled": False,
                "bollinger_enabled": False,
                "sma_short": 7,
                "momentum_threshold": 0.005,
                "bb_std": 2.5,
                "rsi_reversal.exit.conditions.items.1.threshold_pct": 0.08,
            },
        )

        by_id = {rule["rule_id"]: rule for rule in rules["rules"]}
        self.assertTrue(by_id["trend_follow_30m"]["enabled"])
        self.assertFalse(by_id["rsi_reversal"]["enabled"])
        self.assertFalse(by_id["bollinger_breakout"]["enabled"])
        self.assertEqual(
            by_id["trend_follow_30m"]["entry"]["conditions"]["items"][0]["params"]["period"],
            7,
        )
        self.assertEqual(
            by_id["trend_follow_30m"]["entry"]["conditions"]["items"][3]["compare"]["value"],
            0.005,
        )
        self.assertEqual(
            by_id["bollinger_breakout"]["entry"]["conditions"]["items"][0]["params"]["std_dev"],
            2.5,
        )
        self.assertEqual(
            by_id["rsi_reversal"]["exit"]["conditions"]["items"][1]["threshold_pct"],
            0.08,
        )

    def test_api_backtest_batch_uses_temp_rules_file_with_overrides(self):
        base_rules = _build_rules_fixture()
        captured_runs = []

        def fake_run_backtest(config, rules_path):
            path = Path(rules_path)
            captured_runs.append(
                {
                    "config": dict(config.__dict__),
                    "rules_path": path,
                    "rules": json.loads(path.read_text()),
                    "exists_during_run": path.exists(),
                }
            )
            total_return_pct = 1.0 if "baseline" in path.name else 9.5
            return FakeBacktestResult(total_return_pct=total_return_pct)

        fake_backtest_module = types.ModuleType("engine.backtest")
        fake_backtest_module.BacktestConfig = FakeBacktestConfig
        fake_backtest_module.run_backtest = fake_run_backtest
        fake_engine_module = types.ModuleType("engine")
        fake_engine_module.backtest = fake_backtest_module

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifacts_dir = root / "artifacts"
            strategist_artifacts_dir = artifacts_dir / "strategist"
            strategist_memory_dir = strategist_artifacts_dir / "memory"
            strategist_iterations_artifact_dir = strategist_artifacts_dir / "iterations"
            rules_dir = root / "rules"
            runtime_dir = root / "runtime"
            logs_dir = root / "logs"
            strategist_iterations_dir = logs_dir / "agents" / "strategist" / "iterations"
            artifacts_dir.mkdir()
            rules_dir.mkdir()
            runtime_dir.mkdir()
            rules_file = rules_dir / "rules.json"
            rules_file.write_text(json.dumps(base_rules, indent=2, ensure_ascii=False))

            body = {
                "symbols": ["AAPL"],
                "start_date": "2026-01-07",
                "end_date": "2026-04-07",
                "timeframe": "30min",
                "data_source": "yfinance",
                "param_sets": [
                    {"label": "baseline", "params": {}},
                    {
                        "label": "enabled_variant",
                        "params": {
                            "trend_follow_enabled": True,
                            "sma_short": 7,
                        },
                    },
                ],
            }

            with mock.patch.object(dashboard_main, "RULES_DIR", rules_dir), \
                mock.patch.object(dashboard_main, "RULES_FILE", rules_file), \
                mock.patch.object(dashboard_main, "ARTIFACTS_ROOT", artifacts_dir), \
                mock.patch.object(dashboard_main, "STRATEGIST_ARTIFACTS_DIR", strategist_artifacts_dir), \
                mock.patch.object(dashboard_main, "STRATEGIST_MEMORY_DIR", strategist_memory_dir), \
                mock.patch.object(dashboard_main, "STRATEGIST_ITERATIONS_ARTIFACT_DIR", strategist_iterations_artifact_dir), \
                mock.patch.object(dashboard_main, "RUNTIME_DIR", runtime_dir), \
                mock.patch.object(dashboard_main, "STRATEGIST_ITERATIONS_LOG_DIR", strategist_iterations_dir), \
                mock.patch.dict(
                    sys.modules,
                    {
                        "engine": fake_engine_module,
                        "engine.backtest": fake_backtest_module,
                    },
                ):
                result = asyncio.run(dashboard_main.api_backtest_batch(body))
                self.assertEqual(result["status"], "ok")
                self.assertEqual(len(result["results"]), 2)
                self.assertEqual(len(captured_runs), 2)

                baseline_run, variant_run = captured_runs

                self.assertTrue(baseline_run["exists_during_run"])
                self.assertTrue(variant_run["exists_during_run"])
                self.assertNotEqual(baseline_run["rules_path"], rules_file)
                self.assertNotEqual(variant_run["rules_path"], rules_file)

                baseline_by_id = {rule["rule_id"]: rule for rule in baseline_run["rules"]["rules"]}
                variant_by_id = {rule["rule_id"]: rule for rule in variant_run["rules"]["rules"]}

                self.assertFalse(baseline_by_id["trend_follow_30m"]["enabled"])
                self.assertEqual(
                    baseline_by_id["trend_follow_30m"]["entry"]["conditions"]["items"][0]["params"]["period"],
                    5,
                )
                self.assertTrue(variant_by_id["trend_follow_30m"]["enabled"])
                self.assertEqual(
                    variant_by_id["trend_follow_30m"]["entry"]["conditions"]["items"][0]["params"]["period"],
                    7,
                )

                self.assertFalse((rules_dir / "_batch_baseline.json").exists())
                self.assertFalse((rules_dir / "_batch_enabled_variant.json").exists())

                iteration_files = list(strategist_iterations_artifact_dir.glob("iter_*.json"))
                self.assertEqual(len(iteration_files), 1)
                iteration_data = json.loads(iteration_files[0].read_text())
                self.assertEqual(iteration_data["best"]["label"], "enabled_variant")
                self.assertEqual(iteration_data["results"][1]["return_pct"], 9.5)

                legacy_iteration_files = list((runtime_dir / "strategist_iterations").glob("iter_*.json"))
                self.assertEqual(len(legacy_iteration_files), 1)
                legacy_iteration_data = json.loads(legacy_iteration_files[0].read_text())
                self.assertEqual(legacy_iteration_data["iteration_id"], iteration_data["iteration_id"])

                mirrored_iteration_files = list(strategist_iterations_dir.glob("iter_*.json"))
                self.assertEqual(len(mirrored_iteration_files), 1)
                mirrored_data = json.loads(mirrored_iteration_files[0].read_text())
                self.assertEqual(mirrored_data["iteration_id"], iteration_data["iteration_id"])

                self.assertTrue((strategist_iterations_artifact_dir / "latest.json").exists())
                self.assertTrue((runtime_dir / "strategist_iterations" / "latest.json").exists())
                self.assertTrue((strategist_iterations_dir / "latest.json").exists())


if __name__ == "__main__":
    unittest.main()
