from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from .factors.registry import FactorRegistry, load_factor_registry


DIAGNOSTIC_FACTOR_RULES_FILENAME = "diagnostic_factor_rules.json"
DIAGNOSTIC_FACTOR_RULES_TARGET = "rules/diagnostic_factor_rules.json"
FORBIDDEN_DIAGNOSTIC_KEYS = {
    "execution",
    "broker",
    "live_submit",
    "submit_mode",
    "execution_preview",
    "order_intents",
}


def default_diagnostic_factor_rules_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "diagnostic_factor_rules",
        "diagnostic_only": True,
        "production_rules_modified": False,
        "rules": [],
    }


def load_diagnostic_factor_rules(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    if not target.exists():
        return default_diagnostic_factor_rules_payload()
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("diagnostic factor rules payload must be an object")
    return payload


def diagnostic_factor_rules_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = default_diagnostic_factor_rules_payload()
    rules = payload.get("rules") if isinstance(payload.get("rules"), list) else []
    source_rules = sorted(
        {
            str(rule.get("source_rule_id"))
            for rule in rules
            if isinstance(rule, dict) and rule.get("source_rule_id")
        }
    )
    factor_ids = sorted(
        {
            factor_id
            for rule in rules
            if isinstance(rule, dict)
            for factor_id in _factor_ids_from_diagnostic_rule(rule)
        }
    )
    diagnostic_only_count = sum(
        1 for rule in rules if isinstance(rule, dict) and bool(rule.get("diagnostic_only")) is True
    )
    enabled_count = sum(1 for rule in rules if isinstance(rule, dict) and bool(rule.get("enabled", False)))
    latest_rules = [rule for rule in rules[-5:] if isinstance(rule, dict)]
    latest_diagnostic_rule_ids = [
        str(rule.get("rule_id")) for rule in latest_rules if rule.get("rule_id")
    ]
    latest_source_rule_ids = sorted(
        {
            str(rule.get("source_rule_id"))
            for rule in latest_rules
            if rule.get("source_rule_id")
        }
    )
    latest_factor_ids = sorted(
        {
            factor_id
            for rule in latest_rules
            for factor_id in _factor_ids_from_diagnostic_rule(rule)
        }
    )
    return {
        "schema_version": payload.get("schema_version"),
        "kind": payload.get("kind"),
        "diagnostic_only": bool(payload.get("diagnostic_only", False)),
        "production_rules_modified": bool(payload.get("production_rules_modified", False)),
        "rule_count": len(rules),
        "enabled_count": enabled_count,
        "diagnostic_only_count": diagnostic_only_count,
        "source_rules": source_rules,
        "factor_ids": factor_ids,
        "latest_diagnostic_rule_ids": latest_diagnostic_rule_ids,
        "latest_source_rule_ids": latest_source_rule_ids,
        "latest_factor_ids": latest_factor_ids,
    }


def validate_diagnostic_factor_rules(
    payload: Any,
    *,
    source_rules_payload: dict[str, Any] | None = None,
    factor_registry: FactorRegistry | str | Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception as exc:
            return {"valid": False, "errors": [f"invalid diagnostic JSON: {exc}"], "warnings": []}

    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["diagnostic factor rules payload must be an object"], "warnings": []}

    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if payload.get("kind") != "diagnostic_factor_rules":
        errors.append("kind must be diagnostic_factor_rules")
    if payload.get("diagnostic_only") is not True:
        errors.append("diagnostic_only must be true")
    if payload.get("production_rules_modified") is not False:
        errors.append("production_rules_modified must be false")

    forbidden = sorted(_forbidden_keys(payload))
    if forbidden:
        errors.append("diagnostic factor rules may not contain forbidden fields: " + ", ".join(forbidden))

    rules = payload.get("rules")
    if not isinstance(rules, list):
        errors.append("rules must be a list")
        rules = []

    source_rule_ids = _source_rule_ids(source_rules_payload)
    registry_factor_ids, registry_error = _registry_factor_ids(factor_registry)
    if registry_error:
        errors.append(registry_error)

    seen: set[str] = set()
    for index, rule in enumerate(rules):
        prefix = f"diagnostic rule {index}"
        if not isinstance(rule, dict):
            errors.append(f"{prefix}: rule must be an object")
            continue
        rule_id = rule.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            errors.append(f"{prefix}: rule_id must be a non-empty string")
        elif rule_id in seen:
            errors.append(f"{prefix}: duplicate rule_id {rule_id}")
        else:
            seen.add(rule_id)
            prefix = f"diagnostic rule {rule_id}"

        if rule.get("diagnostic_only") is not True:
            errors.append(f"{prefix}: diagnostic_only must be true")
        if rule.get("apply_allowed") is not False:
            errors.append(f"{prefix}: apply_allowed must be false")
        if bool(rule.get("enabled", False)):
            errors.append(f"{prefix}: enabled must be false")
        mode = str(rule.get("mode") or "diagnostic").strip().lower()
        if mode != "diagnostic":
            errors.append(f"{prefix}: mode must be diagnostic")
        if rule.get("target") == "rules/rules.json":
            errors.append(f"{prefix}: target=rules/rules.json is not allowed")
        if rule.get("entered_risk") is not False:
            errors.append(f"{prefix}: entered_risk must be false")
        if rule.get("entered_execution") is not False:
            errors.append(f"{prefix}: entered_execution must be false")
        if rule.get("entered_order_intents") is not False:
            errors.append(f"{prefix}: entered_order_intents must be false")

        source_rule_id = rule.get("source_rule_id")
        if not isinstance(source_rule_id, str) or not source_rule_id.strip():
            errors.append(f"{prefix}: source_rule_id must be a non-empty string")
        elif source_rule_ids is not None and source_rule_id not in source_rule_ids:
            errors.append(f"{prefix}: unknown source_rule_id {source_rule_id}")

        factor_ids = _factor_ids_from_diagnostic_rule(rule)
        if not factor_ids:
            errors.append(f"{prefix}: factors must reference at least one factor_id")
        for factor_id in sorted(factor_ids):
            if registry_factor_ids is not None and factor_id not in registry_factor_ids:
                errors.append(f"{prefix}: unknown factor_id {factor_id}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": diagnostic_factor_rules_summary(payload),
    }


def build_diagnostic_rule_from_proposal(record: dict[str, Any], *, created_at: str) -> dict[str, Any]:
    factor_ids = _factor_ids_from_record(record)
    return {
        "rule_id": str(record.get("diagnostic_rule_id") or f"diag_{record.get('source_rule_id')}_{record.get('factor_id')}"),
        "source_rule_id": str(record.get("source_rule_id")),
        "diagnostic_only": True,
        "enabled": False,
        "mode": "diagnostic",
        "factors": factor_ids,
        "conditions": record.get("conditions") or record.get("diagnostic_conditions") or [],
        "created_from_proposal_id": str(record.get("proposal_id")),
        "created_at": created_at,
        "apply_allowed": False,
        "entered_risk": False,
        "entered_execution": False,
        "entered_order_intents": False,
    }


def merge_diagnostic_rule(payload: dict[str, Any], rule: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    merged = dict(payload or default_diagnostic_factor_rules_payload())
    existing_rules = merged.get("rules") if isinstance(merged.get("rules"), list) else []
    rules = [dict(item) for item in existing_rules if isinstance(item, dict)]
    rule_id = str(rule.get("rule_id"))
    changed = []
    replaced = False
    for index, existing in enumerate(rules):
        if str(existing.get("rule_id")) == rule_id:
            rules[index] = dict(rule)
            replaced = True
            changed.append(rule_id)
            break
    if not replaced:
        rules.append(dict(rule))
        changed.append(rule_id)
    merged.update(default_diagnostic_factor_rules_payload())
    merged["rules"] = rules
    return merged, changed


def _factor_ids_from_record(record: dict[str, Any]) -> list[str]:
    raw_ids = record.get("factor_ids")
    ids: list[str] = []
    if isinstance(raw_ids, list):
        ids.extend(str(item) for item in raw_ids if str(item).strip())
    if record.get("factor_id"):
        ids.append(str(record["factor_id"]))
    return sorted(set(ids))


def _factor_ids_from_diagnostic_rule(rule: dict[str, Any]) -> set[str]:
    factor_ids: set[str] = set()
    raw_factors = rule.get("factors")
    if isinstance(raw_factors, list):
        for item in raw_factors:
            if isinstance(item, str) and item.strip():
                factor_ids.add(item.strip())
            elif isinstance(item, dict) and item.get("factor_id"):
                factor_ids.add(str(item["factor_id"]))
    factor_ids.update(_factor_ids_from_conditions(rule.get("conditions")))
    return factor_ids


def _factor_ids_from_conditions(value: Any) -> set[str]:
    factor_ids: set[str] = set()
    if isinstance(value, dict):
        if value.get("factor_id"):
            factor_ids.add(str(value["factor_id"]))
        for item in value.values():
            factor_ids.update(_factor_ids_from_conditions(item))
    elif isinstance(value, list):
        for item in value:
            factor_ids.update(_factor_ids_from_conditions(item))
    return factor_ids


def _source_rule_ids(payload: dict[str, Any] | None) -> set[str] | None:
    if payload is None:
        return None
    rules = payload.get("rules") if isinstance(payload, dict) else None
    if not isinstance(rules, list):
        return set()
    return {
        str(rule.get("rule_id"))
        for rule in rules
        if isinstance(rule, dict) and rule.get("rule_id")
    }


def _registry_factor_ids(factor_registry: FactorRegistry | str | Path | None) -> tuple[set[str] | None, str | None]:
    if factor_registry is None:
        return None, None
    try:
        registry = load_factor_registry(factor_registry) if isinstance(factor_registry, (str, Path)) else factor_registry
    except Exception as exc:
        return None, f"invalid factor registry: {exc}"
    return set(registry.factors.keys()), None


def _forbidden_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in FORBIDDEN_DIAGNOSTIC_KEYS:
                yield str(key)
            yield from _forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _forbidden_keys(child)


__all__ = [
    "DIAGNOSTIC_FACTOR_RULES_TARGET",
    "build_diagnostic_rule_from_proposal",
    "default_diagnostic_factor_rules_payload",
    "diagnostic_factor_rules_summary",
    "load_diagnostic_factor_rules",
    "merge_diagnostic_rule",
    "validate_diagnostic_factor_rules",
]
