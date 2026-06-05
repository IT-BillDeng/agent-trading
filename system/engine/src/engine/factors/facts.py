from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..artifacts import append_jsonl, resolve_artifacts_root, write_json


SUPPORTED_FACT_USAGES = {
    "debug_only",
    "research_context",
    "label",
    "factor_candidate",
}

DEFAULT_FACTS_DIR = Path("artifacts/factor_research/facts")
DEFAULT_SCENARIOS_DIR = Path("artifacts/factor_research/scenarios")
FACT_REPORT_PATH = "artifacts/factor_research/facts/reports/latest.md"
SCENARIO_REPORT_PATH = "artifacts/factor_research/scenarios/reports/latest.md"

_SCHEMA_FIELDS = {
    "fact_id",
    "fact_type",
    "symbol",
    "event_time",
    "available_at",
    "source",
    "usage",
    "leakage_policy",
    "payload",
    "missing_available_at_reason",
}


def normalize_fact(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise TypeError("fact record must be a dict")

    usage = classify_fact_usage(record)
    leakage_policy = _default_leakage_policy(usage)
    if isinstance(record.get("leakage_policy"), dict):
        leakage_policy.update(record["leakage_policy"])

    payload = record.get("payload")
    if not isinstance(payload, dict):
        payload = {
            key: value
            for key, value in record.items()
            if key not in _SCHEMA_FIELDS
        }

    normalized: dict[str, Any] = {
        "fact_id": str(record.get("fact_id") or "").strip(),
        "fact_type": str(record.get("fact_type") or "").strip(),
        "symbol": _optional_text(record.get("symbol")),
        "event_time": _optional_text(record.get("event_time")),
        "available_at": _optional_text(record.get("available_at")),
        "source": str(record.get("source") or "").strip(),
        "usage": usage,
        "leakage_policy": leakage_policy,
        "payload": dict(payload),
    }
    reason = _optional_text(record.get("missing_available_at_reason"))
    if reason:
        normalized["missing_available_at_reason"] = reason
    if not normalized["fact_id"]:
        normalized["fact_id"] = build_fact_id(normalized)
    return normalized


def validate_fact(record: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(record, dict):
        return {"valid": False, "errors": ["fact must be an object"], "warnings": warnings}

    fact_type = record.get("fact_type")
    if not isinstance(fact_type, str) or not fact_type.strip():
        errors.append("fact_type must be non-empty")

    fact_id = record.get("fact_id")
    if not isinstance(fact_id, str) or not fact_id.strip():
        errors.append("fact_id must be non-empty")

    source = record.get("source")
    if not isinstance(source, str) or not source.strip():
        errors.append("source must be non-empty")

    usage = record.get("usage")
    if usage not in SUPPORTED_FACT_USAGES:
        errors.append(f"usage must be one of {sorted(SUPPORTED_FACT_USAGES)}")

    if _parse_iso_timestamp(record.get("event_time")) is None:
        errors.append("event_time must be an ISO timestamp")

    available_at = record.get("available_at")
    if available_at in (None, ""):
        reason = record.get("missing_available_at_reason")
        if usage == "debug_only" and isinstance(reason, str) and reason.strip():
            warnings.append("debug_only fact has explicit missing available_at reason")
        else:
            errors.append("available_at must be present unless usage=debug_only with explicit reason")
    elif _parse_iso_timestamp(available_at) is None:
        errors.append("available_at must be an ISO timestamp")

    leakage_policy = record.get("leakage_policy")
    if not isinstance(leakage_policy, dict):
        errors.append("leakage_policy must be an object")
        leakage_policy = {}

    payload = record.get("payload")
    if not isinstance(payload, dict):
        errors.append("payload must be an object")

    if usage == "factor_candidate":
        if leakage_policy.get("usable_before_available_at") is not False:
            errors.append("factor_candidate must set leakage_policy.usable_before_available_at=false")
    if usage != "label" and _payload_contains_forward_return(payload):
        errors.append("forward return payloads must use usage=label")
    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def build_fact_id(record: dict[str, Any]) -> str:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    identity = {
        "fact_type": record.get("fact_type"),
        "symbol": record.get("symbol"),
        "event_time": record.get("event_time"),
        "available_at": record.get("available_at"),
        "source": record.get("source"),
        "usage": record.get("usage"),
        "payload_identity": _payload_identity(payload),
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]
    return f"fact_{_slug(record.get('fact_type') or 'unknown')}_{digest}"


def classify_fact_usage(record: dict[str, Any]) -> str:
    usage = record.get("usage")
    if usage in SUPPORTED_FACT_USAGES:
        return str(usage)
    fact_type = str(record.get("fact_type") or "")
    if fact_type in {"diagnostic_label", "forward_return_label"}:
        return "label"
    if fact_type in {"factor_observation", "diagnostic_signal_event"}:
        return "research_context"
    return "debug_only"


def is_point_in_time_safe(record: dict[str, Any], decision_time: str | datetime) -> bool:
    try:
        fact = normalize_fact(record)
    except Exception:
        return False
    if fact.get("usage") != "factor_candidate":
        return False
    validation = validate_fact(fact)
    if not validation["valid"]:
        return False
    leakage_policy = fact.get("leakage_policy") if isinstance(fact.get("leakage_policy"), dict) else {}
    if leakage_policy.get("usable_before_available_at") is not False:
        return False
    available_at = _parse_iso_timestamp(fact.get("available_at"))
    decision_at = _parse_iso_timestamp(decision_time)
    if available_at is None or decision_at is None:
        return False
    return available_at <= decision_at


def collect_historical_facts(
    *,
    artifacts_root: str | Path | None = None,
    logs_root: str | Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    root = Path(artifacts_root) if artifacts_root is not None else resolve_artifacts_root()
    log_root = Path(logs_root) if logs_root is not None else _project_root() / "logs"
    generated_at = generated_at or _utc_now()

    raw_facts: list[dict[str, Any]] = []
    raw_facts.extend(_collect_factor_observation_facts(root))
    raw_facts.extend(_collect_dual_run_facts(root))
    raw_facts.extend(_collect_diagnostic_metric_facts(root))
    raw_facts.extend(_collect_approval_decision_facts(root))
    raw_facts.extend(_collect_deployment_record_facts(root))
    raw_facts.extend(_collect_data_quality_facts(log_root, generated_at=generated_at))

    facts, validation_errors, validation_warnings = _normalize_and_dedupe_facts(raw_facts)
    leakage_warnings = _collect_leakage_warnings(facts, validation_warnings)
    fact_type_counts = dict(sorted(Counter(str(fact.get("fact_type")) for fact in facts).items()))
    usage_counts = dict(sorted(Counter(str(fact.get("usage")) for fact in facts).items()))

    scenarios = build_replay_scenarios(facts, generated_at=generated_at)
    fact_summary = {
        "generated_at": generated_at,
        "generated_by": "historical_fact_replay_collector",
        "status": "ok" if not validation_errors else "partial",
        "fact_count": len(facts),
        "fact_type_counts": fact_type_counts,
        "usage_counts": usage_counts,
        "facts": facts,
        "leakage_warnings": leakage_warnings,
        "validation_errors": validation_errors,
        "report_path": FACT_REPORT_PATH,
        "scenarios_path": "artifacts/factor_research/scenarios/latest.json",
        "safety": _safety_payload(),
    }
    scenario_summary = _scenario_summary_payload(
        scenarios,
        generated_at=generated_at,
        leakage_warnings=leakage_warnings,
    )

    writes = _write_fact_outputs(root, fact_summary, scenario_summary)
    fact_summary["writes"] = writes["facts"]
    scenario_summary["writes"] = writes["scenarios"]
    return {
        "status": fact_summary["status"],
        "generated_at": generated_at,
        "fact_count": fact_summary["fact_count"],
        "scenario_count": scenario_summary["scenario_count"],
        "fact_type_counts": fact_type_counts,
        "usage_counts": usage_counts,
        "leakage_warnings": leakage_warnings,
        "validation_errors": validation_errors,
        "facts": fact_summary,
        "scenarios": scenario_summary,
        "writes": writes,
    }


def summarize_historical_facts(*, artifacts_root: str | Path | None = None) -> dict[str, Any]:
    root = Path(artifacts_root) if artifacts_root is not None else resolve_artifacts_root()
    facts_latest = _read_json(root / "factor_research" / "facts" / "latest.json")
    scenarios_latest = _read_json(root / "factor_research" / "scenarios" / "latest.json")
    if not isinstance(facts_latest, dict):
        facts_latest = _empty_fact_summary(_utc_now())
    if not isinstance(scenarios_latest, dict):
        scenarios_latest = _empty_scenario_summary(_utc_now())

    summary = {
        "generated_at": facts_latest.get("generated_at"),
        "status": facts_latest.get("status", "missing"),
        "fact_count": int(facts_latest.get("fact_count") or 0),
        "fact_type_counts": facts_latest.get("fact_type_counts", {}),
        "usage_counts": facts_latest.get("usage_counts", {}),
        "scenario_count": int(scenarios_latest.get("scenario_count") or 0),
        "top_debug_scenarios": _top_debug_scenarios(scenarios_latest.get("scenarios", [])),
        "leakage_warnings": _string_list(facts_latest.get("leakage_warnings")),
        "report_path": facts_latest.get("report_path") or FACT_REPORT_PATH,
    }
    _write_reports(root, facts_latest, scenarios_latest)
    return summary


def build_replay_scenarios(facts: Sequence[dict[str, Any]], *, generated_at: str | None = None) -> list[dict[str, Any]]:
    generated_at = generated_at or _utc_now()
    by_type: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        by_type.setdefault(str(fact.get("fact_type")), []).append(fact)

    scenarios: list[dict[str, Any]] = []
    ready_facts = [
        fact
        for fact in by_type.get("dual_run_readiness", [])
        if fact.get("payload", {}).get("readiness_status") == "ready"
    ]
    if ready_facts:
        scenarios.append(_make_scenario(
            "dual_run_ready",
            ready_facts[-3:],
            debug_goal="Replay a ready dual-run window and confirm production outputs stay unchanged.",
            replay_command_hint="python -m engine.factors.facts summarize",
            expected_invariants=[
                "historical facts remain debug/research only",
                "production signals and order intents remain unchanged",
                "no broker or execution submit path is called",
            ],
            generated_at=generated_at,
        ))

    mismatch_facts = by_type.get("dual_run_mismatch", [])
    if mismatch_facts:
        scenarios.append(_make_scenario(
            "dual_run_mismatch",
            mismatch_facts[:8],
            debug_goal="Replay dual-run mismatches and inspect parity blockers without applying changes.",
            replay_command_hint="python -m engine.factors.facts summarize",
            expected_invariants=[
                "mismatch evidence does not trigger approve/apply",
                "rules/rules.json and factors/registry.json stay unchanged",
                "diagnostic facts do not enter execution_preview or order_intents",
            ],
            generated_at=generated_at,
        ))

    label_blockers = by_type.get("label_join_blocker", [])
    if label_blockers:
        scenarios.append(_make_scenario(
            "label_join_blocker",
            label_blockers[:8],
            debug_goal="Replay label join blockers and identify missing labels without fabricating outcomes.",
            replay_command_hint="python -m engine.factors.facts summarize",
            expected_invariants=[
                "future returns remain label facts only",
                "unjoined events do not become factor evidence",
                "backfill labels are reported as historical_backfill when present",
            ],
            generated_at=generated_at,
        ))

    unlabeled = [
        fact for fact in by_type.get("diagnostic_signal_event", [])
        if fact.get("payload", {}).get("label_join_status") not in (None, "", "joined")
    ]
    if unlabeled:
        scenarios.append(_make_scenario(
            "diagnostic_signal_unlabeled",
            unlabeled[:8],
            debug_goal="Replay diagnostic signals that have no joined label yet.",
            replay_command_hint="python -m engine.factors.facts summarize",
            expected_invariants=[
                "diagnostic signals remain paper-only",
                "missing labels are blockers, not zero returns",
                "no actionable BUY is generated",
            ],
            generated_at=generated_at,
        ))

    approval_blockers = _approval_integrity_blockers(facts)
    if approval_blockers:
        scenarios.append(_make_scenario(
            "approval_integrity_blocked",
            approval_blockers[:8],
            debug_goal="Replay approval/apply integrity blockers without writing decisions.",
            replay_command_hint="python -m engine.factors.facts summarize",
            expected_invariants=[
                "factor-researcher does not approve or apply",
                "approval_decisions.jsonl is not written",
                "diagnostic apply records cannot modify production rules",
            ],
            generated_at=generated_at,
        ))

    data_blockers = by_type.get("data_quality_blocker", [])
    if data_blockers:
        scenarios.append(_make_scenario(
            "data_health_blocker",
            data_blockers[:8],
            debug_goal="Replay data health blockers that prevented diagnostic or strategy readiness.",
            replay_command_hint="python -m engine.factors.facts summarize",
            expected_invariants=[
                "data blockers remain debug context",
                "no watchlist expansion is performed",
                "RiskManager and execution paths are untouched",
            ],
            generated_at=generated_at,
        ))
    return scenarios


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect and summarize historical debug facts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--artifacts-root", default=None)
    collect_parser.add_argument("--logs-root", default=None)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("--artifacts-root", default=None)

    args = parser.parse_args(argv)
    if args.command == "collect":
        result = collect_historical_facts(
            artifacts_root=args.artifacts_root,
            logs_root=args.logs_root,
        )
    else:
        result = summarize_historical_facts(artifacts_root=args.artifacts_root)
    print(json.dumps(_cli_result(result), ensure_ascii=False, indent=2, default=str))
    return 0


def _collect_factor_observation_facts(root: Path) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    history_dir = root / "factors" / "history"
    for path in sorted(history_dir.glob("*.jsonl")) if history_dir.exists() else []:
        for snapshot in _read_jsonl(path):
            if not isinstance(snapshot, dict):
                continue
            snapshot_time = _first_text(snapshot.get("generated_at"), snapshot.get("timestamp"), _file_mtime_iso(path))
            snapshot_source = _first_text(snapshot.get("sample_source"), snapshot.get("source"), "live_shadow")
            symbols = snapshot.get("symbols")
            if not isinstance(symbols, dict):
                continue
            for symbol, symbol_payload in symbols.items():
                if not isinstance(symbol_payload, dict):
                    continue
                factors = symbol_payload.get("factors")
                if not isinstance(factors, dict):
                    continue
                symbol_time = _first_text(symbol_payload.get("source_bar_time"), symbol_payload.get("timestamp"), snapshot_time)
                for factor_id, payload in sorted(factors.items()):
                    if not isinstance(payload, dict):
                        continue
                    event_time = _first_text(payload.get("source_bar_time"), symbol_time, snapshot_time)
                    available_at = _first_text(snapshot.get("generated_at"), snapshot.get("timestamp"), event_time)
                    sample_source = _first_text(payload.get("sample_source"), snapshot_source)
                    facts.append({
                        "fact_type": "factor_observation",
                        "symbol": str(symbol),
                        "event_time": event_time,
                        "available_at": available_at,
                        "source": "artifacts/factors/history",
                        "usage": "research_context",
                        "payload": {
                            "factor_id": str(factor_id),
                            "value": payload.get("value"),
                            "ready": bool(payload.get("ready", False)),
                            "actionable": bool(payload.get("actionable", False)),
                            "reason": payload.get("reason"),
                            "sample_source": sample_source,
                            "source_bar_time": payload.get("source_bar_time"),
                            "source_bar_is_complete": payload.get("source_bar_is_complete"),
                            "session": payload.get("session"),
                            "timeframe": payload.get("timeframe"),
                            "registry_config_hash": payload.get("registry_config_hash") or payload.get("config_hash"),
                            "observation_id": payload.get("observation_id"),
                            "snapshot_path": str(path),
                        },
                    })
    return facts


def _collect_dual_run_facts(root: Path) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    path = root / "factor_research" / "dual_run" / "observations" / "history.jsonl"
    for item in _read_jsonl(path):
        if not isinstance(item, dict):
            continue
        event_time = _first_text(item.get("observed_at"), item.get("observation_generated_at"), item.get("cycle_generated_at"), _file_mtime_iso(path))
        payload = {
            "readiness_status": item.get("readiness_status"),
            "readiness_reasons": item.get("readiness_reasons", []),
            "warnings": item.get("warnings", []),
            "compared_symbols": item.get("compared_symbols", []),
            "compared_rules": item.get("compared_rules", []),
            "compared_count": item.get("compared_count"),
            "matched_count": item.get("matched_count"),
            "matched_rate": item.get("matched_rate"),
            "blocking_mismatch_count": item.get("blocking_mismatch_count"),
            "warning_mismatch_count": item.get("warning_mismatch_count"),
            "data_health_blockers": item.get("data_health_blockers", []),
            "factor_sample_health": item.get("factor_sample_health", {}),
            "diagnostic_only": bool(item.get("diagnostic_only", True)),
            "apply_allowed": bool(item.get("apply_allowed", False)),
        }
        facts.append({
            "fact_type": "dual_run_readiness",
            "event_time": event_time,
            "available_at": event_time,
            "source": "artifacts/factor_research/dual_run/observations/history.jsonl",
            "usage": "debug_only",
            "payload": payload,
        })
        top_mismatches = item.get("top_mismatches") if isinstance(item.get("top_mismatches"), list) else []
        if top_mismatches:
            for mismatch in top_mismatches:
                if not isinstance(mismatch, dict):
                    continue
                facts.append({
                    "fact_type": "dual_run_mismatch",
                    "symbol": _optional_text(mismatch.get("symbol")),
                    "event_time": event_time,
                    "available_at": event_time,
                    "source": "artifacts/factor_research/dual_run/observations/history.jsonl",
                    "usage": "debug_only",
                    "payload": dict(mismatch, readiness_status=item.get("readiness_status")),
                })
        elif _int_value(item.get("blocking_mismatch_count")) > 0 or _int_value(item.get("mismatch_count")) > 0:
            facts.append({
                "fact_type": "dual_run_mismatch",
                "event_time": event_time,
                "available_at": event_time,
                "source": "artifacts/factor_research/dual_run/observations/history.jsonl",
                "usage": "debug_only",
                "payload": {
                    "readiness_status": item.get("readiness_status"),
                    "mismatch_count": item.get("mismatch_count"),
                    "blocking_mismatch_count": item.get("blocking_mismatch_count"),
                    "reason": "aggregate_mismatch_without_top_mismatches",
                },
            })
    return facts


def _collect_diagnostic_metric_facts(root: Path) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    metrics_dir = root / "factor_research" / "diagnostic_metrics"
    latest = _read_json(metrics_dir / "latest.json")
    event_available_at = _first_text(
        latest.get("generated_at") if isinstance(latest, dict) else None,
        _file_mtime_iso(metrics_dir / "events" / "latest.jsonl"),
    )
    events_path = metrics_dir / "events" / "latest.jsonl"
    for item in _read_jsonl(events_path):
        if not isinstance(item, dict):
            continue
        event_time = _first_text(item.get("event_time"), item.get("source_bar_time"), event_available_at)
        base_payload = {
            key: value
            for key, value in item.items()
            if key not in {"forward_return_1bar", "forward_return_2bar", "forward_return_4bar", "forward_returns"}
        }
        facts.append({
            "fact_type": "diagnostic_signal_event",
            "symbol": _optional_text(item.get("symbol")),
            "event_time": event_time,
            "available_at": event_available_at or event_time,
            "source": "artifacts/factor_research/diagnostic_metrics/events/latest.jsonl",
            "usage": "research_context",
            "payload": base_payload,
        })
        if _has_forward_return(item):
            facts.append({
                "fact_type": "diagnostic_label",
                "symbol": _optional_text(item.get("symbol")),
                "event_time": event_time,
                "available_at": event_available_at or event_time,
                "source": "artifacts/factor_research/diagnostic_metrics/events/latest.jsonl",
                "usage": "label",
                "leakage_policy": {
                    "label_only": True,
                    "usable_before_available_at": False,
                    "allows_future_outcome_as_factor": False,
                },
                "payload": {
                    "event_id": item.get("event_id"),
                    "rule_id": item.get("rule_id"),
                    "source_rule_id": item.get("source_rule_id"),
                    "sample_source": item.get("sample_source"),
                    "source_bar_time": item.get("source_bar_time"),
                    "label_join_status": item.get("label_join_status"),
                    "forward_return_1bar": item.get("forward_return_1bar"),
                    "forward_return_2bar": item.get("forward_return_2bar"),
                    "forward_return_4bar": item.get("forward_return_4bar"),
                    "forward_returns": item.get("forward_returns"),
                },
            })
        if item.get("label_join_status") not in (None, "", "joined") or item.get("label_join_reason"):
            facts.append({
                "fact_type": "label_join_blocker",
                "symbol": _optional_text(item.get("symbol")),
                "event_time": event_time,
                "available_at": event_available_at or event_time,
                "source": "artifacts/factor_research/diagnostic_metrics/events/latest.jsonl",
                "usage": "debug_only",
                "payload": {
                    "event_id": item.get("event_id"),
                    "rule_id": item.get("rule_id"),
                    "sample_source": item.get("sample_source"),
                    "label_join_status": item.get("label_join_status"),
                    "label_join_reason": item.get("label_join_reason"),
                },
            })

    for source_path in (metrics_dir / "events" / "summary.json", metrics_dir / "latest.json"):
        payload = _read_json(source_path)
        if not isinstance(payload, dict):
            continue
        generated_at = _first_text(payload.get("generated_at"), event_available_at, _file_mtime_iso(source_path))
        blockers = payload.get("top_label_join_blockers")
        if not isinstance(blockers, list):
            label_summary = payload.get("label_join_summary")
            reasons = label_summary.get("reasons_count") if isinstance(label_summary, dict) else {}
            blockers = [
                {"reason": reason, "count": count}
                for reason, count in sorted(reasons.items())
            ] if isinstance(reasons, dict) else []
        for blocker in blockers:
            if not isinstance(blocker, dict):
                continue
            facts.append({
                "fact_type": "label_join_blocker",
                "event_time": generated_at,
                "available_at": generated_at,
                "source": _relative_artifact_path(source_path),
                "usage": "debug_only",
                "payload": {
                    "reason": blocker.get("reason"),
                    "count": blocker.get("count"),
                    "source_summary": _relative_artifact_path(source_path),
                },
            })
    return facts


def _collect_approval_decision_facts(root: Path) -> list[dict[str, Any]]:
    path = root / "strategist" / "approval_decisions.jsonl"
    facts: list[dict[str, Any]] = []
    fallback_time = _file_mtime_iso(path)
    for item in _read_jsonl(path):
        if not isinstance(item, dict):
            continue
        event_time = _first_text(item.get("decided_at"), item.get("recorded_at"), item.get("created_at"), fallback_time)
        facts.append({
            "fact_type": "approval_decision",
            "event_time": event_time,
            "available_at": event_time,
            "source": "artifacts/strategist/approval_decisions.jsonl",
            "usage": "debug_only",
            "payload": {
                **item,
                "timestamp_inferred_from_file_mtime": event_time == fallback_time,
            },
        })
    return facts


def _collect_deployment_record_facts(root: Path) -> list[dict[str, Any]]:
    path = root / "strategist" / "deployment_records.jsonl"
    facts: list[dict[str, Any]] = []
    fallback_time = _file_mtime_iso(path)
    for item in _read_jsonl(path):
        if not isinstance(item, dict):
            continue
        event_time = _first_text(item.get("applied_at"), item.get("recorded_at"), item.get("created_at"), fallback_time)
        facts.append({
            "fact_type": "deployment_record",
            "event_time": event_time,
            "available_at": event_time,
            "source": "artifacts/strategist/deployment_records.jsonl",
            "usage": "debug_only",
            "payload": {
                **item,
                "timestamp_inferred_from_file_mtime": event_time == fallback_time,
            },
        })
    return facts


def _collect_data_quality_facts(logs_root: Path, *, generated_at: str) -> list[dict[str, Any]]:
    path = logs_root / "latest" / "strategy_overview.json"
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return []
    overview_time = _first_text(payload.get("generated_at"), _file_mtime_iso(path), generated_at)
    data_health = payload.get("data_health")
    if not isinstance(data_health, dict):
        latest_cycle = payload.get("latest_cycle") if isinstance(payload.get("latest_cycle"), dict) else {}
        data_health = latest_cycle.get("data_health")
    if not isinstance(data_health, dict):
        return []
    facts: list[dict[str, Any]] = []
    for symbol, item in sorted(data_health.items()):
        if not isinstance(item, dict):
            continue
        blocked = (
            item.get("strategy_ready") is False
            or item.get("actionable_ready") is False
            or bool(item.get("reason"))
            or bool(item.get("actionable_block_reason"))
            or bool(item.get("blockers"))
        )
        if not blocked:
            continue
        facts.append({
            "fact_type": "data_quality_blocker",
            "symbol": str(symbol),
            "event_time": overview_time,
            "available_at": overview_time,
            "source": "logs/latest/strategy_overview.json",
            "usage": "debug_only",
            "payload": dict(item),
        })
    return facts


def _normalize_and_dedupe_facts(raw_facts: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    facts_by_id: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    for raw in raw_facts:
        try:
            fact = normalize_fact(raw)
        except Exception as exc:
            errors.append({"error": f"{type(exc).__name__}:{exc}", "record": raw})
            continue
        validation = validate_fact(fact)
        warnings.extend(validation.get("warnings", []))
        if not validation["valid"]:
            errors.append({
                "fact_id": fact.get("fact_id"),
                "fact_type": fact.get("fact_type"),
                "errors": validation.get("errors", []),
            })
            continue
        facts_by_id[fact["fact_id"]] = fact
    return sorted(facts_by_id.values(), key=lambda item: (str(item.get("event_time")), str(item.get("fact_id")))), errors, warnings


def _write_fact_outputs(root: Path, facts_latest: dict[str, Any], scenarios_latest: dict[str, Any]) -> dict[str, dict[str, str | int]]:
    facts_dir = root / "factor_research" / "facts"
    scenarios_dir = root / "factor_research" / "scenarios"
    facts_latest_path = facts_dir / "latest.json"
    facts_history_path = facts_dir / "history.jsonl"
    scenarios_latest_path = scenarios_dir / "latest.json"
    scenarios_history_path = scenarios_dir / "history.jsonl"

    write_json(facts_latest_path, facts_latest)
    write_json(scenarios_latest_path, scenarios_latest)
    fact_appended = _append_new_records(facts_history_path, facts_latest.get("facts", []), "fact_id")
    scenario_appended = _append_new_records(scenarios_history_path, scenarios_latest.get("scenarios", []), "scenario_id")
    _write_reports(root, facts_latest, scenarios_latest)
    return {
        "facts": {
            "latest": str(facts_latest_path),
            "history": str(facts_history_path),
            "report": str(facts_dir / "reports" / "latest.md"),
            "history_appended": fact_appended,
        },
        "scenarios": {
            "latest": str(scenarios_latest_path),
            "history": str(scenarios_history_path),
            "report": str(scenarios_dir / "reports" / "latest.md"),
            "history_appended": scenario_appended,
        },
    }


def _write_reports(root: Path, facts_latest: dict[str, Any], scenarios_latest: dict[str, Any]) -> None:
    fact_report = root / "factor_research" / "facts" / "reports" / "latest.md"
    scenario_report = root / "factor_research" / "scenarios" / "reports" / "latest.md"
    fact_report.parent.mkdir(parents=True, exist_ok=True)
    scenario_report.parent.mkdir(parents=True, exist_ok=True)
    fact_report.write_text(_render_fact_report(facts_latest), encoding="utf-8")
    scenario_report.write_text(_render_scenario_report(scenarios_latest), encoding="utf-8")


def _render_fact_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Historical Fact Replay Summary",
        "",
        f"- generated_at: `{summary.get('generated_at') or '--'}`",
        f"- fact_count: `{summary.get('fact_count', 0)}`",
        f"- status: `{summary.get('status', 'missing')}`",
        "- fact != actionable factor",
        "- debug/research facts do not enter RiskManager, execution_preview, order_intents, or broker submit",
        "- backfill facts cannot impersonate live evidence",
        "",
        "## Fact Type Counts",
    ]
    counts = summary.get("fact_type_counts") if isinstance(summary.get("fact_type_counts"), dict) else {}
    lines.extend(f"- {key}: `{value}`" for key, value in sorted(counts.items()))
    lines.append("")
    lines.append("## Usage Counts")
    usages = summary.get("usage_counts") if isinstance(summary.get("usage_counts"), dict) else {}
    lines.extend(f"- {key}: `{value}`" for key, value in sorted(usages.items()))
    warnings = _string_list(summary.get("leakage_warnings"))
    if warnings:
        lines.append("")
        lines.append("## Leakage Warnings")
        lines.extend(f"- {item}" for item in warnings)
    return "\n".join(lines) + "\n"


def _render_scenario_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Historical Fact Replay Scenarios",
        "",
        f"- generated_at: `{summary.get('generated_at') or '--'}`",
        f"- scenario_count: `{summary.get('scenario_count', 0)}`",
        "- scenarios are debug replay only and do not modify the system",
        "",
    ]
    scenarios = summary.get("scenarios") if isinstance(summary.get("scenarios"), list) else []
    if not scenarios:
        lines.append("No replay scenarios are currently available.")
    for scenario in scenarios:
        lines.extend([
            f"## {scenario.get('scenario_type')}",
            "",
            f"- scenario_id: `{scenario.get('scenario_id')}`",
            f"- debug_goal: {scenario.get('debug_goal') or '--'}",
            f"- symbols: `{', '.join(_string_list(scenario.get('symbols'))) or '--'}`",
            f"- related_facts: `{len(scenario.get('related_facts') or [])}`",
            f"- replay_command_hint: `{scenario.get('replay_command_hint') or '--'}`",
            "",
        ])
    return "\n".join(lines) + "\n"


def _append_new_records(path: Path, records: Any, id_key: str) -> int:
    if not isinstance(records, list):
        return 0
    existing = {
        str(item.get(id_key))
        for item in _read_jsonl(path)
        if isinstance(item, dict) and item.get(id_key)
    }
    appended = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        record_id = record.get(id_key)
        if not record_id or str(record_id) in existing:
            continue
        append_jsonl(path, record)
        existing.add(str(record_id))
        appended += 1
    return appended


def _scenario_summary_payload(
    scenarios: list[dict[str, Any]],
    *,
    generated_at: str,
    leakage_warnings: list[str],
) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "generated_by": "historical_fact_replay_collector",
        "scenario_count": len(scenarios),
        "scenario_type_counts": dict(sorted(Counter(item.get("scenario_type") for item in scenarios).items())),
        "scenarios": scenarios,
        "top_debug_scenarios": _top_debug_scenarios(scenarios),
        "leakage_warnings": leakage_warnings,
        "report_path": SCENARIO_REPORT_PATH,
        "safety": _safety_payload(),
    }


def _make_scenario(
    scenario_type: str,
    facts: Sequence[dict[str, Any]],
    *,
    debug_goal: str,
    replay_command_hint: str,
    expected_invariants: list[str],
    generated_at: str,
) -> dict[str, Any]:
    related_facts = [str(item.get("fact_id")) for item in facts if item.get("fact_id")]
    symbols = sorted({str(item.get("symbol")) for item in facts if item.get("symbol")})
    times = sorted(str(item.get("event_time")) for item in facts if item.get("event_time"))
    payload = {
        "scenario_type": scenario_type,
        "related_facts": related_facts,
        "symbols": symbols,
        "time_window": {"start": times[0] if times else None, "end": times[-1] if times else None},
        "debug_goal": debug_goal,
        "replay_command_hint": replay_command_hint,
        "expected_invariants": expected_invariants,
        "generated_at": generated_at,
    }
    payload["scenario_id"] = _build_scenario_id(payload)
    return payload


def _build_scenario_id(payload: dict[str, Any]) -> str:
    identity = {
        "scenario_type": payload.get("scenario_type"),
        "related_facts": payload.get("related_facts"),
        "time_window": payload.get("time_window"),
    }
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]
    return f"scenario_{_slug(payload.get('scenario_type') or 'unknown')}_{digest}"


