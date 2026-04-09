from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, log_dir: str | Path):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def write_summary(self, summary: dict[str, Any]) -> dict[str, str]:
        ts = datetime.now(timezone.utc).isoformat()
        written: dict[str, str] = {}

        cycle_record = {
            'ts': ts,
            'cycle_id': summary.get('cycle_id'),
            'account_ok': summary.get('account_ok'),
            'assets_ok': summary.get('assets_ok'),
            'positions_ok': summary.get('positions_ok'),
            'active_orders_ok': summary.get('active_orders_ok'),
            'quote_access': summary.get('quote_access'),
            'asset_snapshot': summary.get('asset_snapshot'),
            'position_count': summary.get('position_count'),
            'active_order_count': summary.get('active_order_count'),
        }
        written['cycles'] = self._append('cycles.jsonl', cycle_record)

        strategy_record = {
            'ts': ts,
            'cycle_id': summary.get('cycle_id'),
            'signals': summary.get('strategy', {}).get('signals', []),
        }
        written['strategy'] = self._append('strategy.jsonl', strategy_record)

        risk_record = {
            'ts': ts,
            'cycle_id': summary.get('cycle_id'),
            'decisions': summary.get('risk', {}).get('decisions', []),
            'allowed_count': summary.get('risk', {}).get('allowed_count', 0),
            'preview_blockers': summary.get('risk', {}).get('preview_blockers', []),
        }
        written['risk'] = self._append('risk.jsonl', risk_record)

        intent_record = {
            'ts': ts,
            'cycle_id': summary.get('cycle_id'),
            'items': summary.get('order_intents', {}).get('items', []),
            'count': summary.get('order_intents', {}).get('count', 0),
        }
        written['intents'] = self._append('intents.jsonl', intent_record)

        notify_record = {
            'ts': ts,
            'cycle_id': summary.get('cycle_id'),
            'items': summary.get('notification_preview', {}).get('items', []),
            'count': summary.get('notification_preview', {}).get('count', 0),
            'dispatch_items': summary.get('notification_dispatch', {}).get('items', []),
            'dispatch_count': summary.get('notification_dispatch', {}).get('count', 0),
        }
        written['notifications'] = self._append('notifications.jsonl', notify_record)
        if notify_record['dispatch_count']:
            written['dispatch_queue'] = self._append('dispatch_queue.jsonl', {
                'ts': ts,
                'cycle_id': summary.get('cycle_id'),
                'items': notify_record['dispatch_items'],
            })

        exec_record = {
            'ts': ts,
            'cycle_id': summary.get('cycle_id'),
            'preview_checks': summary.get('execution_preview_check', {}).get('items', []),
            'submit_items': summary.get('execution_submit', {}).get('items', []),
            'sync_items': summary.get('order_sync', {}).get('items', []),
        }
        written['execution'] = self._append('execution.jsonl', exec_record)
        return written

    def _append(self, filename: str, record: dict[str, Any]) -> str:
        path = self.log_dir / filename
        with path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        return str(path)
