"""Yahoo Finance data provider — free alternative for Tiger API.

Wraps yfinance output into Tiger API-compatible response format.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import yfinance as yf

from .data_provider import DataProvider


# Symbol format conversion
def _to_yf_symbol(symbol: str, market: str = "US") -> str:
    """Convert Tiger symbol to yfinance format."""
    return symbol


def _from_yf_symbol(yf_symbol: str) -> str:
    """Convert yfinance symbol back to Tiger format."""
    return yf_symbol


# Interval mapping: Tiger period → yfinance interval
_INTERVAL_MAP = {
    "1min": "1m",
    "5min": "5m",
    "15min": "15m",
    "30min": "30m",
    "60min": "60m",
    "1day": "1d",
}


class YFinanceDataProvider(DataProvider):
    """Market data from Yahoo Finance."""

    def __init__(self, **kwargs):
        pass  # yfinance needs no config

    @property
    def name(self) -> str:
        return "yfinance"

    def get_bars(self, symbols: list[str], period: str = "30min", limit: int = 30) -> dict[str, Any]:
        """Fetch K-line data in Tiger API response format.

        Returns dict compatible with TigerClient.get_bars() response:
        {"body": {"code": 0, "data": [{"symbol": "AAPL", "items": [...]}]}}
        """
        interval = _INTERVAL_MAP.get(period, "30m")
        results = []

        for symbol in symbols:
            try:
                yf_sym = _to_yf_symbol(symbol, "US")

                ticker = yf.Ticker(yf_sym)
                hist = ticker.history(period="60d", interval=interval)

                if hist.empty:
                    continue

                # Take only the requested number of bars
                hist = hist.tail(limit)

                items = []
                for idx, row in hist.iterrows():
                    items.append({
                        "time": idx.strftime("%Y-%m-%d %H:%M:%S") if hasattr(idx, 'strftime') else str(idx),
                        "open": round(float(row.get("Open", 0)), 4),
                        "high": round(float(row.get("High", 0)), 4),
                        "low": round(float(row.get("Low", 0)), 4),
                        "close": round(float(row.get("Close", 0)), 4),
                        "volume": int(row.get("Volume", 0)),
                    })

                if items:
                    results.append({"symbol": symbol, "items": items})

            except Exception:
                continue

        return {
            "http_status": 200,
            "body": {"code": 0, "data": results},
        }

    def get_delay_quotes(self, symbols: list[str], market: str = "US") -> dict[str, Any]:
        """Fetch delayed quotes in Tiger API response format."""
        data_items = []

        for symbol in symbols:
            try:
                yf_sym = _to_yf_symbol(symbol, market)
                ticker = yf.Ticker(yf_sym)
                info = ticker.fast_info

                price = info.get("lastPrice") or info.get("last_price")
                prev = info.get("previousClose") or info.get("previous_close")

                if price is None:
                    continue

                item = {
                    "symbol": symbol,
                    "latestPrice": price,
                    "prevClose": prev,
                    "open": info.get("open") or info.get("openPrice"),
                    "high": info.get("dayHigh") or info.get("day_high"),
                    "low": info.get("dayLow") or info.get("day_low"),
                    "volume": info.get("lastVolume") or info.get("last_volume"),
                }

                if price and prev and prev != 0:
                    item["change"] = round(price - prev, 4)
                    item["changeRate"] = round((price - prev) / prev * 100, 4)

                data_items.append(item)

            except Exception:
                continue

        return {
            "http_status": 200,
            "body": {"code": 0, "data": {"items": data_items}},
        }

    def get_briefs(self, symbols: list[str], market: str = "US") -> dict[str, Any]:
        """Fetch quote briefs — same as delay_quotes for yfinance."""
        return self.get_delay_quotes(symbols, market)

    def get_market_state(self, market: str = "US") -> dict[str, Any]:
        """Get market status based on current time."""
        try:
            import pytz
            now_utc = datetime.now(timezone.utc)

            if market == "US":
                us_tz = pytz.timezone("America/New_York")
                now_local = now_utc.astimezone(us_tz)
                hour = now_local.hour + now_local.minute / 60
                weekday = now_local.weekday()
                # US regular session: Mon-Fri 9:30-16:00 ET
                if weekday < 5 and 9.5 <= hour < 16.0:
                    status, ms = "TRADING", "open"
                elif weekday < 5 and 4.0 <= hour < 9.5:
                    status, ms = "PRE_MARKET", "pre_market"
                elif weekday < 5 and 16.0 <= hour < 20.0:
                    status, ms = "AFTER_HOURS", "post_market"
                else:
                    status, ms = "CLOSED", "closed"
            else:
                status, ms = "UNKNOWN", "unknown"

            return {
                "http_status": 200,
                "body": {"code": 0, "data": [{"status": status, "marketStatus": ms}]},
            }

        except Exception:
            return {
                "http_status": 200,
                "body": {"code": 0, "data": [{"status": "UNKNOWN", "marketStatus": "unknown"}]},
            }

    def get_contract(self, symbol: str, market: str) -> dict[str, Any]:
        """Basic contract info from yfinance."""
        try:
            yf_sym = _to_yf_symbol(symbol, market)
            ticker = yf.Ticker(yf_sym)
            info = ticker.info or {}

            return {
                "http_status": 200,
                "body": {
                    "code": 0,
                    "data": {
                        "symbol": symbol,
                        "name": info.get("shortName", symbol),
                        "currency": "USD",
                        "lotSize": 1,
                        "market": market,
                        "secType": "STK",
                    },
                },
            }
        except Exception:
            return {
                "http_status": 200,
                "body": {
                    "code": 0,
                    "data": {
                        "symbol": symbol,
                        "name": symbol,
                        "currency": "USD",
                        "lotSize": 1,
                        "market": market,
                        "secType": "STK",
                    },
                },
            }
