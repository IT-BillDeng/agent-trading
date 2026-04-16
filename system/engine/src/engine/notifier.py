from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class NotificationPreview:
    channel: str
    enabled: bool
    preview_only: bool
    level: str
    title: str
    body: str
    meta: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NotificationBuilder:
    def __init__(self, app_config: dict[str, Any]):
        notify = dict(app_config.get('notify', {}))
        self.telegram_enabled = bool(notify.get('telegram', False))
        self.telegram_preview_only = bool(notify.get('telegram_preview_only', True))
        self.telegram_send_enabled = bool(notify.get('telegram_send_enabled', False))
        self.telegram_target = self._resolve_target(notify.get('telegram_target'))

    @staticmethod
    def _resolve_target(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        if value.startswith('${') and value.endswith('}'):
            env_key = value[2:-1].strip()
            return os.environ.get(env_key)
        return value

    def build_from_summary(self, summary: dict[str, Any]) -> list[NotificationPreview]:
        previews: list[NotificationPreview] = []
        if self.telegram_enabled:
            previews.append(self._build_cycle_digest(summary))
            previews.extend(self._build_execution_alerts(summary))
            lock_alert = self._build_lock_alert(summary)
            if lock_alert is not None:
                previews.append(lock_alert)
        return previews

    def build_dispatch_requests(self, notifications: list[dict[str, Any]] | list[NotificationPreview]) -> list[dict[str, Any]]:
        requests: list[dict[str, Any]] = []
        for item in notifications:
            data = item.to_dict() if hasattr(item, 'to_dict') else dict(item)
            if data.get('channel') != 'telegram':
                continue
            if not self.telegram_send_enabled or not self.telegram_target:
                continue
            requests.append({
                'channel': 'telegram',
                'target': self.telegram_target,
                'message': f"{data.get('title')}\n{data.get('body')}",
                'meta': data.get('meta', {}),
            })
        return requests

    def _build_cycle_digest(self, summary: dict[str, Any]) -> NotificationPreview:
        strategy = summary.get('strategy', {})
        risk = summary.get('risk', {})
        execution_preview = summary.get('execution_preview', {})
        signals = strategy.get('signals', [])
        buy_signals = [item for item in signals if item.get('action') == 'BUY']
        exit_signals = [item for item in signals if item.get('action') == 'EXIT']
        blockers = risk.get('preview_blockers', [])
        buy_text = ', '.join(f"{item.get('symbol')}({item.get('score')})" for item in buy_signals[:5]) or 'none'
        blocker_parts: list[str] = []
        for item in blockers[:5]:
            if isinstance(item, dict):
                blocker_parts.append(f"{item.get('symbol') or 'system'}:{item.get('reason')}")
            else:
                blocker_parts.append(f"system:{item}")
        blocker_text = ', '.join(blocker_parts) or 'none'
        body = '\n'.join([
            f"cycle_id={summary.get('cycle_id', 'n/a')}",
            f"BUY={len(buy_signals)} [{buy_text}] | EXIT={len(exit_signals)}",
            f"risk_allowed={risk.get('allowed_count', 0)} submit_ready={execution_preview.get('count', 0)}", 
            f"blockers={blocker_text}",
            f"US.quote_delay={summary.get('quote_access', {}).get('US', {}).get('quote_delay', {}).get('ok')}",
        ])
        return NotificationPreview(
            channel='telegram',
            enabled=True,
            preview_only=self.telegram_preview_only,
            level='info',
            title='[PAPER][30m] Cycle digest',
            body=body,
            meta={'kind': 'cycle_digest'},
        )

    def _build_signal_alerts(self, summary: dict[str, Any]) -> list[NotificationPreview]:
        signals = summary.get('strategy', {}).get('signals', [])
        decisions = {item['symbol']: item for item in summary.get('risk', {}).get('decisions', [])}
        alerts: list[NotificationPreview] = []
        for signal in signals:
            if signal.get('action') not in ('BUY', 'EXIT'):
                continue
            decision = decisions.get(signal['symbol'], {})
            level = 'success' if decision.get('allowed') else 'warning'
            title = f"[PAPER][{signal['market']}] {signal['action']} {signal['symbol']}"
            reason_line = f"reason={signal.get('reason')} score={signal.get('score')}"
            risk_line = f"risk_allowed={decision.get('allowed')} blockers={','.join(decision.get('reasons', [])) or 'none'}"
            price_line = f"last_close={signal.get('last_close')} stop={signal.get('stop_loss')} take={signal.get('take_profit')}"
            body = '\n'.join([reason_line, risk_line, price_line])
            alerts.append(NotificationPreview(
                channel='telegram',
                enabled=True,
                preview_only=self.telegram_preview_only,
                level=level,
                title=title,
                body=body,
                meta={'kind': 'signal_alert', 'symbol': signal['symbol']},
            ))
        return alerts

    def _build_execution_alerts(self, summary: dict[str, Any]) -> list[NotificationPreview]:
        alerts: list[NotificationPreview] = []
        for item in summary.get('order_sync', {}).get('items', []):
            normalized = item.get('normalized') or {}
            if not normalized:
                continue
            title = f"[PAPER][SYNC] {normalized.get('symbol')} {normalized.get('status') or 'UNKNOWN'}"
            body = '\n'.join([
                f"filled={normalized.get('filled_quantity')} remaining={normalized.get('remaining_quantity')}",
                f"avg_fill={normalized.get('avg_fill_price')} commission={normalized.get('commission_total')}",
                f"transactions={normalized.get('transactions_count')}",
            ])
            alerts.append(NotificationPreview(
                channel='telegram',
                enabled=True,
                preview_only=self.telegram_preview_only,
                level='info',
                title=title,
                body=body,
                meta={'kind': 'execution_sync', 'symbol': normalized.get('symbol')},
            ))
        return alerts

    def _build_lock_alert(self, summary: dict[str, Any]) -> NotificationPreview | None:
        control = summary.get('control') or {}
        if not control.get('locked'):
            return None
        return NotificationPreview(
            channel='telegram',
            enabled=True,
            preview_only=self.telegram_preview_only,
            level='warning',
            title='[PAPER][LOCKED] Execution locked',
            body='\n'.join([
                f"reason={control.get('reason')}",
                f"updated_by={control.get('updated_by')}",
                f"updated_at={control.get('updated_at')}",
            ]),
            meta={'kind': 'control_lock'},
        )
