from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from ..market_sessions import analyze_symbol_bars
from .builtins import compute_builtin_factor
from .registry import FactorRegistry, load_factor_registry


class FactorEngine:
    def __init__(self, registry: FactorRegistry | str | Path):
        if isinstance(registry, (str, Path)):
            registry = load_factor_registry(registry)
        self.registry = registry
        self.mode = str(registry.defaults.get("mode", "shadow"))
        if self.mode != "shadow":
            raise ValueError(f"FactorEngine only supports shadow mode in FR-03, got {self.mode!r}")

    def evaluate_symbol(
        self,
        symbol: str,
        bars: list[dict[str, Any]],
        *,
        evaluation_time: str | None = None,
        market: str = "US",
        asset_snapshot: dict[str, Any] | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        bar_analysis_cache: dict[tuple[str, str, str], dict[str, Any]] = {}
        factor_payloads: dict[str, dict[str, Any]] = {}
        for factor_id, factor in self.registry.factors.items():
            analysis_key = (market, factor.timeframe, factor.timezone)
            if analysis_key not in bar_analysis_cache:
                bar_analysis_cache[analysis_key] = analyze_symbol_bars(
                    [copy.deepcopy(bar) for bar in bars],
                    asset_snapshot=_factor_asset_snapshot(
                        asset_snapshot=asset_snapshot,
                        evaluation_time=evaluation_time,
                    ),
                    market=market,
                    timeframe=factor.timeframe,
                    app_config=_factor_app_config(
                        market=market,
                        timezone_name=factor.timezone,
                        regular_session_only_for_indicators=bool(
                            self.registry.defaults.get("regular_session_only_for_indicators", True)
                        ),
                    ),
                    provider=provider,
                )
            factor_payloads[factor_id] = compute_builtin_factor(
                factor,
                analysis=bar_analysis_cache[analysis_key],
            ).to_dict()

        timestamp = None
        if bar_analysis_cache:
            first_analysis = next(iter(bar_analysis_cache.values()))
            now_et = first_analysis.get("now_et")
            timestamp = now_et.isoformat() if now_et is not None else None

        return {
            "symbol": symbol,
            "timestamp": timestamp,
            "registry_hash": self.registry.config_hash,
            "mode": self.mode,
            "factors": factor_payloads,
        }


def _factor_asset_snapshot(
    *,
    asset_snapshot: dict[str, Any] | None,
    evaluation_time: str | None,
) -> dict[str, Any] | None:
    if asset_snapshot is None and evaluation_time is None:
        return None
    snapshot = copy.deepcopy(asset_snapshot or {})
    if evaluation_time is not None:
        snapshot["timestamp"] = evaluation_time
    return snapshot


def _factor_app_config(
    *,
    market: str,
    timezone_name: str,
    regular_session_only_for_indicators: bool,
) -> dict[str, Any]:
    return {
        "strategy": {
            "market_data": {
                "include_extended_hours": True,
                "extended_hours_usage": "context_only",
                "regular_session_only_for_indicators": regular_session_only_for_indicators,
                "require_completed_bar_for_actionable_signal": True,
            },
            "sessions": {
                market: {
                    "timezone": timezone_name,
                    "regular_start": "09:30",
                    "regular_end": "16:00",
                    "entry_window_start": "10:00",
                    "entry_window_end": "15:15",
                }
            },
        }
    }
