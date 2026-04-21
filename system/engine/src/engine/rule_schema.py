from __future__ import annotations

import copy
from typing import Any

from .rule_profiles import (
    ALLOWED_ENTRY_OVERRIDE_KEYS,
    ALLOWED_EXIT_OVERRIDE_KEYS,
    ALLOWED_RISK_OVERRIDE_KEYS,
    ALLOWED_RULE_OVERRIDE_SECTIONS,
    DEFAULT_SYMBOL_PROFILE_ID,
    FORBIDDEN_OVERRIDE_KEYS,
    apply_rule_override,
    symbol_profile_templates,
)


SUPPORTED_INDICATORS = {
    "sma",
    "ema",
    "ema_slope",
    "rsi",
    "bollinger",
    "macd",
    "atr",
    "momentum",
    "volume_ratio",
    "bar_range_pct",
}

SUPPORTED_COMPOUND_OPERATORS = {"AND", "OR"}
SUPPORTED_INDICATOR_OPERATORS = {
    "above",
    "below",
    "equal",
    "above_upper",
    "below_lower",
    "above_middle",
    "below_middle",
    "cross_above",
    "cross_below",
}
SUPPORTED_PRICE_OPERATORS = {"above", "below"}
SUPPORTED_VOLUME_OPERATORS = {"above_avg"}
SUPPORTED_CONDITION_TYPES = {"indicator", "price", "volume", "stop_loss", "take_profit", "time"}


