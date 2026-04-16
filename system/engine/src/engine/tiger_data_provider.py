"""Broker data provider — wraps the current default broker client into DataProvider interface."""

from __future__ import annotations

from typing import Any

from .config import TigerProps
from .data_provider import DataProvider
from .tiger_client import TigerClient


class TigerDataProvider(DataProvider):
    """Market data from the configured broker API."""

    def __init__(self, props: TigerProps):
        self._client = TigerClient(props)

    @property
    def name(self) -> str:
        return "tiger"

    def get_bars(self, symbols: list[str], period: str = "30min", limit: int = 30) -> dict[str, Any]:
        return self._client.get_bars(symbols, period=period, limit=limit)

    def get_delay_quotes(self, symbols: list[str], market: str = "US") -> dict[str, Any]:
        return self._client.get_delay_quotes(symbols, market=market)

    def get_briefs(self, symbols: list[str], market: str = "US") -> dict[str, Any]:
        return self._client.get_briefs(symbols, market=market)

    def get_market_state(self, market: str = "US") -> dict[str, Any]:
        return self._client.get_market_state(market)

    def get_contract(self, symbol: str, market: str) -> dict[str, Any]:
        return self._client.get_contract(symbol, market)
