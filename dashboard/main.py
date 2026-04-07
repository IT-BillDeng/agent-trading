"""Tiger Trading Dashboard - FastAPI entry point."""

import os
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .tiger_client import TigerClient
from .data_cache import DataCache
from .quote_provider import get_quote_provider
from .scheduler import SignalScheduler

# --- App lifecycle ---

tiger_client: TigerClient | None = None
cache: DataCache | None = None
scheduler: SignalScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the data cache on app lifecycle."""
    global tiger_client, cache

    config_dir = os.environ.get(
        "TIGER_CONFIG_DIR",
        str(Path(__file__).parent.parent / "config"),
    )

    # TigerClient may fail if credentials are invalid — don't crash the app
    try:
        tiger_client = TigerClient(config_dir=config_dir)
    except Exception as e:
        tiger_client = None
        print(f"[dashboard] TigerClient init failed: {e}")

    # Quote provider: TIGER_QUOTE_PROVIDER env var (default: yfinance)
    provider_name = os.environ.get("TIGER_QUOTE_PROVIDER", "yfinance")
    quote_provider = get_quote_provider(provider_name, config_dir=config_dir)

    if tiger_client:
        cache = DataCache(tiger_client, quote_provider, refresh_interval=30)
        cache.start()
    else:
        cache = None
        print("[dashboard] DataCache not started (no TigerClient)")

    # Start signal scheduler
    global scheduler
    app_config = os.environ.get(
        "TIGER_APP_CONFIG",
        str(Path(config_dir) / "app_config.docker.json"),
    )
    runtime_dir = os.environ.get(
        "TIGER_RUNTIME_DIR",
        str(Path(__file__).parent.parent / "runtime" / "tiger_engine"),
    )
    scheduler_provider = os.environ.get("TIGER_SCHEDULER_PROVIDER", provider_name)
    scheduler_interval = int(os.environ.get("TIGER_SCHEDULER_INTERVAL", "60"))

    try:
        scheduler = SignalScheduler(
            app_config_path=app_config,
            runtime_dir=runtime_dir,
            provider_name=scheduler_provider,
            interval_seconds=scheduler_interval,
        )
        scheduler.start()
    except Exception as e:
        scheduler = None
        print(f"[dashboard] Scheduler init failed: {e}")

    yield

    if scheduler:
        scheduler.stop()
    if cache:
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

RUNTIME_DIR = Path(os.environ.get("TIGER_RUNTIME_DIR", str(Path(__file__).parent.parent / "runtime")))
CONFIG_DIR_PATH = Path(os.environ.get("TIGER_CONFIG_DIR", str(Path(__file__).parent.parent / "config")))


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


def _read_cycle() -> dict | None:
    """Read last execution cycle JSON."""
    import json
    cycle_file = RUNTIME_DIR / ".last_execution_cycle.json"
    if cycle_file.exists():
        try:
            return json.loads(cycle_file.read_text())
        except Exception:
            pass
    return None


@app.get("/api/signals")
async def api_signals():
    """Latest strategy signals (BUY / EXIT / HOLD)."""
    cycle = _read_cycle()
    if not cycle:
        return {"signals": [], "cycle_id": None, "timeframe": None}
    strategy = cycle.get("strategy", {})
    return {
        "signals": strategy.get("signals", []),
        "cycle_id": cycle.get("cycle_id"),
        "timeframe": strategy.get("timeframe"),
    }


@app.get("/api/risk")
async def api_risk():
    """Risk decisions and preview blockers."""
    cycle = _read_cycle()
    if not cycle:
        return {"decisions": [], "allowed_count": 0, "preview_blockers": [], "cycle_id": None}
    risk = cycle.get("risk", {})
    return {
        "decisions": risk.get("decisions", []),
        "allowed_count": risk.get("allowed_count", 0),
        "preview_blockers": risk.get("preview_blockers", []),
        "cycle_id": cycle.get("cycle_id"),
    }


@app.get("/api/execution-preview")
async def api_execution_preview():
    """Execution preview and order intents."""
    cycle = _read_cycle()
    if not cycle:
        return {"preview": None, "intents": None, "cycle_id": None}
    return {
        "preview": cycle.get("execution_preview"),
        "intents": cycle.get("order_intents"),
        "execution_submit": cycle.get("execution_submit"),
        "execution_preview_check": cycle.get("execution_preview_check"),
        "cycle_id": cycle.get("cycle_id"),
    }


@app.get("/api/notifications")
async def api_notifications():
    """Notification preview and dispatch queue."""
    cycle = _read_cycle()
    if not cycle:
        return {"notifications": None, "cycle_id": None}
    return {
        "notifications": cycle.get("notification_preview"),
        "dispatch_requests": cycle.get("dispatch_requests"),
        "cycle_id": cycle.get("cycle_id"),
    }


@app.get("/api/scheduler")
async def api_scheduler_status():
    """Get scheduler status."""
    if not scheduler:
        return {"running": False, "error": "scheduler not initialized"}
    return scheduler.get_state()


@app.post("/api/scheduler/interval")
async def api_scheduler_interval(body: dict):
    """Update scheduler interval (seconds)."""
    if not scheduler:
        return JSONResponse({"error": "scheduler not initialized"}, status_code=503)
    interval = body.get("interval")
    if not isinstance(interval, int) or interval < 10:
        return JSONResponse({"error": "interval must be >= 10 seconds"}, status_code=400)
    scheduler.set_interval(interval)
    return {"status": "ok", "interval": interval}


@app.post("/api/scheduler/run")
async def api_scheduler_run():
    """Manually trigger one engine cycle."""
    if not scheduler:
        return JSONResponse({"error": "scheduler not initialized"}, status_code=503)
    import threading
    t = threading.Thread(target=scheduler._run_cycle, daemon=True)
    t.start()
    return {"status": "ok", "message": "cycle triggered"}


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


def _read_control_state() -> dict:
    """Read control state from runtime."""
    import json
    state_file = RUNTIME_DIR / "state" / "control_state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception:
            pass
    return {"locked": False, "trading_mode": "off"}


def _write_control_state(state: dict):
    """Write control state to runtime."""
    import json
    state_dir = RUNTIME_DIR / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "control_state.json"
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))


@app.post("/api/control/{action}")
async def api_control(action: str):
    """Lock or unlock the engine control plane."""
    state = _read_control_state()

    if action == "lock":
        state["locked"] = True
        state["reason"] = "manual_lock"
        state["updated_by"] = "dashboard"
        _write_control_state(state)
        return {"status": "ok", "action": "locked"}
    elif action == "unlock":
        state["locked"] = False
        state["reason"] = "manual_unlock"
        state["updated_by"] = "dashboard"
        _write_control_state(state)
        return {"status": "ok", "action": "unlocked"}
    else:
        return JSONResponse({"error": f"unknown action: {action}"}, status_code=400)


VALID_TRADING_MODES = {"off", "signals", "trade"}


@app.get("/api/trading/mode")
async def api_trading_mode_get():
    """Get current trading mode."""
    state = _read_control_state()
    mode = state.get("trading_mode", "off")
    return {
        "mode": mode,
        "locked": state.get("locked", False),
        "signal_generation": mode != "off",
        "order_submission": mode == "trade",
    }


@app.post("/api/trading/mode")
async def api_trading_mode_set(body: dict):
    """Set trading mode: off / signals / trade."""
    mode = body.get("mode")
    if mode not in VALID_TRADING_MODES:
        return JSONResponse(
            {"error": f"mode must be one of: {', '.join(VALID_TRADING_MODES)}"},
            status_code=400,
        )
    state = _read_control_state()
    state["trading_mode"] = mode
    state["updated_by"] = "dashboard"
    _write_control_state(state)
    return {
        "status": "ok",
        "mode": mode,
        "signal_generation": mode != "off",
        "order_submission": mode == "trade",
    }


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


# --- Rules API ---

RULES_FILE = CONFIG_DIR_PATH / "rules.json"


@app.get("/api/rules")
async def api_rules_get():
    """Get current rules configuration."""
    if not RULES_FILE.exists():
        return {"rules": [], "global_settings": {}}
    import json
    try:
        return json.loads(RULES_FILE.read_text())
    except Exception as e:
        return JSONResponse({"error": f"Failed to load rules: {e}"}, status_code=500)


class RuleItem(BaseModel):
    rule_id: str
    name: str
    description: str | None = None
    enabled: bool = True
    priority: int = 1
    timeframe: str = "30min"
    symbols: list[str] = ["*"]
    markets: list[str] = ["US", "HK"]
    entry: dict[str, Any] | None = None
    exit: dict[str, Any] | None = None


@app.put("/api/rules")
async def api_rules_update(rules_data: dict):
    """Update rules configuration."""
    import json
    import shutil
    from datetime import datetime
    
    # Validate structure
    if "rules" not in rules_data:
        return JSONResponse({"error": "Missing 'rules' field"}, status_code=400)
    
    # Backup existing rules
    if RULES_FILE.exists():
        backup_dir = CONFIG_DIR_PATH / "rules_backup"
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"rules_{timestamp}.json"
        shutil.copy2(RULES_FILE, backup_file)
    
    # Add metadata
    rules_data["updated_at"] = datetime.now().isoformat()
    if "version" not in rules_data:
        rules_data["version"] = "1.0"
    
    # Write new rules
    RULES_FILE.write_text(json.dumps(rules_data, indent=2, ensure_ascii=False))
    
    return {"status": "ok", "message": "Rules updated", "backup_created": RULES_FILE.exists()}


@app.post("/api/rules/validate")
async def api_rules_validate(rules_data: dict):
    """Validate rules configuration format."""
    errors = []
    
    if "rules" not in rules_data:
        errors.append("Missing 'rules' field")
        return {"valid": False, "errors": errors}
    
    for i, rule in enumerate(rules_data["rules"]):
        if "rule_id" not in rule:
            errors.append(f"Rule {i}: missing 'rule_id'")
        if "name" not in rule:
            errors.append(f"Rule {i}: missing 'name'")
        
        # Validate entry conditions
        entry = rule.get("entry", {})
        if entry:
            conditions = entry.get("conditions", {})
            if not conditions:
                errors.append(f"Rule {rule.get('rule_id', i)}: entry missing conditions")
        
        # Validate exit conditions
        exit_config = rule.get("exit", {})
        if exit_config:
            conditions = exit_config.get("conditions", {})
            if not conditions:
                errors.append(f"Rule {rule.get('rule_id', i)}: exit missing conditions")
    
    return {"valid": len(errors) == 0, "errors": errors}


@app.post("/api/rules/test")
async def api_rules_test(body: dict):
    """Test a rule against historical data."""
    # Import backtest module
    import sys
    backtest_src = str(Path(__file__).parent.parent / "system" / "tiger_engine" / "src")
    if backtest_src not in sys.path:
        sys.path.insert(0, backtest_src)
    
    from tiger_engine.backtest import BacktestConfig, run_backtest
    
    rule_id = body.get("rule_id")
    symbol = body.get("symbol", "AAPL")
    start_date = body.get("start_date", "2026-01-01")
    end_date = body.get("end_date", "2026-04-01")
    
    # Create backtest config
    config = BacktestConfig(
        symbols=[symbol],
        start_date=start_date,
        end_date=end_date,
        timeframe="30min",
        initial_capital=100000.0
    )
    
    # Run backtest
    rules_file = CONFIG_DIR_PATH / "rules.json"
    result = run_backtest(config, rules_file)
    
    return {
        "status": "ok",
        "result": result.to_dict()
    }


@app.post("/api/backtest")
async def api_backtest(body: dict):
    """Run a full backtest."""
    import sys
    backtest_src = str(Path(__file__).parent.parent / "system" / "tiger_engine" / "src")
    if backtest_src not in sys.path:
        sys.path.insert(0, backtest_src)
    
    from tiger_engine.backtest import BacktestConfig, run_backtest
    
    symbols = body.get("symbols", ["AAPL"])
    start_date = body.get("start_date", "2026-01-01")
    end_date = body.get("end_date", "2026-04-01")
    timeframe = body.get("timeframe", "30min")
    initial_capital = body.get("initial_capital", 100000.0)
    data_source = body.get("data_source", "yfinance")  # 'yfinance' 或 'tiger'
    
    config = BacktestConfig(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        timeframe=timeframe,
        initial_capital=initial_capital,
        data_source=data_source
    )
    
    rules_file = CONFIG_DIR_PATH / "rules.json"
    result = run_backtest(config, rules_file)
    
    return {
        "status": "ok",
        "result": result.to_dict()
    }


@app.get("/api/backtest/results")
async def api_backtest_results():
    """Get recent backtest results."""
    import json
    results_dir = RUNTIME_DIR / "backtest_results"
    if not results_dir.exists():
        return {"results": []}
    
    results = []
    for result_file in sorted(results_dir.glob("*.json"), reverse=True)[:10]:
        try:
            content = json.loads(result_file.read_text())
            results.append({
                "filename": result_file.name,
                "symbols": content.get("config", {}).get("symbols"),
                "return_pct": content.get("total_return_pct"),
                "total_trades": content.get("total_trades")
            })
        except Exception:
            continue
    
    return {"results": results}


@app.get("/api/rules/history")
async def api_rules_history():
    """Get rules change history."""
    import json
    backup_dir = CONFIG_DIR_PATH / "rules_backup"
    if not backup_dir.exists():
        return {"history": []}
    
    history = []
    for backup_file in sorted(backup_dir.glob("rules_*.json"), reverse=True)[:10]:
        try:
            content = json.loads(backup_file.read_text())
            history.append({
                "filename": backup_file.name,
                "updated_at": content.get("updated_at"),
                "rule_count": len(content.get("rules", []))
            })
        except Exception:
            continue
    
    return {"history": history}


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


@app.get("/api/quote-providers")
async def api_quote_providers():
    """List available quote providers."""
    return {
        "providers": [
            {"id": "yfinance", "name": "Yahoo Finance", "desc": "免费，有延迟"},
            {"id": "tiger", "name": "Tiger API", "desc": "需要行情权限"},
        ],
        "current": cache._quote_provider.name if cache else None,
    }


@app.get("/api/market-status")
async def api_market_status():
    """Get market open/close status for US and HK markets."""
    import datetime
    import pytz
    
    # Get current time in market timezones
    now = datetime.datetime.now(pytz.UTC)
    
    # US market (Eastern Time)
    us_tz = pytz.timezone("America/New_York")
    us_now = now.astimezone(us_tz)
    us_hour = us_now.hour + us_now.minute / 60
    us_weekday = us_now.weekday()  # 0=Monday, 4=Friday
    
    # US market hours: 9:30 - 16:00 ET (9.5 - 16.0)
    us_open = us_weekday < 5 and 9.5 <= us_hour < 16.0
    us_pre_market = us_weekday < 5 and 4.0 <= us_hour < 9.5
    us_post_market = us_weekday < 5 and 16.0 <= us_hour < 20.0
    
    # HK market (Hong Kong Time)
    hk_tz = pytz.timezone("Asia/Hong_Kong")
    hk_now = now.astimezone(hk_tz)
    hk_hour = hk_now.hour + hk_now.minute / 60
    hk_weekday = hk_now.weekday()
    
    # HK market hours: 9:30 - 16:00 HK time (9.5 - 16.0), lunch 12:00-13:00
    hk_open = hk_weekday < 5 and 9.5 <= hk_hour < 16.0 and not (12.0 <= hk_hour < 13.0)
    
    return {
        "US": {
            "open": us_open,
            "pre_market": us_pre_market,
            "post_market": us_post_market,
            "local_time": us_now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "status": "open" if us_open else ("pre-market" if us_pre_market else ("post-market" if us_post_market else "closed")),
        },
        "HK": {
            "open": hk_open,
            "local_time": hk_now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "status": "open" if hk_open else "closed",
        },
    }


@app.post("/api/quote-provider")
async def api_quote_provider(body: dict):
    """Switch quote provider."""
    provider = body.get("provider")
    if provider not in ("yfinance", "tiger"):
        return JSONResponse({"error": "invalid provider"}, status_code=400)
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    try:
        new_provider = get_quote_provider(provider, config_dir=str(CONFIG_DIR_PATH))
        cache._quote_provider = new_provider
        return {"status": "ok", "provider": provider, "name": new_provider.name}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# --- Tiger config management ---

TIGER_PROPS_FILE = CONFIG_DIR_PATH / "tiger_openapi_config.properties"

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


def _get_api_account_info(config_dir: str) -> dict:
    """Get account info from Tiger API (matches config account)."""
    try:
        from .tiger_client import TigerClient
        client = TigerClient(config_dir=config_dir)
        return client.get_account_type()
    except Exception as e:
        return {"error": str(e)}


def _account_type_to_mode(account_type: str) -> str | None:
    """Map account_type to mode. Returns None if uncertain."""
    at = str(account_type).upper().strip()
    if at == "PAPER":
        return "paper"
    if at in ("GLOBAL", "STANDARD"):
        return "live"
    return None


@app.get("/api/tiger-config")
async def api_tiger_config_get():
    """Get current Tiger API config (sensitive fields masked)."""
    if not TIGER_PROPS_FILE.exists():
        return {"exists": False, "mode": "paper", "fields": {}, "account_info": None}
    props = _parse_properties(TIGER_PROPS_FILE.read_text())
    masked = {}
    sensitive = {"private_key_pk1", "private_key_pk8", "secret_key"}
    for k, v in props.items():
        if k in sensitive:
            masked[k] = _mask_value(v)
        else:
            masked[k] = v
    # Read mode from app_config (fallback)
    config_file = CONFIG_DIR_PATH / "app_config.docker.json"
    mode = "paper"
    if config_file.exists():
        try:
            mode = json.loads(config_file.read_text()).get("mode", "paper")
        except Exception:
            pass
    # Try API detection (non-fatal if fails)
    account_info = None
    try:
        account_info = _get_api_account_info(str(CONFIG_DIR_PATH))
        detected = _account_type_to_mode(account_info.get("account_type", ""))
        if detected:
            mode = detected
            if config_file.exists():
                try:
                    app_config = json.loads(config_file.read_text())
                    if app_config.get("mode") != mode:
                        app_config["mode"] = mode
                        config_file.write_text(json.dumps(app_config, indent=2, ensure_ascii=False))
                except Exception:
                    pass
    except Exception as e:
        account_info = {"error": str(e)}
    return {"exists": True, "mode": mode, "fields": masked, "account_info": account_info}


@app.post("/api/tiger-config/upload")
async def api_tiger_config_upload_file(file: UploadFile = File(...)):
    """Upload Tiger config file.
    
    Validates content, renames to tiger_openapi_config.properties,
    replaces existing file, then detects trading mode via API.
    """
    # Read file
    content_bytes = await file.read()
    
    # Size check (max 64KB — a properties file should be tiny)
    if len(content_bytes) > 64 * 1024:
        return JSONResponse({"error": "file too large (max 64KB)"}, status_code=400)
    
    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return JSONResponse({"error": "file must be UTF-8 text"}, status_code=400)
    
    # Parse and validate
    props = _parse_properties(content)
    required = {"tiger_id", "account"}
    missing = required - set(props.keys())
    if missing:
        return JSONResponse({"error": f"missing required fields: {', '.join(missing)}"}, status_code=400)
    
    # Validate field values are non-empty
    for key in required:
        if not props[key].strip():
            return JSONResponse({"error": f"{key} must not be empty"}, status_code=400)
    
    # Validate private key exists (PKCS8 preferred)
    has_key = "private_key_pk8" in props or "private_key_pk1" in props
    if not has_key:
        return JSONResponse({"error": "missing private key (private_key_pk8 or private_key_pk1)"}, status_code=400)
    
    # Backup existing file
    if TIGER_PROPS_FILE.exists():
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = CONFIG_DIR_PATH / f"tiger_openapi_config.properties.bak.{ts}"
        backup.write_text(TIGER_PROPS_FILE.read_text())
    
    # Write new config (always as tiger_openapi_config.properties)
    TIGER_PROPS_FILE.write_text(content)
    
    # Reinitialize TigerClient and DataCache with new credentials
    global tiger_client, cache
    if cache:
        cache.stop()
    try:
        from .tiger_client import TigerClient as TC
        from .data_cache import DataCache as DC
        tiger_client = TC(config_dir=str(CONFIG_DIR_PATH))
        provider_name = os.environ.get("TIGER_QUOTE_PROVIDER", "yfinance")
        quote_provider = get_quote_provider(provider_name, config_dir=str(CONFIG_DIR_PATH))
        cache = DC(tiger_client, quote_provider, refresh_interval=30)
        cache.start()
    except Exception as e:
        tiger_client = None
        cache = None
    
    # Detect mode from API (non-fatal)
    account_info = None
    detected = None
    if tiger_client:
        try:
            account_info = _get_api_account_info(str(CONFIG_DIR_PATH))
            detected = _account_type_to_mode(account_info.get("account_type", ""))
            if detected:
                config_file = CONFIG_DIR_PATH / "app_config.docker.json"
                if config_file.exists():
                    app_config = json.loads(config_file.read_text())
                    app_config["mode"] = detected
                    config_file.write_text(json.dumps(app_config, indent=2, ensure_ascii=False))
        except Exception as e:
            account_info = {"error": str(e)}
    
    return {
        "status": "ok",
        "filename": TIGER_PROPS_FILE.name,
        "tiger_id": props.get("tiger_id"),
        "account": props.get("account"),
        "has_private_key": has_key,
        "account_info": account_info,
        "detected_mode": detected,
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
