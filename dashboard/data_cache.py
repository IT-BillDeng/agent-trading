"""Polling cache layer for broker data - reduces API call frequency."""

import os
import json
import time
import threading
from pathlib import Path
from datetime import datetime, timedelta

from .tiger_client import TigerClient, ET_ZONE
from .quote_provider import QuoteProvider
from .service_logs import append_service_log

WORKSPACE = Path(os.environ.get("ENGINE_WORKSPACE", str(Path(__file__).parent.parent.parent)))
WATCHLIST_PATH = Path(os.environ.get("ENGINE_WATCHLIST_PATH", str(WORKSPACE / "data" / "watchlist.json")))
MARKET_CONTEXT_PATH = Path(os.environ.get("ENGINE_RUNTIME_DIR", str(WORKSPACE / "runtime" / "engine"))) / "market_context.json"
ANALYSIS_ALL_START = "2000-01-01"
ANALYSIS_PERIODS = {
    "all": {"label": "全部", "days": None},
    "1w": {"label": "1周", "days": 7},
    "1m": {"label": "1个月", "days": 30},
    "3m": {"label": "3个月", "days": 90},
    "6m": {"label": "半年", "days": 180},
}


def _seed_watchlist_if_missing() -> None:
    if WATCHLIST_PATH.exists():
        return
    example_path = WATCHLIST_PATH.with_name("watchlist.json.example")
    if not example_path.exists():
        return
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    WATCHLIST_PATH.write_text(example_path.read_text())


