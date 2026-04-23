from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch


ENGINE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from engine.applier import apply_approved_proposal  # noqa: E402
from engine.config import AppConfig  # noqa: E402
from engine.runtime import build_execution_summary  # noqa: E402
from engine.strategist_artifacts import queue_approval_request  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parents[3]
RULES_FILE = REPO_ROOT / "rules" / "rules.json"
FACTOR_REGISTRY_FILE = REPO_ROOT / "factors" / "registry.json"


def _ok_response(data):
    return {"http_status": 200, "body": {"code": 0, "data": data}}


def _make_bar(ts: str, close: float, *, volume: int) -> dict:
    return {
        "time": ts,
        "open": close - 0.2,
        "high": close + 0.6,
        "low": close - 0.4,
        "close": close,
        "volume": volume,
    }


def _make_regular_day(date: str, *, start_close: float, volume_base: int) -> list[dict]:
    bars: list[dict] = []
    hour = 9
    minute = 30
    close = start_close
    for index in range(13):
        bars.append(
            _make_bar(
                f"{date} {hour:02d}:{minute:02d}:00",
                close,
                volume=volume_base + index * 150,
            )
        )
        close += 0.7
        minute += 30
        if minute >= 60:
            hour += 1
            minute -= 60
    return bars


def _make_cycle_raw(symbol: str, bars_items: list[dict], *, timestamp: str) -> dict:
    return {
        "accounts": _ok_response({"items": []}),
        "assets": _ok_response(
            {
                "items": [
                    {
                        "account": "paper",
                        "netLiquidation": 100000.0,
                        "cashValue": 100000.0,
                        "buyingPower": 100000.0,
                        "grossPositionValue": 0.0,
                        "unrealizedPnL": 0.0,
                        "realizedPnL": 0.0,
                        "timestamp": timestamp,
                        "trading_day": "2026-04-21",
                    }
                ]
            }
        ),
        "positions": _ok_response({"items": []}),
        "active_orders": _ok_response({"items": []}),
        "quote_permissions": _ok_response([]),
        "market_state": {
            "US": _ok_response([{"status": "TRADING", "marketStatus": "open"}]),
        },
        "delay_quotes": {
            "US": _ok_response({"items": [{"symbol": symbol, "latestPrice": 101.0}]}),
        },
        "briefs": {
            "US": _ok_response({"items": [{"symbol": symbol, "latestPrice": 101.0}]}),
        },
        "bars": {
            "US": _ok_response([{"symbol": symbol, "items": bars_items}]),
        },
        "contracts": {
            "US": {
                symbol: _ok_response(
                    {"symbol": symbol, "market": "US", "currency": "USD", "secType": "STK", "tickSizes": []}
                )
            }
        },
        "_provider": "yfinance",
    }


class FactorApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.repo_root = Path(self._tmpdir.name)
        self.artifacts_dir = self.repo_root / "artifacts"
        self.rules_path = self.repo_root / "rules" / "rules.json"
        self.factor_registry_path = self.repo_root / "factors" / "registry.json"

        self.rules_path.parent.mkdir(parents=True, exist_ok=True)
        self.factor_registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.original_rules = json.loads(RULES_FILE.read_text())
        self.original_registry = json.loads(FACTOR_REGISTRY_FILE.read_text())
        self.rules_path.write_text(json.dumps(self.original_rules, ensure_ascii=False, indent=2))
        self.factor_registry_path.write_text(json.dumps(self.original_registry, ensure_ascii=False, indent=2))

        self.live_execution_path = self.repo_root / "system" / "engine" / "src" / "engine" / "live_execution.py"
        self.risk_path = self.repo_root / "system" / "engine" / "src" / "engine" / "risk.py"
        self.broker_path = self.repo_root / "system" / "engine" / "src" / "engine" / "broker_client.py"
        self.factor_impl_path = self.repo_root / "system" / "engine" / "src" / "engine" / "factors" / "builtins.py"
        for path, text in (
            (self.live_execution_path, "LIVE_SENTINEL = 1\n"),
            (self.risk_path, "RISK_SENTINEL = 1\n"),
            (self.broker_path, "BROKER_SENTINEL = 1\n"),
            (self.factor_impl_path, "FACTOR_SENTINEL = 1\n"),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        self._old_env = os.environ.get("ENGINE_ARTIFACTS_DIR")
        os.environ["ENGINE_ARTIFACTS_DIR"] = str(self.artifacts_dir)
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        if self._old_env is None:
            os.environ.pop("ENGINE_ARTIFACTS_DIR", None)
        else:
            os.environ["ENGINE_ARTIFACTS_DIR"] = self._old_env

    def _base_factor_record(
        self,
        proposal_id: str,
        *,
        proposal_type: str,
        factor_id: str,
        target_files: list[str],
        recommended_update_mode: str,
    ) -> dict:
        payload = {
            "proposal_id": proposal_id,
            "proposal_type": proposal_type,
            "status": "approved",
            "recommended_update_mode": recommended_update_mode,
            "target_files": target_files,
            "factor_id": factor_id,
            "hypothesis": "validate factor governance path",
            "input_data": ["regular_session_30m_bars"],
            "session": "regular",
            "usage": ["shadow", "rule_condition_candidate"],
            "lookback_bars": 14,
            "horizon_bars": 1,
            "validation_results": {
                "ic": 0.12,
                "coverage": 0.95,
                "missing_rate": 0.05,
            },
            "ic": 0.12,
            "coverage": 0.95,
            "missing_rate": 0.05,
            "correlation_with_existing": None,
            "backtest_delta": None,
            "fee_cost_impact": None,
            "paper_shadow_required_days": 5,
            "risk_notes": ["shadow only"],
            "rollback_plan": "restore previous file from backup",
        }
        if proposal_type == "factor_rule_link":
            payload["binding_mode"] = "disabled_rule"
        return payload

    def _app(self) -> AppConfig:
        return AppConfig(
            raw={
                "mode": "paper",
                "markets": ["US"],
                "broker": {"platform": "tiger"},
                "execution": {"submit_mode": "guarded", "live_submit": False},
                "notify": {"telegram_preview_only": True, "telegram_send_enabled": False},
                "risk": {
                    "daily_loss_limit_pct": 5,
                    "max_order_notional_usd": 10000,
                    "max_total_exposure_usd": 1000000,
                    "max_trades_per_day": 10,
                    "max_trades_per_symbol_per_day": 3,
                    "symbol_cooldown_minutes_after_order": 30,
                    "symbol_cooldown_minutes_after_loss": 120,
                    "fx_rates_to_usd": {"USD": 1.0},
                },
                "system": {
                    "state_dir": str(self.repo_root / "runtime" / "state"),
                    "debug_factor_parity": False,
                },
                "strategy": {
                    "timeframe": "30min",
                    "use_rule_engine": True,
                    "rules_path": str(self.rules_path),
                    "signal": {
                        "fast_sma": 5,
                        "slow_sma": 10,
                        "trend_sma": 20,
                        "min_momentum_3bars": 0.003,
                        "max_bar_range_pct": 0.04,
                    },
                    "market_data": {
                        "include_extended_hours": True,
                        "extended_hours_usage": "context_only",
                        "regular_session_only_for_indicators": True,
                        "require_completed_bar_for_actionable_signal": True,
                    },
                    "sessions": {
                        "US": {
                            "regular_start": "09:30",
                            "regular_end": "16:00",
                            "entry_window_start": "10:00",
                            "entry_window_end": "15:15",
                            "timezone": "America/New_York",
                        }
                    },
                    "symbols": [{"symbol": "AAPL", "market": "US", "name": "Apple"}],
                },
                "factor_engine": {
                    "enabled": True,
                    "mode": "shadow",
                    "registry_path": str(self.factor_registry_path),
                    "write_artifacts": False,
                    "allow_actionable_consumption": False,
                    "regular_session_only_for_indicators": True,
                },
            }
        )

    def _raw_runtime_cycle(self) -> dict:
        bars = _make_regular_day("2026-04-20", start_close=100.0, volume_base=1000) + _make_regular_day(
            "2026-04-21",
            start_close=109.5,
            volume_base=3000,
        )
        return _make_cycle_raw("AAPL", bars, timestamp="2026-04-21T21:00:00+00:00")

    def _read_queue_record(self, proposal_id: str) -> dict:
        path = self.artifacts_dir / "strategist" / "approval_queue" / f"{proposal_id}.json"
        return json.loads(path.read_text())

    def _read_deployment_records(self) -> list[dict]:
        path = self.artifacts_dir / "strategist" / "deployment_records.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def _read_failure_records(self) -> list[dict]:
        path = self.artifacts_dir / "strategist" / "failure_records.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_approved_factor_config_hot_apply_succeeds(self) -> None:
        updated_registry = copy.deepcopy(self.original_registry)
        updated_registry["factors"]["rsi_14_30m"]["version"] = 2
        proposal_id = "factor_config_hot"
        before_live = self.live_execution_path.read_text()
        before_risk = self.risk_path.read_text()
        before_broker = self.broker_path.read_text()

        record = self._base_factor_record(
            proposal_id,
            proposal_type="factor_config",
            factor_id="rsi_14_30m",
            target_files=["factors/registry.json"],
            recommended_update_mode="hot",
        )
        record["target_contents"] = {"factors/registry.json": updated_registry}
        queue_approval_request(proposal_id, record)

        result = apply_approved_proposal(
            proposal_id,
            operator_type="agent",
            operator_id="applier",
        )

        deployment_record = self._read_deployment_records()[0]
        queue_record = self._read_queue_record(proposal_id)
        applied_registry = json.loads(self.factor_registry_path.read_text())

        self.assertTrue(result["applied"])
        self.assertEqual(queue_record["status"], "applied")
        self.assertEqual(applied_registry["factors"]["rsi_14_30m"]["version"], 2)
        self.assertEqual(deployment_record["proposal_type"], "factor_config")
        self.assertEqual(deployment_record["changed_factors"], ["rsi_14_30m"])
        self.assertEqual(deployment_record["changed_rules"], [])
        self.assertTrue(deployment_record["registry_hash"])
        self.assertTrue(deployment_record["validation_summary"]["factor_registry"]["valid"])
        self.assertEqual(before_live, self.live_execution_path.read_text())
        self.assertEqual(before_risk, self.risk_path.read_text())
        self.assertEqual(before_broker, self.broker_path.read_text())

    def test_invalid_factor_registry_hot_apply_fails_and_records_failure_reason(self) -> None:
        invalid_registry = copy.deepcopy(self.original_registry)
        invalid_registry["defaults"]["allow_actionable_consumption"] = "yes"
        proposal_id = "factor_config_invalid"
        before_bytes = self.factor_registry_path.read_bytes()

        record = self._base_factor_record(
            proposal_id,
            proposal_type="factor_config",
            factor_id="rsi_14_30m",
            target_files=["factors/registry.json"],
            recommended_update_mode="hot",
        )
        record["target_contents"] = {"factors/registry.json": invalid_registry}
        queue_approval_request(proposal_id, record)

        with self.assertRaisesRegex(ValueError, "invalid factor registry payload"):
            apply_approved_proposal(
                proposal_id,
                operator_type="agent",
                operator_id="applier",
            )

        self.assertEqual(before_bytes, self.factor_registry_path.read_bytes())
        deployment_record = self._read_deployment_records()[0]
        failure_record = self._read_failure_records()[0]
        queue_record = self._read_queue_record(proposal_id)

        self.assertEqual(queue_record["status"], "approved")
        self.assertFalse(deployment_record["success"])
        self.assertIn("allow_actionable_consumption", deployment_record["error"])
        self.assertIn("allow_actionable_consumption", failure_record["reason"])
        self.assertEqual(failure_record["proposal_type"], "factor_config")

    def test_shadow_only_factor_registry_hot_apply_rejects_non_shadow_defaults_and_actionable_fields(self) -> None:
        cases = [
            ("mode", "paper", "defaults.mode must be 'shadow'"),
            ("allow_actionable_consumption", True, "defaults.allow_actionable_consumption must be false"),
            ("factor_actionable", True, "actionable must be false"),
            ("usage_actionable", ["shadow", "actionable"], "usage 'actionable' is not allowed"),
        ]

        for case_name, value, expected_reason in cases:
            with self.subTest(case=case_name):
                invalid_registry = copy.deepcopy(self.original_registry)
                proposal_id = f"factor_config_invalid_{case_name}"
                if case_name == "mode":
                    invalid_registry["defaults"]["mode"] = value
                elif case_name == "allow_actionable_consumption":
                    invalid_registry["defaults"]["allow_actionable_consumption"] = value
                elif case_name == "factor_actionable":
                    invalid_registry["factors"]["rsi_14_30m"]["actionable"] = value
                elif case_name == "usage_actionable":
                    invalid_registry["factors"]["rsi_14_30m"]["usage"] = value

                record = self._base_factor_record(
                    proposal_id,
                    proposal_type="factor_config",
                    factor_id="rsi_14_30m",
                    target_files=["factors/registry.json"],
                    recommended_update_mode="hot",
                )
                record["target_contents"] = {"factors/registry.json": invalid_registry}
                queue_approval_request(proposal_id, record)

                with self.assertRaisesRegex(ValueError, "invalid factor registry payload"):
                    apply_approved_proposal(
                        proposal_id,
                        operator_type="agent",
                        operator_id="applier",
                    )

                failure_record = self._read_failure_records()[-1]
                self.assertIn(expected_reason, failure_record["reason"])

    def test_factor_code_is_marked_manual_code_apply_required(self) -> None:
        proposal_id = "factor_code_manual"
        before_bytes = self.factor_impl_path.read_bytes()

        record = self._base_factor_record(
            proposal_id,
            proposal_type="factor_code",
            factor_id="rsi_14_30m",
            target_files=["system/engine/src/engine/factors/builtins.py"],
            recommended_update_mode="cold",
        )
        queue_approval_request(proposal_id, record)

        result = apply_approved_proposal(
            proposal_id,
            operator_type="agent",
            operator_id="applier",
        )

        deployment_record = self._read_deployment_records()[0]
        queue_record = self._read_queue_record(proposal_id)

        self.assertFalse(result["applied"])
        self.assertTrue(result["manual_code_apply_required"])
        self.assertEqual(before_bytes, self.factor_impl_path.read_bytes())
        self.assertEqual(queue_record["status"], "approved")
        self.assertTrue(queue_record["manual_code_apply_required"])
        self.assertEqual(deployment_record["apply_action"], "manual_code_apply_required")
        self.assertFalse(deployment_record["code_applied"])
        self.assertEqual(deployment_record["changed_factors"], ["rsi_14_30m"])

    def test_factor_rule_link_unknown_factor_reference_fails(self) -> None:
        updated_rules = copy.deepcopy(self.original_rules)
        updated_rules["rules"].append(
            {
                "rule_id": "factor_missing_rule",
                "enabled": True,
                "priority": 999,
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "action": "BUY",
                    "conditions": {
                        "type": "indicator",
                        "indicator": "factor",
                        "factor_id": "missing_factor",
                        "compare": {"operator": "above", "value": 1},
                    },
                },
            }
        )
        proposal_id = "factor_rule_link_unknown"
        before_bytes = self.rules_path.read_bytes()

        record = self._base_factor_record(
            proposal_id,
            proposal_type="factor_rule_link",
            factor_id="missing_factor",
            target_files=["rules/rules.json"],
            recommended_update_mode="hot",
        )
        record["correlation_with_existing"] = 0.4
        record["backtest_delta"] = {"sharpe": 0.12}
        record["fee_cost_impact"] = {"bps": 1.0}
        record["paper_shadow_required_days"] = 20
        record["target_contents"] = {"rules/rules.json": updated_rules}
        queue_approval_request(proposal_id, record)

        with self.assertRaisesRegex(ValueError, "unknown factor_id"):
            apply_approved_proposal(
                proposal_id,
                operator_type="agent",
                operator_id="applier",
            )

        self.assertEqual(before_bytes, self.rules_path.read_bytes())
        failure_record = self._read_failure_records()[0]
        self.assertIn("unknown factor_id", failure_record["reason"])
        self.assertEqual(failure_record["proposal_type"], "factor_rule_link")

    def test_factor_rule_link_hot_apply_rejects_enabled_rule_changes(self) -> None:
        updated_rules = copy.deepcopy(self.original_rules)
        for rule in updated_rules["rules"]:
            if rule.get("rule_id") == "rsi_reversal":
                rule["entry"]["conditions"]["items"][0] = {
                    "type": "indicator",
                    "indicator": "factor",
                    "factor_id": "rsi_14_30m",
                    "compare": {"operator": "cross_above", "value": 30},
                }
                break
        proposal_id = "factor_rule_link_enabled_rule_blocked"
        before_bytes = self.rules_path.read_bytes()

        record = self._base_factor_record(
            proposal_id,
            proposal_type="factor_rule_link",
            factor_id="rsi_14_30m",
            target_files=["rules/rules.json"],
            recommended_update_mode="hot",
        )
        record["binding_mode"] = "diagnostic"
        record["correlation_with_existing"] = 0.4
        record["backtest_delta"] = {"sharpe": 0.12}
        record["fee_cost_impact"] = {"bps": 1.0}
        record["paper_shadow_required_days"] = 20
        record["target_contents"] = {"rules/rules.json": updated_rules}
        queue_approval_request(proposal_id, record)

        with self.assertRaisesRegex(ValueError, "unsafe factor_rule_link hot apply"):
            apply_approved_proposal(
                proposal_id,
                operator_type="agent",
                operator_id="applier",
            )

        self.assertEqual(before_bytes, self.rules_path.read_bytes())
        failure_record = self._read_failure_records()[0]
        self.assertIn("enabled rules", failure_record["reason"])
        self.assertEqual(failure_record["proposal_type"], "factor_rule_link")
        self.assertFalse(
            failure_record["validation_summary"]["factor_rule_link_safety"]["valid"]
        )

    def test_disabled_rule_factor_rule_link_hot_apply_preserves_runtime_outputs(self) -> None:
        raw = self._raw_runtime_cycle()
        app = self._app()
        with patch("engine.runtime._cycle_id", return_value="20260421T193000Z"):
            baseline = build_execution_summary(raw, app)

        updated_rules = copy.deepcopy(self.original_rules)
        updated_rules["rules"].append(
            {
                "rule_id": "factor_shadow_probe",
                "name": "Factor Shadow Probe",
                "description": "Disabled diagnostic factor binding rule",
                "enabled": False,
                "priority": 50,
                "timeframe": "30min",
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "conditions": {
                        "type": "indicator",
                        "indicator": "factor",
                        "factor_id": "rsi_14_30m",
                        "compare": {"operator": "above", "value": 55},
                    },
                    "action": "BUY",
                    "order_type": "LMT",
                },
                "exit": {
                    "conditions": {
                        "type": "indicator",
                        "indicator": "factor",
                        "factor_id": "rsi_14_30m",
                        "compare": {"operator": "below", "value": 40},
                    },
                    "action": "EXIT",
                    "order_type": "MKT",
                },
            }
        )

        proposal_id = "factor_rule_link_disabled_rule_safe"
        record = self._base_factor_record(
            proposal_id,
            proposal_type="factor_rule_link",
            factor_id="rsi_14_30m",
            target_files=["rules/rules.json"],
            recommended_update_mode="hot",
        )
        record["binding_mode"] = "disabled_rule"
        record["correlation_with_existing"] = 0.4
        record["backtest_delta"] = {"sharpe": 0.12}
        record["fee_cost_impact"] = {"bps": 1.0}
        record["paper_shadow_required_days"] = 20
        record["target_contents"] = {"rules/rules.json": updated_rules}
        queue_approval_request(proposal_id, record)

        result = apply_approved_proposal(
            proposal_id,
            operator_type="agent",
            operator_id="applier",
        )

        with patch("engine.runtime._cycle_id", return_value="20260421T193000Z"):
            after = build_execution_summary(raw, app)

        deployment_record = self._read_deployment_records()[0]
        applied_rules = json.loads(self.rules_path.read_text())
        by_id = {rule["rule_id"]: rule for rule in applied_rules["rules"]}

        self.assertTrue(result["applied"])
        self.assertEqual(baseline["strategy"]["signals"], after["strategy"]["signals"])
        self.assertEqual(baseline["execution_preview"], after["execution_preview"])
        self.assertEqual(baseline["order_intents"], after["order_intents"])
        self.assertIn("factor_shadow_probe", by_id)
        self.assertFalse(by_id["factor_shadow_probe"]["enabled"])
        self.assertTrue(deployment_record["validation_summary"]["factor_rule_link_safety"]["valid"])
        self.assertEqual(deployment_record["changed_rules"], ["factor_shadow_probe"])

    def test_factor_apply_does_not_modify_live_execution_or_broker_files(self) -> None:
        updated_registry = copy.deepcopy(self.original_registry)
        updated_registry["factors"]["bollinger_zscore_20_2_30m"]["version"] = 2
        proposal_id = "factor_config_safe_targets"
        before_live = self.live_execution_path.read_text()
        before_risk = self.risk_path.read_text()
        before_broker = self.broker_path.read_text()

        record = self._base_factor_record(
            proposal_id,
            proposal_type="factor_config",
            factor_id="bollinger_zscore_20_2_30m",
            target_files=["factors/registry.json"],
            recommended_update_mode="hot",
        )
        record["target_contents"] = {"factors/registry.json": updated_registry}
        queue_approval_request(proposal_id, record)

        apply_approved_proposal(
            proposal_id,
            operator_type="agent",
            operator_id="applier",
        )

        self.assertEqual(before_live, self.live_execution_path.read_text())
        self.assertEqual(before_risk, self.risk_path.read_text())
        self.assertEqual(before_broker, self.broker_path.read_text())


if __name__ == "__main__":
    unittest.main()