def _approval_integrity_blockers(facts: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for fact in facts:
        fact_type = fact.get("fact_type")
        payload = fact.get("payload") if isinstance(fact.get("payload"), dict) else {}
        if fact_type == "approval_decision":
            decision = str(payload.get("decision") or "").lower()
            decider_type = str(payload.get("decider_type") or payload.get("approver_type") or payload.get("approved_by_type") or "")
            if decision == "approved" and decider_type and decider_type not in {"human", "main_agent"}:
                blockers.append(fact)
            if decision not in {"approved", "rejected"}:
                blockers.append(fact)
        if fact_type == "deployment_record":
            if payload.get("proposal_type") == "factor_rule_link" and payload.get("target_file") == "rules/diagnostic_factor_rules.json":
                if not payload.get("approval_decision_snapshot"):
                    blockers.append(fact)
                if payload.get("production_rules_modified") is True or payload.get("actionable_enabled") is True:
                    blockers.append(fact)
                if payload.get("success") is False:
                    blockers.append(fact)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in blockers:
        fact_id = str(item.get("fact_id"))
        if fact_id in seen:
            continue
        seen.add(fact_id)
        unique.append(item)
    return unique


def _collect_leakage_warnings(facts: Sequence[dict[str, Any]], validation_warnings: Sequence[str]) -> list[str]:
    warnings = set(str(item) for item in validation_warnings if item)
    if any(_fact_sample_source(fact) == "historical_backfill" for fact in facts):
        warnings.add("historical_backfill_facts_are_not_live_evidence")
    if any(fact.get("usage") == "label" for fact in facts):
        warnings.add("label_facts_must_not_be_used_as_factor_inputs")
    if any(fact.get("payload", {}).get("timestamp_inferred_from_file_mtime") for fact in facts):
        warnings.add("some_debug_facts_used_file_mtime_for_missing_source_timestamp")
    if any(fact.get("usage") != "label" and _payload_contains_forward_return(fact.get("payload")) for fact in facts):
        warnings.add("non_label_fact_contains_forward_return")
    return sorted(warnings)


def _fact_sample_source(fact: dict[str, Any]) -> str | None:
    payload = fact.get("payload") if isinstance(fact.get("payload"), dict) else {}
    value = payload.get("sample_source")
    return str(value) if value else None


def _empty_fact_summary(generated_at: str) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "status": "missing",
        "fact_count": 0,
        "fact_type_counts": {},
        "usage_counts": {},
        "facts": [],
        "leakage_warnings": [],
        "report_path": FACT_REPORT_PATH,
        "safety": _safety_payload(),
    }


