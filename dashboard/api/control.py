from __future__ import annotations

import threading
import sys
from datetime import datetime

from fastapi.responses import JSONResponse


VALID_TRADING_MODES = {"off", "signals", "trade", "live_trade"}
_dashboard_main_module = None


def set_dashboard_main_module(module) -> None:
    global _dashboard_main_module
    _dashboard_main_module = module


def _dashboard_main():
    if _dashboard_main_module is not None:
        return _dashboard_main_module
    module = sys.modules.get("dashboard.main")
    if module is not None:
        return module
    from dashboard import main as dashboard_main
    return dashboard_main


def _read_control_state() -> dict:
    dashboard_main = _dashboard_main()
    control = dashboard_main.ControlPlane(dashboard_main.RUNTIME_DIR / "state")
    return control.status()


def _write_control_state(state: dict):
    dashboard_main = _dashboard_main()
    control = dashboard_main.ControlPlane(dashboard_main.RUNTIME_DIR / "state")
    control.replace_state(state)


def _trading_mode_payload(state: dict[str, object]) -> dict[str, object]:
    dashboard_main = _dashboard_main()
    global_cfg = state.get("global", {}) if isinstance(state.get("global"), dict) else {}
    canonical_mode = global_cfg.get("mode", "off")
    mode = dashboard_main.canonical_mode_to_legacy_ui_mode(canonical_mode)
    globally_enabled = bool(global_cfg.get("enabled", True))
    risk_cfg = state.get("risk", {}) if isinstance(state.get("risk"), dict) else {}
    live_readiness = state.get("live_readiness", {}) if isinstance(state.get("live_readiness"), dict) else {}
    reduce_only = bool(risk_cfg.get("reduce_only", False))
    emergency_flatten = bool(risk_cfg.get("emergency_flatten", False))
    signal_generation_enabled = globally_enabled and canonical_mode != "off"
    paper_execution_enabled = globally_enabled and canonical_mode in {"paper_trade", "live_trade"}
    live_execution_enabled = globally_enabled and canonical_mode == "live_trade"
    live_submission_ready = (
        live_execution_enabled
        and live_readiness.get("status") == "ready"
        and not live_readiness.get("failed_items")
    )
    if emergency_flatten:
        risk_state = "emergency_flatten"
        risk_label = "紧急平仓"
    elif reduce_only:
        risk_state = "reduce_only"
        risk_label = "只减仓"
    else:
        risk_state = "normal"
        risk_label = "正常"
    return {
        "mode": mode,
        "legacy_mode": mode,
        "canonical_mode": canonical_mode,
        "locked": state.get("locked", False),
        "signal_generation": signal_generation_enabled,
        "signal_generation_enabled": signal_generation_enabled,
        "order_intents_enabled": paper_execution_enabled,
        "paper_execution_enabled": paper_execution_enabled,
        "live_execution_enabled": live_execution_enabled,
        "live_submission_ready": live_submission_ready,
        "order_submission": live_submission_ready,
        "reduce_only": reduce_only,
        "reduce_only_reason": risk_cfg.get("reduce_only_reason"),
        "emergency_flatten": emergency_flatten,
        "risk_state": risk_state,
        "risk_label": risk_label,
        "live_readiness": live_readiness,
    }


async def api_scheduler_status():
    dashboard_main = _dashboard_main()
    if not dashboard_main.scheduler:
        return {
            "running": False,
            "error": "scheduler not initialized",
            "read_only": True,
            "mutable_controls_disabled": True,
        }
    return {
        **dashboard_main.scheduler.get_state(),
        "read_only": True,
        "mutable_controls_disabled": True,
    }


async def api_scheduler_interval(body: dict):
    return JSONResponse(
        {
            "error": "scheduler control disabled from dashboard",
            "read_only": True,
        },
        status_code=403,
    )


async def api_scheduler_run():
    return JSONResponse(
        {
            "error": "scheduler control disabled from dashboard",
            "read_only": True,
        },
        status_code=403,
    )


async def api_control(action: str):
    dashboard_main = _dashboard_main()
    control = dashboard_main.ControlPlane(dashboard_main.RUNTIME_DIR / "state")
    if action == "lock":
        control.lock("manual_lock", updated_by="dashboard")
        return {"status": "ok", "action": "locked"}
    if action == "unlock":
        control.unlock("manual_unlock", updated_by="dashboard")
        return {"status": "ok", "action": "unlocked"}
    return JSONResponse({"error": f"unknown action: {action}"}, status_code=400)


async def api_execution_state_reset():
    dashboard_main = _dashboard_main()
    state_file = dashboard_main.RUNTIME_DIR / "state" / "execution_state.json"
    state = dashboard_main._safe_read_json(state_file)
    if not isinstance(state, dict):
        state = {}

    submitted = state.get("submitted", {})
    previews = state.get("previews", {})
    sync = state.get("sync", {})
    history = state.get("history", [])

    summary = {
        "status": "ok",
        "backup": None,
        "cleared": {
            "submitted": len(submitted) if isinstance(submitted, dict) else 0,
            "previews": len(previews) if isinstance(previews, dict) else 0,
            "sync": len(sync) if isinstance(sync, dict) else 0,
            "history": len(history) if isinstance(history, list) else 0,
        },
    }

    if state_file.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = dashboard_main.RUNTIME_DIR / "state" / f"execution_state.bak.{ts}.json"
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        backup_file.write_text(state_file.read_text())
        summary["backup"] = backup_file.name

    state["submitted"] = {}
    state["previews"] = {}
    state["sync"] = {}
    state["history"] = []
    dashboard_main._write_json_file(state_file, state)

    control = dashboard_main.ControlPlane(dashboard_main.RUNTIME_DIR / "state")
    control.lock("execution_state_reset", updated_by="dashboard")
    summary["engine_locked"] = True
    return summary


async def api_trading_mode_get():
    return _trading_mode_payload(_read_control_state())


async def api_trading_mode_set(body: dict):
    dashboard_main = _dashboard_main()
    mode = body.get("mode")
    if mode not in VALID_TRADING_MODES:
        return JSONResponse({"error": f"mode must be one of: {', '.join(VALID_TRADING_MODES)}"}, status_code=400)
    canonical_mode = mode if mode == "live_trade" else dashboard_main.legacy_ui_mode_to_canonical_mode(mode)
    control = dashboard_main.ControlPlane(dashboard_main.RUNTIME_DIR / "state")
    try:
        state = control.set_mode(
            canonical_mode,
            updated_by="dashboard",
            confirm_live=bool(body.get("confirm_live", False)),
            readiness_checklist_id=body.get("readiness_checklist_id"),
            checklist=body.get("checklist"),
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    payload = _trading_mode_payload(state)
    return {"status": "ok", **payload}


def register_control_routes(app) -> None:
    app.get("/api/scheduler")(api_scheduler_status)
    app.post("/api/scheduler/interval")(api_scheduler_interval)
    app.post("/api/scheduler/run")(api_scheduler_run)
    app.post("/api/control/{action}")(api_control)
    app.post("/api/execution-state/reset")(api_execution_state_reset)
    app.get("/api/trading/mode")(api_trading_mode_get)
    app.post("/api/trading/mode")(api_trading_mode_set)
