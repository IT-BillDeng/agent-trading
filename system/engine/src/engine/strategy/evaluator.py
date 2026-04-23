from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable

from .bindings import StrategyBinding, build_legacy_rule_binding
from .compatibility import evaluate_legacy_symbol


@dataclass(frozen=True)
class ConditionBindingView:
    kind: str
    original_condition: dict[str, Any]
    normalized_condition: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def normalize_condition_to_factor_binding_view(
    condition: dict[str, Any],
    *,
    factor_accessor: Any | None = None,
) -> ConditionBindingView:
    if not isinstance(condition, dict):
        return ConditionBindingView(
            kind="compatibility_legacy_condition",
            original_condition={},
            metadata={"reason": "condition_not_object"},
        )

    if "operator" in condition and "items" in condition:
        item_views = [
            normalize_condition_to_factor_binding_view(item, factor_accessor=factor_accessor)
            for item in list(condition.get("items") or [])
        ]
        return ConditionBindingView(
            kind="structural_condition",
            original_condition=copy.deepcopy(condition),
            metadata={
                "structural_type": "compound",
                "item_views": item_views,
            },
        )

    cond_type = str(condition.get("type") or "")
    if cond_type in {"price", "stop_loss", "take_profit", "time"}:
        return ConditionBindingView(
            kind="structural_condition",
            original_condition=copy.deepcopy(condition),
            metadata={"structural_type": cond_type},
        )

    if cond_type == "indicator":
        indicator = str(condition.get("indicator") or "")
        if indicator == "factor":
            return ConditionBindingView(
                kind="factor_condition",
                original_condition=copy.deepcopy(condition),
                normalized_condition=copy.deepcopy(condition),
                metadata={
                    "source": "explicit_factor",
                    "factor_id": condition.get("factor_id"),
                    "compatibility_fallback": False,
                },
            )

        normalized = _normalize_legacy_indicator_condition(
            condition,
            factor_accessor=factor_accessor,
        )
        if normalized is not None:
            return normalized

        return ConditionBindingView(
            kind="compatibility_legacy_condition",
            original_condition=copy.deepcopy(condition),
            metadata={
                "source": "legacy_indicator",
                "indicator": indicator,
            },
        )

    if cond_type == "volume":
        normalized = _normalize_volume_condition(
            condition,
            factor_accessor=factor_accessor,
        )
        if normalized is not None:
            return normalized
        return ConditionBindingView(
            kind="compatibility_legacy_condition",
            original_condition=copy.deepcopy(condition),
            metadata={"source": "legacy_volume"},
        )

    return ConditionBindingView(
        kind="compatibility_legacy_condition",
        original_condition=copy.deepcopy(condition),
        metadata={
            "source": "legacy_unknown",
            "condition_type": cond_type,
        },
    )


def normalize_rule_to_factor_binding_view(
    rule: dict[str, Any],
    *,
    factor_accessor: Any | None = None,
) -> dict[str, Any]:
    entry_conditions = {}
    exit_conditions = {}
    if isinstance(rule.get("entry"), dict):
        entry_conditions = rule.get("entry", {}).get("conditions", {}) or {}
    if isinstance(rule.get("exit"), dict):
        exit_conditions = rule.get("exit", {}).get("conditions", {}) or {}

    entry_view = normalize_condition_to_factor_binding_view(
        entry_conditions,
        factor_accessor=factor_accessor,
    )
    exit_view = normalize_condition_to_factor_binding_view(
        exit_conditions,
        factor_accessor=factor_accessor,
    )
    factor_ids = sorted(
        set(_collect_factor_ids(entry_view)) | set(_collect_factor_ids(exit_view))
    )
    return {
        "rule_id": rule.get("rule_id"),
        "entry": entry_view,
        "exit": exit_view,
        "factor_ids": factor_ids,
    }


