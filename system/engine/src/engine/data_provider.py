"""Pluggable market data provider abstraction.

Supports switching between the current default API and alternative sources
(e.g., yfinance) for market data like K-lines, quotes, and market state.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any


class DataProvider(ABC):
    """Abstract base for market data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""

    @abstractmethod
    def get_bars(self, symbols: list[str], period: str = "30min", limit: int = 30) -> dict[str, Any]:
        """Fetch K-line/bar data. Returns API-compatible response dict."""

    @abstractmethod
    def get_delay_quotes(self, symbols: list[str], market: str = "US") -> dict[str, Any]:
        """Fetch delayed quotes."""

    @abstractmethod
    def get_briefs(self, symbols: list[str], market: str = "US") -> dict[str, Any]:
        """Fetch quote briefs."""

    @abstractmethod
    def get_market_state(self, market: str = "US") -> dict[str, Any]:
        """Get market open/close status."""

    @abstractmethod
    def get_contract(self, symbol: str, market: str) -> dict[str, Any]:
        """Get contract details."""


def _provider_name(provider: Any, default: str = "unknown") -> str:
    name = getattr(provider, "name", None)
    if callable(name):
        try:
            value = name()
        except TypeError:
            value = name
    else:
        value = name
    return str(value or default)


def _unwrap_data(resp: dict[str, Any] | None) -> Any:
    body = (resp or {}).get("body", {})
    data = body.get("data")
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return data
    return data


def _response_ok(resp: dict[str, Any] | None) -> bool:
    if not isinstance(resp, dict):
        return False
    body = resp.get("body", {})
    return resp.get("http_status", 500) < 400 and body.get("code") == 0


