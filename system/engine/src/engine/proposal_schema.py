from __future__ import annotations

from typing import Any


FACTOR_PROPOSAL_TYPES = {
    "factor_config",
    "factor_rule_link",
    "factor_code",
}
SUPPORTED_PROPOSAL_TYPES = FACTOR_PROPOSAL_TYPES

FACTOR_PROPOSAL_QUALITY_THRESHOLDS = {
    "min_abs_ic": 0.05,
    "min_coverage": 0.8,
    "max_missing_rate": 0.2,
    "min_paper_shadow_required_days": 5,
}

_FACTOR_CONFIG_TARGETS = {
    "factors/registry.json",
    "./factors/registry.json",
    "/workspace/agent-trading/factors/registry.json",
}
_RULES_TARGET_PREFIXES = (
    "rules/",
    "./rules/",
    "/workspace/agent-trading/rules/",
)
_FACTOR_CODE_TARGET_PREFIXES = (
    "system/engine/src/engine/factors/",
    "./system/engine/src/engine/factors/",
    "/workspace/agent-trading/system/engine/src/engine/factors/",
    "system/engine/tests/test_factor_",
    "./system/engine/tests/test_factor_",
    "/workspace/agent-trading/system/engine/tests/test_factor_",
    "tests/test_factor_",
    "./tests/test_factor_",
    "/workspace/agent-trading/tests/test_factor_",
    "docs/factor-",
    "./docs/factor-",
    "/workspace/agent-trading/docs/factor-",
    "specs/factor-",
    "./specs/factor-",
    "/workspace/agent-trading/specs/factor-",
)
_FORBIDDEN_TARGET_MARKERS = (
    ".env",
    "properties/",
    "runtime/",
    "logs/latest/",
    "artifacts/broker/",
    "live_execution.py",
    "risk.py",
    "broker_client.py",
    "tiger_client.py",
    "dashboard/api/control.py",
    "dashboard/scheduler.py",
    "docker-compose.yml",
    "config/app.defaults.json",
    "config/app_config.docker.json",
)


def validate_proposal_record(record: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(record, dict):
        return {
            "valid": False,
            "errors": ["proposal payload must be an object"],
            "warnings": [],
            "proposal_type": None,
            "quality_summary": None,
        }

    proposal_type_raw = record.get("proposal_type")
    if proposal_type_raw in (None, ""):
        return {
            "valid": True,
            "errors": [],
            "warnings": warnings,
            "proposal_type": None,
            "quality_summary": None,
        }

    proposal_type = str(proposal_type_raw).strip().lower()
    if proposal_type not in SUPPORTED_PROPOSAL_TYPES:
        return {
            "valid": False,
            "errors": [f"unsupported proposal_type '{proposal_type_raw}'"],
            "warnings": warnings,
            "proposal_type": proposal_type,
            "quality_summary": None,
        }

    factor_errors, factor_warnings, quality_summary = _validate_factor_proposal(record, proposal_type=proposal_type)
    errors.extend(factor_errors)
    warnings.extend(factor_warnings)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "proposal_type": proposal_type,
        "quality_summary": quality_summary,
    }


