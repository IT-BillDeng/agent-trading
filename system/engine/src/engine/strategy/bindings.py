from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StrategyBinding:
    """Lightweight rule/factor binding placeholder for factor-first migration."""

    binding_id: str
    rule_id: str
    factor_ids: tuple[str, ...] = ()
    mode: str = "compatibility"
    metadata: dict[str, Any] = field(default_factory=dict)


def build_legacy_rule_binding(rule_id: str, *, factor_ids: list[str] | None = None) -> StrategyBinding:
    return StrategyBinding(
        binding_id=f"legacy::{rule_id}",
        rule_id=rule_id,
        factor_ids=tuple(factor_ids or ()),
        mode="compatibility",
    )