def _extract_bars_entry_map(resp: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    data = _unwrap_data(resp) or []
    if not isinstance(data, list):
        return {}
    return {
        str(entry.get("symbol")): entry
        for entry in data
        if isinstance(entry, dict) and entry.get("symbol")
    }


def _evaluate_symbol_bars(resp: dict[str, Any] | None, entry: dict[str, Any] | None) -> dict[str, Any]:
    if not _response_ok(resp):
        return {
            "ok": False,
            "status": "error",
            "reason": "provider_error",
            "bars_count": 0,
            "entry": entry,
        }

    if entry is None:
        return {
            "ok": False,
            "status": "empty",
            "reason": "bars_empty",
            "bars_count": 0,
            "entry": None,
        }

    items = entry.get("items")
    if not isinstance(items, list):
        return {
            "ok": False,
            "status": "malformed",
            "reason": "bars_normalization_failed",
            "bars_count": 0,
            "entry": entry,
        }

    if not items:
        return {
            "ok": False,
            "status": "empty",
            "reason": "bars_empty",
            "bars_count": 0,
            "entry": entry,
        }

    return {
        "ok": True,
        "status": "ok",
        "reason": None,
        "bars_count": len(items),
        "entry": {"symbol": entry.get("symbol"), "items": list(items)},
    }


def _merge_failure_reason(primary_reason: str | None, fallback_reason: str | None) -> str:
    for reason in (fallback_reason, primary_reason):
        if reason in {"provider_error", "bars_normalization_failed"}:
            return reason
    return fallback_reason or primary_reason or "bars_empty"


def fetch_bars_with_fallback(
    primary_provider: Any,
    symbols: list[str],
    *,
    period: str = "30min",
    limit: int = 30,
    fallback_provider: Any | None = None,
    primary_name: str | None = None,
    fallback_name: str | None = None,
    fail_on_empty_bars: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch bars with per-symbol health metadata and optional provider fallback."""

    primary_name = primary_name or _provider_name(primary_provider)
    fallback_name = fallback_name or (
        _provider_name(fallback_provider) if fallback_provider is not None else None
    )

    primary_resp = primary_provider.get_bars(symbols, period=period, limit=limit)
    primary_entries = _extract_bars_entry_map(primary_resp)

    final_entries: list[dict[str, Any]] = []
    final_meta: dict[str, dict[str, Any]] = {}
    unresolved_symbols: list[str] = []

    for symbol in symbols:
        primary_eval = _evaluate_symbol_bars(primary_resp, primary_entries.get(symbol))
        if primary_eval["ok"]:
            final_entries.append(primary_eval["entry"])
            final_meta[symbol] = {
                "provider": primary_name,
                "provider_path": primary_name,
                "status": "primary_ok",
                "reason": None,
                "bars_count": primary_eval["bars_count"],
                "fallback_used": False,
                "primary_status": primary_eval["status"],
                "primary_reason": primary_eval["reason"],
                "fallback_status": None,
                "fallback_reason": None,
            }
        else:
            unresolved_symbols.append(symbol)
            final_meta[symbol] = {
                "provider": primary_name,
                "provider_path": primary_name,
                "status": "failed",
                "reason": primary_eval["reason"],
                "bars_count": 0,
                "fallback_used": False,
                "primary_status": primary_eval["status"],
                "primary_reason": primary_eval["reason"],
                "fallback_status": None,
                "fallback_reason": None,
            }

    fallback_resp: dict[str, Any] | None = None
    fallback_entries: dict[str, dict[str, Any]] = {}
    if unresolved_symbols and fallback_provider is not None and fallback_name and fallback_name != primary_name:
        fallback_resp = fallback_provider.get_bars(unresolved_symbols, period=period, limit=limit)
        fallback_entries = _extract_bars_entry_map(fallback_resp)

    failed_symbols: list[str] = []
    for symbol in unresolved_symbols:
        primary_reason = final_meta[symbol]["primary_reason"]
        fallback_eval = (
            _evaluate_symbol_bars(fallback_resp, fallback_entries.get(symbol))
            if fallback_resp is not None
            else {
                "ok": False,
                "status": "unavailable",
                "reason": None,
                "bars_count": 0,
                "entry": None,
            }
        )

        if fallback_eval["ok"]:
            final_entries.append(fallback_eval["entry"])
            final_meta[symbol].update(
                {
                    "provider": fallback_name,
                    "provider_path": f"{primary_name}->{fallback_name}",
                    "status": "fallback_ok",
                    "reason": None,
                    "bars_count": fallback_eval["bars_count"],
                    "fallback_used": True,
                    "fallback_status": fallback_eval["status"],
                    "fallback_reason": fallback_eval["reason"],
                }
            )
            continue

        failed_symbols.append(symbol)
        final_meta[symbol].update(
            {
                "provider": fallback_name or primary_name,
                "provider_path": f"{primary_name}->{fallback_name}" if fallback_name else primary_name,
                "status": "failed",
                "reason": _merge_failure_reason(primary_reason, fallback_eval["reason"]),
                "fallback_used": fallback_resp is not None,
                "fallback_status": fallback_eval["status"],
                "fallback_reason": fallback_eval["reason"],
            }
        )

    body: dict[str, Any] = {"code": 0, "data": final_entries}
    http_status = 200
    if fail_on_empty_bars and failed_symbols:
        body["code"] = 1
        body["message"] = f"bars_unavailable:{','.join(failed_symbols)}"
        http_status = 424

    return (
        {
            "http_status": http_status,
            "body": body,
        },
        {
            "primary": primary_name,
            "fallback": fallback_name,
            "failed_symbols": failed_symbols,
            "symbols": final_meta,
        },
    )


def create_data_provider(provider: str = "tiger", **kwargs) -> DataProvider:
    """Factory: create data provider by name.

    Args:
        provider: current broker platform | 'yfinance'
        kwargs: passed to provider constructor
    """
    if provider == "tiger":
        from .tiger_data_provider import TigerDataProvider
        return TigerDataProvider(**kwargs)
    elif provider == "yfinance":
        from .yfinance_data_provider import YFinanceDataProvider
        return YFinanceDataProvider(**kwargs)
    else:
        raise ValueError(f"Unknown data provider: {provider}")
