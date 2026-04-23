"""Market-data adapter compatibility exports.

FF-01 keeps the existing provider implementations in place and exposes them
through a new canonical adapter namespace. Provider classes are loaded lazily
to avoid changing base import requirements during the skeleton phase.
"""

from ...data_provider import DataProvider, create_data_provider, fetch_bars_with_fallback

__all__ = [
    "DataProvider",
    "TigerDataProvider",
    "YFinanceDataProvider",
    "create_data_provider",
    "fetch_bars_with_fallback",
]


def __getattr__(name: str):
    if name == "TigerDataProvider":
        from ...tiger_data_provider import TigerDataProvider

        return TigerDataProvider
    if name == "YFinanceDataProvider":
        from ...yfinance_data_provider import YFinanceDataProvider

        return YFinanceDataProvider
    raise AttributeError(name)
