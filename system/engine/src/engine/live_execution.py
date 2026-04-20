from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .broker_fee_artifacts import record_fee_calibration
from .control import ControlPlane
from .state import StateStore
from .sync import normalize_order_snapshot
from .broker_client import BrokerClient


@dataclass
class PreviewResult:
    intent_id: str
    symbol: str
    ok: bool
    reason: str
    warning_text: str | None
    payload: dict[str, Any]
    response: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SubmitResult:
    intent_id: str
    symbol: str
    submitted: bool
    mode: str
    reason: str
    response: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LiveExecutionAdapter:
    TERMINAL_ORDER_STATUSES = {
        'filled',
        'cancelled',
        'canceled',
        'rejected',
        'expired',
    }

    def __init__(self, app_config: dict[str, Any], client: BrokerClient):
        execution = dict(app_config.get('execution', {}))
        system = dict(app_config.get('system', {}))
        self.app_mode = str(app_config.get('mode', 'paper'))
        self.client = client
        self.submit_mode = str(execution.get('submit_mode', 'guarded'))
        self.allow_live_submit = bool(execution.get('live_submit', False))
        self.allow_live_cancel = bool(execution.get('live_cancel', False))
        self.enable_preview_check = bool(execution.get('preview_check', True))
        state_dir = system.get('state_dir', './state')
        if not Path(state_dir).is_absolute():
            state_dir = Path(__file__).resolve().parents[2] / state_dir
        self.state = StateStore(state_dir)
        self.control = ControlPlane(state_dir)

    def preview_intents(self, intents: list[dict[str, Any]], contracts: dict[str, dict[str, dict[str, Any]]]) -> list[PreviewResult]:
        return [self.preview_intent(intent, contracts) for intent in intents]

    def preview_intent(self, intent: dict[str, Any], contracts: dict[str, dict[str, dict[str, Any]]]) -> PreviewResult:
        payload = self._build_payload(intent, contracts)
        order_no = self.client.create_order_no()
        order_no_data = self._extract_order_no(order_no)
        if order_no.get('body', {}).get('code') != 0 or order_no_data is None:
            preview = PreviewResult(intent['intent_id'], intent['symbol'], False, 'order_no_failed', None, payload, order_no)
            self.state.mark_preview(intent['idempotency_key'], preview.to_dict())
            return preview

        payload['order_id'] = order_no_data
        response = self.client.preview_order(payload)
        body = response.get('body', {})
        data = body.get('data') or {}
        if isinstance(data, str):
            try:
                import json as _json
                data = _json.loads(data)
            except Exception:
                data = {}
        warning_text = None
        if isinstance(data, dict):
            warning_text = data.get('warningText') or data.get('warning_text') or data.get('message')
            # Treat isPass=false as a warning even without explicit warningText
            if not warning_text and data.get('isPass') is False:
                warning_text = data.get('message') or 'preview_not_passed'
        reason = self._map_preview_reason(body.get('code'), warning_text)
        ok = reason == 'preview_ok'
        preview = PreviewResult(intent['intent_id'], intent['symbol'], ok, reason, warning_text, payload, response)
        self.state.mark_preview(intent['idempotency_key'], preview.to_dict())
        return preview

    def submit_intents(self, intents: list[dict[str, Any]], contracts: dict[str, dict[str, dict[str, Any]]]) -> list[SubmitResult]:
        results: list[SubmitResult] = []
        for intent in intents:
            results.append(self.submit_intent(intent, contracts))
        return results

    def submit_intent(self, intent: dict[str, Any], contracts: dict[str, dict[str, dict[str, Any]]]) -> SubmitResult:
        idem = intent['idempotency_key']
        gate_ok, gate_reason = self.control.can_trade(intent.get('market'), intent.get('symbol'))
        if not gate_ok:
            return SubmitResult(intent['intent_id'], intent['symbol'], False, self.submit_mode, gate_reason or 'trade_gate_blocked', None)
        existing_submission = self.state.get_submitted_record(idem)
        if existing_submission and self._submission_is_active(idem, existing_submission):
            return SubmitResult(intent['intent_id'], intent['symbol'], False, self.submit_mode, 'duplicate_active_submission', None)

        preview_result = self.preview_intent(intent, contracts) if self.enable_preview_check else None
        if preview_result and not preview_result.ok:
            return SubmitResult(intent['intent_id'], intent['symbol'], False, self.submit_mode, preview_result.reason, preview_result.response)

        live_ok, live_reason = self._can_live_submit(intent)
        if not live_ok:
            return SubmitResult(
                intent['intent_id'],
                intent['symbol'],
                False,
                self.submit_mode,
                live_reason,
                preview_result.response if preview_result else None,
            )

        payload = dict(preview_result.payload if preview_result else self._build_payload(intent, contracts))
        if 'order_id' not in payload:
            order_no = self.client.create_order_no()
            order_no_data = self._extract_order_no(order_no)
            if order_no.get('body', {}).get('code') != 0 or order_no_data is None:
                return SubmitResult(intent['intent_id'], intent['symbol'], False, self.submit_mode, 'order_no_failed', order_no)
            payload['order_id'] = order_no_data

        response = self.client.place_order(payload)
        ok = response.get('body', {}).get('code') == 0
        if ok:
            self.state.mark_submitted(idem, {
                'intent_id': intent['intent_id'],
                'symbol': intent['symbol'],
                'payload': payload,
                'response': response,
            })
        return SubmitResult(intent['intent_id'], intent['symbol'], ok, self.submit_mode, 'submitted' if ok else 'place_order_failed', response)

    def sync_submitted_orders(self) -> list[dict[str, Any]]:
        submitted = self.state.get_submitted()
        snapshots: list[dict[str, Any]] = []
        for idem, record in submitted.items():
            snapshot = self._build_submission_snapshot(idem, record)
            if snapshot is None:
                continue
            snapshot['normalized'] = normalize_order_snapshot(snapshot)
            self.state.mark_sync(idem, snapshot)
            fee_calibration = snapshot['normalized'].get('fee_calibration')
            if fee_calibration:
                record_fee_calibration({
                    'idempotency_key': idem,
                    'intent_id': record.get('intent_id'),
                    'order_id': snapshot.get('order_id'),
                    'global_id': snapshot.get('global_id'),
                    **fee_calibration,
                })
            snapshots.append(snapshot)
        return snapshots

    def cancel_order(self, order_ref: str, id: int | None = None, order_id: int | None = None) -> SubmitResult:
        cancel_ok, cancel_reason = self._can_live_cancel()
        if not cancel_ok:
            return SubmitResult(order_ref, order_ref, False, self.submit_mode, cancel_reason, None)
        response = self.client.cancel_order(id=id, order_id=order_id)
        ok = response.get('body', {}).get('code') == 0
        if ok:
            self.state.mark_cancelled(order_ref, {'response': response})
        return SubmitResult(order_ref, order_ref, ok, self.submit_mode, 'cancelled' if ok else 'cancel_order_failed', response)

    def _build_payload(self, intent: dict[str, Any], contracts: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
        contract = contracts.get(intent['market'], {}).get(intent['symbol'], {})
        payload = {
            'symbol': intent['symbol'],
            'currency': contract.get('currency', 'USD'),
            'sec_type': contract.get('secType', 'STK'),
            'exchange': contract.get('primaryExchange') or contract.get('exchange'),
            'local_symbol': contract.get('localSymbol') or intent['symbol'],
            'multiplier': contract.get('multiplier'),
            'order_type': intent['order_type'],
            'action': intent['side'],
            'total_quantity': intent['quantity'],
            'time_in_force': intent['tif'],
            'outside_rth': False,
        }
        if intent.get('limit_price') is not None:
            payload['limit_price'] = intent['limit_price']
        if intent.get('stop_price') is not None:
            payload['aux_price'] = intent['stop_price']
        return payload

    def _map_preview_reason(self, code: Any, warning_text: str | None) -> str:
        if code == 0 and not warning_text:
            return 'preview_ok'
        text = (warning_text or '').lower()
        if code not in (0, '0', None):
            return 'preview_api_error'
        if not text:
            return 'preview_failed'
        mapping = {
            'insufficient': 'preview_insufficient_buying_power',
            'buying power': 'preview_insufficient_buying_power',
            'cash': 'preview_insufficient_cash',
            'position': 'preview_position_issue',
            'lot': 'preview_lot_size_issue',
            'tick': 'preview_tick_size_issue',
            'trading session': 'preview_session_restricted',
            'outside regular': 'preview_session_restricted',
            'market closed': 'preview_market_closed',
            'not tradable': 'preview_not_tradable',
            'price': 'preview_price_issue',
        }
        for needle, reason in mapping.items():
            if needle in text:
                return reason
        return 'preview_warning'

    def _extract_order_no(self, response: dict[str, Any]) -> int | None:
        data = (response.get('body') or {}).get('data')
        if isinstance(data, int):
            return data
        if isinstance(data, str):
            try:
                import json
                parsed = json.loads(data)
                if isinstance(parsed, dict):
                    raw = parsed.get('orderId') or parsed.get('order_id') or parsed.get('id')
                    return int(raw) if raw is not None else None
                return int(parsed)
            except Exception:
                try:
                    return int(data)
                except Exception:
                    return None
        if isinstance(data, dict):
            raw = data.get('orderId') or data.get('order_id') or data.get('id')
            return int(raw) if raw is not None else None
        return None

    def _can_live_submit(self, intent: dict[str, Any]) -> tuple[bool, str]:
        if self.app_mode != 'live':
            return False, f'app_mode:{self.app_mode}'
        if self.submit_mode != 'live' or not self.allow_live_submit:
            return False, 'guarded_mode'

        gate_ok, gate_reason = self.control.can_live_submit(intent.get('market'), intent.get('symbol'))
        if not gate_ok:
            return False, self._map_control_gate_reason(gate_reason)

        if str(intent.get('side', '')).upper() == 'BUY':
            risk_cfg = self.control.status().get('risk', {})
            if risk_cfg.get('reduce_only', False):
                return False, 'risk_reduce_only'
            if risk_cfg.get('emergency_flatten', False):
                return False, 'risk_emergency_flatten'

        return True, 'live_submit_allowed'

    def _can_live_cancel(self) -> tuple[bool, str]:
        if self.app_mode != 'live':
            return False, f'app_mode:{self.app_mode}'
        if not self.allow_live_cancel:
            return False, 'guarded_cancel_mode'

        gate_ok, gate_reason = self.control.can_live_submit()
        if not gate_ok:
            mapped = self._map_control_gate_reason(gate_reason)
            if mapped == 'guarded_mode':
                return False, 'guarded_cancel_mode'
            return False, mapped

        return True, 'live_cancel_allowed'

    def _map_control_gate_reason(self, reason: str | None) -> str:
        if not reason:
            return 'live_gate_blocked'
        if reason.startswith('mode:'):
            return f"control_mode:{reason.split(':', 1)[1]}"
        return reason

    def _submission_is_active(self, idem: str, record: dict[str, Any]) -> bool:
        sync_record = self.state.get_sync_record(idem)
        if sync_record and not self._normalized_snapshot_is_active(sync_record.get('normalized') or {}):
            return False

        snapshot = self._build_submission_snapshot(idem, record)
        if snapshot is None:
            return True
        normalized = normalize_order_snapshot(snapshot)
        snapshot['normalized'] = normalized
        self.state.mark_sync(idem, snapshot)
        return self._normalized_snapshot_is_active(normalized)

    def _build_submission_snapshot(self, idem: str, record: dict[str, Any]) -> dict[str, Any] | None:
        response_body = (record.get('response') or {}).get('body', {})
        data = response_body.get('data') or {}
        if isinstance(data, str):
            try:
                import json
                data = json.loads(data)
            except Exception:
                data = {}
        order_id = data.get('order_id') or data.get('orderId') or (record.get('payload') or {}).get('order_id')
        global_id = data.get('id')
        if order_id is None and global_id is None:
            return None
        order_snapshot = self.client.get_order(id=global_id, order_id=order_id, show_charges=True)
        transactions = self.client.get_transactions(order_id=order_id, symbol=record.get('symbol')) if order_id is not None else {'http_status': None, 'body': {'code': None, 'message': 'missing_order_id'}}
        return {
            'idempotency_key': idem,
            'intent_id': record.get('intent_id'),
            'symbol': record.get('symbol'),
            'global_id': global_id,
            'order_id': order_id,
            'order': order_snapshot,
            'transactions': transactions,
        }

    def _normalized_snapshot_is_active(self, normalized: dict[str, Any]) -> bool:
        status = str(normalized.get('status') or '').strip().lower()
        if not status:
            return True
        if status in self.TERMINAL_ORDER_STATUSES:
            return False
        filled = self._safe_float(normalized.get('filled_quantity'))
        quantity = self._safe_float(normalized.get('quantity'))
        remaining = normalized.get('remaining_quantity')
        if remaining is not None and self._safe_float(remaining) <= 0:
            return False
        if quantity > 0 and filled >= quantity:
            return False
        return True

    def _safe_float(self, value: Any) -> float:
        try:
            return float(value or 0)
        except Exception:
            return 0.0
