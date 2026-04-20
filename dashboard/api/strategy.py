from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi.responses import JSONResponse


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


async def api_engine():
    dashboard_main = _dashboard_main()

    result = {}
    cycle_file = dashboard_main.RUNTIME_DIR / ".last_execution_cycle.json"
    if cycle_file.exists():
        try:
            result["last_cycle"] = json.loads(cycle_file.read_text())
        except Exception as e:
            result["last_cycle_error"] = str(e)
    else:
        result["last_cycle"] = None

    state_file = dashboard_main.RUNTIME_DIR / "state" / "control_state.json"
    if state_file.exists():
        try:
            result["control_state"] = json.loads(state_file.read_text())
        except Exception:
            result["control_state"] = None
    else:
        result["control_state"] = None
    return result


def _read_cycle() -> dict | None:
    dashboard_main = _dashboard_main()

    cycle_file = dashboard_main.RUNTIME_DIR / ".last_execution_cycle.json"
    if cycle_file.exists():
        try:
            return json.loads(cycle_file.read_text())
        except Exception:
            pass
    return None


async def api_signals():
    cycle = _read_cycle()
    if not cycle:
        return {"signals": [], "cycle_id": None, "timeframe": None}
    strategy = cycle.get("strategy", {})
    return {
        "signals": strategy.get("signals", []),
        "cycle_id": cycle.get("cycle_id"),
        "timeframe": strategy.get("timeframe"),
    }


async def api_risk():
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


async def api_execution_preview():
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


async def api_notifications():
    cycle = _read_cycle()
    if not cycle:
        return {"notifications": None, "cycle_id": None}
    return {
        "notifications": cycle.get("notification_preview"),
        "dispatch_requests": cycle.get("dispatch_requests"),
        "cycle_id": cycle.get("cycle_id"),
    }


async def api_rules_get():
    dashboard_main = _dashboard_main()

    if not dashboard_main.RULES_FILE.exists():
        return {"rules": [], "global_settings": {}}
    try:
        return json.loads(dashboard_main.RULES_FILE.read_text())
    except Exception as e:
        return JSONResponse({"error": f"Failed to load rules: {e}"}, status_code=500)


async def api_rules_update(rules_data: dict):
    dashboard_main = _dashboard_main()
    import shutil
    from datetime import datetime

    if "rules" not in rules_data:
        return JSONResponse({"error": "Missing 'rules' field"}, status_code=400)

    validation = dashboard_main.validate_rules_config(rules_data)
    if not validation["valid"]:
        return JSONResponse(
            {"valid": False, "errors": validation["errors"], "warnings": validation["warnings"]},
            status_code=400,
        )

    if dashboard_main.RULES_FILE.exists():
        backup_dir = dashboard_main.RULES_DIR / "rules_backup"
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"rules_{timestamp}.json"
        shutil.copy2(dashboard_main.RULES_FILE, backup_file)

    rules_data["updated_at"] = datetime.now().isoformat()
    if "version" not in rules_data:
        rules_data["version"] = "1.0"

    dashboard_main.RULES_FILE.write_text(json.dumps(rules_data, indent=2, ensure_ascii=False))
    return {"status": "ok", "message": "Rules updated", "backup_created": dashboard_main.RULES_FILE.exists()}


async def api_rules_validate(rules_data: dict):
    dashboard_main = _dashboard_main()

    validation = dashboard_main.validate_rules_config(rules_data)
    return {
        "valid": validation["valid"],
        "errors": validation["errors"],
        "warnings": validation["warnings"],
    }


async def api_rules_test(body: dict):
    dashboard_main = _dashboard_main()
    import sys

    backtest_src = str(Path(dashboard_main.__file__).parent.parent / "system" / "engine" / "src")
    if backtest_src not in sys.path:
        sys.path.insert(0, backtest_src)

    from engine.backtest import BacktestConfig, run_backtest

    symbol = body.get("symbol", "AAPL")
    start_date = body.get("start_date", "2026-01-01")
    end_date = body.get("end_date", "2026-04-01")

    config = BacktestConfig(
        symbols=[symbol],
        start_date=start_date,
        end_date=end_date,
        timeframe="30min",
        initial_capital=100000.0,
        data_source="yfinance",
    )
    result = run_backtest(config, dashboard_main.RULES_FILE)
    return {"status": "ok", "result": result.to_dict()}


async def api_engine_health():
    dashboard_main = _dashboard_main()

    result = {"status": "unknown"}
    cycle_file = dashboard_main.RUNTIME_DIR / ".last_execution_cycle.json"
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
    state_file = dashboard_main.RUNTIME_DIR / "state" / "control_state.json"
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            result["locked"] = state.get("locked", False)
        except Exception:
            pass
    return result


async def api_news():
    dashboard_main = _dashboard_main()

    news_file = dashboard_main.NEWS_DIR / "latest.json"
    if not news_file.exists():
        return {"items": [], "generated_at": None, "shift": None, "meta": {}}
    try:
        return json.loads(news_file.read_text())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_news_update(body: dict):
    dashboard_main = _dashboard_main()

    dashboard_main.NEWS_DIR.mkdir(parents=True, exist_ok=True)
    news_file = dashboard_main.NEWS_DIR / "latest.json"
    if news_file.exists():
        backup = dashboard_main.NEWS_DIR / "latest_prev.json"
        backup.write_text(news_file.read_text())
    news_file.write_text(json.dumps(body, indent=2, ensure_ascii=False))
    return {"status": "ok", "items": len(body.get("items", [])), "shift": body.get("shift")}


async def api_news_sources():
    dashboard_main = _dashboard_main()

    sources_file = dashboard_main.NEWS_DIR_PATH / "sources.json"
    if not sources_file.exists():
        return {"sources": []}
    try:
        return json.loads(sources_file.read_text())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def api_news_sources_update(body: dict):
    dashboard_main = _dashboard_main()

    sources_file = dashboard_main.NEWS_DIR_PATH / "sources.json"
    if not sources_file.exists():
        return JSONResponse({"error": "sources.json not found"}, status_code=404)

    try:
        config = json.loads(sources_file.read_text())
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

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


async def api_strategy_overview():
    dashboard_main = _dashboard_main()

    try:
        return dashboard_main._build_strategy_overview()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def register_strategy_routes(app) -> None:
    app.get("/api/engine")(api_engine)
    app.get("/api/signals")(api_signals)
    app.get("/api/risk")(api_risk)
    app.get("/api/execution-preview")(api_execution_preview)
    app.get("/api/notifications")(api_notifications)
    app.get("/api/rules")(api_rules_get)
    app.put("/api/rules")(api_rules_update)
    app.post("/api/rules/validate")(api_rules_validate)
    app.post("/api/rules/test")(api_rules_test)
    app.get("/api/health/engine")(api_engine_health)
    app.get("/api/news")(api_news)
    app.post("/api/news")(api_news_update)
    app.get("/api/news/sources")(api_news_sources)
    app.put("/api/news/sources")(api_news_sources_update)
    app.get("/api/strategy-overview")(api_strategy_overview)