def _empty_scenario_summary(generated_at: str) -> dict[str, Any]:
    return {
        "generated_at": generated_at,
        "scenario_count": 0,
        "scenario_type_counts": {},
        "scenarios": [],
        "top_debug_scenarios": [],
        "leakage_warnings": [],
        "report_path": SCENARIO_REPORT_PATH,
        "safety": _safety_payload(),
    }


def _safety_payload() -> dict[str, bool]:
    return {
        "debug_replay_only": True,
        "entered_risk": False,
        "entered_execution": False,
        "entered_execution_preview": False,
        "entered_order_intents": False,
        "broker_submit": False,
        "approve": False,
        "apply": False,
        "production_rules_modified": False,
        "factor_registry_modified": False,
    }


def _top_debug_scenarios(scenarios: Any, limit: int = 6) -> list[dict[str, Any]]:
    if not isinstance(scenarios, list):
        return []
    result: list[dict[str, Any]] = []
    for scenario in scenarios[:limit]:
        if not isinstance(scenario, dict):
            continue
        result.append({
            "scenario_id": scenario.get("scenario_id"),
            "scenario_type": scenario.get("scenario_type"),
            "symbols": scenario.get("symbols", []),
            "time_window": scenario.get("time_window", {}),
            "debug_goal": scenario.get("debug_goal"),
            "replay_command_hint": scenario.get("replay_command_hint"),
            "expected_invariants": scenario.get("expected_invariants", []),
        })
    return result


