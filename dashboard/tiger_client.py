"""Tiger API client wrapper for dashboard."""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta

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

    def get_account_type(self) -> dict:
        """Get account info for the configured account.
        
        Filters get_managed_accounts() to match the account in config.
        Returns account_type: PAPER / STANDARD / GLOBAL.
        """
        try:
            target = self._client_config.account
            accounts = self._trade_client.get_managed_accounts()
            if not accounts:
                return {"error": "no accounts returned"}
            # Find matching account
            for a in accounts:
                if str(getattr(a, "account", "")) == str(target):
                    return {
                        "account": getattr(a, "account", ""),
                        "account_type": str(getattr(a, "account_type", "unknown")),
                        "capability": str(getattr(a, "capability", "")),
                        "status": str(getattr(a, "status", "")),
                    }
            # No match — return all for debugging
            all_info = [{
                "account": str(getattr(a, "account", "")),
                "account_type": str(getattr(a, "account_type", "unknown")),
            } for a in accounts]
            return {"error": f"account {target} not found in managed accounts", "all": all_info}
        except Exception as e:
            return {"error": str(e)}

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

            # Extract segment-level fields
            segments = getattr(pa, 'segments', {})
            seg_s = segments.get('S')  # Securities segment

            gross_pos = safe_val(summary, 'gross_position_value', 0)
            available_funds = safe_val(summary, 'available_funds', 0)
            if seg_s:
                if not gross_pos:
                    gross_pos = safe_val(seg_s, 'gross_position_value', 0)
                if not available_funds:
                    available_funds = safe_val(seg_s, 'available_funds', 0)

            return {
                "account": safe_val(pa, 'account', self.account),
                "net_liquidation": safe_val(summary, 'net_liquidation', 0),
                "cash": safe_val(summary, 'cash', 0),
                "buying_power": safe_val(summary, 'buying_power', 0),
                "unrealized_pnl": safe_val(summary, 'unrealized_pnl', 0),
                "realized_pnl": safe_val(summary, 'realized_pnl', 0),
                "currency": safe_val(summary, 'currency', 'USD'),
                "available_funds": available_funds,
                "gross_position_value": gross_pos,
                "equity_with_loan": safe_val(summary, 'equity_with_loan', 0),
                "excess_liquidity": safe_val(summary, 'excess_liquidity', 0),
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
                    "market_price": getattr(pos, 'market_price', 0),
                    "market_value": getattr(pos, 'market_value', 0),
                    "unrealized_pnl": getattr(pos, 'unrealized_pnl', 0),
                    "realized_pnl": getattr(pos, 'realized_pnl', 0),
                    "today_pnl": getattr(pos, 'today_pnl', 0),
                    "today_pnl_percent": getattr(pos, 'today_pnl_percent', 0),
                    "last_close_price": getattr(pos, 'last_close_price', None),
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
                    "avg_fill_price": getattr(o, 'avg_fill_price', None),
                    "status": str(getattr(o, 'status', '')),
                    "realized_pnl": getattr(o, 'realized_pnl', 0) or 0,
                    "submitted_at": str(getattr(o, 'order_time', '') or getattr(o, 'submitted_at', '')),
                })
            return orders
        except Exception as e:
            return [{"error": str(e)}]

    def get_filled_orders(self) -> list:
        """Get today's filled orders with realized_pnl from Tiger API."""
        try:
            now = datetime.now()
            start = now - timedelta(days=1)
            start_ms = int(start.timestamp() * 1000)
            end_ms = int(now.timestamp() * 1000)

            result = self._trade_client.get_filled_orders(
                start_time=start_ms,
                end_time=end_ms,
                market=Market.US
            )
            if not result:
                return []

            orders = []
            for o in result:
                contract = getattr(o, 'contract', None)
                orders.append({
                    "id": getattr(o, 'id', None) or getattr(o, 'order_id', None),
                    "symbol": getattr(contract, 'symbol', None) if contract else None,
                    "name": getattr(contract, 'name', None) if contract else None,
                    "action": str(getattr(o, 'action', '')),
                    "quantity": getattr(o, 'quantity', 0),
                    "filled_quantity": getattr(o, 'filled_quantity', 0) or getattr(o, 'filled', 0),
                    "avg_fill_price": getattr(o, 'avg_fill_price', None),
                    "status": str(getattr(o, 'status', '')),
                    "realized_pnl": getattr(o, 'realized_pnl', 0) or 0,
                    "order_time": getattr(o, 'order_time', None),
                })
            return orders
        except Exception as e:
            return [{"error": str(e)}]

    def get_quote(self, symbols: list[str], market: str = "US") -> list:
        """Get quotes for given symbols."""
        try:
            market_enum = Market.US
            result = self._quote_client.get_stock_briefs(symbols)
            if result is None or (hasattr(result, 'empty') and result.empty):
                return []
            # get_stock_briefs returns pd.DataFrame
            quotes = []
            for _, row in result.iterrows():
                def val(col, default=None):
                    v = row.get(col, default)
                    if v is None or (isinstance(v, float) and v != v):  # NaN check
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
        """Get market status."""
        try:
            market_enum = Market.US
            result = self._quote_client.get_market_status(market=market_enum)
            return {"market": market, "status": str(result)}
        except Exception as e:
            return {"market": market, "error": str(e)}
