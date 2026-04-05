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

                    fast = t.fast_info
                    info = {}
                    try:
                        info = t.info or {}
                    except Exception:
                        pass

                    price = fast.get("lastPrice") or fast.get("last_price") or info.get("regularMarketPrice")
                    name = info.get("shortName") or info.get("longName") or fast.get("shortName") or orig_sym

                    # Get previous close: try info first, then history
                    prev = info.get("regularMarketPreviousClose") or fast.get("previousClose") or fast.get("previous_close")
                    hist_prev = None
                    try:
                        hist = t.history(period="5d")
                        if hist is not None and len(hist) >= 2:
                            hist_prev = round(float(hist["Close"].iloc[-2]), 4)
                    except Exception:
                        pass

                    if hist_prev is not None and hist_prev > 0:
                        prev = hist_prev

                    # Calculate change
                    change = None
                    change_rate = None
                    if price is not None and prev is not None and prev > 0:
                        change = round(price - prev, 4)
                        change_rate = round(change / prev, 4)  # ratio, e.g. 0.011 = 1.1%

                    # Sanity: daily change within ±30%
                    if change_rate is not None and abs(change_rate) > 0.3:
                        change = None
                        change_rate = None

                    # Get market time from data source
                    market_time = info.get("regularMarketTime") or info.get("regularMarketTimestamp")
                    if market_time and isinstance(market_time, (int, float)):
                        market_time = int(market_time)
                    else:
                        market_time = None

                    quotes.append({
                        "symbol": orig_sym,
                        "name": name,
                        "latest_price": price,
                        "prev_close": prev,
                        "open": info.get("open") or info.get("regularMarketOpen") or fast.get("open"),
                        "high": info.get("dayHigh") or info.get("regularMarketDayHigh") or fast.get("dayHigh"),
                        "low": info.get("dayLow") or info.get("regularMarketDayLow") or fast.get("dayLow"),
                        "volume": info.get("regularMarketVolume") or fast.get("lastVolume"),
                        "change": change,
                        "change_rate": change_rate,
                        "bid_price": info.get("bid"),
                        "ask_price": info.get("ask"),
                        "market_status": "regular",
                        "market_time": market_time,
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
