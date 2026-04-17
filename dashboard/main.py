"""Agent Trading Dashboard - FastAPI entry point."""

import json
import os
from datetime import date, datetime
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .broker_client import BrokerClient
from .tiger_client import TigerClient as DefaultBrokerClient
from .data_cache import DataCache
from .quote_provider import get_quote_provider
from .scheduler import SignalScheduler
from .normalize import get_normalizer, available_brokers
from .service_logs import append_service_log
from .trading_day import get_us_trading_day_status
from system.engine.src.engine.config import (
    load_app_config_raw,
    merge_user_settings,
)

# --- App lifecycle ---

broker_client: BrokerClient | None = None
cache: DataCache | None = None
scheduler: SignalScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop the data cache on app lifecycle."""
    global broker_client, cache

    config_dir = os.environ.get(
        "ENGINE_CONFIG_DIR",
        str(Path(__file__).parent.parent / "config"),
    )

    # Broker client may fail if credentials are invalid - don't crash the app
    try:
        broker_client = DefaultBrokerClient(config_dir=str(BROKER_PROPERTIES_DIR))
        append_service_log(
            "dashboard",
            "info",
            "Broker client initialized",
            kind="startup",
            config_dir=str(BROKER_PROPERTIES_DIR),
        )
    except Exception as e:
        broker_client = None
        print(f"[dashboard] BrokerClient init failed: {e}")
        append_service_log(
            "dashboard",
            "warning",
            "Broker client init failed",
            kind="startup_warning",
            error=str(e),
            config_dir=str(BROKER_PROPERTIES_DIR),
        )

    # Quote provider: ENGINE_QUOTE_PROVIDER env var (default: yfinance)
    provider_name = os.environ.get("ENGINE_QUOTE_PROVIDER", "yfinance")
    quote_provider = get_quote_provider(provider_name, config_dir=config_dir)

    if broker_client:
        cache = DataCache(broker_client, quote_provider, refresh_interval=30)
        cache.start()
        append_service_log(
            "dashboard",
            "info",
            "Data cache started",
            kind="startup",
            provider=provider_name,
            refresh_interval=30,
        )
    else:
        cache = None
        print("[dashboard] DataCache not started (no broker client)")
        append_service_log(
            "dashboard",
            "warning",
            "Data cache not started",
            kind="startup_warning",
            reason="no_broker_client",
            provider=provider_name,
        )

    # Start signal scheduler
    global scheduler
    app_config = os.environ.get(
        "ENGINE_APP_CONFIG",
        str(Path(config_dir) / "app_config.docker.json"),
    )
    runtime_dir = os.environ.get(
        "ENGINE_RUNTIME_DIR",
        str(Path(__file__).parent.parent / "runtime" / "engine"),
    )
    scheduler_provider = os.environ.get("ENGINE_SCHEDULER_PROVIDER", provider_name)
    scheduler_interval = int(os.environ.get("ENGINE_SCHEDULER_INTERVAL", "60"))

    try:
        scheduler = SignalScheduler(
            app_config_path=app_config,
            runtime_dir=runtime_dir,
            provider_name=scheduler_provider,
            interval_seconds=scheduler_interval,
        )
        scheduler.start()
        append_service_log(
            "dashboard",
            "info",
            "Scheduler started from dashboard lifespan",
            kind="startup",
            app_config=app_config,
            runtime_dir=runtime_dir,
            provider=scheduler_provider,
            interval_seconds=scheduler_interval,
        )
    except Exception as e:
        scheduler = None
        print(f"[dashboard] Scheduler init failed: {e}")
        append_service_log(
            "dashboard",
            "error",
            "Scheduler init failed",
            kind="startup_error",
            error=str(e),
            app_config=app_config,
            runtime_dir=runtime_dir,
            provider=scheduler_provider,
        )

    yield

    if scheduler:
        scheduler.stop()
        append_service_log(
            "dashboard",
            "info",
            "Scheduler stopped from dashboard lifespan",
            kind="shutdown",
        )
    if cache:
        cache.stop()
        append_service_log(
            "dashboard",
            "info",
            "Data cache stopped",
            kind="shutdown",
        )


app = FastAPI(
    title="Agent Trading Dashboard",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_service_exceptions(request, call_next):
    try:
        response = await call_next(request)
    except Exception as e:
        append_service_log(
            "dashboard",
            "error",
            "Unhandled request exception",
            kind="request_exception",
            method=request.method,
            path=str(request.url.path),
            query=str(request.url.query),
            error=str(e),
        )
        raise

    if response.status_code >= 500:
        append_service_log(
            "dashboard",
            "error",
            "Request returned server error",
            kind="request_error",
            method=request.method,
            path=str(request.url.path),
            query=str(request.url.query),
            status_code=response.status_code,
        )
    return response

# --- Static files ---

STATIC_DIR = Path(__file__).parent / "static"


def serve_static_html(filename: str):
    return FileResponse(
        STATIC_DIR / filename,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/")
async def index():
    """Serve dashboard HTML."""
    return serve_static_html("index.html")


@app.get("/logs")
async def logs_page():
    """Serve logs dashboard HTML."""
    return serve_static_html("logs.html")


@app.get("/strategy")
async def strategy_page():
    """Serve strategy hub HTML."""
    return serve_static_html("strategy.html")


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
    return _current_normalizer().account(cache.get_account())


@app.get("/api/positions")
async def api_positions():
    """Current positions."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return _current_normalizer().positions(cache.get_positions())


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
    return _current_normalizer().orders(cache.get_orders())


@app.get("/api/pnl")
async def api_pnl():
    """P&L summary."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return _current_normalizer().pnl(cache.get_pnl())


@app.get("/api/stock-analysis")
async def api_stock_analysis(period: str = "all"):
    """Per-symbol analysis for a selected time range."""
    if not cache:
        return JSONResponse({"error": "not ready"}, status_code=503)
    return cache.get_stock_analysis(period=period)


@app.get("/api/trading-day")
async def api_trading_day(date_str: str | None = None, market: str = "US"):
    """Check whether the target day is a trading day using an online calendar source."""
    normalized_market = market.upper()
    if normalized_market != "US":
        return JSONResponse({"error": "unsupported market"}, status_code=400)

    try:
        target_date = date.fromisoformat(date_str) if date_str else None
    except ValueError:
        return JSONResponse({"error": "invalid date, expected YYYY-MM-DD"}, status_code=400)

    try:
        status = get_us_trading_day_status(target_date=target_date)
    except Exception as e:
        append_service_log(
            "dashboard",
            "warning",
            "Trading day lookup failed",
            kind="online_lookup_warning",
            market=normalized_market,
            date=date_str,
            error=str(e),
        )
        return JSONResponse(
            {
                "market": normalized_market,
                "date": target_date.isoformat() if target_date else None,
                "error": "online lookup failed",
                "detail": str(e),
            },
            status_code=503,
        )

    return status.__dict__


@app.get("/api/lookup/{symbol}")
async def api_lookup_symbol(symbol: str):
    """Lookup stock name from yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol.upper())
        info = t.info or {}
        name = info.get("shortName") or info.get("longName") or symbol.upper()
        return {"symbol": symbol.upper(), "name": name}
    except Exception:
        return {"symbol": symbol.upper(), "name": symbol.upper()}



