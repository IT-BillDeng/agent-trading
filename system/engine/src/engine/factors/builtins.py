from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from ..indicators import atr, bollinger, rsi, volume_ratio
from .catalog import BUILTIN_FACTOR_IMPLEMENTATIONS
from .schema import FactorDefinition


@dataclass(frozen=True)
class FactorComputation:
    value: Any
    ready: bool
    actionable: bool
    source: str
    reason: str
    config_hash: str
    implementation_available: bool

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
            implementation_available=False,
        )
    return handler(factor, analysis=analysis)


def available_builtin_implementations() -> tuple[str, ...]:
    return tuple(sorted(_BUILTIN_HANDLERS))


def build_regular_session_analysis(bars: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "regular_completed_bars": [dict(bar) for bar in bars],
    }


def compute_rsi_value(
    analysis: dict[str, Any],
    *,
    period: int,
) -> tuple[float | None, str, str]:
    bars, source = _regular_bars(analysis)
    if len(bars) < (period + 1):
        return None, "insufficient_bars", source

    closes = [float(bar["close"]) for bar in bars]
    value = rsi(closes, period)
    if value is None:
        return None, "insufficient_bars", source
    return float(value), "ok", source


def compute_bollinger_bands_value(
    analysis: dict[str, Any],
    *,
    period: int,
    std_dev: float,
) -> tuple[dict[str, float] | None, str, str]:
    bars, source = _regular_bars(analysis)
    if len(bars) < period:
        return None, "insufficient_bars", source

    closes = [float(bar["close"]) for bar in bars]
    upper, middle, lower = bollinger(closes, period, std_dev)
    if upper is None or middle is None or lower is None:
        return None, "insufficient_bars", source
    return {
        "upper": float(upper),
        "middle": float(middle),
        "lower": float(lower),
    }, "ok", source


def compute_bollinger_zscore_value(
    analysis: dict[str, Any],
    *,
    period: int,
    std_dev: float,
) -> tuple[float | None, str, str]:
    bars, source = _regular_bars(analysis)
    bands, reason, _ = compute_bollinger_bands_value(
        analysis,
        period=period,
        std_dev=std_dev,
    )
    if bands is None:
        return None, reason, source

    closes = [float(bar["close"]) for bar in bars]
    band_std = (bands["upper"] - bands["middle"]) / std_dev if std_dev else 0.0
    if band_std == 0:
        return None, "zero_variance", source
    return float((closes[-1] - bands["middle"]) / band_std), "ok", source


def compute_volume_ratio_value(
    analysis: dict[str, Any],
    *,
    period: int,
) -> tuple[float | None, str, str]:
    bars, source = _regular_bars(analysis)
    if len(bars) < (period + 1):
        return None, "insufficient_bars", source

    volumes = [float(bar.get("volume", 0)) for bar in bars]
    value = volume_ratio(volumes, period)
    if value is None:
        return None, "insufficient_bars", source
    return float(value), "ok", source


def compute_atr_value(
    analysis: dict[str, Any],
    *,
    period: int,
) -> tuple[float | None, str, str]:
    bars, source = _regular_bars(analysis)
    if len(bars) < (period + 1):
        return None, "insufficient_bars", source

    highs = [float(bar["high"]) for bar in bars]
    lows = [float(bar["low"]) for bar in bars]
    closes = [float(bar["close"]) for bar in bars]
    atr_value = atr(highs, lows, closes, period)
    if atr_value is None:
        return None, "insufficient_bars", source
    return float(atr_value), "ok", source


def compute_atr_pct_value(
    analysis: dict[str, Any],
    *,
    period: int,
) -> tuple[float | None, str, str]:
    bars, source = _regular_bars(analysis)
    atr_value, reason, _ = compute_atr_value(analysis, period=period)
    if atr_value is None:
        return None, reason, source

    closes = [float(bar["close"]) for bar in bars]
    latest_close = closes[-1] if closes else None
    if latest_close in (None, 0):
        return None, "zero_close", source
    return float(atr_value) / float(latest_close), "ok", source


def compute_return_value(
    analysis: dict[str, Any],
    *,
    period: int,
) -> tuple[float | None, str, str]:
    bars, source = _regular_bars(analysis)
    if len(bars) < (period + 1):
        return None, "insufficient_bars", source

    closes = [float(bar["close"]) for bar in bars]
    base_close = closes[-(period + 1)]
    if base_close == 0:
        return None, "zero_base", source
    return float((closes[-1] / base_close) - 1.0), "ok", source


