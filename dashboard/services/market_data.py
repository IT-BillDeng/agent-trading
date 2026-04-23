from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from system.engine.src.engine.adapters.market_data import TigerDataProvider, YFinanceDataProvider
from system.engine.src.engine.config import load_tiger_props

from .broker import resolve_broker_props_file


class QuoteProvider(Protocol):
    @property
    def name(self) -> str: ...

    def get_quote(self, symbols: list[str], market: str = "US") -> list[dict[str, Any]]: ...
    def get_market_status(self, market: str = "US") -> dict[str, Any]: ...


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


def _first_present(obj: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = obj.get(key)
        if value not in (None, ""):
            return value
    return default


def _as_items(data: Any) -> list[dict[str, Any]]:
    data = _decode_json_like(data)
    if data is None:
        return []
    if isinstance(data, dict):
        items = data.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
        return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _normalize_quotes(data: Any) -> list[dict[str, Any]]:
    items = _as_items(data)
    normalized: list[dict[str, Any]] = []
    for item in items:
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


def _normalize_market_status(data: Any, market: str) -> dict[str, Any]:
    items = _as_items(data)
    entry = items[0] if items else (data if isinstance(data, dict) else {})
    if isinstance(entry, dict):
        status = _first_present(entry, "marketStatus", "market_status", "status", default="unknown")
        return {"market": market, "status": str(status)}
    if entry is not None:
        return {"market": market, "status": str(entry)}
    return {"market": market, "status": "unknown"}


class _ProviderBridge:
    def __init__(self, provider: Any):
        self._provider = provider

    @property
    def name(self) -> str:
        return str(getattr(self._provider, "name", "unknown"))

    def get_quote(self, symbols: list[str], market: str = "US") -> list[dict[str, Any]]:
        return _normalize_quotes(_unwrap_response_data(self._provider.get_briefs(symbols, market=market)))

    def get_market_status(self, market: str = "US") -> dict[str, Any]:
        return _normalize_market_status(_unwrap_response_data(self._provider.get_market_state(market)), market)


class TigerQuoteProvider(_ProviderBridge):
    def __init__(self, config_dir: str | Path | None = None, props_dir: str | Path | None = None):
        props_file = resolve_broker_props_file(props_dir or config_dir)
        provider = TigerDataProvider(load_tiger_props(props_file))
        super().__init__(provider)


class YFinanceQuoteProvider(_ProviderBridge):
    def __init__(self, **_: Any):
        super().__init__(YFinanceDataProvider())


def get_quote_provider(provider: str = "yfinance", **kwargs: Any) -> QuoteProvider:
    if provider == "tiger":
        return TigerQuoteProvider(**kwargs)
    if provider == "yfinance":
        return YFinanceQuoteProvider(**kwargs)
    raise ValueError(f"Unknown quote provider: {provider}")

