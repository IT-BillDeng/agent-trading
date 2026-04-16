"""Helpers for canonical strategist artifact storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifacts import append_jsonl, resolve_artifacts_root, write_json


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
    write_json(queue_path, record)
    return queue_path


def load_approval_request(proposal_id: str, base_dir: str | Path | None = None) -> dict[str, Any]:
    paths = ensure_strategist_dirs(base_dir)
    queue_path = paths["approval_queue_dir"] / f"{proposal_id}.json"
    if not queue_path.exists():
        raise FileNotFoundError(queue_path)
    return json.loads(queue_path.read_text())


def infer_update_mode(record: dict[str, Any]) -> str:
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

    requires_restart = record.get("requires_restart")
    if requires_restart is None:
        requires_restart = recommended_mode == "cold"

    return {
        "proposal_id": proposal_id,
        "approved": True,
        "update_mode": recommended_mode,
        "requires_restart": bool(requires_restart),
        "apply_action": "apply_rules_only" if recommended_mode == "hot" else "require_restart",
        "target_files": record.get("target_files", []),
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
