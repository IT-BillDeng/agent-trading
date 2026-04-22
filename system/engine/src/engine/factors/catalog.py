from __future__ import annotations


# Keep the schema contract and builtin runtime in sync from a single source.
BUILTIN_FACTOR_IMPLEMENTATIONS: tuple[str, ...] = (
    "builtin:bollinger_zscore",
    "builtin:premarket_gap_pct",
    "builtin:rsi",
    "builtin:volume_ratio",
)

