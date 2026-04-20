"""Apply approved strategist proposals via the canonical apply gate."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import resolve_artifacts_root, write_json
from .rule_schema import validate_rules_config
from .strategist_artifacts import (
    load_approval_request,
    mark_request_applied,
    record_deployment_record,
    resolve_apply_gate,
)


def _artifacts_root(base_dir: str | Path | None = None) -> Path:
    return resolve_artifacts_root(base_dir)


def _repo_root(base_dir: str | Path | None = None) -> Path:
    return _artifacts_root(base_dir).parent


def _approval_queue_path(proposal_id: str, base_dir: str | Path | None = None) -> Path:
    return _artifacts_root(base_dir) / "strategist" / "approval_queue" / f"{proposal_id}.json"


def _checksum_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _normalize_target_content(record: dict[str, Any], target_files: list[str]) -> dict[str, Any]:
    target_contents = record.get("target_contents")
    if isinstance(target_contents, dict):
        return {str(path): payload for path, payload in target_contents.items()}

    if len(target_files) == 1 and "content" in record:
        return {target_files[0]: record.get("content")}

    raise ValueError("hot apply requires target_contents or single-file content payload")


def _resolve_rules_target(repo_root: Path, target_path: str) -> Path:
    normalized = str(target_path).strip()
    prefixes = ("./rules/", "rules/", "/workspace/agent-trading/rules/")
    if not any(normalized.startswith(prefix) for prefix in prefixes):
        raise ValueError(f"hot apply target must stay within rules/: {target_path}")

    if normalized.startswith("/workspace/agent-trading/"):
        normalized = normalized[len("/workspace/agent-trading/") :]
    if normalized.startswith("./"):
        normalized = normalized[2:]

    resolved = (repo_root / normalized).resolve()
    rules_root = (repo_root / "rules").resolve()
    if rules_root not in resolved.parents and resolved != rules_root:
        raise ValueError(f"resolved hot apply target escaped rules/: {target_path}")
    return resolved


def _backup_path(target_path: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return target_path.with_name(f"{target_path.name}.bak.{timestamp}")


def _validate_rules_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("rules payload must be a JSON object")
    return validate_rules_config(payload)


def _write_rules_file(target_path: Path, payload: Any) -> bytes:
    if isinstance(payload, str):
        encoded = payload.encode("utf-8")
    else:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(encoded)
    return encoded


def _apply_hot_rules_update(
    proposal_id: str,
    record: dict[str, Any],
    plan: dict[str, Any],
    *,
    operator_type: str,
    operator_id: str,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    repo_root = _repo_root(base_dir)
    target_files = [str(path) for path in plan["target_files"]]
    content_map = _normalize_target_content(record, target_files)

    backups: list[tuple[Path, Path, bytes, bool]] = []
    deployment_targets: list[dict[str, Any]] = []

    try:
        for target in target_files:
            if target not in content_map:
                raise ValueError(f"missing target content for {target}")

            target_path = _resolve_rules_target(repo_root, target)
            original_bytes = target_path.read_bytes() if target_path.exists() else b""
            backup_path = _backup_path(target_path)
            backup_path.write_bytes(original_bytes)
            backups.append((target_path, backup_path, original_bytes, target_path.exists()))

            before_checksum = _checksum_bytes(original_bytes)
            payload = content_map[target]
            validation = _validate_rules_payload(payload)
            if not validation["valid"]:
                raise ValueError(f"invalid rules payload for {target}: {'; '.join(validation['errors'])}")

            written_bytes = _write_rules_file(target_path, payload)
            after_checksum = _checksum_bytes(written_bytes)
            deployment_targets.append(
                {
                    "target_file": target,
                    "before_checksum": before_checksum,
                    "after_checksum": after_checksum,
                    "backup_path": str(backup_path),
                    "validation_result": {
                        "valid": validation["valid"],
                        "errors": validation["errors"],
                        "warnings": validation["warnings"],
                    },
                }
            )

        deployment_record = {
            "operator_type": operator_type,
            "operator_id": operator_id,
            "update_mode": plan["update_mode"],
            "requires_restart": plan["requires_restart"],
            "apply_action": plan["apply_action"],
            "fee_confidence_snapshot": plan.get("fee_confidence_snapshot"),
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "success": True,
            "targets": deployment_targets,
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
    except Exception as exc:
        for target_path, _, original_bytes, existed_before in reversed(backups):
            if existed_before:
                target_path.write_bytes(original_bytes)
            elif target_path.exists():
                target_path.unlink()
        record_deployment_record(
            {
                "proposal_id": proposal_id,
                "operator_type": operator_type,
                "operator_id": operator_id,
                "update_mode": plan["update_mode"],
                "requires_restart": plan["requires_restart"],
                "apply_action": plan["apply_action"],
                "fee_confidence_snapshot": plan.get("fee_confidence_snapshot"),
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "success": False,
                "error": str(exc),
                "rollback_performed": True,
                "targets": deployment_targets,
            },
            base_dir=base_dir,
        )
        raise


def _record_manual_code_apply_required(
    proposal_id: str,
    record: dict[str, Any],
    plan: dict[str, Any],
    *,
    operator_type: str,
    operator_id: str,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    queue_path = _approval_queue_path(proposal_id, base_dir)
    recorded_at = datetime.now(timezone.utc).isoformat()
    queue_record = dict(record)
    queue_record.update(
        {
            "requires_restart": True,
            "manual_code_apply_required": True,
            "manual_code_apply_recorded_at": recorded_at,
            "manual_code_apply_operator_type": operator_type,
            "manual_code_apply_operator_id": operator_id,
            "manual_code_apply_reason": "cold proposal requires manual code apply",
            "apply_gate": {
                "proposal_id": plan["proposal_id"],
                "update_mode": plan["update_mode"],
                "requires_restart": True,
                "apply_action": "manual_code_apply_required",
                "target_files": plan["target_files"],
                "fee_confidence_snapshot": plan.get("fee_confidence_snapshot"),
                "fee_confidence_gate": plan.get("fee_confidence_gate"),
            },
        }
    )
    write_json(queue_path, queue_record)

    deployment_record = {
        "proposal_id": proposal_id,
        "operator_type": operator_type,
        "operator_id": operator_id,
        "update_mode": plan["update_mode"],
        "requires_restart": True,
        "apply_action": "manual_code_apply_required",
        "fee_confidence_snapshot": plan.get("fee_confidence_snapshot"),
        "recorded_at": recorded_at,
        "success": True,
        "code_applied": False,
        "manual_code_apply_required": True,
        "targets": [{"target_file": target} for target in plan["target_files"]],
    }
    deployment_path = record_deployment_record(deployment_record, base_dir=base_dir)

    return {
        "proposal_id": proposal_id,
        "applied": False,
        "recorded": True,
        "manual_code_apply_required": True,
        "update_mode": plan["update_mode"],
        "requires_restart": True,
        "apply_action": "manual_code_apply_required",
        "queue_path": str(queue_path),
        "deployment_path": str(deployment_path),
    }


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
        "fee_confidence_snapshot": gate.get("fee_confidence_snapshot"),
        "fee_confidence_gate": gate.get("fee_confidence_gate"),
    }


def apply_approved_proposal(
    proposal_id: str,
    operator_type: str,
    operator_id: str,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    plan = build_apply_plan(proposal_id, base_dir)
    record = load_approval_request(proposal_id, base_dir)

    if plan["update_mode"] == "hot":
        return _apply_hot_rules_update(
            proposal_id,
            record,
            plan,
            operator_type=operator_type,
            operator_id=operator_id,
            base_dir=base_dir,
        )

    return _record_manual_code_apply_required(
        proposal_id,
        record,
        plan,
        operator_type=operator_type,
        operator_id=operator_id,
        base_dir=base_dir,
    )
