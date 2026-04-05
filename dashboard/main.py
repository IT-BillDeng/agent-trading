"""Tiger Trading Dashboard - FastAPI entry point."""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .tiger_client import TigerClient
from .data_cache import DataCache
from .quote_provider import get_quote_provider

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

    # Quote provider: TIGER_QUOTE_PROVIDER env var (default: yfinance)
    provider_name = os.environ.get("TIGER_QUOTE_PROVIDER", "yfinance")
    quote_provider = get_quote_provider(provider_name, config_dir=config_dir)

    cache = DataCache(tiger_client, quote_provider, refresh_interval=30)
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


# --- Engine results & control ---

RUNTIME_DIR = Path(os.environ.get("TIGER_RUNTIME_DIR", "/app/runtime"))
CONFIG_DIR_PATH = Path(os.environ.get("TIGER_CONFIG_DIR", "/app/config"))


@app.get("/api/engine")
async def api_engine():
    """Read latest engine cycle output."""
    result = {}
    # Read last execution cycle
    cycle_file = RUNTIME_DIR / ".last_execution_cycle.json"
    if cycle_file.exists():
        try:
            import json
            result["last_cycle"] = json.loads(cycle_file.read_text())
        except Exception as e:
            result["last_cycle_error"] = str(e)
    else:
        result["last_cycle"] = None

    # Read control state
    state_file = RUNTIME_DIR / "state" / "control_state.json"
    if state_file.exists():
        try:
            import json
            result["control_state"] = json.loads(state_file.read_text())
        except Exception:
            result["control_state"] = None
    else:
        result["control_state"] = None

    return result


@app.get("/api/config")
async def api_config_get():
    """Get current engine config (risk params, markets, etc.)."""
    config_file = CONFIG_DIR_PATH / "app_config.docker.json"
    if not config_file.exists():
        return JSONResponse({"error": "config not found"}, status_code=404)
    import json
    return json.loads(config_file.read_text())


@app.patch("/api/config")
async def api_config_update(update: dict):
    """Update engine config (risk params, markets, etc.)."""
    config_file = CONFIG_DIR_PATH / "app_config.docker.json"
    if not config_file.exists():
        return JSONResponse({"error": "config not found"}, status_code=404)
    import json
    config = json.loads(config_file.read_text())
    # Allow updating top-level risk and markets
    if "risk" in update:
        config["risk"].update(update["risk"])
    if "markets" in update:
        config["markets"] = update["markets"]
    if "strategy" in update and "timeframe" in update["strategy"]:
        config["strategy"]["timeframe"] = update["strategy"]["timeframe"]
    config_file.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    return {"status": "ok", "config": config}


@app.post("/api/control/{action}")
async def api_control(action: str):
    """Lock or unlock the engine control plane."""
    import json
    state_dir = RUNTIME_DIR / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "control_state.json"

    if action == "lock":
        state = {"locked": True, "reason": "manual_lock", "updated_by": "dashboard"}
        state_file.write_text(json.dumps(state, indent=2))
        return {"status": "ok", "action": "locked"}
    elif action == "unlock":
        state = {"locked": False, "reason": "manual_unlock", "updated_by": "dashboard"}
        state_file.write_text(json.dumps(state, indent=2))
        return {"status": "ok", "action": "unlocked"}
    else:
        return JSONResponse({"error": f"unknown action: {action}"}, status_code=400)


@app.get("/api/audit")
async def api_audit(limit: int = 50):
    """Read recent audit log entries."""
    import json
    logs_dir = RUNTIME_DIR / "logs"
    result = []
    # Read from JSONL audit files
    for log_file in sorted(logs_dir.glob("*.jsonl"), reverse=True):
        try:
            lines = log_file.read_text().strip().split("\n")
            for line in lines[-limit:]:
                if line.strip():
                    entry = json.loads(line)
                    entry["_source"] = log_file.name
                    result.append(entry)
        except Exception:
            continue
        if len(result) >= limit:
            break
    return {"entries": result[:limit], "count": len(result)}


@app.get("/api/health/engine")
async def api_engine_health():
    """Check engine health from runtime files."""
    import json, time
    result = {"status": "unknown"}
    # Check last execution cycle timestamp
    cycle_file = RUNTIME_DIR / ".last_execution_cycle.json"
    if cycle_file.exists():
        try:
            cycle = json.loads(cycle_file.read_text())
            result["last_cycle_id"] = cycle.get("cycle_id")
            result["has_signals"] = bool(cycle.get("strategy", {}).get("signals"))
            result["signal_count"] = len(cycle.get("strategy", {}).get("signals", []))
            result["status"] = "ok"
        except Exception as e:
            result["status"] = f"error: {e}"
    else:
        result["status"] = "no_cycle_data"
    # Check control state
    state_file = RUNTIME_DIR / "state" / "control_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            result["locked"] = state.get("locked", False)
        except Exception:
            pass
    return result


