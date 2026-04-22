from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .catalog import BUILTIN_FACTOR_IMPLEMENTATIONS


FACTOR_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

SUPPORTED_FACTOR_TYPES = {
    "technical",
    "session",
    "risk",
    "cost",
    "fundamental",
    "text",
    "context_only",
}
SUPPORTED_SESSIONS = {"regular", "premarket", "afterhours", "context_only"}
SUPPORTED_OUTPUTS = {"numeric", "boolean", "categorical", "vector"}
SUPPORTED_USAGES = {
    "shadow",
    "rule_condition_candidate",
    "context_only",
    "risk_hint_candidate",
    "actionable",
}
SUPPORTED_IMPLEMENTATIONS = set(BUILTIN_FACTOR_IMPLEMENTATIONS)
EXTENDED_HOURS_SESSIONS = {"premarket", "afterhours"}
REQUIRED_DEFAULT_FIELDS = {
    "mode",
    "allow_actionable_consumption",
    "regular_session_only_for_indicators",
    "default_timezone",
}
REQUIRED_FACTOR_FIELDS = {
    "type",
    "implementation",
    "inputs",
    "params",
    "session",
    "timeframe",
    "output",
    "usage",
    "actionable",
    "point_in_time",
    "required_bars",
    "lookback_bars",
    "horizon_bars",
    "timezone",
    "no_lookahead",
    "version",
}


@dataclass(frozen=True)
class FactorDefinition:
    factor_id: str
    type: str
    implementation: str
    inputs: tuple[str, ...]
    params: dict[str, Any]
    session: str
    timeframe: str
    output: str
    usage: tuple[str, ...]
    actionable: bool
    version: int
    config_hash: str
    point_in_time: bool
    required_bars: int
    lookback_bars: int
    horizon_bars: int
    timezone: str
    no_lookahead: bool


def validate_factor_registry(data: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    valid_factors: dict[str, FactorDefinition] = {}

    if not isinstance(data, dict):
        return {
            "valid": False,
            "errors": ["factor registry payload must be an object"],
            "warnings": warnings,
            "schema_version": None,
            "defaults": {},
            "factors": valid_factors,
            "config_hash": None,
        }

    schema_version = data.get("schema_version")
    if schema_version != 1:
        errors.append("schema_version must be 1")

    defaults = data.get("defaults")
    if not isinstance(defaults, dict):
        errors.append("Missing 'defaults' field")
        defaults = {}
    else:
        errors.extend(_validate_defaults(defaults))

    factors = data.get("factors")
    if not isinstance(factors, dict) or not factors:
        errors.append("Missing 'factors' field")
        factors = {}

    allow_actionable = bool(defaults.get("allow_actionable_consumption")) if isinstance(defaults, dict) else False

    for factor_id, factor_data in factors.items():
        factor_errors, factor_definition = _validate_factor_definition(
            factor_id,
            factor_data,
            allow_actionable_consumption=allow_actionable,
        )
        if factor_errors:
            errors.extend(factor_errors)
            continue
        if factor_definition is not None:
            valid_factors[factor_id] = factor_definition

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "schema_version": schema_version,
        "defaults": copy.deepcopy(defaults),
        "factors": valid_factors,
        "config_hash": _stable_hash(data) if len(errors) == 0 else None,
    }


