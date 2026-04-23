from __future__ import annotations

import copy
import math
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..market_sessions import parse_bar_timestamp, timeframe_delta
from .engine import FactorEngine
from .registry import FactorRegistry

DEFAULT_HORIZONS = (1, 2)
DEFAULT_MIN_IC_SAMPLES = 3


def build_factor_attribution(
    bars_by_symbol: dict[str, Sequence[Any]],
    *,
    factor_engine: FactorEngine | FactorRegistry | str | Path | Any,
    market_by_symbol: dict[str, str] | None = None,
    timeframe: str = "30min",
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    min_ic_samples: int = DEFAULT_MIN_IC_SAMPLES,
) -> dict[str, Any]:
    engine = _resolve_factor_engine(factor_engine)
    horizon_values = tuple(_normalize_horizons(horizons))
    aggregated: dict[str, list[dict[str, Any]]] = {
        factor_id: []
        for factor_id in engine.registry.factors
    }
    observations_by_symbol: dict[str, dict[str, list[dict[str, Any]]]] = {}
    factors_payload: dict[str, dict[str, Any]] = {}

    for symbol, bars in bars_by_symbol.items():
        observations_by_symbol[symbol] = collect_factor_observations(
            symbol,
            bars,
            factor_engine=engine,
            market=(market_by_symbol or {}).get(symbol, "US"),
            timeframe=timeframe,
            horizons=horizon_values,
        )
        for factor_id, factor_observations in observations_by_symbol[symbol].items():
            aggregated[factor_id].extend(factor_observations)

    symbol_coverage: dict[str, dict[str, Any]] = {}
    for symbol, symbol_observations in observations_by_symbol.items():
        symbol_items: list[dict[str, Any]] = []
        for factor_observations in symbol_observations.values():
            symbol_items.extend(factor_observations)
        symbol_coverage[symbol] = _coverage_summary(symbol_items)

    for factor_id, factor in engine.registry.factors.items():
        symbol_payloads: dict[str, dict[str, Any]] = {}
        for symbol in bars_by_symbol:
            factor_observations = observations_by_symbol.get(symbol, {}).get(factor_id, [])
            symbol_payloads[symbol] = summarize_factor_observations(
                factor_observations,
                horizons=horizon_values,
                min_ic_samples=min_ic_samples,
            )

        factor_summary = summarize_factor_observations(
            aggregated[factor_id],
            horizons=horizon_values,
            min_ic_samples=min_ic_samples,
        )
        factor_summary.update(
            {
                "type": factor.type,
                "session": factor.session,
                "timeframe": factor.timeframe,
                "output": factor.output,
                "usage": list(factor.usage),
                "actionable": bool(factor.actionable),
                "config_hash": factor.config_hash,
                "symbol_level_coverage": {
                    symbol: _coverage_summary(observations_by_symbol.get(symbol, {}).get(factor_id, []))
                    for symbol in bars_by_symbol
                },
                "symbols": symbol_payloads,
            }
        )
        factors_payload[factor_id] = factor_summary

    return {
        "enabled": True,
        "mode": engine.mode,
        "registry_hash": engine.registry.config_hash,
        "horizons": list(horizon_values),
        "min_ic_samples": int(min_ic_samples),
        "symbol_coverage": symbol_coverage,
        "factor_correlation": {
            "status": "placeholder",
            "matrix": None,
            "reason": "factor_correlation_not_computed_in_v1",
        },
        "factors": factors_payload,
    }


def collect_factor_observations(
    symbol: str,
    bars: Sequence[Any],
    *,
    factor_engine: Any,
    market: str = "US",
    timeframe: str = "30min",
    horizons: Iterable[int] = DEFAULT_HORIZONS,
) -> dict[str, list[dict[str, Any]]]:
    normalized_bars = [_normalize_bar(bar) for bar in bars]
    horizon_values = tuple(_normalize_horizons(horizons))
    observations: dict[str, list[dict[str, Any]]] = {
        factor_id: []
        for factor_id in factor_engine.registry.factors
    }

    for index, bar in enumerate(normalized_bars):
        factor_snapshot = factor_engine.evaluate_symbol(
            symbol,
            normalized_bars[: index + 1],
            evaluation_time=_evaluation_time_for_bar(bar, timeframe=timeframe),
            market=market,
        )
        factor_payloads = dict(factor_snapshot.get("factors", {}))

        for factor_id, payload in factor_payloads.items():
            factor_value = _coerce_float(payload.get("value"))
            observations[factor_id].append(
                {
                    "symbol": symbol,
                    "timestamp": _bar_timestamp_text(bar),
                    "value": factor_value,
                    "ready": bool(payload.get("ready")) and factor_value is not None,
                    "reason": str(payload.get("reason") or "unknown"),
                    "source": str(payload.get("source") or "unknown"),
                    "config_hash": str(payload.get("config_hash") or ""),
                    "future_returns": {
                        horizon: _future_return(normalized_bars, index, horizon)
                        for horizon in horizon_values
                    },
                }
            )

    return observations


