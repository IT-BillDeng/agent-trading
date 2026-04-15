"""Tiger (老虎证券) data normalizer."""
from __future__ import annotations
from typing import Any
from . import register


class TigerNormalizer:

    def account(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "total_assets": raw.get("net_liquidation") or raw.get("netLiquidation") or 0,
            "cash_balance": raw.get("cash") or raw.get("cashValue") or 0,
            "buying_power": raw.get("buying_power") or raw.get("buyingPower") or 0,
            "position_value": raw.get("gross_position_value") or raw.get("grossPositionValue") or 0,
            "unrealized_pnl": raw.get("unrealized_pnl") or raw.get("unrealizedPnl") or 0,
            "realized_pnl": raw.get("realized_pnl") or raw.get("realizedPnl") or 0,
            "total_today_pnl": raw.get("total_today_pnl") or raw.get("totalTodayPnl") or 0,
            "available_funds": raw.get("available_funds") or raw.get("availableFunds") or 0,
            "currency": raw.get("currency") or "USD",
        }

    def position(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "symbol": raw.get("symbol") or "",
            "name": raw.get("name") or "",
            "quantity": int(raw.get("quantity") or raw.get("position") or 0),
            "avg_cost": float(raw.get("average_cost") or raw.get("averageCost") or 0),
            "market_price": float(raw.get("latest_price") or raw.get("latestPrice") or 0),
            "market_value": float(raw.get("market_value") or raw.get("marketValue") or 0),
            "unrealized_pnl": float(raw.get("unrealized_pnl") or raw.get("unrealizedPnl") or 0),
            "today_pnl": float(raw.get("today_pnl") or raw.get("todayPnl") or 0),
            "today_pnl_pct": float(raw.get("today_pnl_pct") or raw.get("today_pnl_percent") or raw.get("todayPnlPercent") or 0),
            "last_close": float(raw.get("last_close") or raw.get("last_close_price") or raw.get("lastClosePrice") or 0),
            "currency": raw.get("currency") or "USD",
        }

    def positions(self, raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.position(p) for p in raw_list if isinstance(p, dict)]

    def order(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": raw.get("id") or raw.get("order_id") or "",
            "symbol": raw.get("symbol") or "",
            "name": raw.get("name") or "",
            "side": str(raw.get("action") or raw.get("side") or "").upper(),
            "quantity": int(raw.get("quantity") or 0),
            "filled_qty": int(raw.get("filled_quantity") or raw.get("filledQuantity") or 0),
            "order_type": str(raw.get("order_type") or raw.get("orderType") or ""),
            "limit_price": raw.get("limit_price") or raw.get("limitPrice"),
            "stop_price": raw.get("aux_price") or raw.get("auxPrice") or raw.get("stop_price"),
            "status": str(raw.get("status") or ""),
            "submitted_at": str(raw.get("submitted_at") or raw.get("submittedAt") or ""),
        }

    def orders(self, raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.order(o) for o in raw_list if isinstance(o, dict)]

    def quote(self, raw: dict[str, Any]) -> dict[str, Any]:
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

    def quotes(self, raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.quote(q) for q in raw_list if isinstance(q, dict)]

    def pnl(self, raw: dict[str, Any]) -> dict[str, Any]:
        details = []
        for d in raw.get("details", []):
            if not isinstance(d, dict):
                continue
            details.append({
                "symbol": d.get("symbol") or "",
                "name": d.get("name") or "",
                "status": d.get("status") or "open",
                "unrealized_pnl": float(d.get("unrealized_pnl") or 0),
                "realized_pnl": float(d.get("realized_pnl") or 0),
                "market_value": float(d.get("market_value") or 0),
                "today_pnl": float(d.get("today_pnl") or 0),
                "today_pnl_pct": float(d.get("today_pnl_pct") or 0),
            })
        return {
            "total_today": float(raw.get("total_today") or 0),
            "today_realized": float(raw.get("today_realized") or 0),
            "today_unrealized": float(raw.get("today_unrealized") or 0),
            "total_unrealized": float(raw.get("total_unrealized") or 0),
            "total_realized": float(raw.get("total_realized") or 0),
            "details": details,
        }


# Register on import
register("tiger", TigerNormalizer)