def _validate_defaults(defaults: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field_name in sorted(REQUIRED_DEFAULT_FIELDS):
        if field_name not in defaults:
            errors.append(f"defaults missing required field '{field_name}'")

    mode = defaults.get("mode")
    if mode is not None and (not isinstance(mode, str) or not mode.strip()):
        errors.append("defaults.mode must be a non-empty string")

    if "allow_actionable_consumption" in defaults and not isinstance(defaults.get("allow_actionable_consumption"), bool):
        errors.append("defaults.allow_actionable_consumption must be bool")
    if "regular_session_only_for_indicators" in defaults and not isinstance(defaults.get("regular_session_only_for_indicators"), bool):
        errors.append("defaults.regular_session_only_for_indicators must be bool")

    default_timezone = defaults.get("default_timezone")
    if default_timezone is not None and (not isinstance(default_timezone, str) or not default_timezone.strip()):
        errors.append("defaults.default_timezone must be a non-empty string")

    return errors


def _validate_factor_definition(
    factor_id: Any,
    factor_data: Any,
    *,
    allow_actionable_consumption: bool,
) -> tuple[list[str], FactorDefinition | None]:
    errors: list[str] = []

    if not isinstance(factor_id, str) or not FACTOR_ID_PATTERN.fullmatch(factor_id):
        return ([f"Factor '{factor_id}': invalid factor_id"], None)

    prefix = f"Factor {factor_id}"
    if not isinstance(factor_data, dict):
        return ([f"{prefix}: definition must be an object"], None)

    for field_name in sorted(REQUIRED_FACTOR_FIELDS):
        if field_name not in factor_data:
            errors.append(f"{prefix}: missing required field '{field_name}'")

    if errors:
        return errors, None

    factor_type = factor_data.get("type")
    if factor_type not in SUPPORTED_FACTOR_TYPES:
        errors.append(f"{prefix}: unsupported factor type '{factor_type}'")

    implementation = factor_data.get("implementation")
    if implementation not in SUPPORTED_IMPLEMENTATIONS:
        errors.append(f"{prefix}: unsupported implementation '{implementation}'")

    inputs = factor_data.get("inputs")
    if not isinstance(inputs, list) or not inputs or not all(isinstance(item, str) and item for item in inputs):
        errors.append(f"{prefix}: inputs must be a non-empty list of strings")

    params = factor_data.get("params")
    if not isinstance(params, dict):
        errors.append(f"{prefix}: params must be an object")

    session = factor_data.get("session")
    if session not in SUPPORTED_SESSIONS:
        errors.append(f"{prefix}: unsupported session '{session}'")

    timeframe = factor_data.get("timeframe")
    if not isinstance(timeframe, str) or not timeframe.strip():
        errors.append(f"{prefix}: timeframe must be a non-empty string")

    output = factor_data.get("output")
    if output not in SUPPORTED_OUTPUTS:
        errors.append(f"{prefix}: unsupported output '{output}'")

    usage = factor_data.get("usage")
    if not isinstance(usage, list) or not usage or not all(isinstance(item, str) and item for item in usage):
        errors.append(f"{prefix}: usage must be a non-empty list of strings")
        usage_values: list[str] = []
    else:
        usage_values = list(usage)
        for usage_name in usage_values:
            if usage_name not in SUPPORTED_USAGES:
                errors.append(f"{prefix}: unsupported usage '{usage_name}'")

    actionable = factor_data.get("actionable")
    if not isinstance(actionable, bool):
        errors.append(f"{prefix}: actionable must be bool")

    point_in_time = factor_data.get("point_in_time")
    if not isinstance(point_in_time, bool):
        errors.append(f"{prefix}: point_in_time must be bool")

    required_bars = factor_data.get("required_bars")
    errors.extend(_validate_positive_int(required_bars, path=f"{prefix}.required_bars"))

    lookback_bars = factor_data.get("lookback_bars")
    errors.extend(_validate_positive_int(lookback_bars, path=f"{prefix}.lookback_bars"))

    horizon_bars = factor_data.get("horizon_bars")
    errors.extend(_validate_positive_int(horizon_bars, path=f"{prefix}.horizon_bars"))

    timezone = factor_data.get("timezone")
    if not isinstance(timezone, str) or not timezone.strip():
        errors.append(f"{prefix}: timezone must be a non-empty string")
    elif session in SUPPORTED_SESSIONS - {"context_only"} and timezone != "America/New_York":
        errors.append(f"{prefix}: timezone must be America/New_York for US session factors")

    no_lookahead = factor_data.get("no_lookahead")
    if not isinstance(no_lookahead, bool):
        errors.append(f"{prefix}: no_lookahead must be bool")

    version = factor_data.get("version")
    errors.extend(_validate_positive_int(version, path=f"{prefix}.version"))

    if not allow_actionable_consumption and actionable is True:
        errors.append(f"{prefix}: actionable factor is not allowed when defaults.allow_actionable_consumption=false")

    if not allow_actionable_consumption and "actionable" in usage_values:
        errors.append(f"{prefix}: usage 'actionable' is not allowed when defaults.allow_actionable_consumption=false")

    if session in EXTENDED_HOURS_SESSIONS:
        if actionable is True:
            errors.append(f"{prefix}: extended-hours factor cannot be actionable")
        if "actionable" in usage_values:
            errors.append(f"{prefix}: extended-hours factor usage cannot include 'actionable'")
        if "context_only" not in usage_values:
            errors.append(f"{prefix}: extended-hours factor usage must include 'context_only'")

    if isinstance(params, dict) and implementation in SUPPORTED_IMPLEMENTATIONS:
        errors.extend(_validate_params(implementation, params, prefix=prefix))

    if errors:
        return errors, None

    factor_definition = FactorDefinition(
        factor_id=factor_id,
        type=str(factor_type),
        implementation=str(implementation),
        inputs=tuple(str(item) for item in inputs),
        params=copy.deepcopy(params),
        session=str(session),
        timeframe=str(timeframe),
        output=str(output),
        usage=tuple(usage_values),
        actionable=bool(actionable),
        version=int(version),
        config_hash=_stable_hash({"factor_id": factor_id, "definition": factor_data}),
        point_in_time=bool(point_in_time),
        required_bars=int(required_bars),
        lookback_bars=int(lookback_bars),
        horizon_bars=int(horizon_bars),
        timezone=str(timezone),
        no_lookahead=bool(no_lookahead),
    )
    return [], factor_definition


def _validate_params(implementation: str, params: dict[str, Any], *, prefix: str) -> list[str]:
    errors: list[str] = []

    if implementation == "builtin:rsi":
        errors.extend(_validate_positive_int(params.get("period"), path=f"{prefix}.params.period"))
    elif implementation == "builtin:bollinger_zscore":
        errors.extend(_validate_positive_int(params.get("period"), path=f"{prefix}.params.period"))
        errors.extend(_validate_positive_number(params.get("std_dev"), path=f"{prefix}.params.std_dev"))
    elif implementation == "builtin:volume_ratio":
        errors.extend(_validate_positive_int(params.get("period"), path=f"{prefix}.params.period"))
    elif implementation == "builtin:atr_pct":
        errors.extend(_validate_positive_int(params.get("period"), path=f"{prefix}.params.period"))

    return errors


def _validate_positive_int(value: Any, *, path: str) -> list[str]:
    if isinstance(value, bool) or not isinstance(value, int):
        return [f"{path} must be an integer"]
    if value <= 0:
        return [f"{path} must be greater than 0"]
    return []


def _validate_positive_number(value: Any, *, path: str) -> list[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return [f"{path} must be a number"]
    if float(value) <= 0:
        return [f"{path} must be greater than 0"]
    return []


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
