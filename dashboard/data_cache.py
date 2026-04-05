"""Polling cache layer for Tiger data - reduces API call frequency."""

import os
import json
import time
import threading
from pathlib import Path
from datetime import datetime

from .tiger_client import TigerClient
from .quote_provider import QuoteProvider

WORKSPACE = Path(os.environ.get("TIGER_WORKSPACE", str(Path(__file__).parent.parent.parent)))
WATCHLIST_PATH = Path(os.environ.get("TIGER_WATCHLIST_PATH", str(WORKSPACE / "data" / "watchlist.json")))
MARKET_CONTEXT_PATH = Path(os.environ.get("TIGER_RUNTIME_DIR", str(WORKSPACE / "runtime" / "tiger_engine"))) / "market_context.json"


class DataCache:
    """Caches Tiger API responses with periodic refresh."""

    def __init__(self, tiger_client: TigerClient, quote_provider: QuoteProvider, refresh_interval: int = 30):
        self._client = tiger_client
        self._quote_provider = quote_provider
        self._interval = refresh_interval
        self._lock = threading.Lock()
        self._data = {
            "account": None,
            "positions": [],
            "orders": [],
            "quotes": {},
            "market_status": {},
            "watchlist": None,
            "last_updated": None,
            "refresh_count": 0,
            "errors": [],
        }
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self):
        """Start background polling."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop background polling."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

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

    def get_quotes(self) -> dict:
        with self._lock:
            data = dict(self._data["quotes"])
            data["_fetched_at"] = self._data.get("last_updated")
            return data

    def get_watchlist(self) -> dict:
        with self._lock:
            return dict(self._data["watchlist"]) if self._data["watchlist"] else {}

    def get_pnl(self) -> dict:
        """Calculate P&L from positions."""
        with self._lock:
            positions = self._data["positions"]
            if not positions:
                return {"total_unrealized": 0, "total_realized": 0, "details": []}

            details = []
            total_unrealized = 0
            total_realized = 0

            for pos in positions:
                unrealized = pos.get("unrealized_pnl", 0) or 0
                realized = pos.get("realized_pnl", 0) or 0
                total_unrealized += unrealized
                total_realized += realized
                details.append({
                    "symbol": pos.get("symbol"),
                    "unrealized_pnl": unrealized,
                    "realized_pnl": realized,
                    "market_value": pos.get("market_value"),
                })

            return {
                "total_unrealized": total_unrealized,
                "total_realized": total_realized,
                "total_pnl": total_unrealized + total_realized,
                "details": details,
            }

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
        """Refresh all data from Tiger API."""
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

        # Quotes (from watchlist) — rebuild each cycle so deleted symbols disappear
        quotes = {}
        try:
            watchlist = self._load_watchlist()
            us_symbols = [s["symbol"] for s in watchlist.get("symbols", [])
                         if s.get("enabled") and s.get("market") == "US"]
            hk_symbols = [s["symbol"] for s in watchlist.get("symbols", [])
                         if s.get("enabled") and s.get("market") == "HK"]

            if us_symbols:
                us_quotes = self._quote_provider.get_quote(us_symbols, "US")
                for q in us_quotes:
                    if q.get("symbol"):
                        q["market"] = "US"
                        quotes[q["symbol"]] = q

            if hk_symbols:
                hk_quotes = self._quote_provider.get_quote(hk_symbols, "HK")
                for q in hk_quotes:
                    if q.get("symbol"):
                        q["market"] = "HK"
                        quotes[q["symbol"]] = q
        except Exception as e:
            errors.append(f"quotes: {e}")

        # Update cache
        with self._lock:
            self._data["account"] = account
            self._data["positions"] = positions
            self._data["orders"] = orders
            self._data["quotes"] = quotes
            self._data["last_updated"] = datetime.now().isoformat()
            self._data["refresh_count"] += 1
            self._data["errors"].extend([{
                "time": datetime.now().isoformat(),
                "error": e,
            } for e in errors])

    def _load_watchlist(self) -> dict:
        """Load shared watchlist from file."""
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
