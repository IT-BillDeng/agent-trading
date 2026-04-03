"""Yahoo Finance quote provider — free, no API key required."""

import yfinance as yf
from .quote_provider import QuoteProvider


# HK symbols: Tiger uses "01810", yfinance uses "1810.HK"
def _to_yf_symbol(symbol: str, market: str) -> str:
    """Convert symbol to yfinance format."""
    if market == "HK":
        # "01810" → "1810.HK"
        return f"{symbol.lstrip('0')}.HK"
    return symbol  # US symbols unchanged


class YFinanceQuoteProvider(QuoteProvider):
    """Quote data from Yahoo Finance (yfinance)."""

    def __init__(self, **kwargs):
        pass  # yfinance needs no config

    @property
    def name(self) -> str:
        return "yfinance"

    def get_quote(self, symbols: list[str], market: str = "US") -> list[dict]:
        if not symbols:
            return []

        yf_symbols = [_to_yf_symbol(s, market) for s in symbols]
        # Reverse map: yf_symbol → original symbol
        sym_map = dict(zip(yf_symbols, symbols))

        try:
            tickers = yf.Tickers(" ".join(yf_symbols))
            quotes = []

            for yf_sym, orig_sym in sym_map.items():
                try:
                    t = tickers.tickers.get(yf_sym)
                    if t is None:
                        continue

                    info = t.fast_info
                    price = info.get("lastPrice") or info.get("last_price")
                    prev = info.get("previousClose") or info.get("previous_close")

                    change = None
                    change_rate = None
                    if price is not None and prev is not None and prev != 0:
                        change = round(price - prev, 4)
                        change_rate = round((price - prev) / prev * 100, 4)

                    quotes.append({
                        "symbol": orig_sym,
                        "name": info.get("shortName") or info.get("short_name") or orig_sym,
                        "latest_price": price,
                        "prev_close": prev,
                        "open": info.get("open") or info.get("openPrice"),
                        "high": info.get("dayHigh") or info.get("day_high"),
                        "low": info.get("dayLow") or info.get("day_low"),
                        "volume": info.get("lastVolume") or info.get("last_volume"),
                        "change": change,
                        "change_rate": change_rate,
                        "bid_price": info.get("bid"),
                        "ask_price": info.get("ask"),
                        "market_status": "regular",
                    })
                except Exception:
                    continue

            return quotes

        except Exception as e:
            return [{"error": str(e)}]

    def get_market_status(self, market: str = "US") -> dict:
        """Approximate market status from recent quote data."""
        try:
            spy = yf.Ticker("SPY" if market == "US" else "^HSI")
            hist = spy.history(period="1d")
            if hist.empty:
                return {"market": market, "status": "closed"}
            return {"market": market, "status": "open"}
        except Exception as e:
            return {"market": market, "status": "unknown", "error": str(e)}
