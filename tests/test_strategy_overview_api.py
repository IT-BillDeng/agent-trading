import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dashboard import main as dashboard_main


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

            (config_dir).mkdir(parents=True)
            (runtime_dir / "state").mkdir(parents=True)
            (runtime_dir / "strategist_iterations").mkdir(parents=True)
            (rules_dir).mkdir(parents=True)
            latest_dir.mkdir(parents=True)
            strategist_logs_dir.mkdir(parents=True)

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
                "quote_access": {"US": True},
                "market_state": {"US": {"state": "OPEN"}},
            }, ensure_ascii=False))

            (runtime_dir / "strategy_plan_latest.json").write_text(json.dumps({
                "plan_id": "plan-1",
                "generated_at": "2026-04-16T10:00:00",
                "generator": "tiger-strategist",
                "data_quality": "ok",
                "summary": "继续跟踪 MSFT / AAPL",
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

            with mock.patch.object(dashboard_main, "CONFIG_DIR_PATH", config_dir), \
                mock.patch.object(dashboard_main, "RULES_DIR", rules_dir), \
                mock.patch.object(dashboard_main, "RULES_FILE", rules_dir / "rules.json"), \
                mock.patch.object(dashboard_main, "RUNTIME_DIR", runtime_dir), \
                mock.patch.object(dashboard_main, "LOGS_ROOT", logs_root), \
                mock.patch.object(dashboard_main, "LATEST_LOG_DIR", latest_dir), \
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
            self.assertEqual(len(overview["plan_history"]), 1)
            self.assertEqual(len(overview["iterations"]), 1)
            self.assertTrue((latest_dir / "strategy_overview.json").exists())


if __name__ == "__main__":
    unittest.main()