class FactorConditionEvaluator:
    def __init__(
        self,
        *,
        factor_registry: Any | None,
        compare_fn: Callable[..., bool],
        factor_payload_getter: Callable[[dict[str, Any] | None, str], dict[str, Any] | None],
        factor_allowed_for_actionable_buy: Callable[[Any], tuple[bool, str]],
        factor_binding_value_resolver: Callable[[ConditionBindingView, list[dict[str, Any]], dict[str, Any] | None], dict[str, Any]],
    ):
        self.factor_registry = factor_registry
        self.compare_fn = compare_fn
        self.factor_payload_getter = factor_payload_getter
        self.factor_allowed_for_actionable_buy = factor_allowed_for_actionable_buy
        self.factor_binding_value_resolver = factor_binding_value_resolver

    def evaluate(
        self,
        view: ConditionBindingView,
        *,
        bars: list[dict[str, Any]],
        factor_snapshot: dict[str, Any] | None,
        previous_factor_snapshot: dict[str, Any] | None,
        intent_action: str | None,
    ) -> tuple[bool, dict[str, Any]]:
        source = str(view.metadata.get("source") or "legacy_factor_binding")
        if source == "explicit_factor":
            return self._evaluate_explicit_factor(
                view,
                factor_snapshot=factor_snapshot,
                previous_factor_snapshot=previous_factor_snapshot,
                intent_action=intent_action,
            )
        return self._evaluate_normalized_factor_binding(
            view,
            bars=bars,
            factor_snapshot=factor_snapshot,
            previous_factor_snapshot=previous_factor_snapshot,
            intent_action=intent_action,
        )

    def _evaluate_explicit_factor(
        self,
        view: ConditionBindingView,
        *,
        factor_snapshot: dict[str, Any] | None,
        previous_factor_snapshot: dict[str, Any] | None,
        intent_action: str | None,
    ) -> tuple[bool, dict[str, Any]]:
        condition = dict(view.normalized_condition or view.original_condition)
        factor_id = str(condition.get("factor_id") or "")
        compare = condition.get("compare", {})
        operator = compare.get("operator", "above")
        compare_value = compare.get("value")
        factor_def = self.factor_registry.factors.get(factor_id) if self.factor_registry is not None else None
        payload = self.factor_payload_getter(factor_snapshot, factor_id)
        diagnostics = {
            "indicator": "factor",
            "binding_kind": "factor_condition",
            "binding_source": "explicit_factor",
            "factor_id": factor_id,
            "operator": operator,
            "compare_value": compare_value,
            "value": payload.get("value") if isinstance(payload, dict) else None,
            "prev_value": None,
            "prev_compare_value": compare_value if operator in {"cross_above", "cross_below"} else None,
            "ready": bool(payload.get("ready")) if isinstance(payload, dict) else False,
            "actionable": bool(payload.get("actionable")) if isinstance(payload, dict) else (
                bool(factor_def.actionable) if factor_def is not None else False
            ),
            "source": payload.get("source") if isinstance(payload, dict) else None,
            "config_hash": payload.get("config_hash") if isinstance(payload, dict) else (
                factor_def.config_hash if factor_def is not None else None
            ),
        }

        if factor_def is None:
            diagnostics["reason"] = "unknown_factor"
            diagnostics["result"] = False
            return False, diagnostics

        if intent_action == "BUY":
            allowed, gate_reason = self.factor_allowed_for_actionable_buy(factor_def)
            if not allowed:
                diagnostics["reason"] = gate_reason
                diagnostics["result"] = False
                return False, diagnostics

        if not isinstance(payload, dict):
            diagnostics["reason"] = "factor_unavailable"
            diagnostics["result"] = False
            return False, diagnostics

        if not payload.get("ready"):
            diagnostics["reason"] = "factor_not_ready"
            diagnostics["factor_reason"] = payload.get("reason")
            diagnostics["result"] = False
            return False, diagnostics

        value = payload.get("value")
        if value is None:
            diagnostics["reason"] = "factor_value_missing"
            diagnostics["result"] = False
            return False, diagnostics

        prev_value = None
        prev_compare_value = None
        if operator in {"cross_above", "cross_below"}:
            previous_payload = self.factor_payload_getter(previous_factor_snapshot, factor_id)
            if not isinstance(previous_payload, dict) or not previous_payload.get("ready"):
                diagnostics["reason"] = "insufficient_factor_history"
                diagnostics["result"] = False
                return False, diagnostics
            prev_value = previous_payload.get("value")
            prev_compare_value = compare_value
            if prev_value is None:
                diagnostics["reason"] = "insufficient_factor_history"
                diagnostics["result"] = False
                return False, diagnostics

        result = self.compare_fn(
            value,
            compare_value,
            operator,
            [],
            "factor",
            prev_value=prev_value,
            prev_compare_value=prev_compare_value,
        )
        diagnostics["prev_value"] = prev_value
        diagnostics["prev_compare_value"] = prev_compare_value
        diagnostics["reason"] = "ok" if result else "condition_false"
        diagnostics["result"] = result
        return result, diagnostics

    def _evaluate_normalized_factor_binding(
        self,
        view: ConditionBindingView,
        *,
        bars: list[dict[str, Any]],
        factor_snapshot: dict[str, Any] | None,
        previous_factor_snapshot: dict[str, Any] | None,
        intent_action: str | None,
    ) -> tuple[bool, dict[str, Any]]:
        normalized = dict(view.normalized_condition or {})
        compare = normalized.get("compare", {})
        operator = compare.get("operator", "above")
        compare_value = compare.get("value")
        factor_id = str(view.metadata.get("factor_id") or normalized.get("factor_id") or "")
        factor_def = self.factor_registry.factors.get(factor_id) if self.factor_registry is not None else None
        diagnostics = {
            "indicator": str(view.metadata.get("legacy_indicator") or ""),
            "binding_kind": "factor_condition",
            "binding_source": str(view.metadata.get("source") or "legacy_factor_binding"),
            "factor_id": factor_id,
            "params": copy.deepcopy(view.metadata.get("legacy_params") or {}),
            "operator": operator,
            "compare_value": compare_value,
            "prev_value": None,
            "prev_compare_value": None,
        }

        if factor_def is None:
            diagnostics["reason"] = "unknown_factor"
            diagnostics["result"] = False
            return False, diagnostics

        current = self.factor_binding_value_resolver(view, bars, factor_snapshot)
        diagnostics.update(
            {
                "value": current.get("value"),
                "feature_source": current.get("source"),
                "feature_reason": current.get("reason"),
                "config_hash": current.get("config_hash"),
            }
        )
        if current.get("value") is None:
            diagnostics["reason"] = str(current.get("reason") or "factor_unavailable")
            diagnostics["result"] = False
            return False, diagnostics

        prev_value = None
        prev_compare_value = None
        if operator in {"cross_above", "cross_below"}:
            previous = self.factor_binding_value_resolver(view, bars[:-1], previous_factor_snapshot)
            if previous.get("value") is None:
                diagnostics["reason"] = "insufficient_factor_history"
                diagnostics["result"] = False
                diagnostics["prev_factor_reason"] = previous.get("reason")
                return False, diagnostics
            prev_value = previous.get("value")
            prev_compare_value = compare_value

        result = self.compare_fn(
            current.get("value"),
            compare_value,
            operator,
            bars,
            str(view.metadata.get("legacy_indicator") or ""),
            prev_value=prev_value,
            prev_compare_value=prev_compare_value,
        )
        diagnostics["prev_value"] = prev_value
        diagnostics["prev_compare_value"] = prev_compare_value
        diagnostics["reason"] = "ok" if result else "condition_false"
        diagnostics["result"] = result
        return result, diagnostics


