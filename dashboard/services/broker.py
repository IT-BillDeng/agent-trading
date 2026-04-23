from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from system.engine.src.engine.adapters.broker import TigerClient as EngineTigerClient
from system.engine.src.engine.config import load_tiger_props


ET_ZONE = ZoneInfo("America/New_York")
DEFAULT_PROPERTIES_BASENAME = "tiger_openapi_config.properties"


class BrokerClient(Protocol):
    """Dashboard-facing broker client contract."""

    @property
    def account(self) -> str: ...

    def get_account_type(self) -> dict[str, Any]: ...
    def get_account_info(self) -> dict[str, Any]: ...
    def get_positions(self) -> list[dict[str, Any]]: ...
    def get_orders(self) -> list[dict[str, Any]]: ...
    def get_orders_history(self, start_time: Any, end_time: Any, market: str = "US", limit: int = 300) -> list[dict[str, Any]]: ...
    def get_filled_orders(self) -> list[dict[str, Any]]: ...
    def get_today_transactions(self) -> list[dict[str, Any]]: ...
    def get_quote(self, symbols: list[str], market: str = "US") -> list[dict[str, Any]]: ...
    def get_market_status(self, market: str = "US") -> dict[str, Any]: ...


def resolve_broker_props_file(config_dir: str | Path | None) -> Path:
    if config_dir is None:
        path = Path(__file__).resolve().parents[2] / "properties"
    else:
        path = Path(config_dir)
    if path.is_dir() or path.suffix != ".properties":
        return path / DEFAULT_PROPERTIES_BASENAME
    return path


def _decode_json_like(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _unwrap_response_data(resp: Any) -> Any:
    if not isinstance(resp, dict):
        return None
    body = resp.get("body", {})
    if isinstance(body, dict):
        return _decode_json_like(body.get("data"))
    return None


def _obj_get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _first_present(obj: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = _obj_get(obj, key, None)
        if value not in (None, ""):
            return value
    return default


def _as_list(value: Any) -> list[Any]:
    value = _decode_json_like(value)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "result", "results", "records", "orders", "transactions", "positions", "accounts"):
            candidate = value.get(key)
            if isinstance(candidate, list):
                return candidate
        return [value]
    return [value]


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except Exception:
        return default


def _normalize_timestamp(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 1_000_000_000_000:
            timestamp /= 1000.0
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    return str(value)


def _normalize_market_status(data: Any, market: str) -> dict[str, Any]:
    entries = _as_list(data)
    entry = entries[0] if entries else data
    if isinstance(entry, dict):
        status = _first_present(entry, "marketStatus", "market_status", "status", default="unknown")
        return {"market": market, "status": str(status)}
    if entry is not None:
        return {"market": market, "status": str(entry)}
    return {"market": market, "status": "unknown"}


def _normalize_quote_items(data: Any) -> list[dict[str, Any]]:
    items = _as_list(data)
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "symbol": _first_present(item, "symbol"),
                "name": _first_present(item, "name"),
                "latest_price": _first_present(item, "latestPrice", "latest_price", "lastPrice", "last_price"),
                "prev_close": _first_present(item, "prevClose", "prev_close", "previousClose", "previous_close"),
                "open": _first_present(item, "open", "openPrice"),
                "high": _first_present(item, "high", "dayHigh", "day_high"),
                "low": _first_present(item, "low", "dayLow", "day_low"),
                "volume": _first_present(item, "volume", "lastVolume", "last_volume"),
                "change": _first_present(item, "change"),
                "change_rate": _first_present(item, "changeRate", "change_rate"),
                "bid_price": _first_present(item, "bidPrice", "bid_price"),
                "ask_price": _first_present(item, "askPrice", "ask_price"),
                "market_status": _first_present(item, "marketStatus", "market_status", "status"),
            }
        )
    return normalized


