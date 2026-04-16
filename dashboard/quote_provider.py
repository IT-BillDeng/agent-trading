"""Quote provider abstraction — pluggable data source for market quotes."""

from abc import ABC, abstractmethod


class QuoteProvider(ABC):
    """Abstract base for quote data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g. current broker platform, 'yfinance')."""

    @abstractmethod
    def get_quote(self, symbols: list[str], market: str = "US") -> list[dict]:
        """Fetch quotes for given symbols.

        Returns list of dicts with keys:
            symbol, name, latest_price, prev_close, open, high, low,
            volume, change, change_rate, bid_price, ask_price, market_status
        """

    @abstractmethod
    def get_market_status(self, market: str = "US") -> dict:
        """Get market open/close status."""


def get_quote_provider(provider: str = "yfinance", **kwargs) -> QuoteProvider:
    """Factory: create a quote provider by name.

    Args:
        provider: current broker platform | 'yfinance'
        kwargs: passed to provider constructor
    """
    if provider == "tiger":
        from .tiger_quote_provider import TigerQuoteProvider
        return TigerQuoteProvider(**kwargs)
    elif provider == "yfinance":
        from .yfinance_provider import YFinanceQuoteProvider
        return YFinanceQuoteProvider(**kwargs)
    else:
        raise ValueError(f"Unknown quote provider: {provider}")