def summarize_factor_observations(
    observations: Sequence[dict[str, Any]],
    *,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    min_ic_samples: int = DEFAULT_MIN_IC_SAMPLES,
) -> dict[str, Any]:
    horizon_values = tuple(_normalize_horizons(horizons))
    valid_observations = [
        item
        for item in observations
        if bool(item.get("ready")) and _coerce_float(item.get("value")) is not None
    ]
    values = [_coerce_float(item.get("value")) for item in valid_observations]
    numeric_values = [value for value in values if value is not None]

    summary: dict[str, Any] = {
        **_coverage_summary(observations),
        "mean": _mean(numeric_values),
        "std": _stddev(numeric_values),
        "not_ready_reasons": dict(
            sorted(
                Counter(
                    str(item.get("reason") or "unknown")
                    for item in observations
                    if not bool(item.get("ready")) or _coerce_float(item.get("value")) is None
                ).items()
            )
        ),
        "source": _first_value(observations, "source"),
        "config_hash": _first_value(observations, "config_hash"),
        "decay_basis": {
            "status": "pending",
            "base_horizon": horizon_values[0] if horizon_values else None,
            "by_horizon": {},
        },
    }

    base_horizon = horizon_values[0] if horizon_values else None
    base_ic: float | None = None
    base_rank_ic: float | None = None
    for horizon in horizon_values:
        pairs = [
            (_coerce_float(item.get("value")), _coerce_float(item.get("future_returns", {}).get(horizon)))
            for item in valid_observations
        ]
        filtered_pairs = [
            (factor_value, future_return)
            for factor_value, future_return in pairs
            if factor_value is not None and future_return is not None
        ]
        factor_values = [item[0] for item in filtered_pairs]
        future_returns = [item[1] for item in filtered_pairs]
        ic_value, ic_reason = information_coefficient(
            factor_values,
            future_returns,
            min_samples=min_ic_samples,
        )
        rank_ic_value, rank_ic_reason = rank_information_coefficient(
            factor_values,
            future_returns,
            min_samples=min_ic_samples,
        )
        summary[f"ic_{horizon}bar"] = ic_value
        summary[f"ic_{horizon}bar_reason"] = ic_reason
        summary[f"ic_{horizon}bar_sample_count"] = len(filtered_pairs)
        summary[f"rank_ic_{horizon}bar"] = rank_ic_value
        summary[f"rank_ic_{horizon}bar_reason"] = rank_ic_reason
        summary[f"rank_ic_{horizon}bar_sample_count"] = len(filtered_pairs)
        summary["decay_basis"]["by_horizon"][f"{horizon}bar"] = {
            "ic": ic_value,
            "rank_ic": rank_ic_value,
            "sample_count": len(filtered_pairs),
            "delta_from_base_ic": None,
            "delta_from_base_rank_ic": None,
            "abs_ic_retention_vs_base": None,
            "abs_rank_ic_retention_vs_base": None,
        }
        if base_horizon == horizon:
            base_ic = ic_value
            base_rank_ic = rank_ic_value

    if base_horizon is not None:
        for horizon in horizon_values:
            entry = summary["decay_basis"]["by_horizon"].get(f"{horizon}bar", {})
            ic_value = entry.get("ic")
            rank_ic_value = entry.get("rank_ic")
            if base_ic is not None and ic_value is not None:
                entry["delta_from_base_ic"] = ic_value - base_ic
                entry["abs_ic_retention_vs_base"] = _retention_ratio(ic_value, base_ic)
            if base_rank_ic is not None and rank_ic_value is not None:
                entry["delta_from_base_rank_ic"] = rank_ic_value - base_rank_ic
                entry["abs_rank_ic_retention_vs_base"] = _retention_ratio(rank_ic_value, base_rank_ic)

        base_entry = summary["decay_basis"]["by_horizon"].get(f"{base_horizon}bar", {})
        if base_entry.get("ic") is None and base_entry.get("rank_ic") is None:
            summary["decay_basis"]["status"] = "insufficient_samples"
        else:
            summary["decay_basis"]["status"] = "ok"

    return summary