class DataCache:
    """Caches API responses with periodic refresh."""

    def __init__(self, tiger_client: TigerClient, quote_provider: QuoteProvider, refresh_interval: int = 30):
        self._client = tiger_client
        self._quote_provider = quote_provider
        self._interval = refresh_interval
        self._lock = threading.Lock()
        self._data = {
            "account": None,
            "positions": [],
            "orders": [],
            "filled_orders": [],
            "quotes": {},
            "market_status": {},
            "watchlist": None,
            "last_updated": None,
            "refresh_count": 0,
            "errors": [],
        }
        self._analysis_cache = {}
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self):
        """Start background polling."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        append_service_log(
            "dashboard",
            "info",
            "Data cache background polling started",
            kind="cache_lifecycle",
            refresh_interval=self._interval,
            provider=self._quote_provider.name,
        )

    def stop(self):
        """Stop background polling."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        append_service_log(
            "dashboard",
            "info",
            "Data cache background polling stopped",
            kind="cache_lifecycle",
            refresh_interval=self._interval,
            provider=self._quote_provider.name,
        )

    def get(self) -> dict:
        """Get cached data snapshot."""
        with self._lock:
            return dict(self._data)

    def get_account(self) -> dict:
        with self._lock:
            return self._data["account"] or {}

    def get_positions(self) -> list:
        with self._lock:
            return list(self._data["positions"])

    def get_orders(self) -> list:
        with self._lock:
            return list(self._data["orders"])

    @staticmethod
    def _merge_order_fill_prices(orders: list, filled_orders: list) -> list:
        """Backfill fill-related fields from filled orders into order list."""
        if not orders or not filled_orders:
            return orders

        filled_by_id = {}
        for filled in filled_orders:
            if not isinstance(filled, dict):
                continue
            fill_fields = {
                "avg_fill_price": filled.get("avg_fill_price"),
                "filled_cash_amount": filled.get("filled_cash_amount"),
                "total_cash_amount": filled.get("total_cash_amount"),
            }
            if all(v in (None, "") for v in fill_fields.values()):
                continue
            for key in (filled.get("id"), filled.get("order_id")):
                if key:
                    filled_by_id[str(key)] = fill_fields

        if not filled_by_id:
            return orders

        merged = []
        for order in orders:
            if not isinstance(order, dict):
                merged.append(order)
                continue

            matched_fields = None
            for key in (order.get("id"), order.get("order_id")):
                if key and str(key) in filled_by_id:
                    matched_fields = filled_by_id[str(key)]
                    break

            if not matched_fields:
                merged.append(order)
                continue

            enriched = dict(order)
            for field, value in matched_fields.items():
                if enriched.get(field) in (None, "") and value not in (None, ""):
                    enriched[field] = value
            merged.append(enriched)

        return merged

    @staticmethod
    def _merge_order_transactions(orders: list, transactions: list) -> list:
        """Backfill成交价格 from transaction records into order list."""
        if not orders or not transactions:
            return orders

        tx_by_order_id = {}
        for tx in transactions:
            if not isinstance(tx, dict) or tx.get("error"):
                continue
            order_id = tx.get("order_id")
            filled_price = tx.get("filled_price")
            filled_amount = tx.get("filled_amount")
            if not order_id:
                continue
            if filled_price in (None, "") and filled_amount in (None, ""):
                continue
            tx_by_order_id[str(order_id)] = {
                "avg_fill_price": filled_price,
                "filled_cash_amount": filled_amount,
            }

        if not tx_by_order_id:
            return orders

        merged = []
        for order in orders:
            if not isinstance(order, dict):
                merged.append(order)
                continue

            matched = None
            for key in (order.get("order_id"), order.get("id")):
                if key and str(key) in tx_by_order_id:
                    matched = tx_by_order_id[str(key)]
                    break

            if not matched:
                merged.append(order)
                continue

            enriched = dict(order)
            for field, value in matched.items():
                if enriched.get(field) in (None, "") and value not in (None, ""):
                    enriched[field] = value
            merged.append(enriched)

        return merged

    def get_quotes(self) -> dict:
        with self._lock:
            data = dict(self._data["quotes"])
            data["_fetched_at"] = self._data.get("last_updated")
            return data

    def get_watchlist(self) -> dict:
        with self._lock:
            return dict(self._data["watchlist"]) if self._data["watchlist"] else {}

    def get_pnl(self) -> dict:
        """Calculate P&L using filled_orders for realized_pnl."""
        with self._lock:
            positions = self._data["positions"] or []
            filled_orders = self._data.get("filled_orders") or []
            account = self._data["account"] or {}

            # Account-level P&L
            account_realized = float(account.get("realized_pnl") or account.get("realizedPnl") or 0)
            account_unrealized = float(account.get("unrealized_pnl") or account.get("unrealizedPnl") or 0)
            account_total_today = float(account.get("total_today_pnl") or account.get("totalTodayPnl") or 0)

            # 当前持仓 symbols
            position_symbols = {pos.get("symbol") for pos in positions}

            # 从 filled_orders 按 symbol 汇总 realized_pnl (仅 SELL)
            closed_pnl = {}  # symbol -> realized_pnl
            today_realized = 0
            for o in filled_orders:
                if o.get("action") == "SELL":
                    symbol = o.get("symbol")
                    pnl = o.get("realized_pnl", 0) or 0
                    today_realized += pnl
                    if symbol:
                        closed_pnl[symbol] = closed_pnl.get(symbol, 0) + pnl

            # 持仓今日浮动
            today_unrealized = 0
            details = []
            total_unrealized = 0

            # 当前持仓明细
            for pos in positions:
                symbol = pos.get("symbol")
                unrealized = pos.get("unrealized_pnl", 0) or 0
                today_pos = pos.get("today_pnl", 0) or 0  # 持仓的日内浮动
                realized_today = closed_pnl.get(symbol, 0)  # 今日该股已实现
                total_unrealized += unrealized
                today_unrealized += today_pos
                details.append({
                    "symbol": symbol,
                    "name": pos.get("name", ""),
                    "status": "open",
                    "unrealized_pnl": unrealized,
                    "realized_pnl": realized_today,
                    "market_value": pos.get("market_value"),
                    "today_pnl": today_pos + realized_today,
                    "today_pnl_pct": pos.get("today_pnl_percent", 0) or 0,
                })
                # 移除已处理的
                if symbol in closed_pnl:
                    del closed_pnl[symbol]

            # 已平仓明细（今日平仓但不在持仓中的）
            for symbol, realized in closed_pnl.items():
                details.append({
                    "symbol": symbol,
                    "name": "",
                    "status": "closed",
                    "unrealized_pnl": 0,
                    "realized_pnl": realized,
                    "market_value": 0,
                    "today_pnl": realized,
                    "today_pnl_pct": 0,
                })

            # 首页账户口径优先使用 account.total_today_pnl
            today_total = account_total_today if account_total_today or account_total_today == 0 else (today_realized + today_unrealized)
            today_realized_effective = today_total - today_unrealized

            return {
                "total_today": today_total,
                "today_realized": today_realized_effective,
                "today_unrealized": today_unrealized,
                "total_unrealized": account_unrealized or total_unrealized,
                "total_realized": account_realized,
                "total_pnl": (account_unrealized or total_unrealized) + account_realized,
                "details": details,
            }

    def get_stock_analysis(self, period: str = "all") -> dict:
        """Get per-symbol analysis using historical orders + current positions."""
        period = period if period in ANALYSIS_PERIODS else "all"
        with self._lock:
            refresh_count = self._data["refresh_count"]
            positions = list(self._data["positions"] or [])
            cached = self._analysis_cache.get(period)
            if cached and cached.get("refresh_count") == refresh_count:
                return cached["data"]

        watchlist = self._load_watchlist()
        window = self._get_analysis_window(period)
        orders = self._client.get_orders_history(
            start_time=window["start_time"],
            end_time=window["end_time"],
        )
        # 合并今日成交（历史查询有时漏掉当日数据）
        try:
            today_orders = self._client.get_filled_orders()
            seen_ids = {o.get("id") or o.get("order_id") for o in orders if isinstance(o, dict)}
            for o in today_orders:
                if not isinstance(o, dict):
                    continue
                oid = o.get("id") or o.get("order_id")
                if oid and oid not in seen_ids:
                    orders.append(o)
                    seen_ids.add(oid)
        except Exception:
            pass
        data = self._build_stock_analysis(
            positions=positions,
            orders=orders,
            watchlist=watchlist,
            period=period,
            window=window,
        )

        with self._lock:
            self._analysis_cache[period] = {
                "refresh_count": refresh_count,
                "data": data,
            }

        return data

    def get_agents(self) -> dict:
        """Read agent state from shared context files."""
        agents = {
            "strategist": {"status": "idle", "last_update": None},
            "executor": {"status": "idle", "last_update": None},
            "watcher": {"status": "idle", "last_update": None},
            "newswire": {"status": "idle", "last_update": None},
            "scout": {"status": "idle", "last_update": None},
            "closer": {"status": "idle", "last_update": None},
        }

        # Read market context for agent updates
        try:
            if MARKET_CONTEXT_PATH.exists():
                ctx = json.loads(MARKET_CONTEXT_PATH.read_text())
                if ctx.get("watcher_observation", {}).get("cycle_id"):
                    agents["watcher"]["last_update"] = ctx.get("updated_at")
                if ctx.get("newswire_summary", {}).get("cycle_id"):
                    agents["newswire"]["last_update"] = ctx.get("updated_at")
        except Exception:
            pass

        return agents

    def get_system(self) -> dict:
        """Get system runtime info."""
        with self._lock:
            return {
                "refresh_interval": self._interval,
                "refresh_count": self._data["refresh_count"],
                "last_updated": self._data["last_updated"],
                "errors": self._data["errors"][-10:],  # last 10 errors
                "account_id": self._client.account,
                "quote_provider": self._quote_provider.name,
            }

    # --- Internal ---

    def _poll_loop(self):
        """Background polling loop."""
        while not self._stop_event.is_set():
            try:
                self._refresh()
            except Exception as e:
                append_service_log(
                    "dashboard",
                    "error",
                    "Data cache refresh loop failed",
                    kind="cache_refresh_error",
                    error=str(e),
                    provider=self._quote_provider.name,
                )
                with self._lock:
                    self._data["errors"].append({
                        "time": datetime.now().isoformat(),
                        "error": str(e),
                    })
                    # Keep only last 50 errors
                    if len(self._data["errors"]) > 50:
                        self._data["errors"] = self._data["errors"][-50:]

            self._stop_event.wait(self._interval)

    def _refresh(self):
        """Refresh all data from the API."""
        errors = []

        # Account
        try:
            account = self._client.get_account_info()
        except Exception as e:
            account = {"error": str(e)}
            errors.append(f"account: {e}")

        # Positions
        try:
            positions = self._client.get_positions()
        except Exception as e:
            positions = []
            errors.append(f"positions: {e}")

        # Orders
        try:
            orders = self._client.get_orders()
        except Exception as e:
            orders = []
            errors.append(f"orders: {e}")

        # Filled orders (with realized_pnl from API)
        try:
            filled_orders = self._client.get_filled_orders()
        except Exception as e:
            filled_orders = []
            errors.append(f"filled_orders: {e}")

        orders = self._merge_order_fill_prices(orders, filled_orders)

        try:
            transactions = self._client.get_today_transactions()
        except Exception as e:
            transactions = []
            errors.append(f"transactions: {e}")

        orders = self._merge_order_transactions(orders, transactions)

        # Update core cache first so quote provider stalls don't blank the page.
        with self._lock:
            self._data["account"] = account
            self._data["positions"] = positions
            self._data["orders"] = orders
            self._data["filled_orders"] = filled_orders
            self._data["last_updated"] = datetime.now().isoformat()
            self._data["refresh_count"] += 1
            self._analysis_cache = {}
            self._data["errors"].extend([{
                "time": datetime.now().isoformat(),
                "error": e,
            } for e in errors])

        if errors:
            append_service_log(
                "dashboard",
                "warning",
                "Data cache refresh completed with partial errors",
                kind="cache_refresh_warning",
                provider=self._quote_provider.name,
                errors=errors,
            )

        # Quotes (from watchlist) — rebuild each cycle so deleted symbols disappear
        quotes = {}
        try:
            watchlist = self._load_watchlist()
            us_symbols = [s["symbol"] for s in watchlist.get("symbols", [])
                         if s.get("enabled") and s.get("market") == "US"]

            if us_symbols:
                us_quotes = self._quote_provider.get_quote(us_symbols, "US")
                for q in us_quotes:
                    if q.get("symbol"):
                        q["market"] = "US"
                        quotes[q["symbol"]] = q

            with self._lock:
                self._data["quotes"] = quotes
        except Exception as e:
            append_service_log(
                "dashboard",
                "warning",
                "Quote refresh failed",
                kind="quote_refresh_warning",
                provider=self._quote_provider.name,
                error=str(e),
            )
            with self._lock:
                self._data["errors"].append({
                    "time": datetime.now().isoformat(),
                    "error": f"quotes: {e}",
                })

    def _load_watchlist(self) -> dict:
        """Load shared watchlist from file."""
        _seed_watchlist_if_missing()
        if self._data["watchlist"] is None or (
            self._data.get("_watchlist_mtime", 0) <
            WATCHLIST_PATH.stat().st_mtime if WATCHLIST_PATH.exists() else 0
        ):
            try:
                self._data["watchlist"] = json.loads(WATCHLIST_PATH.read_text())
                self._data["_watchlist_mtime"] = WATCHLIST_PATH.stat().st_mtime
            except Exception:
                self._data["watchlist"] = {"symbols": []}
        return self._data["watchlist"]

    def _save_watchlist(self):
        """Save watchlist back to file."""
        with self._lock:
            data = self._data["watchlist"]
            if data:
                data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
                data["updated_by"] = "dashboard"
                WATCHLIST_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                self._data["_watchlist_mtime"] = WATCHLIST_PATH.stat().st_mtime

    def add_symbol(self, item: dict) -> dict:
        """Add a new symbol to the watchlist."""
        watchlist = self._load_watchlist()
        symbols = watchlist.setdefault("symbols", [])

        # Check for duplicates
        for s in symbols:
            if s["symbol"].upper() == item["symbol"].upper():
                raise ValueError(f"Symbol {item['symbol']} already in watchlist")

        new_entry = {
            "symbol": item["symbol"].upper(),
            "market": item.get("market", "US"),
            "name": item.get("name", ""),
            "enabled": item.get("enabled", True),
            "priority": item.get("priority", "normal"),
            "roles": ["watcher", "strategist", "executor", "newswire", "scout", "closer"],
            "notes": item.get("notes", ""),
        }
        if item.get("lot_size"):
            new_entry["lot_size"] = item["lot_size"]
        symbols.append(new_entry)
        self._save_watchlist()
        return new_entry

    def _get_analysis_window(self, period: str) -> dict:
        now_et = datetime.now(ET_ZONE)
        config = ANALYSIS_PERIODS[period]
        if config["days"] is None:
            start_time = ANALYSIS_ALL_START
        else:
            start_time = (now_et - timedelta(days=config["days"])).strftime("%Y-%m-%d")
        return {
            "period": period,
            "label": config["label"],
            "start_time": start_time,
            "end_time": now_et.strftime("%Y-%m-%d %H:%M:%S"),
            "now_et": now_et.isoformat(),
        }

    def _build_stock_analysis(self, positions: list, orders: list, watchlist: dict, period: str, window: dict) -> dict:
        watchlist_names = {
            item.get("symbol"): item.get("name", "")
            for item in (watchlist or {}).get("symbols", [])
            if item.get("symbol")
        }
        analysis = {}

        def ensure_item(symbol: str) -> dict:
            item = analysis.get(symbol)
            if item is None:
                item = {
                    "symbol": symbol,
                    "name": watchlist_names.get(symbol, ""),
                    "status": "closed",
                    "quantity": 0,
                    "market_value": 0,
                    "unrealized_pnl": 0,
                    "realized_pnl": 0,
                    "total_pnl": 0,
                    "trade_count": 0,
                    "buy_count": 0,
                    "sell_count": 0,
                    "last_trade_time": None,
                }
                analysis[symbol] = item
            return item

        for pos in positions:
            symbol = pos.get("symbol")
            if not symbol:
                continue
            item = ensure_item(symbol)
            item["status"] = "open"
            item["name"] = item["name"] or pos.get("name") or ""
            item["quantity"] = pos.get("quantity", 0) or 0
            item["market_value"] = pos.get("market_value", 0) or 0
            item["unrealized_pnl"] = pos.get("unrealized_pnl", 0) or 0

        for order in orders:
            if not isinstance(order, dict) or order.get("error"):
                continue
            filled_qty = order.get("filled_quantity", 0) or 0
            if filled_qty <= 0:
                continue
            symbol = order.get("symbol")
            if not symbol:
                continue
            item = ensure_item(symbol)
            item["name"] = item["name"] or order.get("name") or ""
            item["trade_count"] += 1

            action = str(order.get("action") or "").upper()
            if action == "BUY":
                item["buy_count"] += 1
            elif action == "SELL":
                item["sell_count"] += 1
                item["realized_pnl"] += float(order.get("realized_pnl") or 0)

            order_time = order.get("order_time")
            if order_time and (item["last_trade_time"] is None or order_time > item["last_trade_time"]):
                item["last_trade_time"] = order_time

        details = []
        for item in analysis.values():
            item["total_pnl"] = float(item["realized_pnl"] or 0) + float(item["unrealized_pnl"] or 0)
            details.append(item)

        details.sort(
            key=lambda item: (
                abs(float(item["realized_pnl"] or 0)) + abs(float(item["unrealized_pnl"] or 0)),
                item["trade_count"],
                item["symbol"],
            ),
            reverse=True,
        )

        summary = {
            "symbol_count": len(details),
            "open_count": sum(1 for item in details if item["status"] == "open"),
            "closed_count": sum(1 for item in details if item["status"] == "closed"),
            "trade_count": sum(int(item["trade_count"] or 0) for item in details),
            "buy_count": sum(int(item["buy_count"] or 0) for item in details),
            "sell_count": sum(int(item["sell_count"] or 0) for item in details),
            "realized_pnl": sum(float(item["realized_pnl"] or 0) for item in details),
            "unrealized_pnl": sum(float(item["unrealized_pnl"] or 0) for item in details),
            "total_pnl": sum(float(item["total_pnl"] or 0) for item in details),
        }

        return {
            "period": period,
            "period_label": window["label"],
            "start_time": window["start_time"],
            "end_time": window["end_time"],
            "as_of": window["now_et"],
            "summary": summary,
            "details": details,
        }

    def update_symbol(self, symbol: str, updates: dict) -> dict | None:
        """Update a symbol in the watchlist."""
        watchlist = self._load_watchlist()
        for s in watchlist.get("symbols", []):
            if s["symbol"].upper() == symbol.upper():
                for key, val in updates.items():
                    if val is not None:
                        s[key] = val
                self._save_watchlist()
                return s
        return None

    def remove_symbol(self, symbol: str) -> bool:
        """Remove a symbol from the watchlist."""
        watchlist = self._load_watchlist()
        symbols = watchlist.get("symbols", [])
        for i, s in enumerate(symbols):
            if s["symbol"].upper() == symbol.upper():
                symbols.pop(i)
                self._save_watchlist()
                return True
        return False
