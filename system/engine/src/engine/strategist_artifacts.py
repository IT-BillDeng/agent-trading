"""Helpers for canonical strategist artifact storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifacts import append_jsonl, resolve_artifacts_root, write_json
from .proposal_schema import validate_proposal_record


APPROVAL_STATUSES = {
    "draft",
    "validated",
    "awaiting_approval",
    "approved",
    "rejected",
    "applied",
}

ALLOWED_APPROVAL_TRANSITIONS = {
    "draft": {"validated", "rejected"},
    "validated": {"awaiting_approval", "rejected"},
    "awaiting_approval": {"approved", "rejected"},
    "approved": {"applied"},
    "rejected": set(),
    "applied": set(),
}

HOT_UPDATE_PREFIXES = (
    "rules/",
    "./rules/",
    "/workspace/agent-trading/rules/",
)

COLD_UPDATE_MARKERS = (
    "system/engine/src/engine/strategy.py",
    "system/engine/src/engine/rule_engine.py",
    "system/engine/src/engine/indicators.py",
)

SAFE_LOW_CONFIDENCE_CHANGE_INTENTS = {
    "paper_shadow",
    "disable_rule",
    "reduce_risk",
    "lower_frequency",
    "lower_position_size",
    "tighten_filter",
    "tighten_filters",
}


def resolve_strategist_dir(base_dir: str | Path | None = None) -> Path:
    return resolve_artifacts_root(base_dir) / "strategist"


def strategist_paths(base_dir: str | Path | None = None) -> dict[str, Path]:
    root = resolve_strategist_dir(base_dir)
    memory_dir = root / "memory"
    iterations_dir = root / "iterations"
    experiments_dir = root / "experiments"
    approval_queue_dir = root / "approval_queue"
    return {
        "root": root,
        "memory_dir": memory_dir,
        "iterations_dir": iterations_dir,
        "experiments_dir": experiments_dir,
        "approval_queue_dir": approval_queue_dir,
        "strategy_plan_latest": root / "strategy_plan_latest.json",
        "strategy_plan_history": root / "strategy_plan_history.jsonl",
        "memory_latest": memory_dir / "latest.json",
        "memory_history": memory_dir / "history.jsonl",
        "proposals": root / "proposals.jsonl",
        "rejections": root / "rejections.jsonl",
        "code_change_proposals": root / "code_change_proposals.jsonl",
        "code_change_results": root / "code_change_results.jsonl",
        "rollback_notes": root / "rollback_notes.jsonl",
        "approval_decisions": root / "approval_decisions.jsonl",
        "deployment_records": root / "deployment_records.jsonl",
        "failure_records": root / "failure_records.jsonl",
    }


def _broker_fee_summary_path(base_dir: str | Path | None = None) -> Path:
    return resolve_artifacts_root(base_dir) / "broker" / "fee_calibration_summary.json"


def _normalize_fee_confidence_level(level: str | None) -> str:
    value = str(level or "").strip().lower()
    if value == "high":
        return "high"
    if value in {"observe", "medium"}:
        return "medium"
    if value == "low":
        return "low"
    return "missing"


def load_fee_confidence_snapshot(base_dir: str | Path | None = None) -> dict[str, Any]:
    path = _broker_fee_summary_path(base_dir)
    if not path.exists():
        return {
            "confidence": "missing",
            "label": "缺失",
            "reason": "fee calibration summary missing",
            "trust": None,
            "summary_path": str(path),
        }

    payload = json.loads(path.read_text())
    trust = payload.get("trust", {}) if isinstance(payload, dict) else {}
    level = _normalize_fee_confidence_level(trust.get("level"))
    labels = {
        "high": "可信",
        "medium": "观察",
        "low": "不可信",
        "missing": "缺失",
    }
    return {
        "confidence": level,
        "label": labels[level],
        "reason": trust.get("reason") or "fee calibration trust unavailable",
        "trust": trust or None,
        "count": payload.get("count") if isinstance(payload, dict) else None,
        "avg_delta": payload.get("avg_delta") if isinstance(payload, dict) else None,
        "max_abs_delta": payload.get("max_abs_delta") if isinstance(payload, dict) else None,
        "summary_path": str(path),
    }


def _proposal_change_intent(record: dict[str, Any]) -> str:
    return str(record.get("change_intent") or "").strip().lower()


def _proposal_turnover_profile(record: dict[str, Any]) -> str:
    return str(record.get("turnover_profile") or "").strip().lower()


def _requires_fee_confidence_gate(record: dict[str, Any], *, update_mode: str) -> bool:
    return update_mode == "hot" and infer_update_mode(record) == "hot"


def evaluate_fee_confidence_gate(
    record: dict[str, Any],
    fee_snapshot: dict[str, Any],
    *,
    update_mode: str,
) -> dict[str, Any]:
    confidence = fee_snapshot.get("confidence", "missing")
    change_intent = _proposal_change_intent(record)
    turnover_profile = _proposal_turnover_profile(record)

    if not _requires_fee_confidence_gate(record, update_mode=update_mode):
        return {
            "allowed": True,
            "reason": "not_fee_sensitive_apply",
            "confidence": confidence,
        }

    if confidence == "high":
        return {
            "allowed": True,
            "reason": "fee_confidence_high",
            "confidence": confidence,
        }

    if not change_intent:
        return {
            "allowed": True,
            "reason": "fee_sensitive_metadata_missing",
            "confidence": confidence,
        }

    if change_intent in SAFE_LOW_CONFIDENCE_CHANGE_INTENTS:
        return {
            "allowed": True,
            "reason": f"safe_change_intent:{change_intent}",
            "confidence": confidence,
        }

    if confidence == "medium":
        if change_intent == "enable_new_buy_rule" and turnover_profile == "low":
            return {
                "allowed": True,
                "reason": "medium_confidence_low_turnover_only",
                "confidence": confidence,
            }
        return {
            "allowed": False,
            "reason": "fee_confidence_medium_blocks_high_or_unknown_turnover",
            "confidence": confidence,
        }

    return {
        "allowed": False,
        "reason": "fee_confidence_low_or_missing_blocks_enablement",
        "confidence": confidence,
    }


def ensure_strategist_dirs(base_dir: str | Path | None = None) -> dict[str, Path]:
    paths = strategist_paths(base_dir)
    paths["root"].mkdir(parents=True, exist_ok=True)
    paths["memory_dir"].mkdir(parents=True, exist_ok=True)
    paths["iterations_dir"].mkdir(parents=True, exist_ok=True)
    paths["experiments_dir"].mkdir(parents=True, exist_ok=True)
    paths["approval_queue_dir"].mkdir(parents=True, exist_ok=True)
    return paths


def record_code_change_proposal(record: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    paths = ensure_strategist_dirs(base_dir)
    append_jsonl(paths["code_change_proposals"], record)
    return paths["code_change_proposals"]


def record_code_change_result(record: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    paths = ensure_strategist_dirs(base_dir)
    append_jsonl(paths["code_change_results"], record)
    return paths["code_change_results"]


def record_rollback_note(record: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    paths = ensure_strategist_dirs(base_dir)
    append_jsonl(paths["rollback_notes"], record)
    return paths["rollback_notes"]


def queue_approval_request(proposal_id: str, record: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    paths = ensure_strategist_dirs(base_dir)
    queue_path = paths["approval_queue_dir"] / f"{proposal_id}.json"
    status = record.get("status", "draft")
    if status not in APPROVAL_STATUSES:
        raise ValueError(f"unknown approval status: {status}")
    if str(record.get("proposal_id") or proposal_id) != proposal_id:
        raise ValueError(f"proposal_id mismatch: expected {proposal_id}, got {record.get('proposal_id')}")
    validation = validate_proposal_record(record)
    if not validation["valid"]:
        raise ValueError("invalid proposal payload: " + "; ".join(validation["errors"]))
    queue_record = dict(record)
    queue_record["proposal_id"] = proposal_id
    queue_record["proposal_validation"] = {
        "valid": validation["valid"],
        "errors": validation["errors"],
        "warnings": validation["warnings"],
        "proposal_type": validation["proposal_type"],
    }
    write_json(queue_path, queue_record)
    return queue_path


def load_approval_request(proposal_id: str, base_dir: str | Path | None = None) -> dict[str, Any]:
    paths = ensure_strategist_dirs(base_dir)
    queue_path = paths["approval_queue_dir"] / f"{proposal_id}.json"
    if not queue_path.exists():
        raise FileNotFoundError(queue_path)
    return json.loads(queue_path.read_text())


def _proposal_validation_summary(record: dict[str, Any], base_dir: str | Path | None = None) -> dict[str, Any]:
    validation = record.get("validation", {})
    if not isinstance(validation, dict):
        validation = {}
    if not validation and isinstance(record.get("validation_results"), dict):
        validation = dict(record.get("validation_results") or {})

    tests = validation.get("tests")
    if not isinstance(tests, list):
        tests = []

    backtest = validation.get("backtest")
    if not isinstance(backtest, dict):
        backtest = {}
    if not backtest and "backtest_delta" in record:
        backtest = {"delta": record.get("backtest_delta")}

    risk = validation.get("risk")
    if not isinstance(risk, dict):
        risk = {}
    if not risk and record.get("risk_notes"):
        risk = {"notes": record.get("risk_notes")}

    fee_confidence = (
        validation.get("fee_confidence")
        or record.get("fee_confidence")
        or load_fee_confidence_snapshot(base_dir).get("confidence", "missing")
    )

    return {
        "tests": tests,
        "backtest": backtest,
        "risk": risk,
        "fee_confidence": fee_confidence,
        "proposal_validation": record.get("proposal_validation"),
    }


def build_proposal_review_record(record: dict[str, Any], base_dir: str | Path | None = None) -> dict[str, Any]:
    proposal_id = str(record.get("proposal_id") or "")
    inferred_mode = infer_update_mode(record)
    recommended_mode = record.get("recommended_update_mode", inferred_mode)
    requires_restart = record.get("requires_restart")
    if requires_restart is None:
        requires_restart = recommended_mode == "cold"

    return {
        "proposal_id": proposal_id,
        "proposal_type": record.get("proposal_type"),
        "status": record.get("status", "draft"),
        "target_files": record.get("target_files", []),
        "recommended_update_mode": recommended_mode,
        "requires_restart": bool(requires_restart),
        "diff_summary": record.get("diff_summary") or record.get("change_summary"),
        "validation": _proposal_validation_summary(record, base_dir),
        "decision": record.get("decision"),
        "generated_at": record.get("generated_at"),
        "change_intent": record.get("change_intent"),
        "turnover_profile": record.get("turnover_profile"),
    }


def get_proposal_review_record(proposal_id: str, base_dir: str | Path | None = None) -> dict[str, Any]:
    record = load_approval_request(proposal_id, base_dir)
    return build_proposal_review_record(record, base_dir)


def list_proposal_review_records(
    base_dir: str | Path | None = None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    paths = ensure_strategist_dirs(base_dir)
    queue_dir = paths["approval_queue_dir"]
    files = sorted(queue_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if limit is not None and limit >= 0:
        files = files[:limit]

    items: list[dict[str, Any]] = []
    for path in files:
        try:
            record = json.loads(path.read_text())
        except Exception:
            continue
        item = build_proposal_review_record(record, base_dir)
        item["source_path"] = str(path)
        items.append(item)
    return items


def infer_update_mode(record: dict[str, Any]) -> str:
    proposal_type = str(record.get("proposal_type") or "").strip().lower()
    if proposal_type == "factor_config":
        return "hot"
    if proposal_type == "factor_rule_link":
        return "hot"
    if proposal_type == "factor_code":
        return "cold"

    target_files = record.get("target_files") or []
    if not target_files:
        return "cold"

    normalized = [str(path) for path in target_files]

    if all(
        any(path.startswith(prefix) for prefix in HOT_UPDATE_PREFIXES)
        for path in normalized
    ):
        return "hot"

    if any(marker in path for marker in COLD_UPDATE_MARKERS for path in normalized):
        return "cold"

    return "cold"


def resolve_apply_gate(proposal_id: str, base_dir: str | Path | None = None) -> dict[str, Any]:
    record = load_approval_request(proposal_id, base_dir)
    status = record.get("status")
    if status != "approved":
        raise ValueError(f"proposal {proposal_id} is not approved: {status}")

    inferred_mode = infer_update_mode(record)
    recommended_mode = record.get("recommended_update_mode", inferred_mode)
    if recommended_mode not in {"hot", "cold"}:
        raise ValueError(f"invalid recommended_update_mode: {recommended_mode}")

    if inferred_mode == "cold" and recommended_mode == "hot":
        raise ValueError("code-changing proposal cannot be applied as hot update")

    proposal_type = str(record.get("proposal_type") or "").strip().lower()
    if proposal_type == "factor_code" and recommended_mode != "cold":
        raise ValueError("factor_code proposal must remain cold/manual")

    requires_restart = record.get("requires_restart")
    if requires_restart is None:
        requires_restart = recommended_mode == "cold"

    fee_confidence_snapshot = load_fee_confidence_snapshot(base_dir)
    fee_gate = evaluate_fee_confidence_gate(
        record,
        fee_confidence_snapshot,
        update_mode=recommended_mode,
    )
    if not fee_gate["allowed"]:
        raise ValueError(f"fee confidence gate blocked apply: {fee_gate['reason']}")

    return {
        "proposal_id": proposal_id,
        "proposal_type": proposal_type or None,
        "approved": True,
        "update_mode": recommended_mode,
        "requires_restart": bool(requires_restart),
        "apply_action": _apply_action_for_record(record, recommended_mode),
        "target_files": record.get("target_files", []),
        "fee_confidence_snapshot": fee_confidence_snapshot,
        "fee_confidence_gate": fee_gate,
    }


def transition_approval_status(
    proposal_id: str,
    new_status: str,
    updates: dict[str, Any] | None = None,
    base_dir: str | Path | None = None,
) -> Path:
    if new_status not in APPROVAL_STATUSES:
        raise ValueError(f"unknown approval status: {new_status}")

    paths = ensure_strategist_dirs(base_dir)
    queue_path = paths["approval_queue_dir"] / f"{proposal_id}.json"
    record = load_approval_request(proposal_id, base_dir)
    current_status = record.get("status", "draft")
    allowed = ALLOWED_APPROVAL_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise ValueError(f"invalid approval transition: {current_status} -> {new_status}")

    record["status"] = new_status
    if updates:
        record.update(updates)
    write_json(queue_path, record)
    return queue_path


def record_approval_decision(record: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    paths = ensure_strategist_dirs(base_dir)
    append_jsonl(paths["approval_decisions"], record)
    return paths["approval_decisions"]


def record_deployment_record(record: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    paths = ensure_strategist_dirs(base_dir)
    append_jsonl(paths["deployment_records"], record)
    return paths["deployment_records"]


def record_failure_record(record: dict[str, Any], base_dir: str | Path | None = None) -> Path:
    paths = ensure_strategist_dirs(base_dir)
    append_jsonl(paths["failure_records"], record)
    return paths["failure_records"]


def approve_request(
    proposal_id: str,
    decision_record: dict[str, Any],
    base_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    queue_path = transition_approval_status(
        proposal_id,
        "approved",
        updates={"decision": "approved", **decision_record},
        base_dir=base_dir,
    )
    decision_path = record_approval_decision(
        {"proposal_id": proposal_id, "decision": "approved", **decision_record},
        base_dir=base_dir,
    )
    return queue_path, decision_path


def reject_request(
    proposal_id: str,
    decision_record: dict[str, Any],
    base_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    queue_path = transition_approval_status(
        proposal_id,
        "rejected",
        updates={"decision": "rejected", **decision_record},
        base_dir=base_dir,
    )
    decision_path = record_approval_decision(
        {"proposal_id": proposal_id, "decision": "rejected", **decision_record},
        base_dir=base_dir,
    )
    return queue_path, decision_path


def mark_request_applied(
    proposal_id: str,
    deployment_record: dict[str, Any],
    base_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    gate = resolve_apply_gate(proposal_id, base_dir)
    requested_mode = deployment_record.get("update_mode", gate["update_mode"])
    if requested_mode != gate["update_mode"]:
        raise ValueError(
            f"deployment mode mismatch for {proposal_id}: expected {gate['update_mode']}, got {requested_mode}"
        )
    queue_path = transition_approval_status(
        proposal_id,
        "applied",
        updates={"applied": True, "apply_gate": gate, **deployment_record},
        base_dir=base_dir,
    )
    deployment_path = record_deployment_record(
        {"proposal_id": proposal_id, "apply_gate": gate, **deployment_record},
        base_dir=base_dir,
    )
    return queue_path, deployment_path


def _apply_action_for_record(record: dict[str, Any], update_mode: str) -> str:
    proposal_type = str(record.get("proposal_type") or "").strip().lower()
    if update_mode != "hot":
        return "manual_code_apply_required" if proposal_type == "factor_code" else "require_restart"
    if proposal_type == "factor_config":
        return "apply_factor_registry_only"
    return "apply_rules_only"
