from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CANONICAL_MODES = {"off", "signal_only", "paper_trade", "live_trade"}
LEGACY_UI_MODES = {"off", "signals", "trade"}
LIVE_READINESS_REQUIRED_ITEMS = (
    "p0_safety_tests_passed",
    "p1_risk_tests_passed",
    "paper_shadow_20d_stable",
    "fee_model_confidence_ok",
    "recent_data_health_ok",
    "broker_no_unknown_open_orders",
    "execution_state_reconciled",
    "operator_confirmed",
)


def legacy_ui_mode_to_canonical_mode(mode: str | None) -> str:
    mapping = {
        "off": "off",
        "signals": "signal_only",
        "trade": "paper_trade",
    }
    return mapping.get(str(mode or "").strip(), "off")


def canonical_mode_to_legacy_ui_mode(mode: str | None) -> str:
    mapping = {
        "off": "off",
        "signal_only": "signals",
        "paper_trade": "trade",
        "live_trade": "trade",
    }
    return mapping.get(str(mode or "").strip(), "off")


class ControlPlane:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / 'control_state.json'
        if not self.path.exists():
            self._write(self._default_state())
        else:
            self._ensure_schema()

    def status(self) -> dict[str, Any]:
        return self._read()

    def mode(self) -> str:
        return str(self._read().get("global", {}).get("mode", "off"))

    def is_locked(self) -> bool:
        return bool(self._read().get('locked', False))

    def lock(self, reason: str, updated_by: str = 'system') -> dict[str, Any]:
        state = self._read()
        state['locked'] = True
        state['reason'] = reason
        state['updated_at'] = self._ts()
        state['updated_by'] = updated_by
        state.setdefault('history', []).append({
            'ts': state['updated_at'],
            'action': 'lock',
            'reason': reason,
            'updated_by': updated_by,
        })
        self._write(state)
        return state

    def unlock(self, reason: str = 'manual_unlock', updated_by: str = 'operator') -> dict[str, Any]:
        state = self._read()
        state['locked'] = False
        state['reason'] = reason
        state['updated_at'] = self._ts()
        state['updated_by'] = updated_by
        state.setdefault('history', []).append({
            'ts': state['updated_at'],
            'action': 'unlock',
            'reason': reason,
            'updated_by': updated_by,
        })
        self._write(state)
        return state

    def clear_daily_loss_lock(
        self,
        reason: str = "daily_loss_override",
        updated_by: str = "operator",
    ) -> dict[str, Any]:
        state = self._read()
        risk_cfg = state.setdefault("risk", {})
        risk_cfg["daily_loss_locked"] = False
        if risk_cfg.get("reduce_only_reason") == "daily_loss_limit_exceeded":
            risk_cfg["reduce_only"] = False
            risk_cfg["reduce_only_reason"] = None
        state["updated_at"] = self._ts()
        state["updated_by"] = updated_by
        state.setdefault("history", []).append(
            {
                "ts": state["updated_at"],
                "action": "clear_daily_loss_lock",
                "reason": reason,
                "updated_by": updated_by,
            }
        )
        self._write(state)
        return state

    def set_mode(
        self,
        mode: str,
        updated_by: str = "operator",
        *,
        confirm_live: bool = False,
        readiness_checklist_id: str | None = None,
        checklist: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if mode not in CANONICAL_MODES:
            raise ValueError(f"unknown canonical mode: {mode}")
        state = self._read()
        if mode == "live_trade":
            state = self._apply_live_readiness(
                state,
                confirm_live=confirm_live,
                readiness_checklist_id=readiness_checklist_id,
                checklist=checklist,
                updated_by=updated_by,
            )
        state.setdefault("global", {})
        state["global"]["mode"] = mode
        state["updated_at"] = self._ts()
        state["updated_by"] = updated_by
        state.setdefault("history", []).append(
            {
                "ts": state["updated_at"],
                "action": "set_mode",
                "mode": mode,
                "updated_by": updated_by,
            }
        )
        self._write(state)
        return state

    def replace_state(self, state: dict[str, Any]) -> dict[str, Any]:
        self._write(state)
        return self._read()

    def update_risk(self, updates: dict[str, Any], updated_by: str = "system", action: str = "risk_update") -> dict[str, Any]:
        state = self._read()
        risk_cfg = state.setdefault("risk", {})
        risk_cfg.update(updates)
        state["updated_at"] = self._ts()
        state["updated_by"] = updated_by
        state.setdefault("history", []).append(
            {
                "ts": state["updated_at"],
                "action": action,
                "risk_updates": dict(updates),
                "updated_by": updated_by,
            }
        )
        self._write(state)
        return self._read()

    def signals_enabled(self) -> bool:
        state = self._read()
        return bool(state.get("global", {}).get("enabled", True)) and self.mode() != "off"

    def paper_execution_enabled(self) -> bool:
        state = self._read()
        return bool(state.get("global", {}).get("enabled", True)) and self.mode() in {"paper_trade", "live_trade"}

    def live_execution_enabled(self) -> bool:
        state = self._read()
        return bool(state.get("global", {}).get("enabled", True)) and self.mode() == "live_trade"

    def can_generate_signals(self, market: str | None = None, symbol: str | None = None) -> tuple[bool, str | None]:
        return self._evaluate_gate({"signal_only", "paper_trade", "live_trade"}, market=market, symbol=symbol)

    def can_build_order_intents(self, market: str | None = None, symbol: str | None = None) -> tuple[bool, str | None]:
        return self._evaluate_gate({"paper_trade", "live_trade"}, market=market, symbol=symbol)

    def can_live_submit(self, market: str | None = None, symbol: str | None = None) -> tuple[bool, str | None]:
        ok, reason = self._evaluate_gate({"live_trade"}, market=market, symbol=symbol)
        if not ok:
            return ok, reason
        readiness = self._read().get("live_readiness", self._default_live_readiness())
        if readiness.get("status") != "ready":
            return False, f"live_readiness:{readiness.get('status') or 'missing'}"
        if readiness.get("failed_items"):
            return False, "live_readiness:failed_items"
        return True, None

    def can_trade(self, market: str | None = None, symbol: str | None = None) -> tuple[bool, str | None]:
        return self.can_build_order_intents(market=market, symbol=symbol)

    def _default_state(self) -> dict[str, Any]:
        return {
            'locked': False,
            'reason': None,
            'updated_at': self._ts(),
            'updated_by': 'system',
            'global': {
                'enabled': True,
                'mode': 'off',
            },
            'trading_mode': 'off',
            'markets': {
                'US': True,
            },
            'symbols': {},
            'risk': {
                'reduce_only': False,
                'reduce_only_reason': None,
                'emergency_flatten': False,
                'daily_loss_locked': False,
                'trading_day': None,
                'day_start_equity_usd': None,
                'last_equity_usd': None,
                'daily_loss_pct': 0.0,
            },
            'live_readiness': self._default_live_readiness(),
            'history': [],
        }

    def _ensure_schema(self) -> None:
        state = self._read_raw()
        self._write(state)

    def _read(self) -> dict[str, Any]:
        return self._normalize_state(self._read_raw())

    def _write(self, data: dict[str, Any]) -> None:
        normalized = self._normalize_state(data)
        self.path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2))

    def _read_raw(self) -> dict[str, Any]:
        return json.loads(self.path.read_text())

    def _normalize_state(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        defaults = self._default_state()
        state = dict(raw) if isinstance(raw, dict) else {}

        normalized: dict[str, Any] = {
            "locked": bool(state.get("locked", defaults["locked"])),
            "reason": state.get("reason", defaults["reason"]),
            "updated_at": state.get("updated_at", defaults["updated_at"]),
            "updated_by": state.get("updated_by", defaults["updated_by"]),
        }

        global_cfg = state.get("global")
        if not isinstance(global_cfg, dict):
            global_cfg = {}

        mode = global_cfg.get("mode")
        if mode not in CANONICAL_MODES:
            legacy_mode = state.get("trading_mode")
            if legacy_mode in LEGACY_UI_MODES:
                mode = legacy_ui_mode_to_canonical_mode(legacy_mode)
            elif global_cfg.get("trade_mode") == "paper_live":
                mode = "paper_trade"
            else:
                mode = defaults["global"]["mode"]

        normalized["global"] = {
            "enabled": bool(global_cfg.get("enabled", defaults["global"]["enabled"])),
            "mode": mode,
        }
        normalized["trading_mode"] = canonical_mode_to_legacy_ui_mode(mode)

        markets = state.get("markets")
        normalized["markets"] = dict(markets) if isinstance(markets, dict) else dict(defaults["markets"])

        symbols = state.get("symbols")
        normalized["symbols"] = dict(symbols) if isinstance(symbols, dict) else {}

        risk = state.get("risk")
        if not isinstance(risk, dict):
            risk = {}
        normalized["risk"] = {
            "reduce_only": bool(risk.get("reduce_only", defaults["risk"]["reduce_only"])),
            "reduce_only_reason": risk.get("reduce_only_reason", defaults["risk"]["reduce_only_reason"]),
            "emergency_flatten": bool(risk.get("emergency_flatten", defaults["risk"]["emergency_flatten"])),
            "daily_loss_locked": bool(risk.get("daily_loss_locked", defaults["risk"]["daily_loss_locked"])),
            "trading_day": risk.get("trading_day", defaults["risk"]["trading_day"]),
            "day_start_equity_usd": self._optional_float(risk.get("day_start_equity_usd", defaults["risk"]["day_start_equity_usd"])),
            "last_equity_usd": self._optional_float(risk.get("last_equity_usd", defaults["risk"]["last_equity_usd"])),
            "daily_loss_pct": float(risk.get("daily_loss_pct", defaults["risk"]["daily_loss_pct"]) or 0.0),
        }

        live_readiness = state.get("live_readiness")
        normalized["live_readiness"] = self._normalize_live_readiness(
            live_readiness if isinstance(live_readiness, dict) else None
        )

        history = state.get("history")
        normalized["history"] = list(history) if isinstance(history, list) else []
        return normalized

    def _default_live_readiness(self) -> dict[str, Any]:
        return {
            "checklist_id": None,
            "status": "missing",
            "confirm_live": False,
            "items": {key: False for key in LIVE_READINESS_REQUIRED_ITEMS},
            "failed_items": list(LIVE_READINESS_REQUIRED_ITEMS),
            "updated_at": None,
            "updated_by": None,
        }

    def _normalize_live_readiness(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        defaults = self._default_live_readiness()
        raw = payload if isinstance(payload, dict) else {}
        raw_items = raw.get("items")
        normalized_items = {
            key: bool(raw_items.get(key, defaults["items"][key])) if isinstance(raw_items, dict) else defaults["items"][key]
            for key in LIVE_READINESS_REQUIRED_ITEMS
        }
        failed_items = [key for key, value in normalized_items.items() if not value]
        status = raw.get("status")
        if status not in {"missing", "blocked", "ready"}:
            status = "ready" if not failed_items and raw.get("checklist_id") else "missing" if not raw.get("checklist_id") else "blocked"
        return {
            "checklist_id": raw.get("checklist_id", defaults["checklist_id"]),
            "status": status,
            "confirm_live": bool(raw.get("confirm_live", defaults["confirm_live"])),
            "items": normalized_items,
            "failed_items": failed_items,
            "updated_at": raw.get("updated_at", defaults["updated_at"]),
            "updated_by": raw.get("updated_by", defaults["updated_by"]),
        }

    def _apply_live_readiness(
        self,
        state: dict[str, Any],
        *,
        confirm_live: bool,
        readiness_checklist_id: str | None,
        checklist: dict[str, Any] | None,
        updated_by: str,
    ) -> dict[str, Any]:
        checklist_id = str(readiness_checklist_id or "").strip() or None
        if not checklist_id:
            raise ValueError("readiness_checklist_id is required for live_trade")
        if not confirm_live:
            raise ValueError("confirm_live must be true for live_trade")

        raw_items = dict(checklist) if isinstance(checklist, dict) else {}
        raw_items["operator_confirmed"] = True
        live_readiness = self._normalize_live_readiness(
            {
                "checklist_id": checklist_id,
                "status": "blocked",
                "confirm_live": confirm_live,
                "items": raw_items,
                "updated_at": self._ts(),
                "updated_by": updated_by,
            }
        )
        if live_readiness["failed_items"]:
            live_readiness["status"] = "blocked"
            state["live_readiness"] = live_readiness
            state["updated_at"] = self._ts()
            state["updated_by"] = updated_by
            state.setdefault("history", []).append(
                {
                    "ts": state["updated_at"],
                    "action": "live_readiness_check_failed",
                    "checklist_id": checklist_id,
                    "failed_items": list(live_readiness["failed_items"]),
                    "updated_by": updated_by,
                }
            )
            self._write(state)
            raise ValueError(
                "live readiness checklist failed: " + ", ".join(live_readiness["failed_items"])
            )

        live_readiness["status"] = "ready"
        state["live_readiness"] = live_readiness
        return state

    def _evaluate_gate(
        self,
        allowed_modes: set[str],
        *,
        market: str | None = None,
        symbol: str | None = None,
    ) -> tuple[bool, str | None]:
        state = self._read()
        if state.get("locked"):
            return False, "manual_lock_active"
        global_cfg = state.get("global", {})
        if not global_cfg.get("enabled", True):
            return False, "global_gate_disabled"
        mode = str(global_cfg.get("mode", "off"))
        if mode not in allowed_modes:
            return False, f"mode:{mode}"
        if market:
            market_enabled = state.get("markets", {}).get(market, True)
            if not market_enabled:
                return False, f"market_disabled:{market}"
        if symbol:
            symbols_cfg = state.get("symbols", {})
            symbol_value = symbols_cfg.get(symbol, True)
            if isinstance(symbol_value, dict):
                if not symbol_value.get("enabled", True):
                    return False, f"symbol_disabled:{symbol}"
                if symbol_value.get("suspended", False):
                    return False, f"symbol_suspended:{symbol}"
            else:
                if not bool(symbol_value):
                    return False, f"symbol_disabled:{symbol}"
        return True, None

    def _ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _optional_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except Exception:
            return None
