"""Tiger Trading Dashboard - FastAPI entry point."""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .tiger_client import TigerClient
from .data_cache import DataCache

# --- App lifecycle ---

tiger_client: TigerClient | None = None
cache: DataCache | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the data cache on app lifecycle."""
    global tiger_client, cache

    config_dir = os.environ.get(
        "TIGER_CONFIG_DIR",
        str(Path(__file__).parent.parent / "config"),
    )

    tiger_client = TigerClient(config_dir=config_dir)
    cache = DataCache(tiger_client, refresh_interval=30)
    cache.start()

    yield

    cache.stop()


app = FastAPI(
    title="Tiger Trading Dashboard",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Static files ---

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/")
async def index():
    """Serve dashboard HTML."""
    return FileResponse(STATIC_DIR / "index.html")


# --- Health ---

@app.get("/health")
async def health():
    """Health check endpoint for Docker."""
    return {"status": "ok"}


# --- API routes ---


@app.get("/api/account")
async def api_account():
    """Account info (assets, buying power)."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return cache.get_account()


@app.get("/api/positions")
async def api_positions():
    """Current positions."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return cache.get_positions()


@app.get("/api/quotes")
async def api_quotes():
    """Quotes for watchlist symbols."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return cache.get_quotes()


@app.get("/api/orders")
async def api_orders():
    """Today's orders."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return cache.get_orders()


@app.get("/api/pnl")
async def api_pnl():
    """P&L summary."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return cache.get_pnl()


@app.get("/api/watchlist")
async def api_watchlist():
    """Shared watchlist."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return cache.get_watchlist()


@app.get("/api/agents")
async def api_agents():
    """Subagent status."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return cache.get_agents()


@app.get("/api/system")
async def api_system():
    """System runtime info."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return cache.get_system()


# --- Watchlist management ---


class WatchlistItem(BaseModel):
    symbol: str
    market: str = "US"
    name: str = ""
    enabled: bool = True
    priority: str = "normal"
    lot_size: int | None = None
    notes: str = ""


class WatchlistUpdate(BaseModel):
    enabled: bool | None = None
    priority: str | None = None
    notes: str | None = None


@app.post("/api/watchlist")
async def api_watchlist_add(item: WatchlistItem):
    """Add a symbol to the watchlist."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    try:
        result = cache.add_symbol(item.model_dump())
        return {"status": "ok", "data": result}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.patch("/api/watchlist/{symbol}")
async def api_watchlist_update(symbol: str, update: WatchlistUpdate):
    """Update a symbol in the watchlist."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    try:
        result = cache.update_symbol(symbol, update.model_dump(exclude_unset=True))
        if result is None:
            return JSONResponse({"error": f"Symbol {symbol} not found"}, status_code=404)
        return {"status": "ok", "data": result}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.delete("/api/watchlist/{symbol}")
async def api_watchlist_remove(symbol: str):
    """Remove a symbol from the watchlist."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    try:
        result = cache.remove_symbol(symbol)
        if not result:
            return JSONResponse({"error": f"Symbol {symbol} not found"}, status_code=404)
        return {"status": "ok", "removed": symbol}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# --- Entry point ---

def main():
    import uvicorn
    port = int(os.environ.get("DASHBOARD_PORT", 8080))
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
