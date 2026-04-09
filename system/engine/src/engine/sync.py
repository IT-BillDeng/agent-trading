from __future__ import annotations

from typing import Any


def unwrap_data(resp: dict[str, Any] | None) -> Any:
    if not isinstance(resp, dict):
        return None
    body = resp.get('body', {})
    data = body.get('data')
    if isinstance(data, str):
        import json
        try:
            return json.loads(data)
        except Exception:
            return data
    return data


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _normalize_transaction_item(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        qty = _safe_float(item.get('filledQuantity') or item.get('quantity') or item.get('filled_quantity'))
        price = _safe_float(item.get('fillPrice') or item.get('price') or item.get('fill_price'))
        commission = _safe_float(item.get('commission'))
        return {
            'transaction_id': item.get('id') or item.get('transactionId') or item.get('transaction_id'),
            'symbol': item.get('symbol'),
            'action': item.get('action'),
            'filled_quantity': qty,
            'fill_price': price,
            'commission': commission,
            'trade_time': item.get('tradeTime') or item.get('trade_time'),
            'raw': item,
        }
    return {
        'transaction_id': None,
        'symbol': None,
        'action': None,
        'filled_quantity': 0.0,
        'fill_price': 0.0,
        'commission': 0.0,
        'trade_time': None,
        'raw': item,
    }


def normalize_order_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    order_data = unwrap_data(snapshot.get('order'))
    tx_data = unwrap_data(snapshot.get('transactions'))

    order_item = None
    if isinstance(order_data, dict) and isinstance(order_data.get('items'), list) and order_data.get('items'):
        first_item = order_data['items'][0]
        if isinstance(first_item, dict):
            order_item = first_item
    elif isinstance(order_data, dict) and 'status' in order_data:
        order_item = order_data

    transactions = []
    if isinstance(tx_data, dict) and isinstance(tx_data.get('items'), list):
        transactions = tx_data.get('items', [])
    elif isinstance(tx_data, list):
        transactions = tx_data
    elif tx_data is not None:
        transactions = [tx_data]

    total_filled_qty = 0.0
    total_filled_value = 0.0
    total_commission = 0.0
    normalized_transactions = []
    for item in transactions:
        normalized_item = _normalize_transaction_item(item)
        qty = normalized_item['filled_quantity']
        price = normalized_item['fill_price']
        commission = normalized_item['commission']
        total_filled_qty += qty
        total_filled_value += qty * price
        total_commission += commission
        normalized_transactions.append(normalized_item)

    avg_fill_price = round(total_filled_value / total_filled_qty, 6) if total_filled_qty > 0 else None

    normalized = {
        'idempotency_key': snapshot.get('idempotency_key'),
        'intent_id': snapshot.get('intent_id'),
        'symbol': snapshot.get('symbol'),
        'global_id': snapshot.get('global_id'),
        'order_id': snapshot.get('order_id'),
        'status': None,
        'quantity': None,
        'filled_quantity': total_filled_qty,
        'remaining_quantity': None,
        'avg_fill_price': avg_fill_price,
        'commission_total': round(total_commission, 6),
        'transactions_count': len(normalized_transactions),
        'transactions': normalized_transactions,
        'raw': {
            'order': order_data,
            'transactions': tx_data,
        },
    }

    if isinstance(order_item, dict):
        normalized.update({
            'status': order_item.get('status'),
            'quantity': order_item.get('totalQuantity') or order_item.get('quantity'),
            'remaining_quantity': order_item.get('remainingQuantity') or order_item.get('remaining'),
            'avg_fill_price': order_item.get('avgFillPrice') or order_item.get('avg_fill_price') or avg_fill_price,
            'last_fill_price': order_item.get('lastFillPrice') or order_item.get('last_fill_price'),
            'limit_price': order_item.get('limitPrice') or order_item.get('limit_price'),
            'stop_price': order_item.get('auxPrice') or order_item.get('aux_price'),
            'order_type': order_item.get('orderType') or order_item.get('order_type'),
            'side': order_item.get('action'),
            'update_time': order_item.get('updateTime') or order_item.get('update_time'),
        })

    return normalized
