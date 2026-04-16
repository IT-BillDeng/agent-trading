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
    queue_path = transition_approval_status(
        proposal_id,
        "applied",
        updates={"applied": True, **deployment_record},
        base_dir=base_dir,
    )
    deployment_path = record_deployment_record(
        {"proposal_id": proposal_id, **deployment_record},
        base_dir=base_dir,
    )
    return queue_path, deployment_path
