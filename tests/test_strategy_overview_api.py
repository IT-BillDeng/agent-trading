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
            factor_research_dir = root / "artifacts" / "factor_research"
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
            (factor_research_dir / "reports").mkdir(parents=True)
            (factor_research_dir / "diagnostic_rule_link_trial").mkdir(parents=True)
            (factor_research_dir / "diagnostic_metrics" / "reports").mkdir(parents=True)
            (factor_research_dir / "ops" / "reports").mkdir(parents=True)
            (factor_research_dir / "facts" / "reports").mkdir(parents=True)
            (factor_research_dir / "scenarios" / "reports").mkdir(parents=True)
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
            (rules_dir / "diagnostic_factor_rules.json").write_text(json.dumps({
                "schema_version": 1,
                "kind": "diagnostic_factor_rules",
                "diagnostic_only": True,
                "production_rules_modified": False,
                "rules": [
                    {
                        "rule_id": "diag_rsi_reversal_rsi_14_30m",
                        "source_rule_id": "rsi_reversal",
                        "diagnostic_only": True,
                        "enabled": False,
                        "mode": "diagnostic",
                        "factors": ["rsi_14_30m"],
                        "conditions": [
                            {
                                "type": "factor",
                                "factor_id": "rsi_14_30m",
                                "operator": "cross_above",
                                "value": 30,
                            }
                        ],
                        "created_from_proposal_id": "frule_diag_1",
                        "created_at": "2026-04-16T12:35:00+00:00",
                        "apply_allowed": False,
                        "entered_risk": False,
                        "entered_execution": False,
                        "entered_order_intents": False,
                    }
                ],
            }, ensure_ascii=False, indent=2))
            with (strategist_artifacts_dir / "deployment_records.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "proposal_id": "frule_diag_1",
                    "proposal_type": "factor_rule_link",
                    "apply_mode": "hot_diagnostic_only",
                    "target_file": "rules/diagnostic_factor_rules.json",
                    "success": True,
                    "applied_at": "2026-04-16T12:35:00+00:00",
                    "changed_diagnostic_rules": ["diag_rsi_reversal_rsi_14_30m"],
                    "approval_decision_snapshot": {
                        "proposal_id": "frule_diag_1",
                        "decision": "approved",
                        "decider_type": "main_agent",
                        "decider_id": "main_agent_test",
                        "decided_at": "2026-04-16T12:34:59+00:00",
                    },
                    "production_rules_modified": False,
                    "actionable_enabled": False,
                }, ensure_ascii=False) + "\n")
            (factor_research_dir / "diagnostic_rule_link_trial" / "latest.json").write_text(json.dumps({
                "latest_trial_mode": "prepare_real_approval",
                "latest_proposal_id": "frule_diag_1",
                "latest_approval_request_path": "artifacts/factor_research/diagnostic_rule_link_trial/approval_request.md",
                "latest_diagnostic_rule_ids": ["diag_rsi_reversal_rsi_14_30m"],
                "latest_source_rule_ids": ["rsi_reversal"],
                "latest_factor_ids": ["rsi_14_30m"],
                "real_apply_ready": False,
                "approval_decision_snapshot_present": False,
                "production_rules_modified": False,
                "actionable_enabled": False,
            }, ensure_ascii=False))
            (factor_research_dir / "diagnostic_metrics" / "latest.json").write_text(json.dumps({
                "generated_at": "2026-04-16T12:45:00+00:00",
                "status": "ok",
                "sample_source": "historical_backfill",
                "sample_sources": ["historical_backfill"],
                "rule_count": 1,
                "evaluated_rule_count": 1,
                "insufficient_rule_count": 0,
                "watchlist_candidate_count": 0,
                "label_join_summary": {
                    "total_events": 3,
                    "joined_events": 3,
                    "unjoined_events": 0,
                    "join_rate": 1.0,
                    "reasons_count": {},
                    "live_joined_events": 0,
                    "backfill_joined_events": 3,
                    "live_unjoined_events": 0,
                    "backfill_unjoined_events": 0,
                },
                "events_path": "artifacts/factor_research/diagnostic_metrics/events/latest.jsonl",
                "events_summary_path": "artifacts/factor_research/diagnostic_metrics/events/summary.json",
                "top_label_join_blockers": [],
                "backfill_replay_available": True,
                "backfill_joined_events": 3,
                "live_joined_events": 0,
                "top_diagnostic_rules": [
                    {
                        "rule_id": "diag_rsi_reversal_rsi_14_30m",
                        "source_rule_id": "rsi_reversal",
                        "factor_ids": ["rsi_14_30m"],
                        "evaluation_status": "research_only",
                        "sample_source": "historical_backfill",
                        "signal_count": 3,
                        "labeled_sample_count": 5,
                        "IC_1bar": 0.42,
                        "hit_rate_1bar": 0.6,
                        "live_shadow_days_observed": 0,
                    }
                ],
                "report_path": "artifacts/factor_research/diagnostic_metrics/reports/latest.md",
            }, ensure_ascii=False))
            (factor_research_dir / "diagnostic_metrics" / "reports" / "latest.md").write_text("# Diagnostic Factor Metrics\n")
            (factor_research_dir / "ops" / "latest.json").write_text(json.dumps({
                "generated_at": "2026-04-16T13:00:00+00:00",
                "promotion_readiness": "collecting_live_shadow",
                "promotion_blockers": ["insufficient_live_shadow_days", "insufficient_live_labeled_events"],
                "live_shadow_days_observed": 2,
                "live_labeled_events": 0,
                "backfill_labeled_events": 3,
                "mixed_labeled_events": 3,
                "dual_run_readiness_status": "ready",
                "dual_run_blocking_mismatch_count": 0,
                "diagnostic_rule_count": 1,
                "diagnostic_signal_count": 3,
                "label_join_rate": 1.0,
                "top_label_join_blockers": [],
                "backfill_symbol_count": 6,
                "backfill_observation_count": 5760,
                "app_universe_symbols": ["AAPL", "AMZN", "BILI", "GOOGL", "INTC", "MSFT", "NVDA", "QQQ", "SMCI", "TSLA"],
                "backfill_universe_symbols": ["AAPL", "AMZN", "GOOGL", "MSFT", "NVDA", "SMCI"],
                "missing_backfill_symbols": ["BILI", "INTC", "QQQ", "TSLA"],
                "report_path": "artifacts/factor_research/ops/reports/latest.md",
            }, ensure_ascii=False))
            (factor_research_dir / "ops" / "reports" / "latest.md").write_text("# Factor Research Ops Summary\n")

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
            (factor_artifacts_dir / "history" / "2026-04-16.jsonl").write_text(
                (factor_artifacts_dir / "latest.json").read_text() + "\n"
            )

            backfill_dir = factor_research_dir / "datasets" / "backfill"
            backfill_dir.mkdir(parents=True)
            (backfill_dir / "latest.jsonl").write_text(json.dumps({
                "observation_id": "AAPL|rsi_14_30m|2026-04-15T15:30:00-04:00|factor-hash-1|historical_backfill",
                "source": "historical_backfill",
                "symbol": "AAPL",
                "factor_id": "rsi_14_30m",
                "value": 41.0,
                "ready": True,
                "factor_timestamp": "2026-04-15T16:00:00-04:00",
                "source_bar_time": "2026-04-15T15:30:00-04:00",
                "source_bar_is_complete": True,
                "registry_config_hash": "factor-hash-1",
                "dataset_id": "unit_backfill",
            }, ensure_ascii=False) + "\n")

            (factor_research_dir / "latest.json").write_text(json.dumps({
                "generated_at": "2026-04-16T11:00:00+00:00",
                "status": "ok",
                "factor_count": 2,
                "factors_with_insufficient_samples": ["return_5_30m"],
                "top_coverage_factors": [
                    {"factor_id": "rsi_14_30m", "coverage": 1.0, "sample_count": 12},
                ],
                "high_redundancy_pairs": [
                    {
                        "factor_pair": ["rsi_14_30m", "return_5_30m"],
                        "correlation": 0.91,
                        "sample_count": 12,
                        "redundancy_hint": "high",
                    }
                ],
                "hypothesis_count": 1,
                "factor_validation_summary": {
                    "latest_generated_at": "2026-04-16T11:00:00+00:00",
                    "sample_source": "historical_backfill",
                    "factor_count": 2,
                    "labeled_sample_count": 31,
                    "insufficient_factor_count": 1,
                    "research_candidate_count": 1,
                    "high_redundancy_pair_count": 1,
                    "top_candidate_factors": [
                        {
                            "factor_id": "rsi_14_30m",
                            "candidate_grade": "research_candidate",
                            "IC_1bar": 0.11,
                            "coverage": 0.9,
                            "labeled_sample_count": 31,
                        }
                    ],
                    "blocked_reasons": {"min_labeled_samples": 1},
                    "candidate_grade_distribution": {"research_candidate": 1, "insufficient": 1},
                    "no_lookahead_validation_status": "pass",
                    "report_path": str(factor_research_dir / "reports" / "latest.md"),
                },
                "report_path": str(factor_research_dir / "reports" / "latest.md"),
            }, ensure_ascii=False))
            (factor_research_dir / "reports" / "latest.md").write_text("# Factor Research Summary\n")
            (factor_research_dir / "hypotheses.jsonl").write_text(json.dumps({
                "hypothesis_id": "fexp_test",
                "status": "draft",
                "apply_allowed": False,
            }, ensure_ascii=False) + "\n")
            (factor_research_dir / "facts" / "latest.json").write_text(json.dumps({
                "generated_at": "2026-04-16T13:05:00+00:00",
                "status": "ok",
                "fact_count": 8,
                "fact_type_counts": {
                    "factor_observation": 2,
                    "dual_run_readiness": 1,
                    "label_join_blocker": 1,
                    "approval_decision": 1,
                    "deployment_record": 1,
                    "data_quality_blocker": 2,
                },
                "usage_counts": {
                    "debug_only": 5,
                    "research_context": 2,
                    "label": 1,
                },
                "leakage_warnings": ["label_facts_must_not_be_used_as_factor_inputs"],
                "report_path": "artifacts/factor_research/facts/reports/latest.md",
            }, ensure_ascii=False))
            (factor_research_dir / "scenarios" / "latest.json").write_text(json.dumps({
                "generated_at": "2026-04-16T13:05:00+00:00",
                "scenario_count": 2,
                "top_debug_scenarios": [
                    {
                        "scenario_id": "scenario_dual_run_ready_1",
                        "scenario_type": "dual_run_ready",
                        "symbols": ["AAPL"],
                        "time_window": {"start": "2026-04-16T12:30:00+00:00", "end": "2026-04-16T12:31:00+00:00"},
                        "debug_goal": "Replay dual-run readiness.",
                        "replay_command_hint": "python -m engine.factors.facts summarize",
                        "expected_invariants": ["debug replay only"],
                    }
                ],
                "leakage_warnings": ["label_facts_must_not_be_used_as_factor_inputs"],
                "report_path": "artifacts/factor_research/scenarios/reports/latest.md",
            }, ensure_ascii=False))
            parity_dir = factor_research_dir / "parity"
            (parity_dir / "reports").mkdir(parents=True)
            (parity_dir / "latest.json").write_text(json.dumps({
                "generated_at": "2026-04-16T12:00:00+00:00",
                "factor_count": 8,
                "compared_factor_count": 8,
                "parity_pass_count": 8,
                "parity_fail_count": 0,
                "blocking_mismatch_count": 0,
                "warning_mismatch_count": 1,
                "signal_parity_pass_count": 2,
                "signal_parity_fail_count": 0,
                "report_path": str(parity_dir / "reports" / "latest.md"),
                "top_mismatches": [
                    {
                        "factor_id": "volume_ratio_20_30m",
                        "symbol": "AAPL",
                        "reason": "missing_volume",
                        "severity": "warning",
                        "delta": None,
                    }
                ],
            }, ensure_ascii=False))
            (parity_dir / "reports" / "latest.md").write_text("# Factor Parity Summary\n")
            dual_run_dir = factor_research_dir / "dual_run"
            (dual_run_dir / "reports").mkdir(parents=True)
            (dual_run_dir / "latest.json").write_text(json.dumps({
                "generated_at": "2026-04-16T12:30:00+00:00",
                "enabled": True,
                "compared_count": 2,
                "matched_count": 2,
                "mismatch_count": 0,
                "blocking_mismatch_count": 0,
                "warning_mismatch_count": 0,
                "matched_rate": 1.0,
                "compared_rules": ["rsi_reversal", "bollinger_breakout"],
                "compared_symbols": ["AAPL", "MSFT"],
                "real_universe_symbols_detected": True,
                "synthetic_fixture_symbols_detected": False,
                "source_bar_session_summary": {"regular": 2},
                "production_path_unchanged": True,
                "report_path": "artifacts/factor_research/dual_run/reports/latest.md",
                "top_mismatches": [],
            }, ensure_ascii=False))
            (dual_run_dir / "reports" / "latest.md").write_text("# Factor Dual-Run Summary\n")
            (dual_run_dir / "observations").mkdir(parents=True)
            (dual_run_dir / "observations" / "latest.json").write_text(json.dumps({
                "observed_at": "2026-04-16T12:31:00+00:00",
                "observation_generated_at": "2026-04-16T12:31:00+00:00",
                "cycle_generated_at": "2026-04-16T12:30:00+00:00",
                "artifact_age_seconds": 60,
                "artifact_is_stale": False,
                "cycle_run_attempted": True,
                "cycle_run_succeeded": True,
                "cycle_run_skipped": False,
                "readiness_status": "ready",
                "readiness_reasons": [],
                "app_universe_symbols": ["AAPL", "MSFT"],
                "compared_count": 2,
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
                "results": [
                    {
                        "label": "base",
                        "params": {},
                        "trades": 4,
                        "return_pct": 2.5,
                        "factor_attribution_summary": {
                            "available": True,
                            "registry_hash": "registry-hash-1",
                            "horizons": [1, 2],
                            "top_factors": [
                                {
                                    "factor_id": "rsi_14_30m",
                                    "coverage": 1.0,
                                    "missing_rate": 0.0,
                                    "ic_1bar": 0.22,
                                    "rank_ic_1bar": 0.2,
                                    "sample_count": 12,
                                }
                            ],
                        },
                    }
                ],
                "best": {
                    "label": "base",
                    "return_pct": 2.5,
                    "factor_attribution_summary": {
                        "available": True,
                        "registry_hash": "registry-hash-1",
                        "horizons": [1, 2],
                        "top_factors": [
                            {
                                "factor_id": "rsi_14_30m",
                                "coverage": 1.0,
                                "missing_rate": 0.0,
                                "ic_1bar": 0.22,
                                "rank_ic_1bar": 0.2,
                                "sample_count": 12,
                            }
                        ],
                    },
                },
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
                mock.patch.object(dashboard_main, "FACTOR_RESEARCH_ARTIFACTS_DIR", factor_research_dir), \
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
            self.assertEqual(overview["factor_research"]["generated_at"], "2026-04-16T11:00:00+00:00")
            self.assertEqual(overview["factor_research"]["factor_count"], 2)
            self.assertEqual(overview["factor_research"]["factors_with_insufficient_samples"], ["return_5_30m"])
            self.assertEqual(overview["factor_research"]["top_coverage_factors"][0]["factor_id"], "rsi_14_30m")
            self.assertEqual(overview["factor_research"]["high_redundancy_pairs"][0]["redundancy_hint"], "high")
            self.assertEqual(overview["factor_research"]["hypothesis_count"], 1)
            self.assertTrue(overview["factor_research"]["last_report_path"].endswith("reports/latest.md"))
            self.assertTrue(overview["factor_sample_health"]["latest_exists"])
            self.assertEqual(overview["factor_sample_health"]["history_count"], 1)
            self.assertEqual(overview["factor_sample_health"]["live_observation_count"], 1)
            self.assertEqual(overview["factor_sample_health"]["backfill_observation_count"], 1)
            self.assertIn("live_shadow", overview["factor_sample_health"]["sample_sources"])
            self.assertIn("historical_backfill", overview["factor_sample_health"]["sample_sources"])
            self.assertEqual(overview["factor_validation_summary"]["sample_source"], "historical_backfill")
            self.assertEqual(overview["factor_validation_summary"]["labeled_sample_count"], 31)
            self.assertEqual(overview["factor_validation_summary"]["research_candidate_count"], 1)
            self.assertEqual(overview["factor_validation_summary"]["top_candidate_factors"][0]["factor_id"], "rsi_14_30m")
            self.assertEqual(overview["factor_parity_summary"]["compared_factor_count"], 8)
            self.assertEqual(overview["factor_parity_summary"]["parity_pass_count"], 8)
            self.assertEqual(overview["factor_parity_summary"]["signal_parity_pass_count"], 2)
            self.assertEqual(overview["factor_parity_summary"]["top_mismatches"][0]["reason"], "missing_volume")
            self.assertTrue(overview["factor_dual_run_summary"]["enabled"])
            self.assertEqual(overview["factor_dual_run_summary"]["compared_count"], 2)
            self.assertEqual(overview["factor_dual_run_summary"]["matched_count"], 2)
            self.assertEqual(overview["factor_dual_run_summary"]["blocking_mismatch_count"], 0)
            self.assertEqual(overview["factor_dual_run_summary"]["compared_rules"], ["rsi_reversal", "bollinger_breakout"])
            self.assertEqual(overview["factor_dual_run_summary"]["compared_symbols"], ["AAPL", "MSFT"])
            self.assertTrue(overview["factor_dual_run_summary"]["real_universe_symbols_detected"])
            self.assertFalse(overview["factor_dual_run_summary"]["synthetic_fixture_symbols_detected"])
            self.assertEqual(overview["factor_dual_run_summary"]["latest_observation_path"], "artifacts/factor_research/dual_run/observations/latest.json")
            self.assertEqual(overview["factor_dual_run_summary"]["source_bar_session_summary"], {"regular": 2})
            self.assertTrue(overview["factor_dual_run_summary"]["production_path_unchanged"])
            self.assertEqual(overview["factor_dual_run_summary"]["readiness_status"], "ready")
            self.assertEqual(overview["factor_dual_run_summary"]["readiness_reasons"], [])
            self.assertFalse(overview["factor_dual_run_summary"]["artifact_is_stale"])
            self.assertEqual(overview["factor_dual_run_summary"]["artifact_age_seconds"], 60)
            self.assertTrue(overview["factor_dual_run_summary"]["cycle_run_attempted"])
            self.assertTrue(overview["factor_dual_run_summary"]["cycle_run_succeeded"])
            self.assertFalse(overview["factor_dual_run_summary"]["cycle_run_skipped"])
            self.assertFalse(overview["factor_dual_run_summary"]["report_path"].startswith("/"))
            self.assertTrue(overview["diagnostic_factor_rules_summary"]["exists"])
            self.assertTrue(overview["diagnostic_factor_rules_summary"]["valid"])
            self.assertEqual(overview["diagnostic_factor_rules_summary"]["rule_count"], 1)
            self.assertEqual(overview["diagnostic_factor_rules_summary"]["enabled_count"], 0)
            self.assertEqual(overview["diagnostic_factor_rules_summary"]["diagnostic_only_count"], 1)
            self.assertEqual(overview["diagnostic_factor_rules_summary"]["source_rules"], ["rsi_reversal"])
            self.assertEqual(overview["diagnostic_factor_rules_summary"]["factor_ids"], ["rsi_14_30m"])
            self.assertEqual(
                overview["diagnostic_factor_rules_summary"]["latest_diagnostic_rule_ids"],
                ["diag_rsi_reversal_rsi_14_30m"],
            )
            self.assertEqual(overview["diagnostic_factor_rules_summary"]["latest_source_rule_ids"], ["rsi_reversal"])
            self.assertEqual(overview["diagnostic_factor_rules_summary"]["latest_factor_ids"], ["rsi_14_30m"])
            self.assertEqual(
                overview["diagnostic_factor_rules_summary"]["target_file"],
                "rules/diagnostic_factor_rules.json",
            )
            self.assertFalse(overview["diagnostic_factor_rules_summary"]["production_rules_modified"])
            self.assertFalse(overview["diagnostic_factor_rules_summary"]["actionable_enabled"])
            self.assertTrue(overview["diagnostic_factor_rules_summary"]["approval_decision_snapshot_present"])
            self.assertEqual(overview["diagnostic_factor_rules_summary"]["last_deployment_record_id"], "frule_diag_1")
            self.assertFalse(overview["diagnostic_factor_rules_summary"]["real_apply_ready"])
            self.assertEqual(overview["diagnostic_factor_rules_summary"]["latest_trial_mode"], "prepare_real_approval")
            self.assertEqual(overview["diagnostic_factor_rules_summary"]["latest_proposal_id"], "frule_diag_1")
            self.assertEqual(
                overview["diagnostic_factor_rules_summary"]["latest_approval_request_path"],
                "artifacts/factor_research/diagnostic_rule_link_trial/approval_request.md",
            )
            self.assertEqual(
                overview["diagnostic_factor_rules_summary"]["last_apply"]["proposal_id"],
                "frule_diag_1",
            )
            self.assertTrue(overview["diagnostic_factor_metrics_summary"]["available"])
            self.assertEqual(overview["diagnostic_factor_metrics_summary"]["rule_count"], 1)
            self.assertEqual(overview["diagnostic_factor_metrics_summary"]["evaluated_rule_count"], 1)
            self.assertEqual(overview["diagnostic_factor_metrics_summary"]["insufficient_rule_count"], 0)
            self.assertEqual(overview["diagnostic_factor_metrics_summary"]["sample_sources"], ["historical_backfill"])
            self.assertEqual(
                overview["diagnostic_factor_metrics_summary"]["top_diagnostic_rules"][0]["rule_id"],
                "diag_rsi_reversal_rsi_14_30m",
            )
            self.assertEqual(
                overview["diagnostic_factor_metrics_summary"]["report_path"],
                "artifacts/factor_research/diagnostic_metrics/reports/latest.md",
            )
            self.assertEqual(overview["diagnostic_factor_metrics_summary"]["label_join_summary"]["joined_events"], 3)
            self.assertEqual(overview["diagnostic_factor_metrics_summary"]["label_join_summary"]["join_rate"], 1.0)
            self.assertTrue(overview["diagnostic_factor_metrics_summary"]["backfill_replay_available"])
            self.assertEqual(overview["diagnostic_factor_metrics_summary"]["backfill_joined_events"], 3)
            self.assertEqual(
                overview["diagnostic_factor_metrics_summary"]["events_path"],
                "artifacts/factor_research/diagnostic_metrics/events/latest.jsonl",
            )
            self.assertTrue(overview["factor_ops_summary"]["available"])
            self.assertEqual(overview["factor_ops_summary"]["promotion_readiness"], "collecting_live_shadow")
            self.assertIn("insufficient_live_shadow_days", overview["factor_ops_summary"]["promotion_blockers"])
            self.assertEqual(overview["factor_ops_summary"]["live_shadow_days_observed"], 2)
            self.assertEqual(overview["factor_ops_summary"]["live_labeled_events"], 0)
            self.assertEqual(overview["factor_ops_summary"]["backfill_labeled_events"], 3)
            self.assertEqual(overview["factor_ops_summary"]["dual_run_readiness_status"], "ready")
            self.assertEqual(overview["factor_ops_summary"]["diagnostic_rule_count"], 1)
            self.assertEqual(overview["factor_ops_summary"]["missing_backfill_symbols"], ["BILI", "INTC", "QQQ", "TSLA"])
            self.assertTrue(overview["historical_fact_summary"]["available"])
            self.assertEqual(overview["historical_fact_summary"]["fact_count"], 8)
            self.assertEqual(overview["historical_fact_summary"]["scenario_count"], 2)
            self.assertEqual(overview["historical_fact_summary"]["usage_counts"]["debug_only"], 5)
            self.assertEqual(
                overview["historical_fact_summary"]["top_debug_scenarios"][0]["scenario_type"],
                "dual_run_ready",
            )
            self.assertIn(
                "label_facts_must_not_be_used_as_factor_inputs",
                overview["historical_fact_summary"]["leakage_warnings"],
            )
            self.assertEqual(
                overview["historical_fact_summary"]["report_path"],
                "artifacts/factor_research/facts/reports/latest.md",
            )
            self.assertTrue(overview["factor_attribution"]["available"])
            self.assertEqual(overview["factor_attribution"]["top_factors"][0]["factor_id"], "rsi_14_30m")
            self.assertEqual(overview["factor_attribution"]["iteration_id"], "iter_20260416_100000")
            self.assertTrue(overview["iterations"][0]["factor_attribution_summary"]["available"])
            self.assertEqual(overview["control"]["legacy_mode"], "signals")
            self.assertEqual(overview["control"]["canonical_mode"], "signal_only")
            self.assertTrue(overview["control"]["signal_generation_enabled"])
            self.assertFalse(overview["control"]["paper_execution_enabled"])
            self.assertFalse(overview["control"]["live_execution_enabled"])
            self.assertFalse(overview["control"]["live_submission_ready"])
            self.assertTrue((latest_dir / "strategy_overview.json").exists())

    def test_strategy_api_returns_factor_engine_field(self):
        expected = {
            "factor_engine": {"enabled": True, "mode": "shadow"},
            "factor_research": {"factor_count": 1},
            "factor_sample_health": {"live_observation_count": 1},
            "factor_validation_summary": {"research_candidate_count": 1},
            "factor_parity_summary": {"parity_pass_count": 8},
            "factor_dual_run_summary": {
                "matched_rate": 1.0,
                "real_universe_symbols_detected": True,
                "synthetic_fixture_symbols_detected": False,
                "readiness_status": "ready",
            },
            "diagnostic_factor_rules_summary": {
                "rule_count": 1,
                "actionable_enabled": False,
                "latest_diagnostic_rule_ids": ["diag_rsi_reversal_rsi_14_30m"],
                "approval_decision_snapshot_present": True,
                "real_apply_ready": False,
                "latest_approval_request_path": "artifacts/factor_research/diagnostic_rule_link_trial/approval_request.md",
            },
            "diagnostic_factor_metrics_summary": {
                "rule_count": 1,
                "evaluated_rule_count": 1,
                "insufficient_rule_count": 0,
                "watchlist_candidate_count": 0,
                "sample_sources": ["historical_backfill"],
                "top_diagnostic_rules": [{"rule_id": "diag_rsi_reversal_rsi_14_30m"}],
                "label_join_summary": {"joined_events": 3, "total_events": 3, "join_rate": 1.0},
                "events_path": "artifacts/factor_research/diagnostic_metrics/events/latest.jsonl",
                "events_summary_path": "artifacts/factor_research/diagnostic_metrics/events/summary.json",
                "top_label_join_blockers": [],
                "backfill_replay_available": True,
                "backfill_joined_events": 3,
                "live_joined_events": 0,
                "report_path": "artifacts/factor_research/diagnostic_metrics/reports/latest.md",
            },
            "factor_ops_summary": {
                "promotion_readiness": "collecting_live_shadow",
                "promotion_blockers": ["insufficient_live_shadow_days"],
                "live_shadow_days_observed": 2,
                "live_labeled_events": 0,
                "backfill_labeled_events": 3,
                "dual_run_readiness_status": "ready",
                "diagnostic_rule_count": 1,
                "report_path": "artifacts/factor_research/ops/reports/latest.md",
            },
            "historical_fact_summary": {
                "latest_generated_at": "2026-04-16T13:05:00+00:00",
                "fact_count": 8,
                "fact_type_counts": {"factor_observation": 2},
                "usage_counts": {"debug_only": 5},
                "scenario_count": 2,
                "top_debug_scenarios": [{"scenario_type": "dual_run_ready"}],
                "leakage_warnings": ["label_facts_must_not_be_used_as_factor_inputs"],
                "report_path": "artifacts/factor_research/facts/reports/latest.md",
            },
        }
        with mock.patch.object(dashboard_main, "_build_strategy_overview", return_value=expected):
            dashboard_strategy_api.set_dashboard_main_module(dashboard_main)
            result = asyncio.run(dashboard_strategy_api.api_strategy_overview())
        self.assertEqual(result["factor_engine"]["mode"], "shadow")
        self.assertTrue(result["factor_engine"]["enabled"])
        self.assertEqual(result["factor_research"]["factor_count"], 1)
        self.assertEqual(result["factor_sample_health"]["live_observation_count"], 1)
        self.assertEqual(result["factor_validation_summary"]["research_candidate_count"], 1)
        self.assertEqual(result["factor_parity_summary"]["parity_pass_count"], 8)
        self.assertEqual(result["factor_dual_run_summary"]["matched_rate"], 1.0)
        self.assertTrue(result["factor_dual_run_summary"]["real_universe_symbols_detected"])
        self.assertFalse(result["factor_dual_run_summary"]["synthetic_fixture_symbols_detected"])
        self.assertEqual(result["factor_dual_run_summary"]["readiness_status"], "ready")
        self.assertEqual(result["diagnostic_factor_rules_summary"]["rule_count"], 1)
        self.assertFalse(result["diagnostic_factor_rules_summary"]["actionable_enabled"])
        self.assertEqual(
            result["diagnostic_factor_rules_summary"]["latest_diagnostic_rule_ids"],
            ["diag_rsi_reversal_rsi_14_30m"],
        )
        self.assertTrue(result["diagnostic_factor_rules_summary"]["approval_decision_snapshot_present"])
        self.assertFalse(result["diagnostic_factor_rules_summary"]["real_apply_ready"])
        self.assertEqual(
            result["diagnostic_factor_rules_summary"]["latest_approval_request_path"],
            "artifacts/factor_research/diagnostic_rule_link_trial/approval_request.md",
        )
        self.assertEqual(result["diagnostic_factor_metrics_summary"]["rule_count"], 1)
        self.assertEqual(result["diagnostic_factor_metrics_summary"]["evaluated_rule_count"], 1)
        self.assertEqual(result["diagnostic_factor_metrics_summary"]["label_join_summary"]["joined_events"], 3)
        self.assertEqual(
            result["diagnostic_factor_metrics_summary"]["events_path"],
            "artifacts/factor_research/diagnostic_metrics/events/latest.jsonl",
        )
        self.assertEqual(
            result["diagnostic_factor_metrics_summary"]["report_path"],
            "artifacts/factor_research/diagnostic_metrics/reports/latest.md",
        )
        self.assertEqual(result["factor_ops_summary"]["promotion_readiness"], "collecting_live_shadow")
        self.assertEqual(result["factor_ops_summary"]["backfill_labeled_events"], 3)
        self.assertEqual(
            result["factor_ops_summary"]["report_path"],
            "artifacts/factor_research/ops/reports/latest.md",
        )
        self.assertEqual(result["historical_fact_summary"]["fact_count"], 8)
        self.assertEqual(result["historical_fact_summary"]["scenario_count"], 2)
        self.assertEqual(result["historical_fact_summary"]["top_debug_scenarios"][0]["scenario_type"], "dual_run_ready")
        self.assertIn("label_facts_must_not_be_used_as_factor_inputs", result["historical_fact_summary"]["leakage_warnings"])


if __name__ == "__main__":
    unittest.main()
