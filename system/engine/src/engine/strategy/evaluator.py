from __future__ import annotations

from typing import Any

from .bindings import StrategyBinding, build_legacy_rule_binding
from .compatibility import evaluate_legacy_symbol


class FactorFirstEvaluator:
    """FF-01 skeleton for the future factor-first strategy evaluator.

    For now it is intentionally compatibility-first and delegates to the legacy
    strategy implementation.
    """

    def __init__(self, app, *, compatibility_mode: bool = True):
        self.app = app
        self.compatibility_mode = compatibility_mode

    def binding_for_rule(self, rule_id: str, *, factor_ids: list[str] | None = None) -> StrategyBinding:
        return build_legacy_rule_binding(rule_id, factor_ids=factor_ids)

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


__all__ = ["FactorFirstEvaluator", "StrategyBinding"]