@app.get("/api/market-status")
async def api_market_status():
    """US market status: trading day + current session (ET-based)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")
    now_et = datetime.now(et)

    # Trading day: weekday Mon-Fri
    is_weekday = now_et.weekday() < 5  # 0=Mon, 4=Fri

    # TODO: exclude US market holidays (2026 calendar)
    # For now, weekday = trading day
    is_trading_day = is_weekday

    # Session detection (ET times)
    hour = now_et.hour
    minute = now_et.minute
    t = hour * 60 + minute  # minutes from midnight

    if not is_trading_day:
        session = "closed"
        session_label = "休市"
    elif 240 <= t < 570:  # 4:00 - 9:30
        session = "premarket"
        session_label = "盘前"
    elif 570 <= t < 960:  # 9:30 - 16:00
        session = "regular"
        session_label = "开盘中"
    elif 960 <= t < 1200:  # 16:00 - 20:00
        session = "afterhours"
        session_label = "盘后"
    else:
        session = "closed"
        session_label = "闭市"

    # Today's date in ET (for day boundary)
    today_et = now_et.strftime("%Y-%m-%d")

    return {
        "is_trading_day": is_trading_day,
        "session": session,
        "session_label": session_label,
        "date_et": today_et,
        "now_et": now_et.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "timezone": str(now_et.tzinfo),
        "is_dst": bool(now_et.dst() and now_et.dst().total_seconds() > 0),
    }

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

RUNTIME_DIR = Path(os.environ.get("ENGINE_RUNTIME_DIR", str(Path(__file__).parent.parent / "runtime")))
CONFIG_DIR_PATH = Path(os.environ.get("ENGINE_CONFIG_DIR", str(Path(__file__).parent.parent / "config")))
RULES_DIR = Path(os.environ.get("ENGINE_RULES_DIR", str(Path(__file__).parent.parent / "rules")))
NEWS_DIR_PATH = Path(os.environ.get("ENGINE_NEWS_DIR", str(Path(__file__).parent.parent / "news")))
BROKER_PROPERTIES_DIR = Path(
    os.environ.get(
        "BROKER_PROPERTIES_DIR",
        os.environ.get("TIGER_PROPERTIES_DIR", str(Path(__file__).parent.parent / "properties")),
    )
)
LOGS_ROOT = Path(os.environ.get("ENGINE_LOGS_DIR", str(Path(__file__).parent.parent / "logs")))
ARTIFACTS_ROOT = Path(os.environ.get("ENGINE_ARTIFACTS_DIR", str(Path(__file__).parent.parent / "artifacts")))
BROKER_ARTIFACTS_DIR = ARTIFACTS_ROOT / "broker"
WATCHER_ARTIFACTS_DIR = ARTIFACTS_ROOT / "watcher"
NEWSWIRE_ARTIFACTS_DIR = ARTIFACTS_ROOT / "newswire"
EXECUTOR_ARTIFACTS_DIR = ARTIFACTS_ROOT / "executor"
SCOUT_ARTIFACTS_DIR = ARTIFACTS_ROOT / "scout"
CLOSER_ARTIFACTS_DIR = ARTIFACTS_ROOT / "closer"
AUDIT_LOG_DIR = LOGS_ROOT / "audit"
SERVICE_LOG_DIR = LOGS_ROOT / "service"
LATEST_LOG_DIR = LOGS_ROOT / "latest"
STRATEGIST_LOG_DIR = LOGS_ROOT / "agents" / "strategist"
STRATEGIST_ITERATIONS_LOG_DIR = STRATEGIST_LOG_DIR / "iterations"
STRATEGIST_ARTIFACTS_DIR = ARTIFACTS_ROOT / "strategist"
STRATEGIST_MEMORY_DIR = STRATEGIST_ARTIFACTS_DIR / "memory"
STRATEGIST_ITERATIONS_ARTIFACT_DIR = STRATEGIST_ARTIFACTS_DIR / "iterations"
LEGACY_LOG_DIR = RUNTIME_DIR / "logs"


def _ensure_logs_layout():
    for path in (LOGS_ROOT, AUDIT_LOG_DIR, SERVICE_LOG_DIR, LATEST_LOG_DIR, STRATEGIST_ITERATIONS_LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def _ensure_artifacts_layout():
    for path in (
        ARTIFACTS_ROOT,
        BROKER_ARTIFACTS_DIR,
        WATCHER_ARTIFACTS_DIR,
        NEWSWIRE_ARTIFACTS_DIR,
        STRATEGIST_ARTIFACTS_DIR,
        STRATEGIST_MEMORY_DIR,
        STRATEGIST_ITERATIONS_ARTIFACT_DIR,
        EXECUTOR_ARTIFACTS_DIR,
        SCOUT_ARTIFACTS_DIR,
        CLOSER_ARTIFACTS_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _app_config_file() -> Path:
    return CONFIG_DIR_PATH / "app_config.docker.json"


def _load_effective_app_config() -> dict[str, Any]:
    return load_app_config_raw(_app_config_file())


def _merge_app_user_settings(updates: dict[str, Any]) -> tuple[dict[str, Any], Path]:
    return merge_user_settings(_app_config_file(), updates)


def _current_broker_platform() -> str:
    env_broker = os.environ.get("ENGINE_BROKER")
    if env_broker:
        return env_broker
    try:
        config = _load_effective_app_config()
        broker = config.get("broker", {})
        if isinstance(broker, dict):
            platform = broker.get("platform")
            if platform:
                return str(platform)
    except Exception:
        pass
    return "tiger"


def _current_normalizer():
    return get_normalizer(_current_broker_platform())


def _first_existing_path(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def _candidate_log_dirs(include_legacy: bool = True) -> list[Path]:
    dirs = [AUDIT_LOG_DIR, SERVICE_LOG_DIR]
    if include_legacy:
        dirs.append(LEGACY_LOG_DIR)
    return dirs


def _iter_log_files() -> list[tuple[str, Path]]:
    items: list[tuple[str, Path]] = []
    seen: set[tuple[str, str]] = set()
    for log_dir in _candidate_log_dirs():
        if not log_dir.exists():
            continue
        section = "audit" if log_dir == AUDIT_LOG_DIR else "service" if log_dir == SERVICE_LOG_DIR else "legacy"
        for path in sorted(log_dir.glob("*.jsonl")):
            key = (section, path.stem)
            if key in seen:
                continue
            seen.add(key)
            items.append((section, path))
    return items


def _resolve_log_file(log_name: str) -> tuple[str, Path] | None:
    for section, path in _iter_log_files():
        if path.stem == log_name:
            return section, path
    return None


def _file_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "path": str(path),
            "modified": None,
            "size": None,
        }
    stat = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "size": stat.st_size,
    }


def _safe_read_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _write_json_file(path: Path, payload: dict[str, Any] | list[Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


def _tail_jsonl_info(path: Path) -> dict[str, Any]:
    meta = _file_meta(path)
    info = {
        "path": meta["path"],
        "exists": meta["exists"],
        "modified": meta["modified"],
        "size": meta["size"],
        "lines": None,
        "last_ts": None,
    }
    if not path.exists():
        return info
    try:
        if meta["size"] is not None and meta["size"] < 1_000_000:
            lines = path.read_text().splitlines()
            info["lines"] = len(lines)
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    break
                info["last_ts"] = entry.get("ts") or entry.get("generated_at")
                break
    except Exception:
        pass
    return info


def _snapshot_source_map() -> dict[str, Path]:
    return {
        "engine_cycle": RUNTIME_DIR / ".last_execution_cycle.json",
        "market_context": RUNTIME_DIR / "market_context.json",
        "control_state": RUNTIME_DIR / "state" / "control_state.json",
        "execution_state": RUNTIME_DIR / "state" / "execution_state.json",
    }


def _sync_latest_snapshots() -> dict[str, Any]:
    _ensure_logs_layout()
    snapshots: dict[str, Any] = {}
    for name, source in _snapshot_source_map().items():
        target = LATEST_LOG_DIR / f"{name}.json"
        payload = _safe_read_json(source)
        meta = _file_meta(source)
        snapshots[name] = {
            **meta,
            "target": str(target),
            "synced": payload is not None,
        }
        if payload is not None:
            _write_json_file(target, payload)
    return snapshots


def _build_agents_status() -> dict[str, Any]:
    watcher_latest = _first_existing_path(
        WATCHER_ARTIFACTS_DIR / "latest.json",
        RUNTIME_DIR / "watcher" / "latest.json",
    )
    watcher_history = _first_existing_path(
        WATCHER_ARTIFACTS_DIR / "history.jsonl",
        RUNTIME_DIR / "watcher" / "history.jsonl",
    )
    newswire_latest = _first_existing_path(
        NEWSWIRE_ARTIFACTS_DIR / "latest.json",
        RUNTIME_DIR / "newswire" / "latest.json",
    )
    newswire_history = _first_existing_path(
        NEWSWIRE_ARTIFACTS_DIR / "history.jsonl",
        RUNTIME_DIR / "newswire" / "history.jsonl",
    )
    strategist_latest = _first_existing_path(
        STRATEGIST_ARTIFACTS_DIR / "strategy_plan_latest.json",
        RUNTIME_DIR / "strategy_plan_latest.json",
    )
    strategist_history = _first_existing_path(
        STRATEGIST_ARTIFACTS_DIR / "strategy_plan_history.jsonl",
        RUNTIME_DIR / "strategy_plan_history.jsonl",
    )
    agents = {
        "watcher": {
            "service_log": _tail_jsonl_info(SERVICE_LOG_DIR / "watcher.jsonl"),
            "latest_output": _file_meta(watcher_latest),
            "history_output": _file_meta(watcher_history),
            "latest_output_artifact": _file_meta(WATCHER_ARTIFACTS_DIR / "latest.json"),
            "history_output_artifact": _file_meta(WATCHER_ARTIFACTS_DIR / "history.jsonl"),
        },
        "newswire": {
            "latest_output": _file_meta(newswire_latest),
            "history_output": _file_meta(newswire_history),
            "latest_output_artifact": _file_meta(NEWSWIRE_ARTIFACTS_DIR / "latest.json"),
            "history_output_artifact": _file_meta(NEWSWIRE_ARTIFACTS_DIR / "history.jsonl"),
        },
        "strategist": {
            "latest_output": _file_meta(strategist_latest),
            "history_output": _file_meta(strategist_history),
            "latest_output_artifact": _file_meta(STRATEGIST_ARTIFACTS_DIR / "strategy_plan_latest.json"),
            "history_output_artifact": _file_meta(STRATEGIST_ARTIFACTS_DIR / "strategy_plan_history.jsonl"),
            "memory_latest_artifact": _file_meta(STRATEGIST_MEMORY_DIR / "latest.json"),
            "memory_history_artifact": _file_meta(STRATEGIST_MEMORY_DIR / "history.jsonl"),
            "iterations_artifact": _file_meta(STRATEGIST_ITERATIONS_ARTIFACT_DIR),
            "iterations_runtime": _file_meta(RUNTIME_DIR / "strategist_iterations"),
            "iterations_logs": _file_meta(STRATEGIST_ITERATIONS_LOG_DIR),
        },
        "executor": {
            "latest_output": _file_meta(_first_existing_path(EXECUTOR_ARTIFACTS_DIR / "checklist_latest.json", RUNTIME_DIR / "executor_checklist_latest.json")),
            "history_output": _file_meta(_first_existing_path(EXECUTOR_ARTIFACTS_DIR / "checklist_history.jsonl", RUNTIME_DIR / "executor_checklist_history.jsonl")),
            "latest_output_artifact": _file_meta(EXECUTOR_ARTIFACTS_DIR / "checklist_latest.json"),
            "history_output_artifact": _file_meta(EXECUTOR_ARTIFACTS_DIR / "checklist_history.jsonl"),
        },
        "scout": {
            "latest_output": _file_meta(_first_existing_path(SCOUT_ARTIFACTS_DIR / "candidates_latest.json", RUNTIME_DIR / "scout_candidates_latest.json")),
            "history_output": _file_meta(_first_existing_path(SCOUT_ARTIFACTS_DIR / "candidates_history.jsonl", RUNTIME_DIR / "scout_candidates_history.jsonl")),
            "latest_output_artifact": _file_meta(SCOUT_ARTIFACTS_DIR / "candidates_latest.json"),
            "history_output_artifact": _file_meta(SCOUT_ARTIFACTS_DIR / "candidates_history.jsonl"),
        },
        "closer": {
            "latest_output": _file_meta(_first_existing_path(CLOSER_ARTIFACTS_DIR / "summary_latest.json", RUNTIME_DIR / "closer_summary_latest.json")),
            "history_output": _file_meta(_first_existing_path(CLOSER_ARTIFACTS_DIR / "summary_history.jsonl", RUNTIME_DIR / "closer_summary_history.jsonl")),
            "latest_output_artifact": _file_meta(CLOSER_ARTIFACTS_DIR / "summary_latest.json"),
            "history_output_artifact": _file_meta(CLOSER_ARTIFACTS_DIR / "summary_history.jsonl"),
            "outbox": _file_meta(RUNTIME_DIR.parent / "outbox" / "closer_outbox.json"),
        },
    }
    status = {
        "generated_at": datetime.now().isoformat(),
        "agents": agents,
    }
    _write_json_file(LATEST_LOG_DIR / "agents_status.json", status)
    return status


def _build_logs_overview() -> dict[str, Any]:
    snapshots = _sync_latest_snapshots()
    _ensure_artifacts_layout()
    agent_status = _build_agents_status()
    sections = {
        "audit": [_tail_jsonl_info(path) for path in sorted(AUDIT_LOG_DIR.glob("*.jsonl"))],
        "service": [_tail_jsonl_info(path) for path in sorted(SERVICE_LOG_DIR.glob("*.jsonl"))],
        "legacy": [_tail_jsonl_info(path) for path in sorted(LEGACY_LOG_DIR.glob("*.jsonl"))] if LEGACY_LOG_DIR.exists() else [],
    }
    overview = {
        "generated_at": datetime.now().isoformat(),
        "logs_root": str(LOGS_ROOT),
        "latest_dir": str(LATEST_LOG_DIR),
        "sections": sections,
        "latest_snapshots": snapshots,
        "agents_status_file": str(LATEST_LOG_DIR / "agents_status.json"),
        "agents_status": agent_status,
    }
    _write_json_file(LATEST_LOG_DIR / "logs_overview.json", overview)
    return overview


def _read_jsonl_tail_entries(path: Path, limit: int = 10) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        text = path.read_text()
    except Exception:
        return []
    entries: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        try:
            item, next_idx = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            next_obj = text.find("{", idx + 1)
            if next_obj == -1:
                break
            idx = next_obj
            continue
        if isinstance(item, dict):
            item["_source"] = path.name
            entries.append(item)
        else:
            entries.append({"_raw": str(item), "_source": path.name})
        idx = next_idx
    if limit <= 0:
        return []
    return list(reversed(entries[-limit:]))


def _sorted_json_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    try:
        return sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return list(directory.glob("*.json"))


def _build_strategy_overview() -> dict[str, Any]:
    config = _load_effective_app_config()
    rules_doc = _safe_read_json(RULES_FILE) or {"rules": [], "global_settings": {}}
    cycle = _safe_read_json(RUNTIME_DIR / ".last_execution_cycle.json") or {}
    control = _read_control_state()
    latest_plan_path = _first_existing_path(
        STRATEGIST_ARTIFACTS_DIR / "strategy_plan_latest.json",
        RUNTIME_DIR / "strategy_plan_latest.json",
    )
    latest_plan = _safe_read_json(latest_plan_path) or {}

    rules = rules_doc.get("rules", []) if isinstance(rules_doc, dict) else []
    rules_by_id = {
        rule.get("rule_id"): rule
        for rule in rules
        if isinstance(rule, dict) and rule.get("rule_id")
    }

    symbol_name_map = {
        item.get("symbol"): item.get("name")
        for item in (config.get("strategy", {}).get("symbols", []) if isinstance(config, dict) else [])
        if isinstance(item, dict) and item.get("symbol")
    }

    raw_signals = cycle.get("strategy", {}).get("signals", []) if isinstance(cycle, dict) else []
    signal_records: list[dict[str, Any]] = []
    signal_counts_by_rule: dict[str, dict[str, int]] = {}
    signal_totals = {"BUY": 0, "EXIT": 0, "HOLD": 0, "total": 0}

    for index, signal in enumerate(raw_signals if isinstance(raw_signals, list) else []):
        if not isinstance(signal, dict):
            continue
        rule_id = signal.get("rule_id") or "unknown"
        action = (signal.get("action") or "HOLD").upper()
        rule = rules_by_id.get(rule_id, {})
        bucket = signal_counts_by_rule.setdefault(rule_id, {"BUY": 0, "EXIT": 0, "HOLD": 0, "total": 0})
        bucket[action if action in bucket else "HOLD"] += 1
        bucket["total"] += 1
        signal_totals[action if action in signal_totals else "HOLD"] += 1
        signal_totals["total"] += 1
        signal_records.append({
            "index": index,
            "rule_id": rule_id,
            "rule_name": rule.get("name"),
            "rule_enabled": bool(rule.get("enabled", True)),
            "rule_priority": rule.get("priority"),
            "timeframe": rule.get("timeframe") or cycle.get("strategy", {}).get("timeframe"),
            "symbol": signal.get("symbol"),
            "symbol_name": symbol_name_map.get(signal.get("symbol")),
            "market": signal.get("market"),
            "action": action,
            "score": signal.get("score"),
            "reason": signal.get("reason"),
            "order_type": signal.get("order_type"),
            "last_close": signal.get("last_close"),
            "diagnostics": signal.get("diagnostics") if isinstance(signal.get("diagnostics"), dict) else {},
        })

    signal_records.sort(
        key=lambda item: (
            0 if item["action"] == "BUY" else 1 if item["action"] == "EXIT" else 2,
            0 if item["rule_enabled"] else 1,
            item["rule_priority"] if item["rule_priority"] is not None else 999,
            item["symbol"] or "",
            item["rule_id"] or "",
        )
    )

    rules_summary: list[dict[str, Any]] = []
    for rule in rules if isinstance(rules, list) else []:
        if not isinstance(rule, dict):
            continue
        rule_id = rule.get("rule_id") or ""
        counts = signal_counts_by_rule.get(rule_id, {"BUY": 0, "EXIT": 0, "HOLD": 0, "total": 0})
        rules_summary.append({
            "rule_id": rule_id,
            "name": rule.get("name"),
            "description": rule.get("description"),
            "enabled": bool(rule.get("enabled", True)),
            "priority": rule.get("priority"),
            "timeframe": rule.get("timeframe"),
            "markets": rule.get("markets", []),
            "symbols": rule.get("symbols", []),
            "entry_action": rule.get("entry", {}).get("action") if isinstance(rule.get("entry"), dict) else None,
            "exit_action": rule.get("exit", {}).get("action") if isinstance(rule.get("exit"), dict) else None,
            "signal_counts": counts,
        })

    rules_summary.sort(key=lambda item: (0 if item["enabled"] else 1, item["priority"] if item["priority"] is not None else 999, item["rule_id"]))

    latest_plan_summary = {
        "plan_id": latest_plan.get("plan_id") or latest_plan.get("timestamp") or latest_plan.get("cycle_id"),
        "generated_at": latest_plan.get("generated_at") or latest_plan.get("timestamp"),
        "generator": latest_plan.get("generator"),
        "data_quality": latest_plan.get("data_quality"),
        "summary": latest_plan.get("summary") or latest_plan.get("notes") or latest_plan.get("type"),
        "timestamp": latest_plan.get("timestamp"),
        "shift": latest_plan.get("shift"),
        "type": latest_plan.get("type"),
        "actions": latest_plan.get("actions", []),
        "notes": latest_plan.get("notes", []),
        "strategy_recommendations": latest_plan.get("strategy_recommendations", []),
        "risk_management": latest_plan.get("risk_management"),
        "risk_notes": latest_plan.get("risk_notes", []),
        "fee_model_confidence": latest_plan.get("fee_model_confidence"),
        "action_items": latest_plan.get("action_items", []),
    } if isinstance(latest_plan, dict) else {}

    plan_history = []
    for history_path in (
        STRATEGIST_ARTIFACTS_DIR / "strategy_plan_history.jsonl",
        RUNTIME_DIR / "strategy_plan_history.jsonl",
    ):
        for entry in _read_jsonl_tail_entries(history_path, limit=6):
            if "_raw" in entry:
                continue
            plan_history.append({
                "source": entry.get("_source"),
                "plan_id": entry.get("plan_id") or entry.get("iteration_id"),
                "generated_at": entry.get("generated_at") or entry.get("timestamp") or entry.get("date"),
                "shift": entry.get("shift") or entry.get("type"),
                "summary": entry.get("summary") or entry.get("notes") or entry.get("data_notes", {}).get("recommendation"),
                "data_quality": entry.get("data_quality"),
                "raw": entry,
            })
        if plan_history:
            break

    iterations = []
    iter_dirs = [STRATEGIST_ITERATIONS_ARTIFACT_DIR, STRATEGIST_ITERATIONS_LOG_DIR, RUNTIME_DIR / "strategist_iterations"]
    seen_iteration_ids: set[str] = set()
    for directory in iter_dirs:
        for path in _sorted_json_files(directory):
            payload = _safe_read_json(path)
            if not isinstance(payload, dict):
                continue
            iteration_id = payload.get("iteration_id") or path.stem
            if iteration_id in seen_iteration_ids:
                continue
            seen_iteration_ids.add(iteration_id)
            results = payload.get("results", []) if isinstance(payload.get("results"), list) else []
            iterations.append({
                "iteration_id": iteration_id,
                "timestamp": payload.get("timestamp"),
                "symbols": payload.get("symbols", []),
                "period": payload.get("period"),
                "best": payload.get("best"),
                "result_count": len(results),
                "wins": sum(1 for item in results if isinstance(item, dict) and item.get("trades", 0) > 0 and item.get("return_pct", 0) > 0),
                "losses": sum(1 for item in results if isinstance(item, dict) and item.get("trades", 0) > 0 and item.get("return_pct", 0) <= 0),
                "source_path": str(path),
            })
            if len(iterations) >= 8:
                break
        if len(iterations) >= 8:
            break

    latest_cycle = {
        "cycle_id": cycle.get("cycle_id"),
        "timeframe": cycle.get("strategy", {}).get("timeframe") if isinstance(cycle.get("strategy"), dict) else None,
        "trading_mode": cycle.get("trading_mode"),
        "signal_count": signal_totals["total"],
        "buy_count": signal_totals["BUY"],
        "exit_count": signal_totals["EXIT"],
        "hold_count": signal_totals["HOLD"],
        "quote_access": cycle.get("quote_access"),
        "market_state": cycle.get("market_state"),
    }

    fee_calibration = _read_json_file(BROKER_ARTIFACTS_DIR / "fee_calibration_summary.json", {})
    if not isinstance(fee_calibration, dict) or not fee_calibration:
        fee_calibration_entries = [
            entry for entry in _read_jsonl_tail_entries(BROKER_ARTIFACTS_DIR / "fee_calibration.jsonl", limit=20)
            if "_raw" not in entry
        ]
        avg_fee_delta = (
            sum(float(entry.get("delta", 0) or 0) for entry in fee_calibration_entries) / len(fee_calibration_entries)
            if fee_calibration_entries else 0.0
        )
        max_abs_fee_delta = max(
            (abs(float(entry.get("delta", 0) or 0)) for entry in fee_calibration_entries),
            default=0.0,
        )
        fee_calibration = {
            "count": len(fee_calibration_entries),
            "avg_delta": round(avg_fee_delta, 6),
            "max_abs_delta": round(max_abs_fee_delta, 6),
            "recent": fee_calibration_entries[:8],
        }

    overview = {
        "generated_at": datetime.now().isoformat(),
        "config": {
            "mode": config.get("mode"),
            "markets": config.get("markets", []),
            "timeframe": config.get("strategy", {}).get("timeframe") if isinstance(config.get("strategy"), dict) else None,
            "watchlist_file": config.get("strategy", {}).get("watchlist_file") if isinstance(config.get("strategy"), dict) else None,
            "rules_path": config.get("strategy", {}).get("rules_path") if isinstance(config.get("strategy"), dict) else None,
        },
        "control": {
            "locked": control.get("locked", False),
            "trading_mode": control.get("trading_mode", "off"),
            "reason": control.get("reason"),
        },
        "latest_cycle": latest_cycle,
        "rules_meta": _file_meta(RULES_FILE),
        "rules_summary": rules_summary,
        "signal_records": signal_records,
        "latest_plan": latest_plan_summary,
        "plan_history": plan_history,
        "iterations": iterations,
        "fee_calibration": fee_calibration,
    }

    _ensure_logs_layout()
    _write_json_file(LATEST_LOG_DIR / "strategy_overview.json", overview)
    return overview


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
    config_file = _app_config_file()
    if not config_file.exists():
        return JSONResponse({"error": "config not found"}, status_code=404)
    return _load_effective_app_config()


@app.patch("/api/config")
async def api_config_update(update: dict):
    """Update engine config (risk params, markets, etc.)."""
    config_file = _app_config_file()
    if not config_file.exists():
        return JSONResponse({"error": "config not found"}, status_code=404)

    user_updates: dict[str, Any] = {}
    if "broker" in update and isinstance(update["broker"], dict):
        broker_update = dict(update["broker"])
        if "platform" in broker_update:
            platform = str(broker_update["platform"]).strip()
            if platform not in available_brokers():
                return JSONResponse(
                    {"error": f"invalid broker platform: {platform}", "available": available_brokers()},
                    status_code=400,
                )
            user_updates.setdefault("broker", {})["platform"] = platform
    if "risk" in update:
        user_updates["risk"] = update["risk"]
    if "markets" in update:
        user_updates["markets"] = update["markets"]
    if "strategy" in update and "timeframe" in update["strategy"]:
        user_updates.setdefault("strategy", {})["timeframe"] = update["strategy"]["timeframe"]
    if not user_updates:
        return {"status": "ok", "config": _load_effective_app_config()}

    _, settings_path = _merge_app_user_settings(user_updates)
    return {
        "status": "ok",
        "config": _load_effective_app_config(),
        "user_settings_path": str(settings_path),
    }


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
    """Reset paper account local state.

    Clears all local order tracking (submitted, previews, sync, history)
    so the system can trade freely after a paper account reset.
    Also locks the engine as a safety measure.
    """
    import json as _json
    from datetime import datetime as _dt

    state_file = RUNTIME_DIR / "state" / "execution_state.json"
    summary = {"cleared": {}, "backup": None}

    # Read current state
    if state_file.exists():
        try:
            state = _json.loads(state_file.read_text())
        except Exception:
            state = {}
    else:
        state = {}

    # Record counts before clearing
    submitted = state.get("submitted", {})
    previews = state.get("previews", {})
    sync = state.get("sync", {})
    history = state.get("history", [])

    summary["cleared"] = {
        "submitted": len(submitted),
        "previews": len(previews),
        "sync": len(sync),
        "history": len(history),
    }

    # Symbol breakdown
    symbols = {}
    for val in submitted.values():
        sym = val.get("symbol", "?")
        symbols[sym] = symbols.get(sym, 0) + 1
    summary["submitted_by_symbol"] = symbols

    # Backup before clearing
    if state_file.exists() and (submitted or previews or history):
        ts = _dt.now().strftime("%Y%m%d_%H%M%S")
        backup_file = RUNTIME_DIR / "state" / f"execution_state.bak.{ts}.json"
        backup_file.write_text(state_file.read_text())
        summary["backup"] = backup_file.name

    # Clear
    state["submitted"] = {}
    state["previews"] = {}
    state["sync"] = {}
    state["history"] = []
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(_json.dumps(state, indent=2, ensure_ascii=False))

    # Lock engine as safety measure
    ctrl = _read_control_state()
    ctrl["locked"] = True
    ctrl["reason"] = "paper_account_reset"
    ctrl["updated_by"] = "dashboard"
    ctrl["updated_at"] = _dt.now().isoformat()
    _write_control_state(ctrl)
    summary["engine_locked"] = True

    summary["status"] = "ok"
    return summary


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
    result = []
    # Read from JSONL audit files
    for log_dir in (AUDIT_LOG_DIR, LEGACY_LOG_DIR):
        if result or not log_dir.exists():
            continue
        for log_file in sorted(log_dir.glob("*.jsonl"), reverse=True):
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

RULES_FILE = RULES_DIR / "rules.json"


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
    markets: list[str] = ["US"]
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
        backup_dir = RULES_DIR / "rules_backup"
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
    backtest_src = str(Path(__file__).parent.parent / "system" / "engine" / "src")
    if backtest_src not in sys.path:
        sys.path.insert(0, backtest_src)

    from engine.backtest import BacktestConfig, run_backtest

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
        initial_capital=100000.0,
        data_source="yfinance"
    )

    # Run backtest
    rules_file = RULES_FILE
    result = run_backtest(config, rules_file)

    return {
        "status": "ok",
        "result": result.to_dict()
    }


def _clean_nan_values(obj):
    """递归清理 NaN/Inf 值,转换为 None"""
    import math
    if isinstance(obj, dict):
        return {k: _clean_nan_values(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_nan_values(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


@app.post("/api/backtest")
async def api_backtest(body: dict):
    """Run a full backtest (data source: configured market data provider)."""
    import sys
    backtest_src = str(Path(__file__).parent.parent / "system" / "engine" / "src")
    if backtest_src not in sys.path:
        sys.path.insert(0, backtest_src)

    from engine.backtest import BacktestConfig, run_backtest

    symbols = body.get("symbols", ["AAPL"])
    start_date = body.get("start_date", "2026-01-01")
    end_date = body.get("end_date", "2026-04-01")
    timeframe = body.get("timeframe", "30min")
    initial_capital = body.get("initial_capital", 100000.0)

    broker_platform = body.get("broker_platform") or _current_broker_platform()
    data_source = body.get("data_source") or broker_platform
    market = body.get("market", "US")

    config = BacktestConfig(
        symbols=symbols,
        start_date=start_date,
        end_date=end_date,
        timeframe=timeframe,
        initial_capital=initial_capital,
        data_source=data_source,
        broker_platform=broker_platform,
        market=market,
    )

    rules_file = RULES_FILE
    result = run_backtest(config, rules_file)

    # 清理 NaN/Inf 值,避免 JSON 序列化错误
    result_dict = _clean_nan_values(result.to_dict())

    return {
        "status": "ok",
        "result": result_dict
    }


@app.post("/api/backtest/batch")
async def api_backtest_batch(body: dict):
    """Run batch backtest with multiple parameter combinations.

    Input:
        symbols: ["AAPL", "NVDA"]
        start_date: "2026-01-07"
        end_date: "2026-04-07"
        timeframe: "30min"
        param_sets: [
            {"label": "baseline", "params": {}},
            {"label": "test1", "params": {"sma_short": 5, "sma_mid": 10, "sma_long": 15}},
            ...
        ]
    Output:
        results: [{"label", "params", "trades", "return_pct", "win_rate", "sharpe", "max_drawdown_pct"}]
        best: {label, params, return_pct}
    """
    import sys
    import json
    backtest_src = str(Path(__file__).parent.parent / "system" / "engine" / "src")
    if backtest_src not in sys.path:
        sys.path.insert(0, backtest_src)

    from engine.backtest import BacktestConfig, run_backtest

    symbols = body.get("symbols", ["AAPL"])
    start_date = body.get("start_date", "2026-01-07")
    end_date = body.get("end_date", "2026-04-07")
    timeframe = body.get("timeframe", "30min")
    broker_platform = body.get("broker_platform") or _current_broker_platform()
    data_source = body.get("data_source") or broker_platform
    market = body.get("market", "US")
    param_sets = body.get("param_sets", [])

    if not param_sets:
        return JSONResponse({"error": "param_sets is required"}, status_code=400)
    if len(param_sets) > 50:
        return JSONResponse({"error": "max 50 param_sets per batch"}, status_code=400)

    results = []
    for ps in param_sets:
        label = ps.get("label", f"set_{len(results)}")
        params = ps.get("params", {})
        try:
            # Load base rules and apply param overrides
            rules_file = RULES_FILE
            rules = json.loads(rules_file.read_text()) if rules_file.exists() else {"rules": []}
            if params:
                _apply_param_overrides(rules, params)
            # Write temp rules file
            tmp_rules = RULES_DIR / f"_batch_{label}.json"
            tmp_rules.write_text(json.dumps(rules, indent=2, ensure_ascii=False))

            config = BacktestConfig(
                symbols=symbols,
                start_date=start_date,
                end_date=end_date,
                timeframe=timeframe,
                initial_capital=100000.0,
                data_source=data_source,
                broker_platform=broker_platform,
                market=market,
            )
            bt_result = run_backtest(config, tmp_rules)
            bt_dict = _clean_nan_values(bt_result.to_dict())

            results.append({
                "label": label,
                "params": params,
                "trades": bt_dict.get("total_trades", 0),
                "return_pct": bt_dict.get("total_return_pct", 0),
                "win_rate": bt_dict.get("win_rate", 0),
                "sharpe": bt_dict.get("sharpe_ratio"),
                "max_drawdown_pct": bt_dict.get("max_drawdown_pct"),
                "winning_trades": bt_dict.get("winning_trades", 0),
                "losing_trades": bt_dict.get("losing_trades", 0),
                "commission_total": bt_dict.get("commission_total", 0),
                "slippage_total": bt_dict.get("slippage_total", 0),
                "transaction_cost_total": bt_dict.get("transaction_cost_total", 0),
                "fee_drag_pct": bt_dict.get("fee_drag_pct", 0),
            })

            # Cleanup temp file
            tmp_rules.unlink(missing_ok=True)
        except Exception as e:
            results.append({
                "label": label,
                "params": params,
                "error": str(e),
            })

    # Find best by net return, then prefer stronger sharpe and lower fee drag.
    valid = [r for r in results if "error" not in r and r.get("trades", 0) > 0]
    best = max(
        valid,
        key=lambda r: (
            r.get("return_pct", 0),
            r.get("sharpe") or float("-inf"),
            -(r.get("fee_drag_pct") or 0),
        ),
    ) if valid else None

    # Save iteration results
    iterations_dir = STRATEGIST_ITERATIONS_ARTIFACT_DIR
    legacy_iterations_dir = RUNTIME_DIR / "strategist_iterations"
    iterations_dir.mkdir(parents=True, exist_ok=True)
    legacy_iterations_dir.mkdir(parents=True, exist_ok=True)
    STRATEGIST_ITERATIONS_LOG_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import datetime as dt
    iter_id = f"iter_{dt.now().strftime('%Y%m%d_%H%M%S')}"
    iteration = {
        "iteration_id": iter_id,
        "timestamp": dt.now().isoformat(),
        "symbols": symbols,
        "period": f"{start_date} ~ {end_date}",
        "results": results,
        "best": best,
    }
    payload = json.dumps(iteration, indent=2, ensure_ascii=False)
    (iterations_dir / f"{iter_id}.json").write_text(payload)
    (iterations_dir / "latest.json").write_text(payload)
    (legacy_iterations_dir / f"{iter_id}.json").write_text(payload)
    (legacy_iterations_dir / "latest.json").write_text(payload)
    (STRATEGIST_ITERATIONS_LOG_DIR / f"{iter_id}.json").write_text(payload)
    (STRATEGIST_ITERATIONS_LOG_DIR / "latest.json").write_text(payload)

    return {"status": "ok", "iteration_id": iter_id, "results": results, "best": best}


def _apply_param_overrides(rules: dict, params: dict):
    """Apply parameter overrides to rules dict.

    Params use {rule_id}.{json_path} format:
        {"trend_follow_30m.entry.conditions.items.0.params.period": 5}

    Or shorthand names mapped to specific rules.
    """
    # Shorthand → (rule_id, json_path)
    param_map = {
        "trend_follow_enabled": ("trend_follow_30m", "enabled"),
        "rsi_enabled": ("rsi_reversal", "enabled"),
        "bollinger_enabled": ("bollinger_breakout", "enabled"),
        "sma_short": ("trend_follow_30m", "entry.conditions.items.0.params.period"),
        "sma_mid":   ("trend_follow_30m", "entry.conditions.items.1.params.period"),
        "sma_long":  ("trend_follow_30m", "entry.conditions.items.2.params.period"),
        "momentum_period": ("trend_follow_30m", "entry.conditions.items.3.params.period"),
        "momentum_threshold": ("trend_follow_30m", "entry.conditions.items.3.compare.value"),
        "bar_range_threshold": ("trend_follow_30m", "entry.conditions.items.4.compare.value"),
        "rsi_period": ("rsi_reversal", "entry.conditions.items.0.params.period"),
        "rsi_oversold": ("rsi_reversal", "entry.conditions.items.0.compare.value"),
        "rsi_overbought": ("rsi_reversal", "exit.conditions.items.0.compare.value"),
        "bb_period": ("bollinger_breakout", "entry.conditions.items.0.params.period"),
        "bb_std": ("bollinger_breakout", "entry.conditions.items.0.params.std_dev"),
        "volume_ratio": ("bollinger_breakout", "entry.conditions.items.1.ratio"),
        "rsi_sl": ("rsi_reversal", "exit.conditions.items.1.threshold_pct"),
        "bb_sl": ("bollinger_breakout", "exit.conditions.items.1.threshold_pct"),
    }

    rules_list = rules.get("rules", [])
    rules_by_id = {r.get("rule_id"): r for r in rules_list}

    for param_name, value in params.items():
        # Check shorthand first
        if param_name in param_map:
            rule_id, json_path = param_map[param_name]
        elif "." in param_name:
            # Direct: rule_id.path.to.field
            parts = param_name.split(".", 1)
            rule_id, json_path = parts[0], parts[1]
        else:
            continue

        rule = rules_by_id.get(rule_id)
        if not rule:
            continue

        # Navigate json_path
        path_keys = json_path.split(".")
        target = rule
        for key in path_keys[:-1]:
            if isinstance(target, dict):
                target = target.get(key)
            elif isinstance(target, list) and key.isdigit():
                idx = int(key)
                target = target[idx] if idx < len(target) else None
            else:
                target = None
                break
            if target is None:
                break

        last_key = path_keys[-1]
        if target is not None:
            if isinstance(target, dict):
                target[last_key] = value
            elif isinstance(target, list) and last_key.isdigit():
                idx = int(last_key)
                if idx < len(target):
                    target[idx] = value


@app.get("/api/backtest/results")
async def api_backtest_results():
    """Get recent backtest results."""
    import json
    results_dir = STRATEGIST_ITERATIONS_ARTIFACT_DIR
    legacy_results_dir = RUNTIME_DIR / "backtest_results"
    if not results_dir.exists() and not legacy_results_dir.exists():
        return {"results": []}

    results = []
    candidate_files = []
    if results_dir.exists():
        candidate_files.extend(sorted(results_dir.glob("*.json"), reverse=True))
    if legacy_results_dir.exists():
        candidate_files.extend(sorted(legacy_results_dir.glob("*.json"), reverse=True))

    for result_file in candidate_files[:10]:
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
    backup_dir = RULES_DIR / "rules_backup"
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


@app.get("/api/broker")
async def api_broker():
    """Current broker and available brokers."""
    return {
        "current": _current_broker_platform(),
        "available": available_brokers(),
    }


@app.get("/api/quote-providers")
async def api_quote_providers():
    """List available quote providers."""
    return {
        "providers": [
            {"id": "yfinance", "name": "Yahoo Finance", "desc": "免费,有延迟"},
            {"id": "tiger", "name": "Broker API", "desc": "需要行情权限"},
        ],
        "current": cache._quote_provider.name if cache else None,
    }


@app.get("/api/market-status")
async def api_market_status():
    """Get market open/close status for US market."""
    import datetime
    import pytz

    # Get current time in market timezone
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

    return {
        "US": {
            "open": us_open,
            "pre_market": us_pre_market,
            "post_market": us_post_market,
            "local_time": us_now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "status": "open" if us_open else ("pre-market" if us_pre_market else ("post-market" if us_post_market else "closed")),
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


# --- Broker config management ---

BROKER_PROPS_FILE = BROKER_PROPERTIES_DIR / "tiger_openapi_config.properties"

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


def _get_broker_account_info(config_dir: str) -> dict:
    """Get account info from the configured broker API (matches config account)."""
    try:
        from .tiger_client import TigerClient as DefaultBrokerClient
        client = DefaultBrokerClient(config_dir=config_dir)
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


@app.get("/api/broker-config")
@app.get("/api/tiger-config")
async def api_broker_config_get():
    """Get current broker API config (sensitive fields masked)."""
    if not BROKER_PROPS_FILE.exists():
        return {"exists": False, "mode": "paper", "broker_platform": _current_broker_platform(), "fields": {}, "account_info": None}
    props = _parse_properties(BROKER_PROPS_FILE.read_text())
    masked = {}
    sensitive = {"private_key_pk1", "private_key_pk8", "secret_key"}
    for k, v in props.items():
        if k in sensitive:
            masked[k] = _mask_value(v)
        else:
            masked[k] = v
    # Read mode from app_config (fallback)
    config_file = _app_config_file()
    mode = "paper"
    if config_file.exists():
        try:
            mode = _load_effective_app_config().get("mode", "paper")
        except Exception:
            pass
    broker_platform = _current_broker_platform()
    # Try API detection (non-fatal if fails)
    account_info = None
    try:
            account_info = _get_broker_account_info(str(BROKER_PROPERTIES_DIR))
            detected = _account_type_to_mode(account_info.get("account_type", ""))
            if detected:
                mode = detected
                if config_file.exists():
                    try:
                        effective = _load_effective_app_config()
                        if effective.get("mode") != mode:
                            _merge_app_user_settings({"mode": mode})
                    except Exception:
                        pass
    except Exception as e:
        account_info = {"error": str(e)}
    return {"exists": True, "mode": mode, "broker_platform": broker_platform, "fields": masked, "account_info": account_info}


@app.post("/api/broker-config/upload")
@app.post("/api/tiger-config/upload")
async def api_broker_config_upload_file(file: UploadFile = File(...)):
    """Upload broker config file.

    Validates content, writes to tiger_openapi_config.properties for compatibility,
    replaces existing file, then detects trading mode via API.
    """
    # Read file
    content_bytes = await file.read()

    # Size check (max 64KB - a properties file should be tiny)
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
    if BROKER_PROPS_FILE.exists():
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = BROKER_PROPERTIES_DIR / f"tiger_openapi_config.properties.bak.{ts}"
        backup.write_text(BROKER_PROPS_FILE.read_text())

    # Write new config (compatibility filename retained for the current broker SDK)
    BROKER_PROPS_FILE.write_text(content)

    # Clear execution state (idempotency keys) — account changed, old tracking is stale
    state_file = RUNTIME_DIR / "state" / "execution_state.json"
    state_cleared = False
    if state_file.exists():
        try:
            old_state = json.loads(state_file.read_text())
            old_submitted = len(old_state.get("submitted", {}))
            old_previews = len(old_state.get("previews", {}))
            old_history = len(old_state.get("history", []))
            if old_submitted or old_previews or old_history:
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                bak = RUNTIME_DIR / "state" / f"execution_state.bak.{ts}.json"
                bak.write_text(state_file.read_text())
                old_state["submitted"] = {}
                old_state["previews"] = {}
                old_state["sync"] = {}
                old_state["history"] = []
                state_file.write_text(json.dumps(old_state, indent=2, ensure_ascii=False))
                state_cleared = True
        except Exception:
            pass

    # Reinitialize broker client and DataCache with new credentials
    global broker_client, cache
    if cache:
        cache.stop()
    try:
        from .tiger_client import TigerClient as DefaultBrokerClientImpl
        from .data_cache import DataCache as DC
        broker_client = DefaultBrokerClientImpl(config_dir=str(BROKER_PROPERTIES_DIR))
        provider_name = os.environ.get("ENGINE_QUOTE_PROVIDER", "yfinance")
        quote_provider = get_quote_provider(provider_name, config_dir=str(CONFIG_DIR_PATH))
        cache = DC(broker_client, quote_provider, refresh_interval=30)
        cache.start()
    except Exception as e:
        broker_client = None
        cache = None

    # Detect mode from API (non-fatal)
    account_info = None
    detected = None
    if broker_client:
        try:
            account_info = _get_broker_account_info(str(BROKER_PROPERTIES_DIR))
            detected = _account_type_to_mode(account_info.get("account_type", ""))
            if detected:
                config_file = _app_config_file()
                if config_file.exists():
                    _merge_app_user_settings({"mode": detected})
        except Exception as e:
            account_info = {"error": str(e)}

    return {
        "status": "ok",
        "filename": BROKER_PROPS_FILE.name,
        "tiger_id": props.get("tiger_id"),
        "account": props.get("account"),
        "has_private_key": has_key,
        "account_info": account_info,
        "detected_mode": detected,
        "state_cleared": state_cleared,
    }


@app.post("/api/config/mode")
async def api_config_mode(body: dict):
    """Manually set paper/live mode."""
    mode = body.get("mode")
    if mode not in ("paper", "live"):
        return JSONResponse({"error": "mode must be paper or live"}, status_code=400)
    config_file = _app_config_file()
    if not config_file.exists():
        return JSONResponse({"error": "config not found"}, status_code=404)
    user_updates: dict[str, Any] = {"mode": mode}
    # Live mode safety: disable live_submit/live_cancel by default
    if mode == "live":
        user_updates["execution"] = {"live_submit": False, "live_cancel": False}
    _merge_app_user_settings(user_updates)
    return {"status": "ok", "mode": mode}


# --- News API ---

NEWS_DIR = RUNTIME_DIR / "newswire"


@app.get("/api/news")
async def api_news():
    """Read latest newswire output."""
    import json
    news_file = NEWS_DIR / "latest.json"
    if not news_file.exists():
        return {"items": [], "generated_at": None, "shift": None, "meta": {}}
    try:
        return json.loads(news_file.read_text())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/news")
async def api_news_update(body: dict):
    """Write newswire data (called by cron agents in sandbox)."""
    import json
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    news_file = NEWS_DIR / "latest.json"
    # Backup previous
    if news_file.exists():
        backup = NEWS_DIR / "latest_prev.json"
        backup.write_text(news_file.read_text())
    news_file.write_text(json.dumps(body, indent=2, ensure_ascii=False))
    return {"status": "ok", "items": len(body.get("items", [])), "shift": body.get("shift")}


@app.get("/api/news/sources")
async def api_news_sources():
    """Get news source configuration (for Dashboard checkboxes)."""
    import json
    sources_file = NEWS_DIR_PATH / "sources.json"
    if not sources_file.exists():
        return {"sources": []}
    try:
        return json.loads(sources_file.read_text())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.put("/api/news/sources")
async def api_news_sources_update(body: dict):
    """Update news source enabled status."""
    import json
    sources_file = NEWS_DIR_PATH / "sources.json"
    if not sources_file.exists():
        return JSONResponse({"error": "sources.json not found"}, status_code=404)

    try:
        config = json.loads(sources_file.read_text())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    # Update enabled status for each source
    updates = body.get("sources", [])
    for update in updates:
        sid = update.get("id")
        enabled = update.get("enabled")
        if sid is None or enabled is None:
            continue
        for src in config.get("sources", []):
            if src.get("id") == sid:
                src["enabled"] = enabled
                break

    config["updated_at"] = __import__("datetime").datetime.now().isoformat()
    sources_file.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    return {"status": "ok", "sources": config.get("sources", [])}


# --- Logs ---

@app.get("/api/logs")
@app.get("/api/logs/{log_name}")
async def api_logs(log_name: str = "execution", lines: int = 100):
    """Read log files from root logs/ first, with runtime/logs fallback."""
    import json
    resolved = _resolve_log_file(log_name)
    if not resolved:
        available = [path.stem for _, path in _iter_log_files()]
        return JSONResponse({"error": f"log not found: {log_name}", "available": available}, status_code=404)
    section, log_file = resolved
    try:
        all_lines = log_file.read_text().strip().split("\n")
        entries = []
        for line in all_lines[-lines:]:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    entries.append({"_raw": line})
        return {
            "log": log_name,
            "section": section,
            "total_lines": len(all_lines),
            "returned": len(entries),
            "entries": entries,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/logs-overview")
async def api_logs_overview():
    """Return a debugging-oriented overview of logs and latest runtime snapshots."""
    try:
        return _build_logs_overview()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/strategy-overview")
async def api_strategy_overview():
    """Return strategy switches, signal trace, and strategist adjustment history."""
    try:
        return _build_strategy_overview()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/logs-list")
async def api_logs_list():
    """List available log files."""
    from datetime import datetime
    logs = []
    for section, f in _iter_log_files():
        stat = f.stat()
        logs.append({
            "name": f.stem,
            "section": section,
            "path": str(f),
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "lines": sum(1 for _ in open(f)) if stat.st_size < 1_000_000 else None,
        })
    return {"logs": logs}


# --- Entry point ---

def main():
    import uvicorn
    port = int(os.environ.get("DASHBOARD_PORT", 8088))
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
