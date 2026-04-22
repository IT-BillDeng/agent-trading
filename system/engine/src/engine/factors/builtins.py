from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from ..indicators import bollinger, rsi, volume_ratio
from .schema import FactorDefinition


@dataclass(frozen=True)
class FactorComputation:
    value: Any
    ready: bool
    actionable: bool
    source: str
    reason: str
    config_hash: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_builtin_factor(
    factor: FactorDefinition,
    *,
    analysis: dict[str, Any],
) -> FactorComputation:
    handler = _BUILTIN_HANDLERS.get(factor.implementation)
    if handler is None:
        return FactorComputation(
            value=None,
            ready=False,
            actionable=bool(factor.actionable),
            source="registry",
            reason="implementation_not_available",
            config_hash=factor.config_hash,
        )
    return handler(factor, analysis=analysis)


def _compute_rsi(
    factor: FactorDefinition,
    *,
    analysis: dict[str, Any],
) -> FactorComputation:
    bars = list(analysis.get("regular_completed_bars") or [])
    source = "regular_session_completed_bars"
    period = int(factor.params.get("period", 14))
    min_required = max(int(factor.required_bars), period + 1)
    if len(bars) < min_required:
        return _not_ready(factor, source=source, reason="insufficient_bars")

    closes = [float(bar["close"]) for bar in bars]
    value = rsi(closes, period)
    if value is None:
        return _not_ready(factor, source=source, reason="insufficient_bars")
    return _ready(factor, value=value, source=source)


def _compute_bollinger_zscore(
    factor: FactorDefinition,
    *,
    analysis: dict[str, Any],
) -> FactorComputation:
    bars = list(analysis.get("regular_completed_bars") or [])
    source = "regular_session_completed_bars"
    period = int(factor.params.get("period", 20))
    std_dev = float(factor.params.get("std_dev", 2.0))
    min_required = max(int(factor.required_bars), period)
    if len(bars) < min_required:
        return _not_ready(factor, source=source, reason="insufficient_bars")

    closes = [float(bar["close"]) for bar in bars]
    upper, middle, lower = bollinger(closes, period, std_dev)
    if upper is None or middle is None or lower is None:
        return _not_ready(factor, source=source, reason="insufficient_bars")

    band_std = (upper - middle) / std_dev if std_dev else 0.0
    if band_std == 0:
        return _not_ready(factor, source=source, reason="zero_variance")

    zscore = (closes[-1] - middle) / band_std
    return _ready(factor, value=zscore, source=source)


def _compute_volume_ratio(
    factor: FactorDefinition,
    *,
    analysis: dict[str, Any],
) -> FactorComputation:
    bars = list(analysis.get("regular_completed_bars") or [])
    source = "regular_session_completed_bars"
    period = int(factor.params.get("period", 20))
    min_required = max(int(factor.required_bars), period + 1)
    if len(bars) < min_required:
        return _not_ready(factor, source=source, reason="insufficient_bars")

    volumes = [float(bar.get("volume", 0)) for bar in bars]
    value = volume_ratio(volumes, period)
    if value is None:
        return _not_ready(factor, source=source, reason="insufficient_bars")
    return _ready(factor, value=value, source=source)


def _compute_premarket_gap_pct(
    factor: FactorDefinition,
    *,
    analysis: dict[str, Any],
) -> FactorComputation:
    source = "extended_hours_context"
    value = (
        analysis.get("extended_context", {}).get("premarket_gap_pct")
        if isinstance(analysis.get("extended_context"), dict)
        else None
    )
    if value is None:
        return _not_ready(factor, source=source, reason="no_premarket_context")
    return _ready(factor, value=value, source=source)


def _ready(
    factor: FactorDefinition,
    *,
    value: Any,
    source: str,
) -> FactorComputation:
    return FactorComputation(
        value=value,
        ready=True,
        actionable=bool(factor.actionable),
        source=source,
        reason="ok",
        config_hash=factor.config_hash,
    )


def _not_ready(
    factor: FactorDefinition,
    *,
    source: str,
    reason: str,
) -> FactorComputation:
    return FactorComputation(
        value=None,
        ready=False,
        actionable=bool(factor.actionable),
        source=source,
        reason=reason,
        config_hash=factor.config_hash,
    )


_BUILTIN_HANDLERS: dict[str, Callable[[FactorDefinition], FactorComputation]] = {
    "builtin:rsi": _compute_rsi,
    "builtin:bollinger_zscore": _compute_bollinger_zscore,
    "builtin:volume_ratio": _compute_volume_ratio,
    "builtin:premarket_gap_pct": _compute_premarket_gap_pct,
}
