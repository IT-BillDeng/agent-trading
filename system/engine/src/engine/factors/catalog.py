from __future__ import annotations


# Keep the schema contract and builtin runtime in sync from a single source.
BUILTIN_FACTOR_IMPLEMENTATIONS: tuple[str, ...] = (
    "builtin:afterhours_move_pct",
    "builtin:atr_pct",
    "builtin:bollinger_zscore",
    "builtin:overnight_return_pct",
    "builtin:premarket_gap_pct",
    "builtin:return",
    "builtin:rsi",
    "builtin:volume_ratio",
)
