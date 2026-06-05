from __future__ import annotations

import json
import os
import sys

from fastapi import File, UploadFile
from fastapi.responses import JSONResponse

from dashboard.services.runtime import create_dashboard_bindings, get_broker_account_info


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


def _parse_properties(text: str) -> dict:
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
    if not val or len(val) <= visible:
        return "****"
    return "*" * (len(val) - visible) + val[-visible:]


def _get_broker_account_info(config_dir: str) -> dict:
    try:
        return get_broker_account_info(config_dir)
    except Exception as e:
        return {"error": str(e)}


def _account_type_to_mode(account_type: str) -> str | None:
    at = str(account_type).upper().strip()
    if at == "PAPER":
        return "paper"
    if at in ("GLOBAL", "STANDARD"):
        return "live"
    return None


def _broker_config_upload_enabled() -> bool:
    value = os.environ.get("DASHBOARD_ENABLE_CONFIG_UPLOAD", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


async def api_config_get():
    dashboard_main = _dashboard_main()

    config_file = dashboard_main._app_config_file()
    if not config_file.exists():
        return JSONResponse({"error": "config not found"}, status_code=404)
    return dashboard_main._load_effective_app_config()


async def api_config_update(update: dict):
    dashboard_main = _dashboard_main()

    config_file = dashboard_main._app_config_file()
    if not config_file.exists():
        return JSONResponse({"error": "config not found"}, status_code=404)

    user_updates: dict[str, object] = {}
    if "broker" in update and isinstance(update["broker"], dict):
        broker_update = dict(update["broker"])
        if "platform" in broker_update:
            platform = str(broker_update["platform"]).strip()
            if platform not in dashboard_main.available_brokers():
                return JSONResponse(
                    {"error": f"invalid broker platform: {platform}", "available": dashboard_main.available_brokers()},
                    status_code=400,
                )
            user_updates.setdefault("broker", {})["platform"] = platform  # type: ignore[index]
    if "risk" in update:
        user_updates["risk"] = update["risk"]
    if "markets" in update:
        user_updates["markets"] = update["markets"]
    if "strategy" in update and "timeframe" in update["strategy"]:
        user_updates.setdefault("strategy", {})["timeframe"] = update["strategy"]["timeframe"]  # type: ignore[index]
    if not user_updates:
        return {"status": "ok", "config": dashboard_main._load_effective_app_config()}

    _, settings_path = dashboard_main._merge_app_user_settings(user_updates)
    return {
        "status": "ok",
        "config": dashboard_main._load_effective_app_config(),
        "user_settings_path": str(settings_path),
    }


async def api_broker_config_get():
    dashboard_main = _dashboard_main()
    upload_enabled = _broker_config_upload_enabled()

    if not dashboard_main.BROKER_PROPS_FILE.exists():
        return {
            "exists": False,
            "mode": "paper",
            "broker_platform": dashboard_main._current_broker_platform(),
            "fields": {},
            "account_info": None,
            "upload_enabled": upload_enabled,
        }
    props = _parse_properties(dashboard_main.BROKER_PROPS_FILE.read_text())
    masked = {}
    sensitive = {"private_key_pk1", "private_key_pk8", "secret_key"}
    for key, value in props.items():
        masked[key] = _mask_value(value) if key in sensitive else value
    config_file = dashboard_main._app_config_file()
    mode = "paper"
    if config_file.exists():
        try:
            mode = dashboard_main._load_effective_app_config().get("mode", "paper")
        except Exception:
            pass
    broker_platform = dashboard_main._current_broker_platform()
    account_info = None
    try:
        account_info = _get_broker_account_info(str(dashboard_main.BROKER_PROPERTIES_DIR))
        detected = _account_type_to_mode(account_info.get("account_type", ""))
        if detected:
            mode = detected
            if config_file.exists():
                try:
                    effective = dashboard_main._load_effective_app_config()
                    if effective.get("mode") != mode:
                        dashboard_main._merge_app_user_settings({"mode": mode})
                except Exception:
                    pass
    except Exception as e:
        account_info = {"error": str(e)}
    return {
        "exists": True,
        "mode": mode,
        "broker_platform": broker_platform,
        "fields": masked,
        "account_info": account_info,
        "upload_enabled": upload_enabled,
    }


async def api_broker_config_upload_file(file: UploadFile = File(...)):
    dashboard_main = _dashboard_main()
    if not _broker_config_upload_enabled():
        return JSONResponse(
            {
                "error": "broker config upload disabled",
                "reason": "set DASHBOARD_ENABLE_CONFIG_UPLOAD=true only for local trusted development",
            },
            status_code=403,
        )

    content_bytes = await file.read()
    if len(content_bytes) > 64 * 1024:
        return JSONResponse({"error": "file too large (max 64KB)"}, status_code=400)

    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return JSONResponse({"error": "file must be UTF-8 text"}, status_code=400)

    props = _parse_properties(content)
    required = {"tiger_id", "account"}
    missing = required - set(props.keys())
    if missing:
        return JSONResponse({"error": f"missing required fields: {', '.join(missing)}"}, status_code=400)
    for key in required:
        if not props[key].strip():
            return JSONResponse({"error": f"{key} must not be empty"}, status_code=400)

    has_key = "private_key_pk8" in props or "private_key_pk1" in props
    if not has_key:
        return JSONResponse({"error": "missing private key (private_key_pk8 or private_key_pk1)"}, status_code=400)

    if dashboard_main.BROKER_PROPS_FILE.exists():
        from datetime import datetime

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = dashboard_main.BROKER_PROPERTIES_DIR / f"tiger_openapi_config.properties.bak.{ts}"
        backup.write_text(dashboard_main.BROKER_PROPS_FILE.read_text())

    dashboard_main.BROKER_PROPS_FILE.write_text(content)

    state_file = dashboard_main.RUNTIME_DIR / "state" / "execution_state.json"
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
                bak = dashboard_main.RUNTIME_DIR / "state" / f"execution_state.bak.{ts}.json"
                bak.write_text(state_file.read_text())
                old_state["submitted"] = {}
                old_state["previews"] = {}
                old_state["sync"] = {}
                old_state["history"] = []
                state_file.write_text(json.dumps(old_state, indent=2, ensure_ascii=False))
                state_cleared = True
        except Exception:
            pass

    broker_client = None
    cache = None
    if dashboard_main.cache:
        dashboard_main.cache.stop()
    try:
        provider_name = dashboard_main.os.environ.get("ENGINE_QUOTE_PROVIDER", "yfinance")
        broker_client, _, cache = create_dashboard_bindings(
            broker_properties_dir=dashboard_main.BROKER_PROPERTIES_DIR,
            config_dir=dashboard_main.CONFIG_DIR_PATH,
            provider_name=provider_name,
            refresh_interval=30,
        )
        cache.start()
    except Exception:
        broker_client = None
        cache = None

    dashboard_main.broker_client = broker_client
    dashboard_main.cache = cache

    account_info = None
    detected = None
    if broker_client:
        try:
            account_info = _get_broker_account_info(str(dashboard_main.BROKER_PROPERTIES_DIR))
            detected = _account_type_to_mode(account_info.get("account_type", ""))
            if detected:
                config_file = dashboard_main._app_config_file()
                if config_file.exists():
                    dashboard_main._merge_app_user_settings({"mode": detected})
        except Exception as e:
            account_info = {"error": str(e)}

    return {
        "status": "ok",
        "filename": dashboard_main.BROKER_PROPS_FILE.name,
        "tiger_id": props.get("tiger_id"),
        "account": props.get("account"),
        "has_private_key": has_key,
        "account_info": account_info,
        "detected_mode": detected,
        "state_cleared": state_cleared,
    }


async def api_config_mode(body: dict):
    dashboard_main = _dashboard_main()

    mode = body.get("mode")
    if mode not in ("paper", "live"):
        return JSONResponse({"error": "mode must be paper or live"}, status_code=400)
    config_file = dashboard_main._app_config_file()
    if not config_file.exists():
        return JSONResponse({"error": "config not found"}, status_code=404)
    user_updates: dict[str, object] = {"mode": mode}
    if mode == "live":
        user_updates["execution"] = {"live_submit": False, "live_cancel": False}
    dashboard_main._merge_app_user_settings(user_updates)
    return {"status": "ok", "mode": mode}


def register_config_routes(app) -> None:
    app.get("/api/config")(api_config_get)
    app.patch("/api/config")(api_config_update)
    app.get("/api/broker-config")(api_broker_config_get)
    app.get("/api/tiger-config")(api_broker_config_get)
    app.post("/api/broker-config/upload")(api_broker_config_upload_file)
    app.post("/api/tiger-config/upload")(api_broker_config_upload_file)
    app.post("/api/config/mode")(api_config_mode)