class CompatibilityLegacyConditionEvaluator:
    def __init__(
        self,
        *,
        indicator_calc: Any,
        compare_fn: Callable[..., bool],
    ):
        self.indicator_calc = indicator_calc
        self.compare_fn = compare_fn

    def evaluate(
        self,
        condition: dict[str, Any],
        bars: list[dict[str, Any]],
    ) -> tuple[bool, dict[str, Any]]:
        cond_type = condition.get("type")
        if cond_type == "indicator":
            return self._eval_indicator(condition, bars)
        if cond_type == "volume":
            return self._eval_volume(condition, bars)
        return False, {
            "reason": f"unsupported_compatibility_condition:{cond_type}",
            "binding_kind": "compatibility_legacy_condition",
        }

    def _eval_indicator(self, condition: dict[str, Any], bars: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
        indicator = condition.get("indicator")
        params = condition.get("params", {})
        compare = condition.get("compare", {})
        operator = compare.get("operator", "above")

        value = self.indicator_calc.calculate(indicator, params, bars)
        if value is None:
            return False, {
                "indicator": indicator,
                "binding_kind": "compatibility_legacy_condition",
                "value": None,
                "reason": "insufficient_data",
            }

        compare_value = None
        compare_field = compare.get("field")
        compare_indicator = compare.get("indicator")
        compare_value_const = compare.get("value")

        if compare_field == "close":
            compare_value = float(bars[-1]["close"]) if bars else None
        elif compare_indicator:
            compare_params = compare.get("params", {})
            compare_value = self.indicator_calc.calculate(compare_indicator, compare_params, bars)
        elif compare_value_const is not None:
            compare_value = compare_value_const

        if compare_value is None:
            return False, {
                "indicator": indicator,
                "binding_kind": "compatibility_legacy_condition",
                "value": value,
                "compare_value": None,
                "reason": "no_compare_value",
            }

        prev_value = None
        prev_compare_value = None
        if operator in {"cross_above", "cross_below"}:
            prev_bars = bars[:-1]
            if not prev_bars:
                return False, {
                    "indicator": indicator,
                    "binding_kind": "compatibility_legacy_condition",
                    "value": value,
                    "compare_value": compare_value,
                    "reason": "insufficient_data_for_cross",
                }

            prev_value = self.indicator_calc.calculate(indicator, params, prev_bars)
            if prev_value is None:
                return False, {
                    "indicator": indicator,
                    "binding_kind": "compatibility_legacy_condition",
                    "value": value,
                    "compare_value": compare_value,
                    "reason": "insufficient_data_for_cross",
                }

            if compare_field == "close":
                prev_compare_value = float(prev_bars[-1]["close"]) if prev_bars else None
            elif compare_indicator:
                compare_params = compare.get("params", {})
                prev_compare_value = self.indicator_calc.calculate(compare_indicator, compare_params, prev_bars)
            elif compare_value_const is not None:
                prev_compare_value = compare_value_const

            if prev_compare_value is None:
                return False, {
                    "indicator": indicator,
                    "binding_kind": "compatibility_legacy_condition",
                    "value": value,
                    "compare_value": compare_value,
                    "reason": "insufficient_data_for_cross",
                }

        result = self.compare_fn(
            value,
            compare_value,
            operator,
            bars,
            indicator,
            prev_value=prev_value,
            prev_compare_value=prev_compare_value,
        )
        return result, {
            "indicator": indicator,
            "binding_kind": "compatibility_legacy_condition",
            "params": params,
            "value": value,
            "operator": operator,
            "compare_value": compare_value,
            "prev_value": prev_value,
            "prev_compare_value": prev_compare_value,
            "result": result,
            "reason": "ok" if result else "condition_false",
        }

    def _eval_volume(self, condition: dict[str, Any], bars: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
        operator = condition.get("operator")
        ratio = condition.get("ratio", 1.5)
        volume_ratio_val = self.indicator_calc.calculate("volume_ratio", {"period": 20}, bars)
        if volume_ratio_val is None:
            return False, {
                "binding_kind": "compatibility_legacy_condition",
                "reason": "insufficient_data",
            }
        result = operator == "above_avg" and volume_ratio_val > ratio
        return result, {
            "binding_kind": "compatibility_legacy_condition",
            "volume_ratio": volume_ratio_val,
            "threshold": ratio,
            "result": result,
        }


class StructuralConditionEvaluator:
    def __init__(
        self,
        *,
        router: Callable[..., tuple[bool, dict[str, Any]]],
        position_avg_cost_resolver: Callable[[dict[str, Any]], float],
    ):
        self.router = router
        self.position_avg_cost_resolver = position_avg_cost_resolver

    def evaluate(
        self,
        view: ConditionBindingView,
        *,
        bars: list[dict[str, Any]],
        position: dict[str, Any] | None,
        factor_snapshot: dict[str, Any] | None,
        previous_factor_snapshot: dict[str, Any] | None,
        intent_action: str | None,
    ) -> tuple[bool, dict[str, Any]]:
        condition = view.original_condition
        if "operator" in condition and "items" in condition:
            return self._eval_compound(
                condition,
                bars,
                position,
                factor_snapshot=factor_snapshot,
                previous_factor_snapshot=previous_factor_snapshot,
                intent_action=intent_action,
            )

        cond_type = condition.get("type")
        if cond_type == "price":
            return self._eval_price(condition, bars)
        if cond_type == "stop_loss":
            return self._eval_stop_loss(condition, bars, position)
        if cond_type == "take_profit":
            return self._eval_take_profit(condition, bars, position)
        if cond_type == "time":
            return True, {
                "binding_kind": "structural_condition",
                "result": True,
                "reason": "time_check_simplified",
            }
        return False, {
            "binding_kind": "structural_condition",
            "reason": f"unsupported_structural_condition:{cond_type}",
        }

    def _eval_price(self, condition: dict[str, Any], bars: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
        field = condition.get("field", "close")
        operator = condition.get("operator")
        value = condition.get("value")
        if not bars:
            return False, {"binding_kind": "structural_condition", "reason": "no_bars"}
        current_price = float(bars[-1].get(field, 0))
        result = False
        if operator == "above":
            result = current_price > value
        elif operator == "below":
            result = current_price < value
        return result, {
            "binding_kind": "structural_condition",
            "field": field,
            "current": current_price,
            "threshold": value,
            "result": result,
        }

    def _eval_stop_loss(
        self,
        condition: dict[str, Any],
        bars: list[dict[str, Any]],
        position: dict[str, Any] | None,
    ) -> tuple[bool, dict[str, Any]]:
        if not position:
            return False, {"binding_kind": "structural_condition", "reason": "no_position"}
        threshold_pct = condition.get("threshold_pct", 0.03)
        entry_price = self.position_avg_cost_resolver(position)
        current_price = float(bars[-1]["close"]) if bars else 0
        if entry_price == 0:
            return False, {"binding_kind": "structural_condition", "reason": "no_entry_price"}
        loss_pct = (entry_price - current_price) / entry_price
        result = loss_pct >= threshold_pct
        return result, {
            "binding_kind": "structural_condition",
            "entry_price": entry_price,
            "current_price": current_price,
            "loss_pct": loss_pct,
            "threshold_pct": threshold_pct,
            "result": result,
        }

    def _eval_take_profit(
        self,
        condition: dict[str, Any],
        bars: list[dict[str, Any]],
        position: dict[str, Any] | None,
    ) -> tuple[bool, dict[str, Any]]:
        if not position:
            return False, {"binding_kind": "structural_condition", "reason": "no_position"}
        threshold_pct = condition.get("threshold_pct", 0.06)
        entry_price = self.position_avg_cost_resolver(position)
        current_price = float(bars[-1]["close"]) if bars else 0
        if entry_price == 0:
            return False, {"binding_kind": "structural_condition", "reason": "no_entry_price"}
        profit_pct = (current_price - entry_price) / entry_price
        result = profit_pct >= threshold_pct
        return result, {
            "binding_kind": "structural_condition",
            "entry_price": entry_price,
            "current_price": current_price,
            "profit_pct": profit_pct,
            "threshold_pct": threshold_pct,
            "result": result,
        }

    def _eval_compound(
        self,
        condition: dict[str, Any],
        bars: list[dict[str, Any]],
        position: dict[str, Any] | None,
        *,
        factor_snapshot: dict[str, Any] | None,
        previous_factor_snapshot: dict[str, Any] | None,
        intent_action: str | None,
    ) -> tuple[bool, dict[str, Any]]:
        operator = condition.get("operator", "AND")
        items = condition.get("items", [])
        results = []
        diagnostics = []
        for item in items:
            result, diag = self.router(
                item,
                bars,
                position,
                factor_snapshot=factor_snapshot,
                previous_factor_snapshot=previous_factor_snapshot,
                intent_action=intent_action,
            )
            results.append(result)
            diagnostics.append(diag)
        if operator == "AND":
            final_result = all(results)
        elif operator == "OR":
            final_result = any(results)
        else:
            final_result = False
        return final_result, {
            "binding_kind": "structural_condition",
            "operator": operator,
            "item_results": results,
            "diagnostics": diagnostics,
            "final_result": final_result,
        }


class FactorFirstEvaluator:
    """Factor-first migration helper for rule/binding normalization."""

    def __init__(self, app, *, compatibility_mode: bool = True, factor_accessor: Any | None = None):
        self.app = app
        self.compatibility_mode = compatibility_mode
        self.factor_accessor = factor_accessor

    def binding_for_rule(self, rule_id: str, *, factor_ids: list[str] | None = None) -> StrategyBinding:
        return build_legacy_rule_binding(rule_id, factor_ids=factor_ids)

    def binding_view_for_rule(self, rule: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_rule_to_factor_binding_view(
            rule,
            factor_accessor=self.factor_accessor,
        )
        return normalized

    def evaluate_symbol(
        self,
        *,
        symbol: str,
        market: str,
        bars: list[dict[str, Any]],
        position: dict[str, Any] | None = None,
    ):
        return evaluate_legacy_symbol(
            self.app,
            symbol=symbol,
            market=market,
            bars=bars,
            position=position,
        )


def _normalize_legacy_indicator_condition(
    condition: dict[str, Any],
    *,
    factor_accessor: Any | None,
) -> ConditionBindingView | None:
    indicator = str(condition.get("indicator") or "")
    params = dict(condition.get("params") or {})
    compare = dict(condition.get("compare") or {})
    factor_def = _matching_factor_definition(factor_accessor, indicator, params)
    if factor_def is None:
        return None

    normalized_compare = _normalized_compare_for_indicator(indicator, params, compare)
    if normalized_compare is None:
        return None

    normalized = {
        "type": "indicator",
        "indicator": "factor",
        "factor_id": factor_def.factor_id,
        "compare": normalized_compare,
    }
    return ConditionBindingView(
        kind="factor_condition",
        original_condition=copy.deepcopy(condition),
        normalized_condition=normalized,
        metadata={
            "source": "legacy_indicator_binding",
            "legacy_indicator": indicator,
            "legacy_params": params,
            "factor_id": factor_def.factor_id,
            "compatibility_fallback": True,
        },
    )


def _normalize_volume_condition(
    condition: dict[str, Any],
    *,
    factor_accessor: Any | None,
) -> ConditionBindingView | None:
    factor_def = _matching_factor_definition(factor_accessor, "volume_ratio", {"period": 20})
    if factor_def is None:
        return None
    if str(condition.get("operator") or "") != "above_avg":
        return None
    normalized = {
        "type": "indicator",
        "indicator": "factor",
        "factor_id": factor_def.factor_id,
        "compare": {
            "operator": "above",
            "value": float(condition.get("ratio", 1.5)),
        },
    }
    return ConditionBindingView(
        kind="factor_condition",
        original_condition=copy.deepcopy(condition),
        normalized_condition=normalized,
        metadata={
            "source": "legacy_volume_binding",
            "legacy_indicator": "volume_ratio",
            "legacy_params": {"period": 20},
            "factor_id": factor_def.factor_id,
            "compatibility_fallback": True,
        },
    )


def _normalized_compare_for_indicator(
    indicator: str,
    params: dict[str, Any],
    compare: dict[str, Any],
) -> dict[str, Any] | None:
    operator = str(compare.get("operator") or "above")
    if compare.get("indicator") is not None or compare.get("field") is not None:
        return None

    if indicator == "bollinger":
        std_dev = float(params.get("std_dev", 2.0))
        mapping = {
            "above_upper": {"operator": "above", "value": std_dev},
            "below_lower": {"operator": "below", "value": -std_dev},
            "above_middle": {"operator": "above", "value": 0.0},
            "below_middle": {"operator": "below", "value": 0.0},
        }
        return mapping.get(operator)

    if "value" not in compare:
        return None
    if operator not in {"above", "below", "equal", "cross_above", "cross_below"}:
        return None
    return {"operator": operator, "value": compare.get("value")}


def _matching_factor_definition(
    factor_accessor: Any | None,
    indicator: str,
    params: dict[str, Any],
) -> Any | None:
    if factor_accessor is None:
        return None
    matcher = getattr(factor_accessor, "_matching_factor_definition", None)
    if callable(matcher):
        return matcher(indicator, params)
    return None


def _collect_factor_ids(view: ConditionBindingView) -> list[str]:
    factor_ids: list[str] = []
    factor_id = view.metadata.get("factor_id")
    if isinstance(factor_id, str) and factor_id and factor_id not in factor_ids:
        factor_ids.append(factor_id)
    for item_view in view.metadata.get("item_views", []) if isinstance(view.metadata, dict) else []:
        if isinstance(item_view, ConditionBindingView):
            for nested_id in _collect_factor_ids(item_view):
                if nested_id not in factor_ids:
                    factor_ids.append(nested_id)
    return factor_ids


__all__ = [
    "CompatibilityLegacyConditionEvaluator",
    "ConditionBindingView",
    "FactorConditionEvaluator",
    "FactorFirstEvaluator",
    "StructuralConditionEvaluator",
    "StrategyBinding",
    "normalize_condition_to_factor_binding_view",
    "normalize_rule_to_factor_binding_view",
]