class RefreshConfig(BaseModel):
    interval: int | None = None


@app.post("/api/refresh")
async def api_refresh(config: RefreshConfig):
    """Adjust quote refresh interval (seconds)."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    if config.interval is not None:
        if config.interval < 5:
            return JSONResponse({"error": "minimum interval is 5 seconds"}, status_code=400)
        cache._interval = config.interval
    return {"status": "ok", "interval": cache._interval}


# --- Tiger config management ---

TIGER_PROPS_FILE = CONFIG_DIR_PATH / "tiger_openapi_config.properties"

# env field in .properties → mode mapping
ENV_TO_MODE = {
    "PROD": "live",
    "SIMULATE": "paper",
    "TEST": "paper",
}


def _parse_properties(text: str) -> dict:
    """Parse a .properties file into a dict."""
    result = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    return result


def _mask_value(val: str, visible: int = 6) -> str:
    """Mask a sensitive value, showing only the last N chars."""
    if not val or len(val) <= visible:
        return "****"
    return "*" * (len(val) - visible) + val[-visible:]


@app.get("/api/tiger-config")
async def api_tiger_config_get():
    """Get current Tiger API config (sensitive fields masked)."""
    if not TIGER_PROPS_FILE.exists():
        return {"exists": False, "env": None, "mode": "paper", "fields": {}}
    props = _parse_properties(TIGER_PROPS_FILE.read_text())
    env = props.get("env", "SIMULATE")
    mode = ENV_TO_MODE.get(env, "paper")
    masked = {}
    sensitive = {"private_key_pk1", "private_key_pk8", "secret_key"}
    for k, v in props.items():
        if k in sensitive:
            masked[k] = _mask_value(v)
        else:
            masked[k] = v
    return {"exists": True, "env": env, "mode": mode, "fields": masked}


@app.post("/api/tiger-config/upload")
async def api_tiger_config_upload_file(content: str = Form(None)):
    """Upload Tiger config (form field 'content' with plain text)."""
    if not content:
        return JSONResponse({"error": "no file content provided"}, status_code=400)

    props = _parse_properties(content)
    if "tiger_id" not in props or "account" not in props:
        return JSONResponse({"error": "invalid config: missing tiger_id or account"}, status_code=400)

    # Backup existing
    if TIGER_PROPS_FILE.exists():
        backup = TIGER_PROPS_FILE.with_suffix(".properties.bak")
        backup.write_text(TIGER_PROPS_FILE.read_text())

    TIGER_PROPS_FILE.write_text(content)

    # Auto-detect mode from env
    env = props.get("env", "SIMULATE")
    detected_mode = ENV_TO_MODE.get(env, "paper")

    # Update app_config mode if changed
    config_file = CONFIG_DIR_PATH / "app_config.docker.json"
    if config_file.exists():
        app_config = json.loads(config_file.read_text())
        old_mode = app_config.get("mode", "paper")
        if old_mode != detected_mode:
            app_config["mode"] = detected_mode
            config_file.write_text(json.dumps(app_config, indent=2, ensure_ascii=False))

    return {
        "status": "ok",
        "env": env,
        "detected_mode": detected_mode,
        "tiger_id": props.get("tiger_id"),
        "account": props.get("account"),
    }


@app.post("/api/config/mode")
async def api_config_mode(body: dict):
    """Manually set paper/live mode."""
    mode = body.get("mode")
    if mode not in ("paper", "live"):
        return JSONResponse({"error": "mode must be paper or live"}, status_code=400)
    config_file = CONFIG_DIR_PATH / "app_config.docker.json"
    if not config_file.exists():
        return JSONResponse({"error": "config not found"}, status_code=404)
    config = json.loads(config_file.read_text())
    config["mode"] = mode
    # Live mode safety: disable live_submit/live_cancel by default
    if mode == "live":
        config.setdefault("execution", {})["live_submit"] = False
        config.setdefault("execution", {})["live_cancel"] = False
    config_file.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    return {"status": "ok", "mode": mode}


# --- Entry point ---

def main():
    import uvicorn
    port = int(os.environ.get("DASHBOARD_PORT", 8088))
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
