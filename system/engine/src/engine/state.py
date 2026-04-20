from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / 'execution_state.json'
        if not self.path.exists():
            self._write({'submitted': {}, 'cancelled': {}, 'previews': {}, 'sync': {}, 'history': []})

    def has_submitted(self, idempotency_key: str) -> bool:
        state = self._read()
        return idempotency_key in state.get('submitted', {})

    def get_submitted_record(self, idempotency_key: str) -> dict[str, Any] | None:
        state = self._read()
        record = state.get('submitted', {}).get(idempotency_key)
        return dict(record) if isinstance(record, dict) else None

    def get_submitted(self) -> dict[str, Any]:
        state = self._read()
        return dict(state.get('submitted', {}))

    def get_sync_record(self, key: str) -> dict[str, Any] | None:
        state = self._read()
        record = state.get('sync', {}).get(key)
        return dict(record) if isinstance(record, dict) else None

    def mark_preview(self, idempotency_key: str, record: dict[str, Any]) -> None:
        state = self._read()
        state.setdefault('previews', {})[idempotency_key] = record
        state.setdefault('history', []).append({'ts': self._ts(), 'kind': 'preview', 'idempotency_key': idempotency_key, 'record': record})
        self._write(state)

    def mark_submitted(self, idempotency_key: str, record: dict[str, Any]) -> None:
        state = self._read()
        state.setdefault('submitted', {})[idempotency_key] = record
        state.setdefault('history', []).append({'ts': self._ts(), 'kind': 'submitted', 'idempotency_key': idempotency_key, 'record': record})
        self._write(state)

    def mark_cancelled(self, order_ref: str, record: dict[str, Any]) -> None:
        state = self._read()
        state.setdefault('cancelled', {})[order_ref] = record
        state.setdefault('history', []).append({'ts': self._ts(), 'kind': 'cancelled', 'order_ref': order_ref, 'record': record})
        self._write(state)

    def mark_sync(self, key: str, record: dict[str, Any]) -> None:
        state = self._read()
        state.setdefault('sync', {})[key] = record
        state.setdefault('history', []).append({'ts': self._ts(), 'kind': 'sync', 'key': key, 'record': record})
        self._write(state)

    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text())

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()


class TradeLimitStore:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / 'trade_limits_state.json'
        if not self.path.exists():
            self._write(self._default_state())

    def snapshot(self, trading_day: str) -> dict[str, Any]:
        state = self._read()
        if state.get('trading_day') != trading_day:
            state = self._reset_for_day(trading_day)
            self._write(state)
        return state

    def record_trade(
        self,
        trading_day: str,
        *,
        symbol: str,
        side: str,
        ts: str | None = None,
        pnl: float | None = None,
    ) -> dict[str, Any]:
        ts = ts or self._ts()
        state = self.snapshot(trading_day)
        state['total_trades'] = int(state.get('total_trades', 0)) + 1
        symbol_state = state.setdefault('symbols', {}).setdefault(
            symbol,
            {
                'trade_count': 0,
                'last_order_at': None,
                'last_side': None,
                'last_loss_at': None,
            },
        )
        symbol_state['trade_count'] = int(symbol_state.get('trade_count', 0)) + 1
        symbol_state['last_order_at'] = ts
        symbol_state['last_side'] = side
        if pnl is not None:
            try:
                if float(pnl) < 0:
                    symbol_state['last_loss_at'] = ts
            except Exception:
                pass
        state.setdefault('history', []).append(
            {
                'ts': ts,
                'kind': 'trade_recorded',
                'symbol': symbol,
                'side': side,
                'trading_day': trading_day,
                'pnl': pnl,
            }
        )
        self._write(state)
        return state

    def _default_state(self) -> dict[str, Any]:
        return {
            'trading_day': None,
            'total_trades': 0,
            'symbols': {},
            'history': [],
        }

    def _reset_for_day(self, trading_day: str) -> dict[str, Any]:
        return {
            'trading_day': trading_day,
            'total_trades': 0,
            'symbols': {},
            'history': [],
        }

    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text())

    def _write(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def _ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()
