from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


DEFAULT_SYMBOL_PROFILE_ID = "default_shared_30m"
DEFAULT_SYMBOL_PROFILE_TEMPLATE = {
    "description": "Behavior-preserving default profile. Uses the same enabled rules as the base rules.",
    "enabled_rules": {},
    "rule_overrides": {},
}

ALLOWED_RULE_OVERRIDE_SECTIONS = {"entry", "exit", "risk"}
ALLOWED_ENTRY_OVERRIDE_KEYS = {"conditions"}
ALLOWED_EXIT_OVERRIDE_KEYS = {"conditions"}
ALLOWED_RISK_OVERRIDE_KEYS = {"stop_loss_pct", "take_profit_pct", "risk_budget"}
FORBIDDEN_OVERRIDE_KEYS = {
    "rule_id",
    "name",
    "strategy_id",
    "symbols",
    "broker",
    "execution",
    "live_submit",
    "submit_mode",
}


def symbol_profile_templates(rules_config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    templates = dict(rules_config.get("symbol_profile_templates") or {})
    default_template = templates.get(DEFAULT_SYMBOL_PROFILE_ID)
    if not isinstance(default_template, dict):
        templates[DEFAULT_SYMBOL_PROFILE_ID] = copy.deepcopy(DEFAULT_SYMBOL_PROFILE_TEMPLATE)
    return templates


def symbol_profile_config(rules_config: dict[str, Any], symbol: str) -> dict[str, Any]:
    symbol_profiles = rules_config.get("symbol_profiles") or {}
    profile = symbol_profiles.get(symbol)
    if not isinstance(profile, dict):
        return {
            "profile": DEFAULT_SYMBOL_PROFILE_ID,
            "enabled_rules": {},
            "rule_overrides": {},
        }
    return {
        "profile": str(profile.get("profile") or DEFAULT_SYMBOL_PROFILE_ID),
        "enabled_rules": dict(profile.get("enabled_rules") or {}),
        "rule_overrides": dict(profile.get("rule_overrides") or {}),
    }


def resolve_symbol_profile(
    rules_config: dict[str, Any],
    symbol: str,
) -> dict[str, Any]:
    templates = symbol_profile_templates(rules_config)
    symbol_cfg = symbol_profile_config(rules_config, symbol)
    profile_id = symbol_cfg["profile"]
    template = templates.get(profile_id)
    if not isinstance(template, dict):
        raise ValueError(f"unknown profile name '{profile_id}' for symbol {symbol}")
    return {
        "profile_id": profile_id,
        "template": {
            "description": template.get("description"),
            "enabled_rules": dict(template.get("enabled_rules") or {}),
            "rule_overrides": dict(template.get("rule_overrides") or {}),
        },
        "symbol": {
            "enabled_rules": dict(symbol_cfg.get("enabled_rules") or {}),
            "rule_overrides": dict(symbol_cfg.get("rule_overrides") or {}),
        },
    }


def rule_applies_to_symbol(rule: dict[str, Any], symbol: str, market: str | None = None) -> bool:
    rule_symbols = rule.get("symbols", ["*"])
    if not isinstance(rule_symbols, list):
        rule_symbols = ["*"]
    if market is not None:
        rule_markets = rule.get("markets", [])
        if isinstance(rule_markets, list) and rule_markets and market not in rule_markets:
            return False
    return "*" in rule_symbols or symbol in rule_symbols


def merge_rule_overrides(
    template_override: dict[str, Any] | None,
    symbol_override: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for raw_override in (template_override or {}, symbol_override or {}):
        for section, value in raw_override.items():
            if not isinstance(value, dict):
                continue
            existing = merged.get(section)
            if not isinstance(existing, dict):
                existing = {}
            next_value = copy.deepcopy(existing)
            for key, item in value.items():
                next_value[key] = copy.deepcopy(item)
            merged[section] = next_value
    return merged


def apply_rule_override(base_rule: dict[str, Any], override: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    effective_rule = copy.deepcopy(base_rule)
    override = override or {}
    applied: dict[str, Any] = {}

    risk_override = override.get("risk")
    if isinstance(risk_override, dict):
        applied_risk: dict[str, Any] = {}
        if "stop_loss_pct" in risk_override:
            stop_loss_pct = risk_override["stop_loss_pct"]
            if isinstance(effective_rule.get("entry"), dict):
                effective_rule["entry"]["stop_loss_pct"] = stop_loss_pct
            _sync_stop_loss_thresholds(effective_rule.get("exit", {}).get("conditions"), stop_loss_pct)
            applied_risk["stop_loss_pct"] = stop_loss_pct
        if "take_profit_pct" in risk_override:
            take_profit_pct = risk_override["take_profit_pct"]
            if isinstance(effective_rule.get("entry"), dict):
                effective_rule["entry"]["take_profit_pct"] = take_profit_pct
            applied_risk["take_profit_pct"] = take_profit_pct
        if "risk_budget" in risk_override:
            risk_budget = risk_override["risk_budget"]
            if isinstance(effective_rule.get("entry"), dict):
                effective_rule["entry"]["risk_budget"] = risk_budget
            applied_risk["risk_budget"] = risk_budget
        if applied_risk:
            applied["risk"] = applied_risk

    for section, allowed_keys in (("entry", ALLOWED_ENTRY_OVERRIDE_KEYS), ("exit", ALLOWED_EXIT_OVERRIDE_KEYS)):
        section_override = override.get(section)
        if not isinstance(section_override, dict):
            continue
        applied_section: dict[str, Any] = {}
        for key in allowed_keys:
            if key not in section_override:
                continue
            if not isinstance(effective_rule.get(section), dict):
                effective_rule[section] = {}
            effective_rule[section][key] = copy.deepcopy(section_override[key])
            applied_section[key] = copy.deepcopy(section_override[key])
        if applied_section:
            applied[section] = applied_section

    return effective_rule, applied


def resolve_rule_state(
    rules_config: dict[str, Any],
    symbol: str,
    rule_id: str,
    *,
    market: str | None = None,
) -> dict[str, Any]:
    rules_by_id = {
        rule.get("rule_id"): rule
        for rule in rules_config.get("rules", [])
        if isinstance(rule, dict) and rule.get("rule_id")
    }
    base_rule = rules_by_id.get(rule_id)
    if not isinstance(base_rule, dict):
        raise ValueError(f"unknown rule_id '{rule_id}'")

    profile_info = resolve_symbol_profile(rules_config, symbol)
    profile_id = profile_info["profile_id"]
    template_enabled = profile_info["template"]["enabled_rules"]
    symbol_enabled = profile_info["symbol"]["enabled_rules"]
    template_override = profile_info["template"]["rule_overrides"].get(rule_id)
    symbol_override = profile_info["symbol"]["rule_overrides"].get(rule_id)
    merged_override = merge_rule_overrides(template_override, symbol_override)
    has_override = bool(merged_override)

    base_enabled = bool(base_rule.get("enabled", True))
    applies = rule_applies_to_symbol(base_rule, symbol, market)
    effective_enabled = base_enabled and applies
    disable_reason: str | None = None

    if not applies:
        disable_reason = "rule_scope_excluded"

    for source, enabled_map in (("template", template_enabled), ("symbol", symbol_enabled)):
        if rule_id not in enabled_map:
            continue
        requested = bool(enabled_map[rule_id])
        if not requested:
            effective_enabled = False
            disable_reason = f"{source}_disabled"
        elif not base_enabled:
            effective_enabled = False
            disable_reason = "base_disabled"

    effective_rule = None
    applied_override = {}
    effective_config_hash = None
    if applies:
        effective_rule, applied_override = apply_rule_override(base_rule, merged_override)
        effective_config_hash = _effective_rule_hash(
            effective_rule,
            symbol=symbol,
            profile_id=profile_id,
        )
        effective_rule["__rule_profile__"] = {
            "base_rule_id": str(base_rule.get("rule_id") or rule_id),
            "profile_id": profile_id,
            "symbol": symbol,
            "overrides_applied": applied_override,
            "effective_config_hash": effective_config_hash,
        }
        if not effective_enabled:
            effective_rule = None

    return {
        "rule_id": rule_id,
        "base_rule_id": str(base_rule.get("rule_id") or rule_id),
        "symbol": symbol,
        "profile_id": profile_id,
        "applies": applies,
        "base_enabled": base_enabled,
        "enabled": effective_enabled,
        "disable_reason": disable_reason,
        "has_override": has_override,
        "overrides_applied": applied_override,
        "effective_config_hash": effective_config_hash,
        "effective_rule": effective_rule,
    }


def resolve_effective_rule(
    rules_config: dict[str, Any],
    symbol: str,
    rule_id: str,
    *,
    market: str | None = None,
) -> dict[str, Any] | None:
    return resolve_rule_state(rules_config, symbol, rule_id, market=market)["effective_rule"]


def build_symbol_profile_overview(
    rules_config: dict[str, Any],
    symbols: list[str],
    *,
    market_by_symbol: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    overview: dict[str, dict[str, Any]] = {}
    rules = [
        rule
        for rule in rules_config.get("rules", [])
        if isinstance(rule, dict) and rule.get("rule_id")
    ]

    for symbol in symbols:
        market = (market_by_symbol or {}).get(symbol)
        profile_info = resolve_symbol_profile(rules_config, symbol)
        enabled_rules: list[str] = []
        disabled_rules: list[str] = []
        rules_with_overrides: list[str] = []
        overrides: dict[str, Any] = {}
        rules_meta: dict[str, Any] = {}

        for rule in rules:
            state = resolve_rule_state(
                rules_config,
                symbol,
                str(rule["rule_id"]),
                market=market,
            )
            if not state["applies"]:
                continue
            rule_id = state["rule_id"]
            if state["enabled"]:
                enabled_rules.append(rule_id)
            else:
                disabled_rules.append(rule_id)
            if state["has_override"]:
                rules_with_overrides.append(rule_id)
                overrides[rule_id] = state["overrides_applied"]
            rules_meta[rule_id] = {
                "enabled": state["enabled"],
                "base_enabled": state["base_enabled"],
                "disable_reason": state["disable_reason"],
                "has_override": state["has_override"],
                "effective_config_hash": state["effective_config_hash"],
                "overrides_applied": state["overrides_applied"],
            }

        overview[symbol] = {
            "profile": profile_info["profile_id"],
            "enabled_rules": enabled_rules,
            "disabled_rules": disabled_rules,
            "rules_with_overrides": rules_with_overrides,
            "effective_rule_count": len(enabled_rules),
            "overrides": overrides,
            "rules": rules_meta,
        }

    return overview


def _sync_stop_loss_thresholds(conditions: Any, threshold_pct: Any) -> None:
    if not isinstance(conditions, dict):
        return
    if conditions.get("type") == "stop_loss":
        conditions["threshold_pct"] = threshold_pct
    items = conditions.get("items")
    if isinstance(items, list):
        for item in items:
            _sync_stop_loss_thresholds(item, threshold_pct)


def _effective_rule_hash(rule: dict[str, Any], *, symbol: str, profile_id: str) -> str:
    payload = {
        "symbol": symbol,
        "profile_id": profile_id,
        "rule": rule,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
