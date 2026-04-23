"""Legacy strategy compatibility facade.

Factor-first rule evaluation is canonical. ``engine.strategy`` remains only as a
thin import-compatible wrapper for the pre-rule-engine heuristic strategy.
"""

from __future__ import annotations

from pathlib import Path

# Keep ``engine.strategy`` import-compatible while exposing
# ``engine.strategy.bindings`` / ``engine.strategy.evaluator`` / etc.
__path__ = [str(Path(__file__).with_suffix(""))]

from .strategy.compatibility import (  # noqa: E402
    LegacyStrategyEngine as StrategyEngine,
    LegacyStrategySignal as StrategySignal,
    build_legacy_strategy_engine,
    evaluate_legacy_symbol as evaluate_symbol,
)

__all__ = [
    "StrategyEngine",
    "StrategySignal",
    "build_legacy_strategy_engine",
    "evaluate_symbol",
]
