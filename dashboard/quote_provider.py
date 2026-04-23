"""Compatibility export for dashboard quote provider factory."""

from .services.market_data import (
    QuoteProvider,
    TigerQuoteProvider,
    YFinanceQuoteProvider,
    get_quote_provider,
)

__all__ = [
    "QuoteProvider",
    "TigerQuoteProvider",
    "YFinanceQuoteProvider",
    "get_quote_provider",
]
