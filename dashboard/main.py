"""Tiger Trading Dashboard - FastAPI entry point."""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

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


# --- Entry point ---

def main():
    import uvicorn
    port = int(os.environ.get("DASHBOARD_PORT", 8080))
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
