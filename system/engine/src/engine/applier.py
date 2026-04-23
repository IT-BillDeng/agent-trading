"""Apply approved strategist proposals via the canonical apply gate."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import resolve_artifacts_root, write_json
from .config import load_app_config_raw
from .factors.registry import load_factor_registry
from .factors.schema import validate_factor_registry
from .rule_schema import validate_rules_config
from .strategist_artifacts import (
    load_approval_request,
    mark_request_applied,
    record_deployment_record,
    record_failure_record,
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
        if not target_contents:
            raise ValueError("hot apply requires non-empty target_contents payload")
        return {str(path): payload for path, payload in target_contents.items()}

    if len(target_files) == 1 and record.get("content") not in (None, ""):
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


def _resolve_factor_registry_target(repo_root: Path, target_path: str) -> Path:
    normalized = str(target_path).strip()
    allowed = {
        "factors/registry.json",
        "./factors/registry.json",
        "/workspace/agent-trading/factors/registry.json",
    }
    if normalized not in allowed:
        raise ValueError(f"factor hot apply target must be factors/registry.json: {target_path}")
    return (repo_root / "factors" / "registry.json").resolve()


def _backup_path(target_path: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return target_path.with_name(f"{target_path.name}.bak.{timestamp}")


def _validate_rules_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("rules payload must be a JSON object")
    return validate_rules_config(payload)


def _validate_factor_registry_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("factor registry payload must be a JSON object")
    return validate_factor_registry(payload)


def _write_rules_file(target_path: Path, payload: Any) -> bytes:
    if isinstance(payload, str):
        encoded = payload.encode("utf-8")
    else:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(encoded)
    return encoded


def _write_json_file(target_path: Path, payload: Any) -> bytes:
    if isinstance(payload, str):
        encoded = payload.encode("utf-8")
    else:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(encoded)
    return encoded


def _load_symbol_universe(repo_root: Path) -> list[str] | None:
    for config_path in (repo_root / "config" / "app_config.docker.json", repo_root / "config" / "app.defaults.json"):
        if not config_path.exists():
            continue
        try:
            config = load_app_config_raw(config_path)
        except Exception:
            continue
        strategy = config.get("strategy", {}) if isinstance(config, dict) else {}
        symbols = strategy.get("symbols", []) if isinstance(strategy, dict) else []
        universe = [
            str(item.get("symbol")).upper()
            for item in symbols
            if isinstance(item, dict) and item.get("symbol")
        ]
        if universe:
            return universe
    return None


def _validate_rules_payload_for_repo(
    payload: Any,
    repo_root: Path,
    *,
    factor_registry: Any = None,
) -> dict[str, Any]:
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("rules payload must be a JSON object")
    return validate_rules_config(
        payload,
        symbol_universe=_load_symbol_universe(repo_root),
        factor_registry=factor_registry,
    )


def _extract_factor_ids_from_condition(condition: Any) -> set[str]:
    factor_ids: set[str] = set()
    if not isinstance(condition, dict):
        return factor_ids

    if condition.get("indicator") == "factor" and condition.get("factor_id"):
        factor_ids.add(str(condition["factor_id"]))

    items = condition.get("items")
    if isinstance(items, list):
        for item in items:
            factor_ids.update(_extract_factor_ids_from_condition(item))
    return factor_ids


def _factor_ids_from_rule(rule: dict[str, Any]) -> set[str]:
    factor_ids: set[str] = set()
    for section in ("entry", "exit"):
        cfg = rule.get(section)
        if isinstance(cfg, dict):
            factor_ids.update(_extract_factor_ids_from_condition(cfg.get("conditions")))
    return factor_ids


def _rule_enabled(rule: dict[str, Any] | None) -> bool:
    if not isinstance(rule, dict):
        return False
    return bool(rule.get("enabled", True))


def _validate_factor_rule_link_hot_apply(
    before_payload: dict[str, Any],
    after_payload: dict[str, Any],
) -> dict[str, Any]:
    before_rules = {
        str(rule.get("rule_id")): rule
        for rule in before_payload.get("rules", [])
        if isinstance(rule, dict) and rule.get("rule_id")
    }
    after_rules = {
        str(rule.get("rule_id")): rule
        for rule in after_payload.get("rules", [])
        if isinstance(rule, dict) and rule.get("rule_id")
    }

    changed_rule_ids: list[str] = []
    changed_enabled_rule_ids: list[str] = []
    for rule_id in sorted(set(before_rules.keys()) | set(after_rules.keys())):
        if before_rules.get(rule_id) == after_rules.get(rule_id):
            continue
        changed_rule_ids.append(rule_id)
        if _rule_enabled(before_rules.get(rule_id)) or _rule_enabled(after_rules.get(rule_id)):
            changed_enabled_rule_ids.append(rule_id)

    changed_global_settings = before_payload.get("global_settings") != after_payload.get("global_settings")
    changed_profile_templates = before_payload.get("symbol_profile_templates") != after_payload.get("symbol_profile_templates")
    changed_symbol_profiles = before_payload.get("symbol_profiles") != after_payload.get("symbol_profiles")

    errors: list[str] = []
    if changed_enabled_rule_ids:
        errors.append(
            "factor_rule_link hot apply may not change enabled rules: "
            + ", ".join(changed_enabled_rule_ids)
        )
    if changed_global_settings:
        errors.append("factor_rule_link hot apply may not change global_settings")
    if changed_profile_templates:
        errors.append("factor_rule_link hot apply may not change symbol_profile_templates")
    if changed_symbol_profiles:
        errors.append("factor_rule_link hot apply may not change symbol_profiles")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "changed_rule_ids": changed_rule_ids,
        "changed_enabled_rule_ids": changed_enabled_rule_ids,
        "changed_global_settings": changed_global_settings,
        "changed_symbol_profile_templates": changed_profile_templates,
        "changed_symbol_profiles": changed_symbol_profiles,
    }


def _factor_registry_state(repo_root: Path) -> tuple[Any | None, dict[str, Any], str | None]:
    registry_path = (repo_root / "factors" / "registry.json").resolve()
    if not registry_path.exists():
        return None, {"valid": False, "errors": [f"missing factor registry: {registry_path}"], "warnings": []}, None
    try:
        registry = load_factor_registry(registry_path)
    except Exception as exc:
        return None, {"valid": False, "errors": [str(exc)], "warnings": []}, None
    return registry, {"valid": True, "errors": [], "warnings": []}, registry.config_hash


def _rule_ids_from_profile_payload(payload: dict[str, Any]) -> set[str]:
    rule_ids: set[str] = set()
    enabled_rules = payload.get("enabled_rules")
    if isinstance(enabled_rules, dict):
        rule_ids.update(str(rule_id) for rule_id in enabled_rules.keys())
    rule_overrides = payload.get("rule_overrides")
    if isinstance(rule_overrides, dict):
        rule_ids.update(str(rule_id) for rule_id in rule_overrides.keys())
    return rule_ids


def _describe_rules_changes(before_payload: dict[str, Any], after_payload: dict[str, Any]) -> dict[str, list[str]]:
    changed_rules: set[str] = set()
    changed_profiles: set[str] = set()
    changed_symbols: set[str] = set()
    changed_factors: set[str] = set()

    before_rules = {
        str(rule.get("rule_id")): rule
        for rule in before_payload.get("rules", [])
        if isinstance(rule, dict) and rule.get("rule_id")
    }
    after_rules = {
        str(rule.get("rule_id")): rule
        for rule in after_payload.get("rules", [])
        if isinstance(rule, dict) and rule.get("rule_id")
    }
    for rule_id in sorted(set(before_rules.keys()) | set(after_rules.keys())):
        if before_rules.get(rule_id) != after_rules.get(rule_id):
            changed_rules.add(rule_id)
            changed_factors.update(_factor_ids_from_rule(after_rules.get(rule_id) or before_rules.get(rule_id) or {}))

    before_templates = before_payload.get("symbol_profile_templates", {}) if isinstance(before_payload.get("symbol_profile_templates"), dict) else {}
    after_templates = after_payload.get("symbol_profile_templates", {}) if isinstance(after_payload.get("symbol_profile_templates"), dict) else {}
    for profile_id in sorted(set(before_templates.keys()) | set(after_templates.keys())):
        if before_templates.get(profile_id) != after_templates.get(profile_id):
            changed_profiles.add(str(profile_id))
            changed_rules.update(_rule_ids_from_profile_payload(after_templates.get(profile_id) or before_templates.get(profile_id) or {}))

    before_symbol_profiles = before_payload.get("symbol_profiles", {}) if isinstance(before_payload.get("symbol_profiles"), dict) else {}
    after_symbol_profiles = after_payload.get("symbol_profiles", {}) if isinstance(after_payload.get("symbol_profiles"), dict) else {}
    for symbol in sorted(set(before_symbol_profiles.keys()) | set(after_symbol_profiles.keys())):
        if before_symbol_profiles.get(symbol) != after_symbol_profiles.get(symbol):
            changed_symbols.add(str(symbol))
            after_symbol_profile = after_symbol_profiles.get(symbol) or {}
            before_symbol_profile = before_symbol_profiles.get(symbol) or {}
            profile_name = after_symbol_profile.get("profile") or before_symbol_profile.get("profile")
            if profile_name:
                changed_profiles.add(str(profile_name))
            changed_rules.update(_rule_ids_from_profile_payload(after_symbol_profile or before_symbol_profile or {}))

    return {
        "changed_factors": sorted(changed_factors),
        "changed_profiles": sorted(changed_profiles),
        "changed_symbols": sorted(changed_symbols),
        "changed_rules": sorted(changed_rules),
    }


def _describe_factor_registry_changes(before_payload: dict[str, Any], after_payload: dict[str, Any]) -> list[str]:
    before_factors = before_payload.get("factors", {}) if isinstance(before_payload.get("factors"), dict) else {}
    after_factors = after_payload.get("factors", {}) if isinstance(after_payload.get("factors"), dict) else {}
    changed_factors: set[str] = set()
    for factor_id in sorted(set(before_factors.keys()) | set(after_factors.keys())):
        if before_factors.get(factor_id) != after_factors.get(factor_id):
            changed_factors.add(str(factor_id))
    return sorted(changed_factors)


def _proposal_validation_summary(record: dict[str, Any]) -> dict[str, Any]:
    validation = record.get("proposal_validation")
    if isinstance(validation, dict):
        return dict(validation)
    return {"valid": True, "errors": [], "warnings": [], "proposal_type": None}


def _record_apply_failure(
    *,
    proposal_id: str,
    record: dict[str, Any],
    plan: dict[str, Any],
    operator_type: str,
    operator_id: str,
    error: Exception,
    deployment_targets: list[dict[str, Any]],
    validation_summary: dict[str, Any],
    rollback_performed: bool,
    changed_factors: list[str] | None = None,
    changed_rules: list[str] | None = None,
    registry_hash: str | None = None,
    base_dir: str | Path | None = None,
) -> None:
    recorded_at = datetime.now(timezone.utc).isoformat()
    deployment_record = {
        "proposal_id": proposal_id,
        "proposal_type": record.get("proposal_type"),
        "operator_type": operator_type,
        "operator_id": operator_id,
        "update_mode": plan["update_mode"],
        "requires_restart": plan["requires_restart"],
        "apply_action": plan["apply_action"],
        "fee_confidence_snapshot": plan.get("fee_confidence_snapshot"),
        "applied_at": recorded_at,
        "success": False,
        "error": str(error),
        "rollback_performed": rollback_performed,
        "changed_factors": list(changed_factors or []),
        "changed_rules": list(changed_rules or []),
        "registry_hash": registry_hash,
        "validation_summary": validation_summary,
        "targets": deployment_targets,
    }
    record_deployment_record(deployment_record, base_dir=base_dir)
    record_failure_record(
        {
            "proposal_id": proposal_id,
            "proposal_type": record.get("proposal_type"),
            "operator_type": operator_type,
            "operator_id": operator_id,
            "failed_at": recorded_at,
            "reason": str(error),
            "update_mode": plan["update_mode"],
            "apply_action": plan["apply_action"],
            "rollback_performed": rollback_performed,
            "changed_factors": list(changed_factors or []),
            "changed_rules": list(changed_rules or []),
            "registry_hash": registry_hash,
            "validation_summary": validation_summary,
            "targets": deployment_targets,
        },
        base_dir=base_dir,
    )


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
    proposal_type = str(record.get("proposal_type") or "").strip().lower()

    backups: list[tuple[Path, Path, bytes, bool]] = []
    deployment_targets: list[dict[str, Any]] = []
    changed_profiles: set[str] = set()
    changed_symbols: set[str] = set()
    changed_rules: set[str] = set()
    changed_factors: set[str] = set()
    factor_validation_summary: dict[str, Any] | None = None
    factor_rule_link_safety_summary: dict[str, Any] | None = None
    registry_hash: str | None = None

    try:
        content_map = _normalize_target_content(record, target_files)
        for target in target_files:
            if target not in content_map:
                raise ValueError(f"missing target content for {target}")

            target_path = _resolve_rules_target(repo_root, target)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            original_bytes = target_path.read_bytes() if target_path.exists() else b""
            backup_path = _backup_path(target_path)
            backup_path.write_bytes(original_bytes)
            backups.append((target_path, backup_path, original_bytes, target_path.exists()))

            before_checksum = _checksum_bytes(original_bytes)
            payload = content_map[target]
            factor_registry = None
            if proposal_type == "factor_rule_link":
                factor_registry, factor_validation_summary, registry_hash = _factor_registry_state(repo_root)
                if factor_registry is None:
                    raise ValueError(
                        "factor_rule_link hot apply requires valid factor registry: "
                        + "; ".join(factor_validation_summary.get("errors", []))
                    )

            validation = _validate_rules_payload_for_repo(
                payload,
                repo_root,
                factor_registry=factor_registry,
            )
            if not validation["valid"]:
                raise ValueError(f"invalid rules payload for {target}: {'; '.join(validation['errors'])}")
            rules_validation_summary = {
                "valid": validation["valid"],
                "errors": validation["errors"],
                "warnings": validation["warnings"],
            }

            before_payload = json.loads(original_bytes.decode("utf-8")) if original_bytes else {"rules": []}
            after_payload = json.loads(payload) if isinstance(payload, str) else payload
            if proposal_type == "factor_rule_link":
                factor_rule_link_safety_summary = _validate_factor_rule_link_hot_apply(
                    before_payload,
                    after_payload,
                )
                if not factor_rule_link_safety_summary["valid"]:
                    raise ValueError(
                        "unsafe factor_rule_link hot apply: "
                        + "; ".join(factor_rule_link_safety_summary["errors"])
                    )

            written_bytes = _write_rules_file(target_path, payload)
            after_checksum = _checksum_bytes(written_bytes)
            target_record = {
                "target_file": target,
                "before_checksum": before_checksum,
                "after_checksum": after_checksum,
                "backup_path": str(backup_path),
                "validation_result": rules_validation_summary,
                "validation_summary": {
                    "proposal": _proposal_validation_summary(record),
                    "rules": rules_validation_summary,
                    "factor_registry": factor_validation_summary,
                    "factor_rule_link_safety": factor_rule_link_safety_summary,
                },
                **_describe_rules_changes(before_payload, after_payload),
            }
            changed_factors.update(target_record.get("changed_factors", []))
            changed_profiles.update(target_record.get("changed_profiles", []))
            changed_symbols.update(target_record.get("changed_symbols", []))
            changed_rules.update(target_record.get("changed_rules", []))
            deployment_targets.append(target_record)

        deployment_record = {
            "operator_type": operator_type,
            "operator_id": operator_id,
            "update_mode": plan["update_mode"],
            "requires_restart": plan["requires_restart"],
            "apply_action": plan["apply_action"],
            "fee_confidence_snapshot": plan.get("fee_confidence_snapshot"),
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "success": True,
            "proposal_type": record.get("proposal_type"),
            "changed_factors": sorted(changed_factors),
            "changed_profiles": sorted(changed_profiles),
            "changed_symbols": sorted(changed_symbols),
            "changed_rules": sorted(changed_rules),
            "registry_hash": registry_hash,
            "validation_summary": {
                "proposal": _proposal_validation_summary(record),
                "rules": deployment_targets[0]["validation_result"] if deployment_targets else None,
                "factor_registry": factor_validation_summary,
                "factor_rule_link_safety": factor_rule_link_safety_summary,
            },
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
            "registry_hash": registry_hash,
            "queue_path": str(queue_path),
            "deployment_path": str(deployment_path),
        }
    except Exception as exc:
        for target_path, _, original_bytes, existed_before in reversed(backups):
            if existed_before:
                target_path.write_bytes(original_bytes)
            elif target_path.exists():
                target_path.unlink()
        _record_apply_failure(
            proposal_id=proposal_id,
            record=record,
            plan=plan,
            operator_type=operator_type,
            operator_id=operator_id,
            error=exc,
            deployment_targets=deployment_targets,
            validation_summary={
                "proposal": _proposal_validation_summary(record),
                "rules": deployment_targets[-1]["validation_result"] if deployment_targets else None,
                "factor_registry": factor_validation_summary,
                "factor_rule_link_safety": factor_rule_link_safety_summary,
            },
            rollback_performed=True,
            changed_factors=sorted(changed_factors),
            changed_rules=sorted(changed_rules),
            registry_hash=registry_hash,
            base_dir=base_dir,
        )
        raise


def _apply_hot_factor_registry_update(
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

    backups: list[tuple[Path, Path, bytes, bool]] = []
    deployment_targets: list[dict[str, Any]] = []
    changed_factors: list[str] = []
    registry_hash: str | None = None
    factor_validation_summary: dict[str, Any] | None = None

    try:
        content_map = _normalize_target_content(record, target_files)
        for target in target_files:
            if target not in content_map:
                raise ValueError(f"missing target content for {target}")

            target_path = _resolve_factor_registry_target(repo_root, target)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            original_bytes = target_path.read_bytes() if target_path.exists() else b""
            backup_path = _backup_path(target_path)
            backup_path.write_bytes(original_bytes)
            backups.append((target_path, backup_path, original_bytes, target_path.exists()))

            before_checksum = _checksum_bytes(original_bytes)
            payload = content_map[target]
            validation = _validate_factor_registry_payload(payload)
            factor_validation_summary = {
                "valid": validation["valid"],
                "errors": validation["errors"],
                "warnings": validation["warnings"],
            }
            if not validation["valid"]:
                raise ValueError(f"invalid factor registry payload for {target}: {'; '.join(validation['errors'])}")

            before_payload = json.loads(original_bytes.decode("utf-8")) if original_bytes else {"factors": {}}
            after_payload = json.loads(payload) if isinstance(payload, str) else payload

            written_bytes = _write_json_file(target_path, payload)
            after_checksum = _checksum_bytes(written_bytes)
            changed_factors = _describe_factor_registry_changes(before_payload, after_payload)
            registry_hash = str(validation.get("config_hash") or "")
            deployment_targets.append(
                {
                    "target_file": target,
                    "before_checksum": before_checksum,
                    "after_checksum": after_checksum,
                    "backup_path": str(backup_path),
                    "validation_result": factor_validation_summary,
                    "validation_summary": {
                        "proposal": _proposal_validation_summary(record),
                        "factor_registry": factor_validation_summary,
                    },
                    "changed_factors": changed_factors,
                    "changed_rules": [],
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
            "proposal_type": record.get("proposal_type"),
            "changed_factors": changed_factors,
            "changed_rules": [],
            "registry_hash": registry_hash,
            "validation_summary": {
                "proposal": _proposal_validation_summary(record),
                "factor_registry": factor_validation_summary,
            },
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
            "registry_hash": registry_hash,
            "queue_path": str(queue_path),
            "deployment_path": str(deployment_path),
        }
    except Exception as exc:
        for target_path, _, original_bytes, existed_before in reversed(backups):
            if existed_before:
                target_path.write_bytes(original_bytes)
            elif target_path.exists():
                target_path.unlink()
        _record_apply_failure(
            proposal_id=proposal_id,
            record=record,
            plan=plan,
            operator_type=operator_type,
            operator_id=operator_id,
            error=exc,
            deployment_targets=deployment_targets,
            validation_summary={
                "proposal": _proposal_validation_summary(record),
                "factor_registry": factor_validation_summary,
            },
            rollback_performed=True,
            changed_factors=changed_factors,
            changed_rules=[],
            registry_hash=registry_hash,
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
        "proposal_type": record.get("proposal_type"),
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
        "changed_factors": [str(record.get("factor_id"))] if record.get("proposal_type") in {"factor_config", "factor_rule_link", "factor_code"} and record.get("factor_id") else [],
        "changed_rules": [],
        "registry_hash": (_factor_registry_state(_repo_root(base_dir))[2] if record.get("proposal_type") in {"factor_config", "factor_rule_link", "factor_code"} else None),
        "validation_summary": {
            "proposal": _proposal_validation_summary(record),
        },
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
        "proposal_type": record.get("proposal_type"),
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
        if plan.get("proposal_type") == "factor_config":
            return _apply_hot_factor_registry_update(
                proposal_id,
                record,
                plan,
                operator_type=operator_type,
                operator_id=operator_id,
                base_dir=base_dir,
            )
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