def validate_rules_config(
    rules_data: dict[str, Any],
    *,
    symbol_universe: list[str] | set[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(rules_data, dict):
        return {"valid": False, "errors": ["rules payload must be an object"], "warnings": [], "valid_rules": []}

    rules = rules_data.get("rules")
    if not isinstance(rules, list):
        return {"valid": False, "errors": ["Missing 'rules' field"], "warnings": [], "valid_rules": []}

    seen_rule_ids: set[str] = set()
    valid_rules: list[dict[str, Any]] = []
    valid_rule_ids: set[str] = set()

    for index, rule in enumerate(rules):
        rule_errors = _validate_rule(rule, index=index, seen_rule_ids=seen_rule_ids)
        if rule_errors:
            errors.extend(rule_errors)
        else:
            valid_rules.append(rule)
            valid_rule_ids.add(str(rule.get("rule_id")))

    if not errors:
        profile_result = _validate_symbol_profiles(
            rules_data,
            valid_rule_ids=valid_rule_ids,
            symbol_universe=_normalize_symbol_universe(symbol_universe),
        )
        errors.extend(profile_result["errors"])
        warnings.extend(profile_result["warnings"])

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "valid_rules": valid_rules,
    }


def _validate_rule(rule: Any, *, index: int, seen_rule_ids: set[str]) -> list[str]:
    prefix = f"Rule {index}"
    errors: list[str] = []

    if not isinstance(rule, dict):
        return [f"{prefix}: rule must be an object"]

    rule_id = rule.get("rule_id")
    if not isinstance(rule_id, str) or not rule_id.strip():
        errors.append(f"{prefix}: missing or invalid rule_id")
    else:
        if rule_id in seen_rule_ids:
            errors.append(f"{prefix}: duplicate rule_id '{rule_id}'")
        seen_rule_ids.add(rule_id)
        prefix = f"Rule {rule_id}"

    if "enabled" in rule and not isinstance(rule.get("enabled"), bool):
        errors.append(f"{prefix}: enabled must be bool")
    if "priority" in rule and not isinstance(rule.get("priority"), int):
        errors.append(f"{prefix}: priority must be int")

    entry = rule.get("entry")
    if entry is not None:
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: entry must be object")
        else:
            if entry.get("action") != "BUY":
                errors.append(f"{prefix}: entry.action must be BUY")
            errors.extend(_validate_condition_block(entry.get("conditions"), f"{prefix}.entry.conditions"))

    exit_cfg = rule.get("exit")
    if exit_cfg is not None:
        if not isinstance(exit_cfg, dict):
            errors.append(f"{prefix}: exit must be object")
        else:
            if exit_cfg.get("action") != "EXIT":
                errors.append(f"{prefix}: exit.action must be EXIT")
            errors.extend(_validate_condition_block(exit_cfg.get("conditions"), f"{prefix}.exit.conditions"))

    search_space = rule.get("search_space")
    if search_space is not None:
        if not isinstance(search_space, dict):
            errors.append(f"{prefix}: search_space must be object")
        else:
            for name, spec in search_space.items():
                if not isinstance(spec, dict):
                    errors.append(f"{prefix}: search_space.{name} must be object")
                    continue
                path = spec.get("path")
                if not isinstance(path, str) or not path:
                    errors.append(f"{prefix}: search_space.{name} missing path")
                    continue
                resolved = _resolve_path(rule, path)
                if resolved is _MISSING:
                    errors.append(f"{prefix}: search_space path '{path}' does not resolve to a real field")

    errors.extend(_validate_rule_numeric_ranges(rule, prefix))
    return errors


def _validate_condition_block(condition: Any, path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(condition, dict):
        return [f"{path}: conditions must be object"]

    if "operator" in condition and "items" in condition:
        operator = condition.get("operator")
        items = condition.get("items")
        if operator not in SUPPORTED_COMPOUND_OPERATORS:
            errors.append(f"{path}: unsupported compound operator '{operator}'")
        if not isinstance(items, list) or not items:
            errors.append(f"{path}: compound items must be non-empty list")
            return errors
        for idx, item in enumerate(items):
            errors.extend(_validate_condition_block(item, f"{path}.items[{idx}]"))
        return errors

    cond_type = condition.get("type")
    if cond_type not in SUPPORTED_CONDITION_TYPES:
        return [f"{path}: unsupported condition type '{cond_type}'"]

    if cond_type == "indicator":
        indicator = condition.get("indicator")
        if indicator not in SUPPORTED_INDICATORS:
            errors.append(f"{path}: unsupported indicator '{indicator}'")
        compare = condition.get("compare")
        if not isinstance(compare, dict):
            errors.append(f"{path}: indicator compare must be object")
            return errors
        operator = compare.get("operator")
        if operator not in SUPPORTED_INDICATOR_OPERATORS:
            errors.append(f"{path}: unsupported operator '{operator}'")
        compare_indicator = compare.get("indicator")
        compare_field = compare.get("field")
        has_const_value = "value" in compare
        if compare_indicator is not None and compare_indicator not in SUPPORTED_INDICATORS:
            errors.append(f"{path}: unsupported compare indicator '{compare_indicator}'")
        if operator in {"cross_above", "cross_below"} and not (has_const_value or compare_indicator is not None or compare_field == "close"):
            errors.append(f"{path}: cross operator requires compare value, compare indicator, or field='close'")
        if not (has_const_value or compare_indicator is not None or compare_field == "close"):
            errors.append(f"{path}: indicator compare must provide value, compare indicator, or field='close'")
        errors.extend(_validate_indicator_numeric_ranges(condition, path))
        return errors

    if cond_type == "price":
        operator = condition.get("operator")
        if operator not in SUPPORTED_PRICE_OPERATORS:
            errors.append(f"{path}: unsupported operator '{operator}'")
        if condition.get("field") not in {"open", "high", "low", "close"}:
            errors.append(f"{path}: unsupported price field '{condition.get('field')}'")
        if "value" not in condition:
            errors.append(f"{path}: price condition missing value")
        return errors

    if cond_type == "volume":
        operator = condition.get("operator")
        if operator not in SUPPORTED_VOLUME_OPERATORS:
            errors.append(f"{path}: unsupported operator '{operator}'")
        ratio = condition.get("ratio")
        if ratio is not None:
            errors.extend(_validate_range(ratio, min_value=0.1, max_value=10.0, path=f"{path}.ratio"))
        return errors

    if cond_type == "stop_loss":
        errors.extend(_validate_range(condition.get("threshold_pct"), min_value=0.0001, max_value=0.25, path=f"{path}.threshold_pct"))
        return errors

    if cond_type == "take_profit":
        errors.extend(_validate_range(condition.get("threshold_pct"), min_value=0.0001, max_value=0.5, path=f"{path}.threshold_pct"))
        return errors

    return errors


_MISSING = object()


def _resolve_path(payload: Any, path: str) -> Any:
    current = payload
    for token in _tokenize_path(path):
        if isinstance(token, str):
            if not isinstance(current, dict) or token not in current:
                return _MISSING
            current = current[token]
        else:
            if not isinstance(current, list) or token >= len(current):
                return _MISSING
            current = current[token]
    return current


def _tokenize_path(path: str) -> list[str | int]:
    tokens: list[str | int] = []
    segment = ""
    i = 0
    while i < len(path):
        char = path[i]
        if char == ".":
            if segment:
                tokens.append(segment)
                segment = ""
            i += 1
            continue
        if char == "[":
            if segment:
                tokens.append(segment)
                segment = ""
            end = path.find("]", i)
            if end == -1:
                return []
            index_text = path[i + 1:end]
            try:
                tokens.append(int(index_text))
            except ValueError:
                return []
            i = end + 1
            continue
        segment += char
        i += 1
    if segment:
        tokens.append(segment)
    return tokens


def _validate_entry_risk_fields(entry: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    if "stop_loss_pct" in entry:
        errors.extend(_validate_range(entry.get("stop_loss_pct"), min_value=0.0001, max_value=0.25, path=f"{prefix}.entry.stop_loss_pct"))
    if "take_profit_pct" in entry:
        errors.extend(_validate_range(entry.get("take_profit_pct"), min_value=0.0001, max_value=0.5, path=f"{prefix}.entry.take_profit_pct"))
    if "risk_budget" in entry:
        errors.extend(_validate_range(entry.get("risk_budget"), min_value=1.0, max_value=100000.0, path=f"{prefix}.entry.risk_budget"))
    return errors


def _validate_indicator_numeric_ranges(condition: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    indicator = condition.get("indicator")
    params = condition.get("params") if isinstance(condition.get("params"), dict) else {}
    compare = condition.get("compare") if isinstance(condition.get("compare"), dict) else {}
    compare_value = compare.get("value")

    if "period" in params:
        errors.extend(_validate_range(params.get("period"), min_value=1, max_value=250, integer_only=True, path=f"{path}.params.period"))

    if indicator == "ema_slope" and "lookback" in params:
        errors.extend(_validate_range(params.get("lookback"), min_value=1, max_value=50, integer_only=True, path=f"{path}.params.lookback"))

    if indicator == "rsi" and compare_value is not None:
        errors.extend(_validate_range(compare_value, min_value=0, max_value=100, path=f"{path}.compare.value"))
    elif indicator == "bollinger":
        if "std_dev" in params:
            errors.extend(_validate_range(params.get("std_dev"), min_value=0.1, max_value=5.0, path=f"{path}.params.std_dev"))
    elif indicator == "momentum" and compare_value is not None:
        errors.extend(_validate_range(compare_value, min_value=-1.0, max_value=1.0, path=f"{path}.compare.value"))
    elif indicator == "bar_range_pct" and compare_value is not None:
        errors.extend(_validate_range(compare_value, min_value=0.0, max_value=0.5, path=f"{path}.compare.value"))

    if compare.get("indicator") == "bollinger":
        compare_params = compare.get("params") if isinstance(compare.get("params"), dict) else {}
        if "period" in compare_params:
            errors.extend(_validate_range(compare_params.get("period"), min_value=1, max_value=250, integer_only=True, path=f"{path}.compare.params.period"))
        if "std_dev" in compare_params:
            errors.extend(_validate_range(compare_params.get("std_dev"), min_value=0.1, max_value=5.0, path=f"{path}.compare.params.std_dev"))

    return errors


def _validate_rule_numeric_ranges(rule: dict[str, Any], prefix: str) -> list[str]:
    errors: list[str] = []
    entry = rule.get("entry")
    if isinstance(entry, dict):
        errors.extend(_validate_entry_risk_fields(entry, prefix))
    return errors


def _validate_range(
    value: Any,
    *,
    min_value: float,
    max_value: float,
    path: str,
    integer_only: bool = False,
) -> list[str]:
    if value is None:
        return [f"{path} must be provided"]
    if integer_only:
        if not isinstance(value, int) or isinstance(value, bool):
            return [f"{path} must be integer"]
        numeric = float(value)
    else:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return [f"{path} must be numeric"]
        numeric = float(value)
    if numeric < min_value or numeric > max_value:
        return [f"{path} out of range [{min_value}, {max_value}]"]
    return []


def _normalize_symbol_universe(
    symbol_universe: list[str] | set[str] | tuple[str, ...] | None,
) -> set[str] | None:
    if symbol_universe is None:
        return None
    return {str(symbol).strip().upper() for symbol in symbol_universe if str(symbol).strip()}


def _validate_symbol_profiles(
    rules_data: dict[str, Any],
    *,
    valid_rule_ids: set[str],
    symbol_universe: set[str] | None,
) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    templates = rules_data.get("symbol_profile_templates")
    symbol_profiles = rules_data.get("symbol_profiles")

    if templates is not None and not isinstance(templates, dict):
        errors.append("symbol_profile_templates must be an object")
        return {"errors": errors, "warnings": warnings}
    if symbol_profiles is not None and not isinstance(symbol_profiles, dict):
        errors.append("symbol_profiles must be an object")
        return {"errors": errors, "warnings": warnings}

    templates = symbol_profile_templates(rules_data)
    template_names = set(templates.keys())
    rules_by_id = {
        rule.get("rule_id"): rule
        for rule in rules_data.get("rules", [])
        if isinstance(rule, dict) and rule.get("rule_id")
    }

    for template_name, template in templates.items():
        if not isinstance(template, dict):
            errors.append(f"symbol_profile_templates.{template_name} must be an object")
            continue
        if "description" in template and not isinstance(template.get("description"), str):
            errors.append(f"symbol_profile_templates.{template_name}.description must be string")
        errors.extend(
            _validate_profile_rule_controls(
                template_name,
                template,
                rules_by_id=rules_by_id,
                scope="symbol_profile_templates",
            )
        )

    for symbol, profile in (symbol_profiles or {}).items():
        symbol_key = str(symbol).strip().upper()
        if not isinstance(profile, dict):
            errors.append(f"symbol_profiles.{symbol} must be an object")
            continue
        profile_name = str(profile.get("profile") or DEFAULT_SYMBOL_PROFILE_ID)
        if profile_name not in template_names:
            errors.append(f"symbol_profiles.{symbol}.profile references unknown profile '{profile_name}'")
        errors.extend(
            _validate_profile_rule_controls(
                symbol_key,
                profile,
                rules_by_id=rules_by_id,
                scope="symbol_profiles",
            )
        )
        if symbol_universe is not None and symbol_key not in symbol_universe:
            errors.append(f"symbol_profiles.{symbol} references symbol outside current universe")

    for template_name, template in templates.items():
        errors.extend(
            _validate_profile_effective_rules(
                template_name,
                template,
                rules_by_id=rules_by_id,
                scope="symbol_profile_templates",
            )
        )

    for symbol, profile in (symbol_profiles or {}).items():
        profile_name = str(profile.get("profile") or DEFAULT_SYMBOL_PROFILE_ID)
        template = templates.get(profile_name)
        if not isinstance(template, dict):
            continue
        errors.extend(
            _validate_profile_effective_rules(
                str(symbol),
                profile,
                rules_by_id=rules_by_id,
                scope="symbol_profiles",
                template=template,
            )
        )

    return {"errors": errors, "warnings": warnings}


def _validate_profile_rule_controls(
    owner: str,
    payload: dict[str, Any],
    *,
    rules_by_id: dict[str, dict[str, Any]],
    scope: str,
) -> list[str]:
    errors: list[str] = []

    enabled_rules = payload.get("enabled_rules", {})
    if enabled_rules is not None and not isinstance(enabled_rules, dict):
        errors.append(f"{scope}.{owner}.enabled_rules must be an object")
    for rule_id, enabled in (enabled_rules or {}).items():
        if rule_id not in rules_by_id:
            errors.append(f"{scope}.{owner}.enabled_rules references unknown rule_id '{rule_id}'")
            continue
        if not isinstance(enabled, bool):
            errors.append(f"{scope}.{owner}.enabled_rules.{rule_id} must be bool")
        elif enabled and not bool(rules_by_id[rule_id].get("enabled", True)):
            errors.append(f"{scope}.{owner}.enabled_rules.{rule_id} cannot enable base disabled rule")

    rule_overrides = payload.get("rule_overrides", {})
    if rule_overrides is not None and not isinstance(rule_overrides, dict):
        errors.append(f"{scope}.{owner}.rule_overrides must be an object")
    for rule_id, override in (rule_overrides or {}).items():
        if rule_id not in rules_by_id:
            errors.append(f"{scope}.{owner}.rule_overrides references unknown rule_id '{rule_id}'")
            continue
        if not isinstance(override, dict):
            errors.append(f"{scope}.{owner}.rule_overrides.{rule_id} must be an object")
            continue
        errors.extend(_validate_rule_override_shape(override, f"{scope}.{owner}.rule_overrides.{rule_id}"))

    return errors


def _validate_rule_override_shape(override: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    for key in override.keys():
        if key in FORBIDDEN_OVERRIDE_KEYS:
            errors.append(f"{path}.{key} is forbidden")
        elif key not in ALLOWED_RULE_OVERRIDE_SECTIONS:
            errors.append(f"{path}.{key} is not allowed")

    entry = override.get("entry")
    if entry is not None:
        if not isinstance(entry, dict):
            errors.append(f"{path}.entry must be an object")
        else:
            for key in entry.keys():
                if key in FORBIDDEN_OVERRIDE_KEYS:
                    errors.append(f"{path}.entry.{key} is forbidden")
                elif key not in ALLOWED_ENTRY_OVERRIDE_KEYS:
                    errors.append(f"{path}.entry.{key} is not allowed")

    exit_cfg = override.get("exit")
    if exit_cfg is not None:
        if not isinstance(exit_cfg, dict):
            errors.append(f"{path}.exit must be an object")
        else:
            for key in exit_cfg.keys():
                if key in FORBIDDEN_OVERRIDE_KEYS:
                    errors.append(f"{path}.exit.{key} is forbidden")
                elif key not in ALLOWED_EXIT_OVERRIDE_KEYS:
                    errors.append(f"{path}.exit.{key} is not allowed")

    risk = override.get("risk")
    if risk is not None:
        if not isinstance(risk, dict):
            errors.append(f"{path}.risk must be an object")
        else:
            for key in risk.keys():
                if key in FORBIDDEN_OVERRIDE_KEYS:
                    errors.append(f"{path}.risk.{key} is forbidden")
                elif key not in ALLOWED_RISK_OVERRIDE_KEYS:
                    errors.append(f"{path}.risk.{key} is not allowed")

    return errors


def _validate_profile_effective_rules(
    owner: str,
    payload: dict[str, Any],
    *,
    rules_by_id: dict[str, dict[str, Any]],
    scope: str,
    template: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    enabled_rules = dict(template.get("enabled_rules") or {}) if isinstance(template, dict) else {}
    enabled_rules.update(payload.get("enabled_rules") or {})

    merged_rule_overrides = dict(template.get("rule_overrides") or {}) if isinstance(template, dict) else {}
    for rule_id, override in (payload.get("rule_overrides") or {}).items():
        if rule_id not in merged_rule_overrides:
            merged_rule_overrides[rule_id] = copy.deepcopy(override)
            continue
        merged_rule_overrides[rule_id] = _merge_override_payload(merged_rule_overrides[rule_id], override)

    for rule_id, requested_enabled in enabled_rules.items():
        rule = rules_by_id.get(rule_id)
        if not isinstance(rule, dict):
            continue
        if requested_enabled and not bool(rule.get("enabled", True)):
            errors.append(f"{scope}.{owner}.enabled_rules.{rule_id} cannot enable base disabled rule")

    for rule_id, override in merged_rule_overrides.items():
        rule = rules_by_id.get(rule_id)
        if not isinstance(rule, dict):
            continue
        try:
            effective_rule, _ = apply_rule_override(rule, override)
        except Exception as exc:
            errors.append(f"{scope}.{owner}.rule_overrides.{rule_id} invalid: {exc}")
            continue
        errors.extend(_validate_rule(copy.deepcopy(effective_rule), index=-1, seen_rule_ids=set()))
        prefix = f"{scope}.{owner}.rule_overrides.{rule_id}"
        errors.extend(_validate_rule_numeric_ranges(effective_rule, prefix))

    return errors


def _merge_override_payload(base: Any, override: Any) -> dict[str, Any]:
    if not isinstance(base, dict):
        return copy.deepcopy(override) if isinstance(override, dict) else {}
    result = copy.deepcopy(base)
    if not isinstance(override, dict):
        return result
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            next_value = copy.deepcopy(result[key])
            for nested_key, nested_value in value.items():
                next_value[nested_key] = copy.deepcopy(nested_value)
            result[key] = next_value
        else:
            result[key] = copy.deepcopy(value)
    return result