def _default_leakage_policy(usage: str) -> dict[str, Any]:
    return {
        "usable_before_available_at": False,
        "allows_future_outcome_as_factor": False,
        "backfill_may_impersonate_live_evidence": False,
        "label_only": usage == "label",
    }


def _payload_identity(payload: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "observation_id",
        "event_id",
        "proposal_id",
        "deployment_record_id",
        "rule_id",
        "source_rule_id",
        "factor_id",
        "source_bar_time",
        "sample_source",
        "decision",
        "reason",
        "label_join_reason",
        "readiness_status",
        "target_file",
        "apply_mode",
    ]
    identity = {key: payload.get(key) for key in keys if key in payload}
    return identity or payload


def _payload_contains_forward_return(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return any(str(key).startswith("forward_return") for key in payload)


def _has_forward_return(payload: dict[str, Any]) -> bool:
    return any(key in payload and payload.get(key) is not None for key in ("forward_return_1bar", "forward_return_2bar", "forward_return_4bar", "forward_returns"))


def _read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return rows
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            rows.append({"_raw": line})
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _parse_iso_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and "T" in value:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _file_mtime_iso(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _project_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = _optional_text(value)
        if text:
            return text
    return None


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    if value in (None, ""):
        return []
    return [str(value)]


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _slug(value: Any) -> str:
    text = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "unknown").strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def _relative_artifact_path(path: str | Path) -> str:
    text = str(path)
    marker = "artifacts/"
    if marker in text:
        return text[text.index(marker):]
    return text


def _cli_result(result: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "status",
        "generated_at",
        "fact_count",
        "scenario_count",
        "fact_type_counts",
        "usage_counts",
        "leakage_warnings",
        "report_path",
    ]
    payload = {key: result.get(key) for key in keys if key in result}
    if "facts" in result and isinstance(result["facts"], dict):
        payload["fact_report_path"] = result["facts"].get("report_path")
    if "scenarios" in result and isinstance(result["scenarios"], dict):
        payload["scenario_report_path"] = result["scenarios"].get("report_path")
    if "writes" in result:
        payload["writes"] = result["writes"]
    return payload


__all__ = [
    "SUPPORTED_FACT_USAGES",
    "build_fact_id",
    "build_replay_scenarios",
    "classify_fact_usage",
    "collect_historical_facts",
    "is_point_in_time_safe",
    "normalize_fact",
    "summarize_historical_facts",
    "validate_fact",
]


if __name__ == "__main__":
    raise SystemExit(main())
