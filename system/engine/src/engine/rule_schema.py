from __future__ import annotations

from typing import Any


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


def validate_rules_config(rules_data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(rules_data, dict):
        return {"valid": False, "errors": ["rules payload must be an object"], "warnings": [], "valid_rules": []}

    rules = rules_data.get("rules")
    if not isinstance(rules, list):
        return {"valid": False, "errors": ["Missing 'rules' field"], "warnings": [], "valid_rules": []}

    seen_rule_ids: set[str] = set()
    valid_rules: list[dict[str, Any]] = []

    for index, rule in enumerate(rules):
        rule_errors = _validate_rule(rule, index=index, seen_rule_ids=seen_rule_ids)
        if rule_errors:
            errors.extend(rule_errors)
        else:
            valid_rules.append(rule)

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
