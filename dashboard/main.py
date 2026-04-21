from __future__ import annotations

"""Agent Trading Dashboard - FastAPI entry point."""

import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .api.backtest import (
    _apply_param_overrides,
    api_backtest,
    api_backtest_batch,
    api_backtest_results,
    api_rules_history,
    register_backtest_routes,
    set_dashboard_main_module as set_backtest_dashboard_main_module,
)
from .api.config import (
    api_broker_config_get,
    api_broker_config_upload_file,
    api_config_get,
    api_config_mode,
    api_config_update,
    register_config_routes,
    set_dashboard_main_module as set_config_dashboard_main_module,
)
from .api.control import (
    api_control,
    api_execution_state_reset,
    api_scheduler_interval,
    api_scheduler_run,
    api_scheduler_status,
    api_trading_mode_get,
    api_trading_mode_set,
    register_control_routes,
    set_dashboard_main_module as set_control_dashboard_main_module,
)
from .api.logs import (
    api_audit,
    api_logs,
    api_logs_list,
    api_logs_overview,
    register_logs_routes,
    set_dashboard_main_module as set_logs_dashboard_main_module,
)
from .api.market import (
    api_account,
    api_agents,
    api_broker,
    api_lookup_symbol,
    api_market_status,
    api_orders,
    api_pnl,
    api_positions,
    api_quote_provider,
    api_quote_providers,
    api_quotes,
    api_refresh,
    api_stock_analysis,
    api_system,
    api_trading_day,
    api_watchlist,
    api_watchlist_add,
    api_watchlist_remove,
    api_watchlist_update,
    register_market_routes,
    set_dashboard_main_module as set_market_dashboard_main_module,
)
from .api.proposals import (
    api_strategy_proposal_approve,
    api_strategy_proposal_detail,
    api_strategy_proposal_reject,
    api_strategy_proposals,
    register_proposal_routes,
    set_proposal_artifacts_root_getter,
)
from .api.strategy import (
    api_engine,
    api_engine_health,
    api_execution_preview,
    api_news,
    api_news_sources,
    api_news_sources_update,
    api_news_update,
    api_notifications,
    api_risk,
    api_rules_get,
    api_rules_test,
    api_rules_update,
    api_rules_validate,
    api_signals,
    api_strategy_overview,
    register_strategy_routes,
    set_dashboard_main_module as set_strategy_dashboard_main_module,
)
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
from system.engine.src.engine.control import (
    ControlPlane,
    canonical_mode_to_legacy_ui_mode,
    legacy_ui_mode_to_canonical_mode,
)
from system.engine.src.engine.rule_profiles import build_symbol_profile_overview
from system.engine.src.engine.rule_schema import validate_rules_config

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
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
set_proposal_artifacts_root_getter(lambda: ARTIFACTS_ROOT)
_DASHBOARD_MAIN_MODULE = sys.modules[__name__]
set_market_dashboard_main_module(_DASHBOARD_MAIN_MODULE)
set_control_dashboard_main_module(_DASHBOARD_MAIN_MODULE)
set_config_dashboard_main_module(_DASHBOARD_MAIN_MODULE)
set_strategy_dashboard_main_module(_DASHBOARD_MAIN_MODULE)
set_backtest_dashboard_main_module(_DASHBOARD_MAIN_MODULE)
set_logs_dashboard_main_module(_DASHBOARD_MAIN_MODULE)
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


def _current_symbol_universe() -> list[str]:
    try:
        config = _load_effective_app_config()
    except Exception:
        return []
    strategy = config.get("strategy", {}) if isinstance(config, dict) else {}
    symbols = strategy.get("symbols", []) if isinstance(strategy, dict) else []
    result: list[str] = []
    for item in symbols:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol")
        if symbol:
            result.append(str(symbol).upper())
    return result


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


def _read_control_state() -> dict[str, Any]:
    control = ControlPlane(RUNTIME_DIR / "state")
    return control.status()


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
    market_by_symbol = {
        item.get("symbol"): item.get("market", "US")
        for item in (config.get("strategy", {}).get("symbols", []) if isinstance(config, dict) else [])
        if isinstance(item, dict) and item.get("symbol")
    }
    symbol_profiles = build_symbol_profile_overview(
        rules_doc if isinstance(rules_doc, dict) else {"rules": []},
        list(symbol_name_map.keys()),
        market_by_symbol=market_by_symbol,
    )

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
            "base_rule_id": signal.get("base_rule_id") or rule_id,
            "primary_rule_id": signal.get("primary_rule_id") or rule_id,
            "source_rule_ids": signal.get("source_rule_ids", []),
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
            "symbol_profile": signal.get("symbol_profile") or symbol_profiles.get(signal.get("symbol"), {}).get("profile"),
            "effective_config_hash": signal.get("effective_config_hash"),
            "effective_config_hashes": signal.get("effective_config_hashes", []),
            "overrides_applied": signal.get("overrides_applied", {}),
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
        "data_health": cycle.get("data_health", {}),
        "symbol_profiles": cycle.get("strategy", {}).get("symbol_profiles", {}) if isinstance(cycle.get("strategy"), dict) else {},
    }

    fee_calibration = _safe_read_json(BROKER_ARTIFACTS_DIR / "fee_calibration_summary.json") or {}
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

    control_global = control.get("global", {}) if isinstance(control.get("global"), dict) else {}
    control_enabled = bool(control_global.get("enabled", True))
    control_canonical_mode = control_global.get("mode") or legacy_ui_mode_to_canonical_mode(control.get("trading_mode", "off"))
    live_readiness = control.get("live_readiness", {}) if isinstance(control.get("live_readiness"), dict) else {}
    live_submission_ready = (
        control_enabled
        and control_canonical_mode == "live_trade"
        and live_readiness.get("status") == "ready"
        and not live_readiness.get("failed_items")
    )

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
            "legacy_mode": control.get("trading_mode", "off"),
            "canonical_mode": control_canonical_mode,
            "signal_generation_enabled": control_enabled and control_canonical_mode != "off",
            "paper_execution_enabled": control_enabled and control_canonical_mode in {"paper_trade", "live_trade"},
            "live_execution_enabled": control_enabled and control_canonical_mode == "live_trade",
            "live_submission_ready": live_submission_ready,
            "reason": control.get("reason"),
        },
        "latest_cycle": latest_cycle,
        "data_health": cycle.get("data_health", {}),
        "rules_meta": _file_meta(RULES_FILE),
        "rules_summary": rules_summary,
        "symbol_profiles": symbol_profiles,
        "signal_records": signal_records,
        "latest_plan": latest_plan_summary,
        "plan_history": plan_history,
        "iterations": iterations,
        "fee_calibration": fee_calibration,
    }

    _ensure_logs_layout()
    _write_json_file(LATEST_LOG_DIR / "strategy_overview.json", overview)
    return overview
RULES_FILE = RULES_DIR / "rules.json"


# Route registration is delegated to domain modules below.

register_market_routes(app)
register_proposal_routes(app)
register_control_routes(app)
register_config_routes(app)
register_strategy_routes(app)
register_backtest_routes(app)
register_logs_routes(app)


# --- Entry point ---

def main():
    import uvicorn
    port = int(os.environ.get("DASHBOARD_PORT", 8088))
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
