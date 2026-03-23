"""Tiger API client wrapper for dashboard."""

import os
import json
from pathlib import Path

from tigeropen.tiger_open_client import TigerOpenClient
from tigeropen.tiger_open_config import TigerOpenClientConfig
from tigeropen.quote.quote_client import QuoteClient
from tigeropen.trade.trade_client import TradeClient
from tigeropen.common.consts import Language, Market

CONFIG_DIR = str(Path(__file__).parent.parent / "config")


class TigerClient:
    """Unified Tiger API client for dashboard data."""

    def __init__(self, config_dir: str | None = None):
        self._config_dir = config_dir or CONFIG_DIR
        self._client_config = TigerOpenClientConfig(props_path=self._config_dir)
        self._client_config.language = Language.zh_CN
        self._quote_client = QuoteClient(self._client_config)
        self._trade_client = TradeClient(self._client_config)

    @property
    def account(self) -> str:
        return self._client_config.account

    def get_account_info(self) -> dict:
        """Get account assets and buying power."""
        try:
            result = self._trade_client.get_assets()
            if not result:
                return {}
            # get_assets() returns list of PortfolioAccount
            if isinstance(result, list) and len(result) > 0:
                pa = result[0]
            else:
                pa = result

            # Extract from PortfolioAccount.summary (Account object)
            summary = getattr(pa, 'summary', None)
            if not summary:
                return {"raw": str(pa)}

            def safe_val(obj, attr, default=None):
                v = getattr(obj, attr, default)
                if v is None:
                    return default
                try:
                    if v != v:  # NaN check
                        return default
                    if str(v).lower() == 'inf':
                        return default
                except:
                    pass
                return v

            return {
                "account": safe_val(pa, 'account', self.account),
                "net_liquidation": safe_val(summary, 'net_liquidation', 0),
                "cash": safe_val(summary, 'cash', 0),
                "buying_power": safe_val(summary, 'buying_power', 0),
                "unrealized_pnl": safe_val(summary, 'unrealized_pnl', 0),
                "realized_pnl": safe_val(summary, 'realized_pnl', 0),
                "currency": safe_val(summary, 'currency', 'USD'),
                "available_funds": safe_val(summary, 'available_funds', 0),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_positions(self) -> list:
        """Get current positions."""
        try:
            result = self._trade_client.get_positions()
            if not result:
                return []
            positions = []
            for pos in result:
                positions.append({
                    "symbol": getattr(pos, 'contract', None) and getattr(pos.contract, 'symbol', None) or getattr(pos, 'symbol', None),
                    "name": getattr(pos, 'contract', None) and getattr(pos.contract, 'name', None) or getattr(pos, 'name', None),
                    "quantity": getattr(pos, 'quantity', 0),
                    "average_cost": getattr(pos, 'average_cost', 0) or getattr(pos, 'avg_cost', 0),
                    "market_value": getattr(pos, 'market_value', 0),
                    "unrealized_pnl": getattr(pos, 'unrealized_pnl', 0),
                    "realized_pnl": getattr(pos, 'realized_pnl', 0),
                    "currency": getattr(pos, 'currency', None),
                })
            return positions
        except Exception as e:
            return [{"error": str(e)}]

    def get_orders(self) -> list:
        """Get today's orders."""
        try:
            result = self._trade_client.get_orders()
            if not result:
                return []
            orders = []
            for o in result:
                orders.append({
                    "id": getattr(o, 'id', None) or getattr(o, 'order_id', None),
                    "symbol": getattr(o, 'contract', None) and getattr(o.contract, 'symbol', None) or getattr(o, 'symbol', None),
                    "name": getattr(o, 'contract', None) and getattr(o.contract, 'name', None) or getattr(o, 'name', None),
                    "action": str(getattr(o, 'action', '')),
                    "quantity": getattr(o, 'quantity', 0),
                    "filled_quantity": getattr(o, 'filled', 0) or getattr(o, 'filled_quantity', 0),
                    "order_type": str(getattr(o, 'order_type', '')),
                    "limit_price": getattr(o, 'limit_price', None),
                    "status": str(getattr(o, 'status', '')),
                    "submitted_at": str(getattr(o, 'order_time', '') or getattr(o, 'submitted_at', '')),
                })
            return orders
        except Exception as e:
            return [{"error": str(e)}]

    def get_quote(self, symbols: list[str], market: str = "US") -> list:
        """Get quotes for given symbols."""
        try:
            market_enum = Market.US if market == "US" else Market.HK
            result = self._quote_client.get_stock_briefs(symbols, market=market_enum)
            if not result:
                return []
            quotes = []
            for q in result:
                quotes.append({
                    "symbol": getattr(q, 'symbol', None),
                    "name": getattr(q, 'name', None),
                    "latest_price": getattr(q, 'latest_price', None) or getattr(q, 'last_price', None),
                    "prev_close": getattr(q, 'prev_close', None),
                    "open": getattr(q, 'open', None),
                    "high": getattr(q, 'high', None),
                    "low": getattr(q, 'low', None),
                    "volume": getattr(q, 'volume', None),
                    "change": getattr(q, 'change', None),
                    "change_rate": getattr(q, 'change_rate', None),
                    "bid_price": getattr(q, 'bid_price', None),
                    "ask_price": getattr(q, 'ask_price', None),
                    "market_status": getattr(q, 'market_status', None),
                })
            return quotes
        except Exception as e:
            return [{"error": str(e)}]

    def get_market_status(self, market: str = "US") -> dict:
        """Get market status."""
        try:
            market_enum = Market.US if market == "US" else Market.HK
            result = self._quote_client.get_market_status(market=market_enum)
            return {"market": market, "status": str(result)}
        except Exception as e:
            return {"market": market, "error": str(e)}