def _normalize_positions(data: Any) -> list[dict[str, Any]]:
    positions = []
    for item in _as_list(data):
        if not isinstance(item, dict):
            continue
        positions.append(
            {
                "symbol": _first_present(item, "symbol"),
                "name": _first_present(item, "name"),
                "quantity": _safe_float(_first_present(item, "quantity", "position", "qty"), 0) or 0,
                "average_cost": _safe_float(_first_present(item, "averageCost", "average_cost", "avgCost", "avg_cost"), 0) or 0,
                "market_price": _safe_float(_first_present(item, "marketPrice", "market_price", "latestPrice", "latest_price"), 0) or 0,
                "market_value": _safe_float(_first_present(item, "marketValue", "market_value"), 0) or 0,
                "unrealized_pnl": _safe_float(_first_present(item, "unrealizedPnL", "unrealized_pnl", "unrealizedPL"), 0) or 0,
                "realized_pnl": _safe_float(_first_present(item, "realizedPnL", "realized_pnl", "realizedPL"), 0) or 0,
                "today_pnl": _safe_float(_first_present(item, "todayPnL", "today_pnl", "totalTodayPL"), 0) or 0,
                "today_pnl_percent": _safe_float(_first_present(item, "todayPnLPercent", "today_pnl_percent"), 0) or 0,
                "last_close_price": _safe_float(_first_present(item, "lastClosePrice", "last_close_price")),
                "currency": _first_present(item, "currency", default="USD"),
            }
        )
    return positions


