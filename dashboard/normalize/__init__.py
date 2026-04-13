"""Broker-agnostic data normalization package.

Usage:
    from dashboard.normalize import get_normalizer

    norm = get_normalizer("tiger")  # or "ib", "futu", etc.
    account = norm.account(raw_data)
    positions = norm.positions(raw_list)

To add a new broker:
    1. Create dashboard/normalize/<broker>.py
    2. Implement the BaseNormalizer protocol
    3. Register in the NORMALIZERS dict below
"""
from __future__ import annotations
from typing import Any, Protocol


class BaseNormalizer(Protocol):
    """Broker normalizer protocol. All methods take raw broker data and return unified dicts."""

    def account(self, raw: dict[str, Any]) -> dict[str, Any]: ...
    def position(self, raw: dict[str, Any]) -> dict[str, Any]: ...
    def positions(self, raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
    def order(self, raw: dict[str, Any]) -> dict[str, Any]: ...
    def orders(self, raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
    def quote(self, raw: dict[str, Any]) -> dict[str, Any]: ...
    def quotes(self, raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]: ...
    def pnl(self, raw: dict[str, Any]) -> dict[str, Any]: ...


# ── Registry ─────────────────────────────────────────────

_NORMALIZERS: dict[str, type] = {}


def register(broker: str, cls: type) -> None:
    """Register a normalizer class for a broker."""
    _NORMALIZERS[broker] = cls


def get_normalizer(broker: str) -> BaseNormalizer:
    """Get a normalizer instance for the given broker."""
    if broker not in _NORMALIZERS:
        raise ValueError(f"Unknown broker: {broker}. Available: {list(_NORMALIZERS.keys())}")
    return _NORMALIZERS[broker]()


def available_brokers() -> list[str]:
    """List registered broker names."""
    return list(_NORMALIZERS.keys())


# ── Unified Schema ───────────────────────────────────────
# Field names that all normalizers must produce.

ACCOUNT_FIELDS = [
    "total_assets", "cash_balance", "buying_power", "position_value",
    "unrealized_pnl", "realized_pnl", "available_funds", "currency",
]

POSITION_FIELDS = [
    "symbol", "name", "quantity", "avg_cost", "market_price", "market_value",
    "unrealized_pnl", "today_pnl", "today_pnl_pct", "last_close", "currency",
]

ORDER_FIELDS = [
    "id", "symbol", "name", "side", "quantity", "filled_qty",
    "order_type", "limit_price", "stop_price", "status", "submitted_at",
]

QUOTE_FIELDS = [
    "symbol", "name", "latest_price", "prev_close", "open",
    "high", "low", "volume", "change", "change_pct",
]

PNL_DETAIL_FIELDS = [
    "symbol", "unrealized_pnl", "realized_pnl", "market_value",
    "today_pnl", "today_pnl_pct",
]


# ── Auto-import normalizers ──────────────────────────────

from . import tiger  # noqa: F401 — triggers registration
