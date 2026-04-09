from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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

    def can_trade(self, market: str | None = None, symbol: str | None = None) -> tuple[bool, str | None]:
        state = self._read()
        if state.get('locked'):
            return False, 'manual_lock_active'
        global_cfg = state.get('global', {})
        if not global_cfg.get('enabled', True):
            return False, 'global_gate_disabled'
        if global_cfg.get('trade_mode', 'disabled') != 'paper_live':
            return False, f"trade_mode:{global_cfg.get('trade_mode', 'disabled')}"
        if market:
            market_enabled = state.get('markets', {}).get(market, True)
            if not market_enabled:
                return False, f'market_disabled:{market}'
        if symbol:
            symbols_cfg = state.get('symbols', {})
            symbol_value = symbols_cfg.get(symbol, True)
            if isinstance(symbol_value, dict):
                symbol_enabled = symbol_value.get('enabled', True)
            else:
                symbol_enabled = bool(symbol_value)
            if not symbol_enabled:
                return False, f'symbol_disabled:{symbol}'
        return True, None

    def _default_state(self) -> dict[str, Any]:
        return {
            'locked': False,
            'reason': None,
            'updated_at': self._ts(),
            'updated_by': 'system',
            'global': {
                'enabled': True,
                'trade_mode': 'paper_live',
            },
            'markets': {
                'US': True,
            },
            'symbols': {},
            'history': [],
        }

    def _ensure_schema(self) -> None:
        state = self._read()
        changed = False
        defaults = self._default_state()
        for key, value in defaults.items():
            if key not in state:
                state[key] = value
                changed = True
        if not isinstance(state.get('global'), dict):
            state['global'] = defaults['global']
            changed = True
        else:
            for key, value in defaults['global'].items():
                if key not in state['global']:
                    state['global'][key] = value
                    changed = True
        for section in ('markets', 'history'):
            if not isinstance(state.get(section), type(defaults[section])):
                state[section] = defaults[section]
                changed = True
        if not isinstance(state.get('symbols'), dict):
            state['symbols'] = defaults['symbols']
            changed = True
        if changed:
            self._write(state)

    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text())

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()