def _validate_factor_proposal(
    record: dict[str, Any],
    *,
    proposal_type: str,
) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []

    proposal_id = record.get("proposal_id")
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        errors.append("proposal_id must be a non-empty string")

    recommended_update_mode = str(record.get("recommended_update_mode") or "").strip().lower()
    if recommended_update_mode not in {"hot", "cold"}:
        errors.append("recommended_update_mode must be 'hot' or 'cold'")

    factor_id = record.get("factor_id")
    if not isinstance(factor_id, str) or not factor_id.strip():
        errors.append("factor proposals require non-empty factor_id")

    hypothesis = record.get("hypothesis")
    if not isinstance(hypothesis, str) or not hypothesis.strip():
        errors.append("factor proposals require non-empty hypothesis")

    if record.get("input_data") is None:
        errors.append("factor proposals require input_data")

    session = record.get("session")
    if not isinstance(session, str) or not session.strip():
        errors.append("factor proposals require non-empty session")

    usage = record.get("usage")
    if isinstance(usage, str):
        if not usage.strip():
            errors.append("factor proposals require non-empty usage")
    elif not isinstance(usage, list) or not usage or not all(isinstance(item, str) and item.strip() for item in usage):
        errors.append("factor proposals require usage as non-empty string or string list")

    if not _has_any_key(record, "lookback", "lookback_bars"):
        errors.append("factor proposals require lookback or lookback_bars")
    if not _has_any_key(record, "horizon", "horizon_bars"):
        errors.append("factor proposals require horizon or horizon_bars")

    validation_results = record.get("validation_results")
    if not isinstance(validation_results, dict):
        errors.append("factor proposals require validation_results object")
        validation_results = {}

    ic_value = _required_metric_number(record, validation_results, "ic", "ic_1bar")
    if ic_value is None:
        errors.append("factor proposals require explicit numeric ic")
    coverage_value = _required_metric_number(record, validation_results, "coverage")
    if coverage_value is None:
        errors.append("factor proposals require explicit numeric coverage")
    missing_rate_value = _required_metric_number(record, validation_results, "missing_rate")
    if missing_rate_value is None:
        errors.append("factor proposals require explicit numeric missing_rate")

    if "correlation_with_existing" not in record:
        errors.append("factor proposals require explicit correlation_with_existing field")
    correlation_value = _optional_metric_number(record.get("correlation_with_existing"))
    if record.get("correlation_with_existing") is None:
        warnings.append("factor proposals should include numeric correlation_with_existing")
    elif correlation_value is None:
        errors.append("correlation_with_existing must be numeric or null")
    elif abs(correlation_value) > 1:
        errors.append("correlation_with_existing must be between -1 and 1")

    if "backtest_delta" not in record:
        errors.append("factor proposals require explicit backtest_delta field")
    if record.get("backtest_delta") is None:
        warnings.append("factor proposals should include explicit backtest_delta analysis")
    if not _has_any_key(record, "fee_cost_impact", "cost_impact", "fee_impact"):
        errors.append("factor proposals require explicit fee/cost impact field")
    elif _first_present_value(record, "fee_cost_impact", "cost_impact", "fee_impact") is None:
        warnings.append("factor proposals should include explicit fee/cost impact analysis")

    paper_shadow_required_days = record.get("paper_shadow_required_days")
    if not isinstance(paper_shadow_required_days, int) or isinstance(paper_shadow_required_days, bool) or paper_shadow_required_days < 0:
        errors.append("paper_shadow_required_days must be a non-negative integer")

    if record.get("risk_notes") is None:
        errors.append("factor proposals require risk_notes")
    if record.get("rollback_plan") is None:
        errors.append("factor proposals require rollback_plan")

    target_files = record.get("target_files")
    if not isinstance(target_files, list) or not target_files or not all(isinstance(path, str) and path.strip() for path in target_files):
        errors.append("factor proposals require non-empty target_files")
        target_files = []

    for target in target_files:
        if any(marker in target for marker in _FORBIDDEN_TARGET_MARKERS):
            errors.append(f"factor proposals cannot target protected path '{target}'")

    if proposal_type == "factor_config":
        if any(target not in _FACTOR_CONFIG_TARGETS for target in target_files):
            errors.append("factor_config proposals may only target factors/registry.json")
    elif proposal_type == "factor_rule_link":
        if any(not any(target.startswith(prefix) for prefix in _RULES_TARGET_PREFIXES) for target in target_files):
            errors.append("factor_rule_link proposals may only target rules/")
    elif proposal_type == "factor_code":
        if recommended_update_mode == "hot":
            errors.append("factor_code proposals must use recommended_update_mode='cold'")
        if any(not any(target.startswith(prefix) for prefix in _FACTOR_CODE_TARGET_PREFIXES) for target in target_files):
            errors.append("factor_code proposals may only target factor source, factor tests, factor docs, or factor specs")

    failed_checks: list[str] = []
    if ic_value is not None and abs(ic_value) < FACTOR_PROPOSAL_QUALITY_THRESHOLDS["min_abs_ic"]:
        failed_checks.append(
            f"proposal quality failed: abs(ic)={abs(ic_value):.4f} < {FACTOR_PROPOSAL_QUALITY_THRESHOLDS['min_abs_ic']:.4f}"
        )
    if coverage_value is not None:
        if coverage_value < 0 or coverage_value > 1:
            failed_checks.append("proposal quality failed: coverage must be between 0 and 1")
        elif coverage_value < FACTOR_PROPOSAL_QUALITY_THRESHOLDS["min_coverage"]:
            failed_checks.append(
                f"proposal quality failed: coverage={coverage_value:.4f} < {FACTOR_PROPOSAL_QUALITY_THRESHOLDS['min_coverage']:.4f}"
            )
    if missing_rate_value is not None:
        if missing_rate_value < 0 or missing_rate_value > 1:
            failed_checks.append("proposal quality failed: missing_rate must be between 0 and 1")
        elif missing_rate_value > FACTOR_PROPOSAL_QUALITY_THRESHOLDS["max_missing_rate"]:
            failed_checks.append(
                f"proposal quality failed: missing_rate={missing_rate_value:.4f} > {FACTOR_PROPOSAL_QUALITY_THRESHOLDS['max_missing_rate']:.4f}"
            )
    if (
        isinstance(paper_shadow_required_days, int)
        and not isinstance(paper_shadow_required_days, bool)
        and paper_shadow_required_days < FACTOR_PROPOSAL_QUALITY_THRESHOLDS["min_paper_shadow_required_days"]
    ):
        failed_checks.append(
            "proposal quality failed: "
            f"paper_shadow_required_days={paper_shadow_required_days} < "
            f"{FACTOR_PROPOSAL_QUALITY_THRESHOLDS['min_paper_shadow_required_days']}"
        )

    errors.extend(failed_checks)

    quality_summary = {
        "thresholds": dict(FACTOR_PROPOSAL_QUALITY_THRESHOLDS),
        "metrics": {
            "ic": ic_value,
            "coverage": coverage_value,
            "missing_rate": missing_rate_value,
            "correlation_with_existing": correlation_value,
            "paper_shadow_required_days": paper_shadow_required_days,
            "backtest_delta_present": record.get("backtest_delta") is not None,
            "fee_cost_impact_present": _first_present_value(record, "fee_cost_impact", "cost_impact", "fee_impact")
            is not None,
        },
        "failed_checks": failed_checks,
    }
    return errors, warnings, quality_summary


def _has_any_key(record: dict[str, Any], *keys: str) -> bool:
    return any(key in record for key in keys)


def _metric_present(record: dict[str, Any], validation_results: dict[str, Any], *keys: str) -> bool:
    return any(key in record or key in validation_results for key in keys)


def _required_metric_number(record: dict[str, Any], validation_results: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in record:
            return _optional_metric_number(record.get(key))
        if key in validation_results:
            return _optional_metric_number(validation_results.get(key))
    return None


def _optional_metric_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _first_present_value(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record:
            return record.get(key)
    return None