def information_coefficient(
    factor_values: Sequence[float],
    future_returns: Sequence[float],
    *,
    min_samples: int = DEFAULT_MIN_IC_SAMPLES,
) -> tuple[float | None, str | None]:
    if len(factor_values) != len(future_returns):
        raise ValueError("factor_values and future_returns must have the same length")
    if len(factor_values) < int(min_samples):
        return None, "insufficient_samples"

    mean_x = _mean(factor_values)
    mean_y = _mean(future_returns)
    if mean_x is None or mean_y is None:
        return None, "insufficient_samples"

    centered_x = [value - mean_x for value in factor_values]
    centered_y = [value - mean_y for value in future_returns]
    variance_x = sum(value * value for value in centered_x)
    variance_y = sum(value * value for value in centered_y)

    if variance_x == 0:
        return None, "zero_variance_factor"
    if variance_y == 0:
        return None, "zero_variance_future_return"

    covariance = sum(left * right for left, right in zip(centered_x, centered_y))
    correlation = covariance / math.sqrt(variance_x * variance_y)
    return correlation, None


def rank_information_coefficient(
    factor_values: Sequence[float],
    future_returns: Sequence[float],
    *,
    min_samples: int = DEFAULT_MIN_IC_SAMPLES,
) -> tuple[float | None, str | None]:
    ranked_factor_values = _rank_series(factor_values)
    ranked_future_returns = _rank_series(future_returns)
    return information_coefficient(
        ranked_factor_values,
        ranked_future_returns,
        min_samples=min_samples,
    )


def _resolve_factor_engine(factor_engine: FactorEngine | FactorRegistry | str | Path | Any) -> Any:
    if isinstance(factor_engine, FactorEngine):
        return factor_engine
    if (
        hasattr(factor_engine, "evaluate_symbol")
        and hasattr(factor_engine, "registry")
        and hasattr(factor_engine, "mode")
    ):
        return factor_engine
    return FactorEngine(factor_engine)


def _normalize_horizons(horizons: Iterable[int]) -> list[int]:
    normalized: list[int] = []
    for horizon in horizons:
        value = int(horizon)
        if value <= 0:
            raise ValueError("horizons must contain positive integers")
        normalized.append(value)
    return sorted(dict.fromkeys(normalized))


def _coverage_summary(observations: Sequence[dict[str, Any]]) -> dict[str, Any]:
    total_samples = len(observations)
    valid_count = sum(
        1
        for item in observations
        if bool(item.get("ready")) and _coerce_float(item.get("value")) is not None
    )
    missing_count = total_samples - valid_count
    return {
        "sample_count": total_samples,
        "valid_count": valid_count,
        "missing_count": missing_count,
        "coverage": (valid_count / total_samples) if total_samples > 0 else 0.0,
        "missing_rate": (missing_count / total_samples) if total_samples > 0 else 0.0,
    }


def _rank_series(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(indexed):
        end = index
        value = indexed[index][1]
        while end < len(indexed) and indexed[end][1] == value:
            end += 1
        average_rank = (index + 1 + end) / 2.0
        for original_index, _ in indexed[index:end]:
            ranks[original_index] = average_rank
        index = end
    return ranks


def _retention_ratio(value: float, base_value: float) -> float | None:
    if base_value == 0:
        return None
    return abs(value) / abs(base_value)


def _normalize_bar(bar: Any) -> dict[str, Any]:
    if hasattr(bar, "to_dict"):
        return copy.deepcopy(bar.to_dict())
    if isinstance(bar, dict):
        return copy.deepcopy(bar)
    raise TypeError(f"unsupported bar payload {type(bar)!r}")


def _evaluation_time_for_bar(bar: dict[str, Any], *, timeframe: str) -> str | None:
    parsed = parse_bar_timestamp(bar)
    if parsed is None:
        value = _bar_timestamp_text(bar)
        return value if value else None

    delta = timeframe_delta(timeframe) or timedelta()
    return (parsed + delta).isoformat()


def _future_return(bars: Sequence[dict[str, Any]], index: int, horizon: int) -> float | None:
    future_index = index + int(horizon)
    if future_index >= len(bars):
        return None

    current_close = _coerce_float(bars[index].get("close"))
    future_close = _coerce_float(bars[future_index].get("close"))
    if current_close in (None, 0.0) or future_close is None:
        return None
    return (future_close - current_close) / current_close


def _bar_timestamp_text(bar: dict[str, Any]) -> str | None:
    for key in ("timestamp", "time", "datetime", "date"):
        value = bar.get(key)
        if value:
            return str(value)
    return None


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_value(observations: Sequence[dict[str, Any]], key: str) -> Any:
    for item in observations:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return None


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _stddev(values: Sequence[float]) -> float | None:
    if not values:
        return None
    mean_value = _mean(values)
    if mean_value is None:
        return None
    return math.sqrt(sum((value - mean_value) ** 2 for value in values) / len(values))
