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
from .data_cache import DataCache
from .quote_provider import get_quote_provider
from .scheduler import SignalScheduler
from .normalize import get_normalizer, available_brokers
from .service_logs import append_service_log
from .services.runtime import create_dashboard_bindings
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
from system.engine.src.engine.factors import available_builtin_implementations
from system.engine.src.engine.diagnostic_factor_rules import (
    diagnostic_factor_rules_summary,
    load_diagnostic_factor_rules,
    validate_diagnostic_factor_rules,
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
    provider_name = os.environ.get("ENGINE_QUOTE_PROVIDER", "yfinance")

    # Broker client may fail if credentials are invalid - don't crash the app
    try:
        broker_client, _, cache = create_dashboard_bindings(
            broker_properties_dir=BROKER_PROPERTIES_DIR,
            config_dir=config_dir,
            provider_name=provider_name,
            refresh_interval=30,
        )
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

    if broker_client:
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
EXPERIMENTS_DIR = Path(
    os.environ.get("ENGINE_EXPERIMENTS_DIR", str(Path(__file__).parent.parent / "experiments"))
)
EXPERIMENT_RULE_BATCHES_DIR = Path(
    os.environ.get("ENGINE_RULE_BATCHES_DIR", str(EXPERIMENTS_DIR / "rule_batches"))
)
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
FACTOR_ARTIFACTS_DIR = ARTIFACTS_ROOT / "factors"
FACTOR_RESEARCH_ARTIFACTS_DIR = ARTIFACTS_ROOT / "factor_research"
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
        FACTOR_ARTIFACTS_DIR,
        FACTOR_RESEARCH_ARTIFACTS_DIR,
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


def _resolve_factor_registry_path(config: dict[str, Any]) -> Path | None:
    factor_engine = config.get("factor_engine")
    if not isinstance(factor_engine, dict):
        return None
    registry_path = factor_engine.get("registry_path")
    if not registry_path:
        return None
    path = Path(str(registry_path))
    if path.is_absolute():
        return path
    return (Path(__file__).parent.parent / path).resolve()


def _load_factor_registry_meta(config: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None]:
    registry_path = _resolve_factor_registry_path(config)
    if registry_path is None:
        return {}, None

    payload = _safe_read_json(registry_path)
    if not isinstance(payload, dict):
        return {}, _file_meta(registry_path)

    result: dict[str, dict[str, Any]] = {}
    available = set(available_builtin_implementations())
    factors = payload.get("factors")
    if isinstance(factors, dict):
        for factor_id, entry in factors.items():
            if not isinstance(entry, dict):
                continue
            result[str(factor_id)] = {
                "type": entry.get("type"),
                "session": entry.get("session"),
                "timeframe": entry.get("timeframe"),
                "implementation": entry.get("implementation"),
                "usage": entry.get("usage", []) if isinstance(entry.get("usage"), list) else [],
                "actionable": bool(entry.get("actionable", False)),
                "implementation_available": str(entry.get("implementation")) in available,
            }
    return result, _file_meta(registry_path)


def _last_factor_apply_summary() -> dict[str, Any] | None:
    path = STRATEGIST_ARTIFACTS_DIR / "deployment_records.jsonl"
    if not path.exists():
        return None
    try:
        lines = path.read_text().splitlines()
    except Exception:
        return None

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        proposal_type = str(entry.get("proposal_type") or "")
        if (
            proposal_type == "factor_rule_link"
            and entry.get("target_file") == "rules/diagnostic_factor_rules.json"
        ):
            continue
        if proposal_type not in {"factor_config", "factor_rule_link", "factor_code"} and not entry.get("changed_factors"):
            continue
        return {
            "proposal_id": entry.get("proposal_id"),
            "proposal_type": entry.get("proposal_type"),
            "apply_action": entry.get("apply_action"),
            "success": bool(entry.get("success")),
            "timestamp": entry.get("applied_at") or entry.get("recorded_at"),
            "registry_hash": entry.get("registry_hash"),
            "changed_factors": entry.get("changed_factors", []),
        }
    return None


def _build_factor_engine_overview(config: dict[str, Any], cycle: dict[str, Any]) -> dict[str, Any]:
    configured = config.get("factor_engine") if isinstance(config.get("factor_engine"), dict) else {}
    cycle_factor = cycle.get("factor_engine") if isinstance(cycle.get("factor_engine"), dict) else {}
    latest_snapshot_path = _first_existing_path(
        FACTOR_ARTIFACTS_DIR / "latest.json",
        RUNTIME_DIR / "factors" / "latest.json",
    )
    latest_snapshot = _safe_read_json(latest_snapshot_path)
    snapshot_symbols = latest_snapshot.get("symbols", {}) if isinstance(latest_snapshot, dict) else {}
    cycle_symbols = cycle_factor.get("symbols", {}) if isinstance(cycle_factor, dict) else {}
    registry_meta, registry_file = _load_factor_registry_meta(config)

    factor_engine = {
        "enabled": bool(cycle_factor.get("enabled", configured.get("enabled", False))),
        "mode": cycle_factor.get("mode") or configured.get("mode"),
        "allow_actionable_consumption": bool(
            cycle_factor.get(
                "allow_actionable_consumption",
                configured.get("allow_actionable_consumption", False),
            )
        ),
        "registry_path": cycle_factor.get("registry_path")
        or (latest_snapshot.get("registry_path") if isinstance(latest_snapshot, dict) else None)
        or (registry_file.get("path") if isinstance(registry_file, dict) else None),
        "registry_hash": cycle_factor.get("registry_hash")
        or (latest_snapshot.get("registry_hash") if isinstance(latest_snapshot, dict) else None),
        "registry_hash_source": cycle_factor.get("registry_hash_source")
        or (latest_snapshot.get("registry_hash_source") if isinstance(latest_snapshot, dict) else None)
        or ("latest_snapshot" if isinstance(latest_snapshot, dict) and latest_snapshot.get("registry_hash") else None),
        "schema_valid": cycle_factor.get("schema_valid")
        if "schema_valid" in cycle_factor
        else (latest_snapshot.get("schema_valid") if isinstance(latest_snapshot, dict) else None),
        "schema_errors": cycle_factor.get("schema_errors", [])
        or (latest_snapshot.get("schema_errors", []) if isinstance(latest_snapshot, dict) else []),
        "schema_warnings": cycle_factor.get("schema_warnings", [])
        or (latest_snapshot.get("schema_warnings", []) if isinstance(latest_snapshot, dict) else []),
        "implementation_summary": cycle_factor.get("implementation_summary")
        or (latest_snapshot.get("implementation_summary") if isinstance(latest_snapshot, dict) else None),
        "error": cycle_factor.get("error"),
        "message": cycle_factor.get("message"),
        "store_error": cycle_factor.get("store_error"),
        "latest_snapshot": _file_meta(latest_snapshot_path),
        "registry_file": registry_file,
        "last_apply": _last_factor_apply_summary(),
        "symbols": {},
        "factor_rows": [],
    }

    configured_symbols = []
    strategy = config.get("strategy")
    if isinstance(strategy, dict) and isinstance(strategy.get("symbols"), list):
        configured_symbols = [
            str(item.get("symbol"))
            for item in strategy.get("symbols")
            if isinstance(item, dict) and item.get("symbol")
        ]
    symbol_order = list(dict.fromkeys(configured_symbols + list(cycle_symbols.keys()) + list(snapshot_symbols.keys())))

    for symbol in symbol_order:
        cycle_entry = cycle_symbols.get(symbol) if isinstance(cycle_symbols, dict) else {}
        if not isinstance(cycle_entry, dict):
            cycle_entry = {}
        snapshot_entry = snapshot_symbols.get(symbol) if isinstance(snapshot_symbols, dict) else {}
        if not isinstance(snapshot_entry, dict):
            snapshot_entry = {}
        snapshot_factors = snapshot_entry.get("factors") if isinstance(snapshot_entry.get("factors"), dict) else {}

        symbol_factors: dict[str, Any] = {}
        for factor_id, payload in sorted(snapshot_factors.items()):
            if not isinstance(payload, dict):
                continue
            factor_meta = registry_meta.get(str(factor_id), {})
            factor_payload = {
                "factor_id": str(factor_id),
                "value": payload.get("value"),
                "ready": bool(payload.get("ready")),
                "reason": payload.get("reason"),
                "actionable": bool(payload.get("actionable", factor_meta.get("actionable", False))),
                "source": payload.get("source"),
                "session": factor_meta.get("session"),
                "timeframe": factor_meta.get("timeframe"),
                "usage": factor_meta.get("usage", []),
                "type": factor_meta.get("type"),
                "implementation": factor_meta.get("implementation"),
                "implementation_available": bool(
                    payload.get("implementation_available", factor_meta.get("implementation_available", False))
                ),
                "config_hash": payload.get("config_hash"),
            }
            symbol_factors[str(factor_id)] = factor_payload
            factor_engine["factor_rows"].append({
                "symbol": symbol,
                **factor_payload,
            })

        factor_engine["symbols"][symbol] = {
            "factors_ready": cycle_entry.get(
                "factors_ready",
                sum(1 for item in symbol_factors.values() if item.get("ready")),
            ),
            "factors_total": cycle_entry.get("factors_total", len(symbol_factors)),
            "blocking": bool(cycle_entry.get("blocking", False)),
            "reasons": cycle_entry.get("reasons", []),
            "timestamp": snapshot_entry.get("timestamp"),
            "factors": symbol_factors,
        }

    return factor_engine


def _build_factor_research_summary() -> dict[str, Any]:
    latest_path = FACTOR_RESEARCH_ARTIFACTS_DIR / "latest.json"
    report_path = FACTOR_RESEARCH_ARTIFACTS_DIR / "reports" / "latest.md"
    hypotheses_path = FACTOR_RESEARCH_ARTIFACTS_DIR / "hypotheses.jsonl"
    latest = _safe_read_json(latest_path)
    if not isinstance(latest, dict):
        latest = {}

    factors = latest.get("factors") if isinstance(latest.get("factors"), dict) else {}
    insufficient = latest.get("factors_with_insufficient_samples")
    if not isinstance(insufficient, list):
        insufficient = [
            factor_id
            for factor_id, payload in factors.items()
            if isinstance(payload, dict) and payload.get("data_quality_reason") == "insufficient_samples"
        ]
    top_coverage = latest.get("top_coverage_factors")
    if not isinstance(top_coverage, list):
        top_coverage = sorted(
            (
                {
                    "factor_id": factor_id,
                    "coverage": payload.get("coverage"),
                    "sample_count": payload.get("sample_count"),
                }
                for factor_id, payload in factors.items()
                if isinstance(payload, dict)
            ),
            key=lambda item: (float(item.get("coverage") or 0), int(item.get("sample_count") or 0)),
            reverse=True,
        )[:5]
    high_redundancy_pairs = latest.get("high_redundancy_pairs")
    if not isinstance(high_redundancy_pairs, list):
        high_redundancy_pairs = []

    hypotheses_info = _tail_jsonl_info(hypotheses_path)
    report_meta = _file_meta(report_path)
    return {
        "available": bool(latest),
        "generated_at": latest.get("generated_at"),
        "status": latest.get("status") or ("missing" if not latest else None),
        "factor_count": int(latest.get("factor_count") or len(factors)),
        "factors_with_insufficient_samples": insufficient,
        "top_coverage_factors": top_coverage[:5],
        "high_redundancy_pairs": high_redundancy_pairs,
        "hypothesis_count": int(latest.get("hypothesis_count") or hypotheses_info.get("lines") or 0),
        "last_report_path": str(report_path) if report_meta["exists"] else None,
        "latest": _file_meta(latest_path),
        "report": report_meta,
        "hypotheses": hypotheses_info,
    }


def _build_factor_validation_summary() -> dict[str, Any]:
    latest_path = FACTOR_RESEARCH_ARTIFACTS_DIR / "latest.json"
    latest = _safe_read_json(latest_path)
    if not isinstance(latest, dict):
        latest = {}
    summary = latest.get("factor_validation_summary") if isinstance(latest.get("factor_validation_summary"), dict) else {}
    factors = latest.get("factors") if isinstance(latest.get("factors"), dict) else {}
    if not summary:
        factor_items = [payload for payload in factors.values() if isinstance(payload, dict)]
        summary = {
            "latest_generated_at": latest.get("generated_at"),
            "sample_source": latest.get("sample_source"),
            "factor_count": int(latest.get("factor_count") or len(factor_items)),
            "labeled_sample_count": sum(int(item.get("labeled_sample_count") or 0) for item in factor_items),
            "insufficient_factor_count": sum(1 for item in factor_items if item.get("gate_status") == "insufficient"),
            "research_candidate_count": sum(1 for item in factor_items if item.get("candidate_grade") == "research_candidate"),
            "high_redundancy_pair_count": len(latest.get("high_redundancy_pairs") or []),
            "top_candidate_factors": [
                {
                    "factor_id": item.get("factor_id"),
                    "candidate_grade": item.get("candidate_grade"),
                    "IC_1bar": item.get("IC_1bar"),
                    "coverage": item.get("coverage"),
                    "labeled_sample_count": item.get("labeled_sample_count"),
                }
                for item in factor_items
                if item.get("candidate_grade") == "research_candidate"
            ][:5],
            "blocked_reasons": {},
            "report_path": latest.get("report_path"),
        }
    return {
        "available": bool(latest),
        "latest_generated_at": summary.get("latest_generated_at") or latest.get("generated_at"),
        "sample_source": summary.get("sample_source") or latest.get("sample_source"),
        "factor_count": int(summary.get("factor_count") or latest.get("factor_count") or 0),
        "labeled_sample_count": int(summary.get("labeled_sample_count") or 0),
        "insufficient_factor_count": int(summary.get("insufficient_factor_count") or 0),
        "research_candidate_count": int(summary.get("research_candidate_count") or 0),
        "high_redundancy_pair_count": int(summary.get("high_redundancy_pair_count") or 0),
        "top_candidate_factors": summary.get("top_candidate_factors", []),
        "blocked_reasons": summary.get("blocked_reasons", {}),
        "candidate_grade_distribution": summary.get("candidate_grade_distribution", {}),
        "no_lookahead_validation_status": summary.get("no_lookahead_validation_status"),
        "report_path": summary.get("report_path") or latest.get("report_path"),
    }


def _build_factor_parity_summary() -> dict[str, Any]:
    latest_path = FACTOR_RESEARCH_ARTIFACTS_DIR / "parity" / "latest.json"
    latest = _safe_read_json(latest_path)
    if not isinstance(latest, dict):
        latest = {}
    return {
        "available": bool(latest),
        "latest_generated_at": latest.get("generated_at"),
        "factor_count": int(latest.get("factor_count") or 0),
        "compared_factor_count": int(latest.get("compared_factor_count") or 0),
        "parity_pass_count": int(latest.get("parity_pass_count") or 0),
        "parity_fail_count": int(latest.get("parity_fail_count") or 0),
        "blocking_mismatch_count": int(latest.get("blocking_mismatch_count") or 0),
        "warning_mismatch_count": int(latest.get("warning_mismatch_count") or 0),
        "signal_parity_pass_count": int(latest.get("signal_parity_pass_count") or 0),
        "signal_parity_fail_count": int(latest.get("signal_parity_fail_count") or 0),
        "report_path": latest.get("report_path"),
        "top_mismatches": latest.get("top_mismatches", []),
    }


def _build_factor_dual_run_summary(cycle: dict[str, Any] | None = None) -> dict[str, Any]:
    latest_path = FACTOR_RESEARCH_ARTIFACTS_DIR / "dual_run" / "latest.json"
    observation_path = FACTOR_RESEARCH_ARTIFACTS_DIR / "dual_run" / "observations" / "latest.json"
    latest = _safe_read_json(latest_path)
    if not isinstance(latest, dict):
        latest = {}
    observation = _safe_read_json(observation_path)
    if not isinstance(observation, dict):
        observation = {}
    cycle_summary = cycle.get("factor_dual_run") if isinstance(cycle, dict) and isinstance(cycle.get("factor_dual_run"), dict) else {}
    source = cycle_summary if cycle_summary else latest
    report_path = _relative_artifact_path(
        source.get("report_path") or latest.get("report_path") or "artifacts/factor_research/dual_run/reports/latest.md"
    )
    return {
        "available": bool(latest) or bool(cycle_summary),
        "enabled": bool(source.get("enabled", False)),
        "latest_generated_at": source.get("generated_at"),
        "reason": source.get("reason"),
        "compared_count": int(source.get("compared_count") or 0),
        "matched_count": int(source.get("matched_count") or 0),
        "mismatch_count": int(source.get("mismatch_count") or 0),
        "blocking_mismatch_count": int(source.get("blocking_mismatch_count") or 0),
        "warning_mismatch_count": int(source.get("warning_mismatch_count") or 0),
        "matched_rate": source.get("matched_rate"),
        "compared_rules": source.get("compared_rules", []),
        "compared_symbols": source.get("compared_symbols", []),
        "top_mismatches": source.get("top_mismatches", []),
        "real_universe_symbols_detected": bool(source.get("real_universe_symbols_detected", False)),
        "synthetic_fixture_symbols_detected": bool(source.get("synthetic_fixture_symbols_detected", False)),
        "latest_observation_path": "artifacts/factor_research/dual_run/observations/latest.json" if observation_path.exists() else None,
        "source_bar_session_summary": source.get("source_bar_session_summary", {}),
        "production_path_unchanged": bool(source.get("production_path_unchanged", True)),
        "readiness_status": observation.get("readiness_status"),
        "readiness_reasons": observation.get("readiness_reasons", []),
        "artifact_age_seconds": observation.get("artifact_age_seconds"),
        "artifact_is_stale": bool(observation.get("artifact_is_stale", False)),
        "cycle_run_attempted": bool(observation.get("cycle_run_attempted", False)),
        "cycle_run_succeeded": bool(observation.get("cycle_run_succeeded", False)),
        "cycle_run_skipped": bool(observation.get("cycle_run_skipped", False)),
        "app_universe_symbols": observation.get("app_universe_symbols", []),
        "report_path": report_path if (latest or cycle_summary) else None,
    }


def _build_diagnostic_factor_rules_summary() -> dict[str, Any]:
    target_path = RULES_DIR / "diagnostic_factor_rules.json"
    source_rules_payload = _safe_read_json(RULES_FILE)
    registry_path = Path(__file__).parent.parent / "factors" / "registry.json"
    payload: dict[str, Any] | None = None
    validation = {"valid": True, "errors": [], "warnings": []}
    if target_path.exists():
        try:
            payload = load_diagnostic_factor_rules(target_path)
            validation = validate_diagnostic_factor_rules(
                payload,
                source_rules_payload=source_rules_payload if isinstance(source_rules_payload, dict) else None,
                factor_registry=registry_path,
            )
        except Exception as exc:
            validation = {"valid": False, "errors": [f"{type(exc).__name__}:{exc}"], "warnings": []}
            payload = None
    summary = diagnostic_factor_rules_summary(payload)
    last_apply = _latest_diagnostic_factor_rule_apply()
    trial_status = _latest_diagnostic_factor_rule_trial_status()
    return {
        "exists": target_path.exists(),
        "valid": bool(validation.get("valid", False)),
        "errors": validation.get("errors", []),
        "warnings": validation.get("warnings", []),
        "rule_count": int(summary.get("rule_count") or 0),
        "enabled_count": int(summary.get("enabled_count") or 0),
        "diagnostic_only_count": int(summary.get("diagnostic_only_count") or 0),
        "source_rules": summary.get("source_rules", []),
        "factor_ids": summary.get("factor_ids", []),
        "latest_diagnostic_rule_ids": summary.get("latest_diagnostic_rule_ids", []),
        "latest_source_rule_ids": summary.get("latest_source_rule_ids", []),
        "latest_factor_ids": summary.get("latest_factor_ids", []),
        "last_apply": last_apply,
        "last_deployment_record_id": (last_apply or {}).get("last_deployment_record_id"),
        "approval_decision_snapshot_present": bool((last_apply or {}).get("approval_decision_snapshot_present")),
        "real_apply_ready": bool(trial_status.get("real_apply_ready", False)),
        "latest_approval_request_path": trial_status.get("latest_approval_request_path"),
        "latest_trial_mode": trial_status.get("latest_trial_mode"),
        "latest_proposal_id": trial_status.get("latest_proposal_id"),
        "target_file": "rules/diagnostic_factor_rules.json",
        "production_rules_modified": False,
        "actionable_enabled": False,
    }


def _build_diagnostic_factor_metrics_summary() -> dict[str, Any]:
    latest_path = FACTOR_RESEARCH_ARTIFACTS_DIR / "diagnostic_metrics" / "latest.json"
    latest = _safe_read_json(latest_path)
    if not isinstance(latest, dict):
        latest = {}
    rules = latest.get("rules") if isinstance(latest.get("rules"), list) else []
    top_rules = latest.get("top_diagnostic_rules")
    if not isinstance(top_rules, list):
        top_rules = sorted(
            (
                {
                    "rule_id": item.get("rule_id"),
                    "source_rule_id": item.get("source_rule_id"),
                    "factor_ids": item.get("factor_ids", []),
                    "evaluation_status": item.get("evaluation_status"),
                    "sample_source": item.get("sample_source"),
                    "signal_count": item.get("signal_count"),
                    "labeled_sample_count": item.get("labeled_sample_count"),
                    "IC_1bar": item.get("IC_1bar"),
                    "hit_rate_1bar": item.get("hit_rate_1bar"),
                    "live_shadow_days_observed": item.get("live_shadow_days_observed"),
                    "insufficient_reason": item.get("insufficient_reason"),
                }
                for item in rules
                if isinstance(item, dict)
            ),
            key=lambda item: (
                item.get("evaluation_status") == "watchlist_candidate",
                item.get("evaluation_status") == "research_only",
                abs(float(item.get("IC_1bar") or 0.0)),
                int(item.get("labeled_sample_count") or 0),
            ),
            reverse=True,
        )[:5]
    return {
        "available": bool(latest),
        "latest_generated_at": latest.get("generated_at"),
        "status": latest.get("status") or ("missing" if not latest else None),
        "rule_count": int(latest.get("rule_count") or len(rules)),
        "evaluated_rule_count": int(latest.get("evaluated_rule_count") or 0),
        "insufficient_rule_count": int(latest.get("insufficient_rule_count") or 0),
        "watchlist_candidate_count": int(latest.get("watchlist_candidate_count") or 0),
        "sample_sources": latest.get("sample_sources", []),
        "top_diagnostic_rules": top_rules[:5],
        "label_join_summary": latest.get("label_join_summary") or {
            "total_events": 0,
            "joined_events": 0,
            "unjoined_events": 0,
            "join_rate": 0.0,
            "reasons_count": {},
            "live_joined_events": 0,
            "backfill_joined_events": 0,
            "live_unjoined_events": 0,
            "backfill_unjoined_events": 0,
        },
        "events_path": _relative_artifact_path(latest.get("events_path")),
        "events_summary_path": _relative_artifact_path(latest.get("events_summary_path")),
        "top_label_join_blockers": latest.get("top_label_join_blockers", []),
        "backfill_replay_available": bool(latest.get("backfill_replay_available", False)),
        "backfill_joined_events": int(latest.get("backfill_joined_events") or 0),
        "live_joined_events": int(latest.get("live_joined_events") or 0),
        "report_path": _relative_artifact_path(latest.get("report_path")),
    }


def _build_factor_ops_summary() -> dict[str, Any]:
    latest_path = FACTOR_RESEARCH_ARTIFACTS_DIR / "ops" / "latest.json"
    latest = _safe_read_json(latest_path)
    if not isinstance(latest, dict):
        latest = {}
    return {
        "available": bool(latest),
        "latest_generated_at": latest.get("generated_at"),
        "promotion_readiness": latest.get("promotion_readiness") or ("missing" if not latest else None),
        "promotion_blockers": latest.get("promotion_blockers", []),
        "live_shadow_days_observed": int(latest.get("live_shadow_days_observed") or 0),
        "live_labeled_events": int(latest.get("live_labeled_events") or 0),
        "backfill_labeled_events": int(latest.get("backfill_labeled_events") or 0),
        "mixed_labeled_events": int(latest.get("mixed_labeled_events") or 0),
        "dual_run_readiness_status": latest.get("dual_run_readiness_status"),
        "dual_run_blocking_mismatch_count": int(latest.get("dual_run_blocking_mismatch_count") or 0),
        "diagnostic_rule_count": int(latest.get("diagnostic_rule_count") or 0),
        "diagnostic_signal_count": int(latest.get("diagnostic_signal_count") or 0),
        "label_join_rate": latest.get("label_join_rate"),
        "top_label_join_blockers": latest.get("top_label_join_blockers", []),
        "backfill_symbol_count": int(latest.get("backfill_symbol_count") or 0),
        "backfill_observation_count": int(latest.get("backfill_observation_count") or 0),
        "app_universe_symbols": latest.get("app_universe_symbols", []),
        "backfill_universe_symbols": latest.get("backfill_universe_symbols", []),
        "missing_backfill_symbols": latest.get("missing_backfill_symbols", []),
        "report_path": _relative_artifact_path(latest.get("report_path")),
    }


def _latest_diagnostic_factor_rule_trial_status() -> dict[str, Any]:
    path = FACTOR_RESEARCH_ARTIFACTS_DIR / "diagnostic_rule_link_trial" / "latest.json"
    payload = _safe_read_json(path)
    return payload if isinstance(payload, dict) else {}


def _latest_diagnostic_factor_rule_apply() -> dict[str, Any] | None:
    path = STRATEGIST_ARTIFACTS_DIR / "deployment_records.jsonl"
    if not path.exists():
        return None
    latest: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if item.get("target_file") == "rules/diagnostic_factor_rules.json":
            latest = item
    if latest is None:
        return None
    return {
        "last_deployment_record_id": latest.get("deployment_record_id") or latest.get("proposal_id"),
        "proposal_id": latest.get("proposal_id"),
        "applied_at": latest.get("applied_at") or latest.get("recorded_at"),
        "apply_mode": latest.get("apply_mode"),
        "changed_diagnostic_rules": latest.get("changed_diagnostic_rules", []),
        "approval_decision_snapshot_present": bool(latest.get("approval_decision_snapshot")),
        "production_rules_modified": bool(latest.get("production_rules_modified", False)),
        "actionable_enabled": bool(latest.get("actionable_enabled", False)),
    }


def _relative_artifact_path(path: Any) -> str | None:
    if path in (None, ""):
        return None
    text = str(path)
    marker = "artifacts/"
    if marker in text:
        return text[text.index(marker):]
    if text.startswith("/"):
        return Path(text).name
    return text


def _build_historical_fact_summary() -> dict[str, Any]:
    facts_path = FACTOR_RESEARCH_ARTIFACTS_DIR / "facts" / "latest.json"
    scenarios_path = FACTOR_RESEARCH_ARTIFACTS_DIR / "scenarios" / "latest.json"
    facts_latest = _safe_read_json(facts_path)
    scenarios_latest = _safe_read_json(scenarios_path)
    if not isinstance(facts_latest, dict):
        facts_latest = {}
    if not isinstance(scenarios_latest, dict):
        scenarios_latest = {}

    scenarios = scenarios_latest.get("top_debug_scenarios")
    if not isinstance(scenarios, list):
        scenarios = scenarios_latest.get("scenarios") if isinstance(scenarios_latest.get("scenarios"), list) else []
    top_debug_scenarios = []
    for item in scenarios[:6]:
        if not isinstance(item, dict):
            continue
        top_debug_scenarios.append({
            "scenario_id": item.get("scenario_id"),
            "scenario_type": item.get("scenario_type"),
            "symbols": item.get("symbols", []),
            "time_window": item.get("time_window", {}),
            "debug_goal": item.get("debug_goal"),
            "replay_command_hint": item.get("replay_command_hint"),
            "expected_invariants": item.get("expected_invariants", []),
        })

    leakage_warnings = []
    for value in (facts_latest.get("leakage_warnings"), scenarios_latest.get("leakage_warnings")):
        if isinstance(value, list):
            leakage_warnings.extend(str(item) for item in value if item)
    return {
        "available": bool(facts_latest),
        "latest_generated_at": facts_latest.get("generated_at") or scenarios_latest.get("generated_at"),
        "fact_count": int(facts_latest.get("fact_count") or 0),
        "fact_type_counts": facts_latest.get("fact_type_counts", {}) if isinstance(facts_latest.get("fact_type_counts"), dict) else {},
        "usage_counts": facts_latest.get("usage_counts", {}) if isinstance(facts_latest.get("usage_counts"), dict) else {},
        "scenario_count": int(scenarios_latest.get("scenario_count") or 0),
        "top_debug_scenarios": top_debug_scenarios,
        "leakage_warnings": sorted(set(leakage_warnings)),
        "report_path": _relative_artifact_path(facts_latest.get("report_path")) or "artifacts/factor_research/facts/reports/latest.md",
        "scenario_report_path": _relative_artifact_path(scenarios_latest.get("report_path")) or "artifacts/factor_research/scenarios/reports/latest.md",
    }


def _build_factor_sample_health() -> dict[str, Any]:
    latest_path = _first_existing_path(
        FACTOR_ARTIFACTS_DIR / "latest.json",
        RUNTIME_DIR / "factors" / "latest.json",
    )
    latest_exists = bool(latest_path and latest_path.exists())
    history_dir = FACTOR_ARTIFACTS_DIR / "history"
    backfill_path = FACTOR_RESEARCH_ARTIFACTS_DIR / "datasets" / "backfill" / "latest.jsonl"

    history_count = 0
    live_observation_count = 0
    last_observation_time = None
    for path in sorted(history_dir.glob("*.jsonl")) if history_dir.exists() else []:
        entries = _read_jsonl_tail_entries(path, limit=100000)
        history_count += len(entries)
        for entry in entries:
            observation_count, latest_time = _factor_snapshot_health(entry)
            live_observation_count += observation_count
            last_observation_time = _max_time_text(last_observation_time, latest_time)

    latest = _safe_read_json(latest_path) if latest_exists else None
    if isinstance(latest, dict):
        latest_observation_count, latest_time = _factor_snapshot_health(latest)
        if live_observation_count == 0:
            live_observation_count = latest_observation_count
        last_observation_time = _max_time_text(last_observation_time, latest_time)

    backfill_rows = _read_jsonl_tail_entries(backfill_path, limit=100000)
    backfill_observation_count = len(backfill_rows)
    for row in backfill_rows:
        last_observation_time = _max_time_text(
            last_observation_time,
            row.get("factor_timestamp") or row.get("source_bar_time") or row.get("timestamp"),
        )

    sample_sources = []
    if live_observation_count:
        sample_sources.append("live_shadow")
    if backfill_observation_count:
        sample_sources.append("historical_backfill")
    insufficient_reason = None
    if not latest_exists and live_observation_count == 0:
        insufficient_reason = "latest_missing"
    elif live_observation_count == 0 and backfill_observation_count == 0:
        insufficient_reason = "no_factor_samples"

    return {
        "latest_exists": latest_exists,
        "latest_path": str(latest_path) if latest_exists else str(FACTOR_ARTIFACTS_DIR / "latest.json"),
        "history_count": history_count,
        "last_observation_time": last_observation_time,
        "live_observation_count": live_observation_count,
        "backfill_observation_count": backfill_observation_count,
        "sample_sources": sample_sources,
        "insufficient_samples_reason": insufficient_reason,
    }


def _factor_snapshot_health(snapshot: dict[str, Any]) -> tuple[int, str | None]:
    symbols = snapshot.get("symbols")
    if not isinstance(symbols, dict):
        return 0, snapshot.get("timestamp") or snapshot.get("generated_at")
    count = 0
    latest_time = snapshot.get("timestamp") or snapshot.get("generated_at")
    for symbol_payload in symbols.values():
        if not isinstance(symbol_payload, dict):
            continue
        factors = symbol_payload.get("factors")
        if isinstance(factors, dict):
            count += len(factors)
            for factor_payload in factors.values():
                if isinstance(factor_payload, dict):
                    latest_time = _max_time_text(
                        latest_time,
                        factor_payload.get("source_bar_time") or symbol_payload.get("timestamp"),
                    )
    return count, latest_time


def _max_time_text(left: Any, right: Any) -> str | None:
    if not left:
        return str(right) if right else None
    if not right:
        return str(left)
    return max(str(left), str(right))


def _extract_factor_attribution_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    candidates: list[dict[str, Any]] = []
    best = payload.get("best")
    if isinstance(best, dict):
        candidates.append(best)
    results = payload.get("results")
    if isinstance(results, list):
        candidates.extend(item for item in results if isinstance(item, dict))

    for candidate in candidates:
        summary = candidate.get("factor_attribution_summary")
        if isinstance(summary, dict):
            return summary
    return None


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
    latest_factor_attribution_summary: dict[str, Any] | None = None
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
            factor_attribution_summary = _extract_factor_attribution_summary(payload)
            if latest_factor_attribution_summary is None and isinstance(factor_attribution_summary, dict):
                latest_factor_attribution_summary = {
                    **factor_attribution_summary,
                    "iteration_id": iteration_id,
                    "source_path": str(path),
                }
            iterations.append({
                "iteration_id": iteration_id,
                "timestamp": payload.get("timestamp"),
                "symbols": payload.get("symbols", []),
                "period": payload.get("period"),
                "best": payload.get("best"),
                "factor_attribution_summary": factor_attribution_summary,
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
        "factor_engine": cycle.get("factor_engine", {}) if isinstance(cycle.get("factor_engine"), dict) else {},
    }
    factor_engine = _build_factor_engine_overview(config, cycle)
    factor_research = _build_factor_research_summary()
    factor_sample_health = _build_factor_sample_health()
    factor_validation_summary = _build_factor_validation_summary()
    factor_parity_summary = _build_factor_parity_summary()
    factor_dual_run_summary = _build_factor_dual_run_summary(cycle)
    diagnostic_factor_rules_summary = _build_diagnostic_factor_rules_summary()
    diagnostic_factor_metrics_summary = _build_diagnostic_factor_metrics_summary()
    factor_ops_summary = _build_factor_ops_summary()
    historical_fact_summary = _build_historical_fact_summary()

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
        "factor_engine": factor_engine,
        "factor_research": factor_research,
        "factor_sample_health": factor_sample_health,
        "factor_validation_summary": factor_validation_summary,
        "factor_parity_summary": factor_parity_summary,
        "factor_dual_run_summary": factor_dual_run_summary,
        "diagnostic_factor_rules_summary": diagnostic_factor_rules_summary,
        "diagnostic_factor_metrics_summary": diagnostic_factor_metrics_summary,
        "factor_ops_summary": factor_ops_summary,
        "historical_fact_summary": historical_fact_summary,
        "factor_attribution": latest_factor_attribution_summary,
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
    host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
