"""Pluggable market data provider abstraction.

Supports switching between the current default API and alternative sources
(e.g., yfinance) for market data like K-lines, quotes, and market state.
"""

from __future__ import annotations

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
