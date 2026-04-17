"""Apply approved strategist proposals via the canonical apply gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .strategist_artifacts import load_approval_request, mark_request_applied, resolve_apply_gate


def build_apply_plan(proposal_id: str, base_dir: str | Path | None = None) -> dict[str, Any]:
    record = load_approval_request(proposal_id, base_dir)
    gate = resolve_apply_gate(proposal_id, base_dir)
    return {
        "proposal_id": proposal_id,
        "status": record.get("status"),
        "update_mode": gate["update_mode"],
        "requires_restart": gate["requires_restart"],
        "apply_action": gate["apply_action"],
        "target_files": gate["target_files"],
        "recommended_update_mode": record.get("recommended_update_mode", gate["update_mode"]),
    }


def apply_approved_proposal(
    proposal_id: str,
    operator_type: str,
    operator_id: str,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    plan = build_apply_plan(proposal_id, base_dir)

    deployment_record = {
        "operator_type": operator_type,
        "operator_id": operator_id,
        "update_mode": plan["update_mode"],
        "requires_restart": plan["requires_restart"],
        "apply_action": plan["apply_action"],
        "success": True,
    }

    queue_path, deployment_path = mark_request_applied(
        proposal_id,
        deployment_record,
        base_dir=base_dir,
    )

    return {
        "proposal_id": proposal_id,
        "applied": True,
        "update_mode": plan["update_mode"],
        "requires_restart": plan["requires_restart"],
        "apply_action": plan["apply_action"],
        "queue_path": str(queue_path),
        "deployment_path": str(deployment_path),
    }
