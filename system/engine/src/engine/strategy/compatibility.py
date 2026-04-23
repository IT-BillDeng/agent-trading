from __future__ import annotations

from typing import Any

from ..strategy import StrategyEngine as LegacyStrategyEngine
from ..strategy import StrategySignal as LegacyStrategySignal


def build_legacy_strategy_engine(app) -> LegacyStrategyEngine:
    return LegacyStrategyEngine(app)


def evaluate_legacy_symbol(
    app,
    *,
    symbol: str,
    market: str,
    bars: list[dict[str, Any]],
    position: dict[str, Any] | None = None,
) -> LegacyStrategySignal:
    engine = build_legacy_strategy_engine(app)
    return engine.evaluate_symbol(symbol=symbol, market=market, bars=bars, position=position)


__all__ = [
    "LegacyStrategyEngine",
    "LegacyStrategySignal",
    "build_legacy_strategy_engine",
    "evaluate_legacy_symbol",
]
