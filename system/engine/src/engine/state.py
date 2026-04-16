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