def compute_legacy_indicator_baseline(
    indicator: str,
    params: dict[str, Any],
    bars: list[dict[str, Any]],
) -> Any:
    period = int(params.get("period", 20))
    if indicator == "rsi":
        value, _, _ = compute_rsi_value(build_regular_session_analysis(bars), period=period)
        return value
    if indicator == "bollinger":
        std_dev = float(params.get("std_dev", 2.0))
        bands, _, _ = compute_bollinger_bands_value(
            build_regular_session_analysis(bars),
            period=period,
            std_dev=std_dev,
        )
        return bands
    if indicator == "volume_ratio":
        value, _, _ = compute_volume_ratio_value(build_regular_session_analysis(bars), period=period)
        return value
    if indicator == "atr":
        value, _, _ = compute_atr_value(build_regular_session_analysis(bars), period=period)
        return value
    if indicator == "momentum":
        value, _, _ = compute_return_value(build_regular_session_analysis(bars), period=period)
        return value
    return None


def _compute_rsi(
    factor: FactorDefinition,
    *,
    analysis: dict[str, Any],
) -> FactorComputation:
    period = int(factor.params.get("period", 14))
    value, reason, source = compute_rsi_value(analysis, period=period)
    if value is None:
        return _not_ready(factor, source=source, reason=reason)
    return _ready(factor, value=value, source=source)


def _compute_bollinger_zscore(
    factor: FactorDefinition,
    *,
    analysis: dict[str, Any],
) -> FactorComputation:
    period = int(factor.params.get("period", 20))
    std_dev = float(factor.params.get("std_dev", 2.0))
    value, reason, source = compute_bollinger_zscore_value(
        analysis,
        period=period,
        std_dev=std_dev,
    )
    if value is None:
        return _not_ready(factor, source=source, reason=reason)
    return _ready(factor, value=value, source=source)


def _compute_volume_ratio(
    factor: FactorDefinition,
    *,
    analysis: dict[str, Any],
) -> FactorComputation:
    period = int(factor.params.get("period", 20))
    value, reason, source = compute_volume_ratio_value(analysis, period=period)
    if value is None:
        return _not_ready(factor, source=source, reason=reason)
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


def _compute_afterhours_move_pct(
    factor: FactorDefinition,
    *,
    analysis: dict[str, Any],
) -> FactorComputation:
    source = "extended_hours_context"
    value = (
        analysis.get("extended_context", {}).get("afterhours_move_pct")
        if isinstance(analysis.get("extended_context"), dict)
        else None
    )
    if value is None:
        return _not_ready(factor, source=source, reason="no_afterhours_context")
    return _ready(factor, value=value, source=source)


def _compute_overnight_return_pct(
    factor: FactorDefinition,
    *,
    analysis: dict[str, Any],
) -> FactorComputation:
    source = "extended_hours_context"
    value = (
        analysis.get("extended_context", {}).get("overnight_return_pct")
        if isinstance(analysis.get("extended_context"), dict)
        else None
    )
    if value is None:
        return _not_ready(factor, source=source, reason="no_overnight_context")
    return _ready(factor, value=value, source=source)


def _compute_atr_pct(
    factor: FactorDefinition,
    *,
    analysis: dict[str, Any],
) -> FactorComputation:
    period = int(factor.params.get("period", 14))
    value, reason, source = compute_atr_pct_value(analysis, period=period)
    if value is None:
        return _not_ready(factor, source=source, reason=reason)
    return _ready(factor, value=value, source=source)


def _compute_return(
    factor: FactorDefinition,
    *,
    analysis: dict[str, Any],
) -> FactorComputation:
    period = int(factor.params.get("period", 1))
    value, reason, source = compute_return_value(analysis, period=period)
    if value is None:
        return _not_ready(factor, source=source, reason=reason)
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
        implementation_available=True,
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
        implementation_available=True,
    )


def _regular_bars(analysis: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    return list(analysis.get("regular_completed_bars") or []), "regular_session_completed_bars"


_BUILTIN_HANDLERS: dict[str, Callable[[FactorDefinition], FactorComputation]] = {
    "builtin:afterhours_move_pct": _compute_afterhours_move_pct,
    "builtin:atr_pct": _compute_atr_pct,
    "builtin:rsi": _compute_rsi,
    "builtin:bollinger_zscore": _compute_bollinger_zscore,
    "builtin:overnight_return_pct": _compute_overnight_return_pct,
    "builtin:volume_ratio": _compute_volume_ratio,
    "builtin:premarket_gap_pct": _compute_premarket_gap_pct,
    "builtin:return": _compute_return,
}

if set(BUILTIN_FACTOR_IMPLEMENTATIONS) != set(_BUILTIN_HANDLERS):
    raise RuntimeError(
        "builtin factor catalog does not match registered handlers: "
        f"catalog={sorted(BUILTIN_FACTOR_IMPLEMENTATIONS)!r} "
        f"handlers={sorted(_BUILTIN_HANDLERS)!r}"
    )
