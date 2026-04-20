from __future__ import annotations

import threading
import sys
from datetime import datetime

from fastapi.responses import JSONResponse


VALID_TRADING_MODES = {"off", "signals", "trade"}
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
    canonical_mode = state.get("global", {}).get("mode", "off")  # type: ignore[union-attr]
    mode = dashboard_main.canonical_mode_to_legacy_ui_mode(canonical_mode)
    risk_cfg = state.get("risk", {}) if isinstance(state.get("risk"), dict) else {}
    reduce_only = bool(risk_cfg.get("reduce_only", False))
    emergency_flatten = bool(risk_cfg.get("emergency_flatten", False))
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
        "canonical_mode": canonical_mode,
        "locked": state.get("locked", False),
        "signal_generation": mode != "off",
        "order_submission": mode == "trade",
        "reduce_only": reduce_only,
        "reduce_only_reason": risk_cfg.get("reduce_only_reason"),
        "emergency_flatten": emergency_flatten,
        "risk_state": risk_state,
        "risk_label": risk_label,
    }


async def api_scheduler_status():
    dashboard_main = _dashboard_main()
    if not dashboard_main.scheduler:
        return {"running": False, "error": "scheduler not initialized"}
    return dashboard_main.scheduler.get_state()


async def api_scheduler_interval(body: dict):
    dashboard_main = _dashboard_main()
    if not dashboard_main.scheduler:
        return JSONResponse({"error": "scheduler not initialized"}, status_code=503)
    interval = body.get("interval")
    if not isinstance(interval, int) or interval < 10:
        return JSONResponse({"error": "interval must be >= 10 seconds"}, status_code=400)
    dashboard_main.scheduler.set_interval(interval)
    return {"status": "ok", "interval": interval}


async def api_scheduler_run():
    dashboard_main = _dashboard_main()
    if not dashboard_main.scheduler:
        return JSONResponse({"error": "scheduler not initialized"}, status_code=503)
    thread = threading.Thread(target=dashboard_main.scheduler._run_cycle, daemon=True)
    thread.start()
    return {"status": "ok", "message": "cycle triggered"}


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
    canonical_mode = dashboard_main.legacy_ui_mode_to_canonical_mode(mode)
    control = dashboard_main.ControlPlane(dashboard_main.RUNTIME_DIR / "state")
    state = control.set_mode(canonical_mode, updated_by="dashboard")
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
