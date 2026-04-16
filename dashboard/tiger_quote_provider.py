"""Default API quote provider — requires market quote permissions."""

from tigeropen.quote.quote_client import QuoteClient
from tigeropen.tiger_open_config import TigerOpenClientConfig
from tigeropen.common.consts import Language, Market

from .quote_provider import QuoteProvider


class TigerQuoteProvider(QuoteProvider):
    """Quote data from the current default API."""

    def __init__(self, config_dir: str):
        self._client_config = TigerOpenClientConfig(props_path=config_dir)
        self._client_config.language = Language.zh_CN
        self._quote_client = QuoteClient(self._client_config)

    @property
    def name(self) -> str:
        return "tiger"

    def get_quote(self, symbols: list[str], market: str = "US") -> list[dict]:
        try:
            result = self._quote_client.get_stock_briefs(symbols)
            if result is None or (hasattr(result, 'empty') and result.empty):
                return []
            quotes = []
            for _, row in result.iterrows():
                def val(col, default=None):
                    v = row.get(col, default)
                    if v is None or (isinstance(v, float) and v != v):
                        return default
                    return v
                quotes.append({
                    "symbol": val('symbol'),
                    "name": val('name'),
                    "latest_price": val('latest_price') or val('last_price'),
                    "prev_close": val('prev_close'),
                    "open": val('open'),
                    "high": val('high'),
                    "low": val('low'),
                    "volume": val('volume'),
                    "change": val('change'),
                    "change_rate": val('change_rate'),
                    "bid_price": val('bid_price'),
                    "ask_price": val('ask_price'),
                    "market_status": val('market_status'),
                })
            return quotes
        except Exception as e:
            return [{"error": str(e)}]

    def get_market_status(self, market: str = "US") -> dict:
        try:
            market_enum = Market.US
            result = self._quote_client.get_market_status(market=market_enum)
            return {"market": market, "status": str(result)}
        except Exception as e:
            return {"market": market, "error": str(e)}