def _normalize_order(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    return {
        "id": _first_present(item, "id", "orderId", "order_id"),
        "order_id": _first_present(item, "orderId", "order_id", "id"),
        "symbol": _first_present(item, "symbol"),
        "name": _first_present(item, "name"),
        "action": str(_first_present(item, "action", default="") or ""),
        "quantity": _safe_float(_first_present(item, "quantity", "qty"), 0) or 0,
        "filled_quantity": _safe_float(_first_present(item, "filledQuantity", "filled_quantity", "filled"), 0) or 0,
        "order_type": str(_first_present(item, "orderType", "order_type", default="") or ""),
        "limit_price": _safe_float(_first_present(item, "limitPrice", "limit_price")),
        "avg_fill_price": _safe_float(_first_present(item, "avgFillPrice", "avg_fill_price")),
        "filled_cash_amount": _safe_float(_first_present(item, "filledCashAmount", "filled_cash_amount")),
        "total_cash_amount": _safe_float(_first_present(item, "totalCashAmount", "total_cash_amount")),
        "status": str(_first_present(item, "status", default="") or ""),
        "realized_pnl": _safe_float(_first_present(item, "realizedPnL", "realized_pnl"), 0) or 0,
        "submitted_at": _normalize_timestamp(_first_present(item, "submittedAt", "submitted_at", "orderTime", "order_time")),
        "order_time": _normalize_timestamp(_first_present(item, "orderTime", "order_time")),
    }


def _normalize_transaction(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    return {
        "id": _first_present(item, "id"),
        "order_id": _first_present(item, "orderId", "order_id"),
        "symbol": _first_present(item, "symbol"),
        "name": _first_present(item, "name"),
        "action": str(_first_present(item, "action", default="") or ""),
        "filled_quantity": _safe_float(_first_present(item, "filledQuantity", "filled_quantity"), 0) or 0,
        "filled_price": _safe_float(_first_present(item, "filledPrice", "filled_price")),
        "filled_amount": _safe_float(_first_present(item, "filledAmount", "filled_amount")),
        "transacted_at": _normalize_timestamp(_first_present(item, "transactedAt", "transacted_at", "orderTime", "order_time")),
    }


def _filter_orders_by_window(orders: list[dict[str, Any]], start_time: Any, end_time: Any) -> list[dict[str, Any]]:
    start_ms = _safe_int(start_time, 0)
    end_ms = _safe_int(end_time, 0)
    if not start_ms or not end_ms:
        return orders

    filtered: list[dict[str, Any]] = []
    for order in orders:
        timestamp = order.get("order_time") or order.get("submitted_at")
        if not timestamp:
            filtered.append(order)
            continue
        try:
            dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except Exception:
            filtered.append(order)
            continue
        ts_ms = int(dt.astimezone(timezone.utc).timestamp() * 1000)
        if start_ms <= ts_ms <= end_ms:
            filtered.append(order)
    return filtered


class TigerClient:
    """Dashboard compatibility adapter backed by engine broker adapters."""

    def __init__(self, config_dir: str | Path | None = None):
        props_file = resolve_broker_props_file(config_dir)
        props = load_tiger_props(props_file)
        self._client = EngineTigerClient(props)
        self._props = props

    @property
    def account(self) -> str:
        return self._props.account

    def get_account_type(self) -> dict[str, Any]:
        try:
            data = _unwrap_response_data(self._client.get_accounts())
            items = _as_list(data)
            target = None
            for item in items:
                if not isinstance(item, dict):
                    continue
                if str(_first_present(item, "account", "accountId", default="")) == str(self.account):
                    target = item
                    break
            target = target or (items[0] if items and isinstance(items[0], dict) else {})
            return {
                "account": _first_present(target, "account", "accountId", default=self.account),
                "account_type": _first_present(target, "accountType", "account_type", default="unknown"),
                "capability": _first_present(target, "capability", default=""),
                "status": _first_present(target, "status", default=""),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_account_info(self) -> dict[str, Any]:
        try:
            data = _unwrap_response_data(self._client.get_assets())
            payload = data if isinstance(data, dict) else {}
            segments = _first_present(payload, "segments", "_segments", default={}) or {}
            seg_s = segments.get("S") if isinstance(segments, dict) else None
            source = seg_s if isinstance(seg_s, dict) else payload
            return {
                "account": _first_present(payload, "account", default=self.account),
                "net_liquidation": _safe_float(_first_present(source, "netLiquidation", "net_liquidation"), 0) or 0,
                "cash": _safe_float(_first_present(source, "cashBalance", "cash_balance", "cash"), 0) or 0,
                "buying_power": _safe_float(_first_present(source, "buyingPower", "buying_power"), 0) or 0,
                "unrealized_pnl": _safe_float(_first_present(source, "unrealizedPL", "unrealized_pnl", "unrealizedPnL"), 0) or 0,
                "realized_pnl": _safe_float(_first_present(source, "realizedPL", "realized_pnl", "realizedPnL"), 0) or 0,
                "total_today_pnl": _safe_float(_first_present(source, "totalTodayPL", "total_today_pnl", "todayPnL"), 0) or 0,
                "currency": _first_present(source, "currency", default="USD"),
                "available_funds": _safe_float(_first_present(source, "cashAvailableForTrade", "cash_available_for_trade"), 0) or 0,
                "gross_position_value": _safe_float(_first_present(source, "grossPositionValue", "gross_position_value"), 0) or 0,
                "equity_with_loan": _safe_float(_first_present(source, "equityWithLoan", "equity_with_loan"), 0) or 0,
                "excess_liquidity": _safe_float(_first_present(source, "excessLiquidation", "excess_liquidity"), 0) or 0,
            }
        except Exception as e:
            return {"error": str(e)}

    def get_positions(self) -> list[dict[str, Any]]:
        try:
            return _normalize_positions(_unwrap_response_data(self._client.get_positions()))
        except Exception as e:
            return [{"error": str(e)}]

    def get_orders(self) -> list[dict[str, Any]]:
        try:
            return [_normalize_order(item) for item in _as_list(_unwrap_response_data(self._client.get_active_orders()))]
        except Exception as e:
            return [{"error": str(e)}]

    def get_orders_history(self, start_time: Any, end_time: Any, market: str = "US", limit: int = 300) -> list[dict[str, Any]]:
        try:
            orders = [_normalize_order(item) for item in _as_list(_unwrap_response_data(self._client.get_inactive_orders(limit=limit)))]
            filled = [_normalize_order(item) for item in _as_list(_unwrap_response_data(self._client.get_filled_orders(limit=limit)))]
            merged: list[dict[str, Any]] = []
            seen: set[str] = set()
            for order in orders + filled:
                key = str(order.get("id") or order.get("order_id") or "")
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                merged.append(order)
            return _filter_orders_by_window(merged, start_time, end_time)
        except Exception as e:
            return [{"error": str(e)}]

    def get_filled_orders(self) -> list[dict[str, Any]]:
        try:
            return [_normalize_order(item) for item in _as_list(_unwrap_response_data(self._client.get_filled_orders(limit=200)))]
        except Exception as e:
            return [{"error": str(e)}]

    def get_today_transactions(self) -> list[dict[str, Any]]:
        try:
            return [_normalize_transaction(item) for item in _as_list(_unwrap_response_data(self._client.get_transactions(limit=200)))]
        except Exception as e:
            return [{"error": str(e)}]

    def get_quote(self, symbols: list[str], market: str = "US") -> list[dict[str, Any]]:
        try:
            return _normalize_quote_items(_unwrap_response_data(self._client.get_briefs(symbols, market=market)))
        except Exception as e:
            return [{"error": str(e)}]

    def get_market_status(self, market: str = "US") -> dict[str, Any]:
        try:
            return _normalize_market_status(_unwrap_response_data(self._client.get_market_state(market)), market)
        except Exception as e:
            return {"market": market, "error": str(e)}


def create_broker_client(config_dir: str | Path | None = None) -> TigerClient:
    return TigerClient(config_dir=config_dir)

