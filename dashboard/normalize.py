"""Data normalization layer — broker-agnostic field names.

All dashboard APIs return normalized data through this layer.
To add a new broker, implement a normalizer that maps its fields
to the unified schema defined here.

Unified Schema
--------------

Account:
    total_assets        float   net_liquidation (total portfolio value)
    cash_balance        float   cash available (no leverage)
    buying_power        float   maximum purchasable amount
    position_value      float   gross position market value
    unrealized_pnl      float   total unrealized P&L
    realized_pnl        float   today's realized P&L
    available_funds     float   funds available for new orders
    currency            str     account currency

Position:
    symbol              str     ticker symbol
    name                str     company name
    quantity            int     shares held
    avg_cost            float   average entry cost
    market_price        float   current market price
    market_value        float   current market value
    unrealized_pnl      float   unrealized P&L for this position
    today_pnl           float   today's P&L for this position
    today_pnl_pct       float   today's P&L percentage
    last_close          float   previous close price
    currency            str

Order:
    id                  str|int order identifier
    symbol              str
    side                str     BUY / SELL
    quantity            int
    filled_qty          int
    order_type          str     LMT / MKT / STP / STP_LMT
    limit_price         float|None
    stop_price          float|None
    status              str
    submitted_at        str

Quote:
    symbol              str
    name                str
    latest_price        float
    prev_close          float
    open                float
    high                float
    low                 float
    volume              int
    change              float
    change_pct          float

PnlSummary:
    total_unrealized    float
    total_realized      float
    details             list[PositionPnl]

PositionPnl:
    symbol              str
    unrealized_pnl      float
    realized_pnl        float
    market_value        float
    today_pnl           float
    today_pnl_pct       float
"""
from __future__ import annotations
from typing import Any


# ── Account ──────────────────────────────────────────────

def normalize_account(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize account/assets data from any broker."""
    # Tiger mapping
    return {
        "total_assets": raw.get("total_assets") or raw.get("net_liquidation") or raw.get("netLiquidation") or 0,
        "cash_balance": raw.get("cash_balance") or raw.get("cash") or raw.get("cashValue") or 0,
        "buying_power": raw.get("buying_power") or raw.get("buyingPower") or 0,
        "position_value": raw.get("position_value") or raw.get("gross_position_value") or raw.get("grossPositionValue") or 0,
        "unrealized_pnl": raw.get("unrealized_pnl") or raw.get("unrealizedPnl") or 0,
        "realized_pnl": raw.get("realized_pnl") or raw.get("realizedPnl") or 0,
        "available_funds": raw.get("available_funds") or raw.get("availableFunds") or 0,
        "currency": raw.get("currency") or "USD",
    }


# ── Position ─────────────────────────────────────────────

def normalize_position(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single position from any broker."""
    return {
        "symbol": raw.get("symbol") or "",
        "name": raw.get("name") or "",
        "quantity": int(raw.get("quantity") or raw.get("position") or 0),
        "avg_cost": float(raw.get("avg_cost") or raw.get("average_cost") or raw.get("averageCost") or 0),
        "market_price": float(raw.get("market_price") or raw.get("latest_price") or raw.get("latestPrice") or 0),
        "market_value": float(raw.get("market_value") or raw.get("marketValue") or 0),
        "unrealized_pnl": float(raw.get("unrealized_pnl") or raw.get("unrealizedPnl") or 0),
        "today_pnl": float(raw.get("today_pnl") or raw.get("todayPnl") or 0),
        "today_pnl_pct": float(raw.get("today_pnl_percent") or raw.get("todayPnlPercent") or 0),
        "last_close": float(raw.get("last_close") or raw.get("last_close_price") or raw.get("lastClosePrice") or 0),
        "currency": raw.get("currency") or "USD",
    }


def normalize_positions(raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize a list of positions."""
    return [normalize_position(p) for p in raw_list if isinstance(p, dict)]


# ── Order ────────────────────────────────────────────────

def normalize_order(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single order from any broker."""
    return {
        "id": raw.get("id") or raw.get("order_id") or "",
        "symbol": raw.get("symbol") or "",
        "name": raw.get("name") or "",
        "side": str(raw.get("side") or raw.get("action") or "").upper(),
        "quantity": int(raw.get("quantity") or 0),
        "filled_qty": int(raw.get("filled_qty") or raw.get("filled_quantity") or 0),
        "order_type": str(raw.get("order_type") or raw.get("orderType") or ""),
        "limit_price": raw.get("limit_price") or raw.get("limitPrice"),
        "stop_price": raw.get("stop_price") or raw.get("aux_price") or raw.get("auxPrice"),
        "status": str(raw.get("status") or ""),
        "submitted_at": str(raw.get("submitted_at") or raw.get("submittedAt") or ""),
    }


def normalize_orders(raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize a list of orders."""
    return [normalize_order(o) for o in raw_list if isinstance(o, dict)]


# ── Quote ────────────────────────────────────────────────

def normalize_quote(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single quote from any broker."""
    change = raw.get("change") or 0
    prev_close = raw.get("prev_close") or raw.get("prevClose") or 0
    latest = raw.get("latest_price") or raw.get("last_price") or raw.get("latestPrice") or 0
    change_pct = raw.get("change_rate") or raw.get("changeRate") or (change / prev_close if prev_close else 0)
    return {
        "symbol": raw.get("symbol") or "",
        "name": raw.get("name") or "",
        "latest_price": float(latest),
        "prev_close": float(prev_close),
        "open": float(raw.get("open") or 0),
        "high": float(raw.get("high") or 0),
        "low": float(raw.get("low") or 0),
        "volume": int(raw.get("volume") or 0),
        "change": float(change),
        "change_pct": float(change_pct),
    }


def normalize_quotes(raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize a list of quotes."""
    return [normalize_quote(q) for q in raw_list if isinstance(q, dict)]


# ── PnL ──────────────────────────────────────────────────

def normalize_pnl(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize P&L summary."""
    details = []
    for d in raw.get("details", []):
        if not isinstance(d, dict):
            continue
        details.append({
            "symbol": d.get("symbol") or "",
            "unrealized_pnl": float(d.get("unrealized_pnl") or d.get("unrealizedPnl") or 0),
            "realized_pnl": float(d.get("realized_pnl") or d.get("realizedPnl") or 0),
            "market_value": float(d.get("market_value") or d.get("marketValue") or 0),
            "today_pnl": float(d.get("today_pnl") or d.get("todayPnl") or 0),
            "today_pnl_pct": float(d.get("today_pnl_percent") or d.get("todayPnlPercent") or 0),
        })
    return {
        "total_unrealized": float(raw.get("total_unrealized") or 0),
        "total_realized": float(raw.get("total_realized") or 0),
        "details": details,
    }
