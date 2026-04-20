from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audit import AuditLogger
from .config import AppConfig
from .control import ControlPlane
from .execution import DryRunExecutor
from .intent import IntentBuilder
from .live_execution import LiveExecutionAdapter
from .notifier import NotificationBuilder
from .risk import RiskManager
from .strategy import StrategyEngine
from .rule_engine import RuleEngine
from .broker_client import BrokerClient
from .state import TradeLimitStore


def _unwrap_data(resp: dict[str, Any]) -> Any:
    body = resp.get('body', {})
    data = body.get('data')
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return data
    return data


def _extract_positions_map(resp: dict[str, Any]) -> dict[str, dict[str, Any]]:
    data = _unwrap_data(resp) or {}
    items = data.get('items', []) if isinstance(data, dict) else []
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        symbol = item.get('symbol')
        if symbol:
            result[symbol] = item
    return result


def _extract_active_orders_map(resp: dict[str, Any]) -> dict[str, dict[str, Any]]:
    data = _unwrap_data(resp) or {}
    items = data.get('items', []) if isinstance(data, dict) else []
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        symbol = item.get('symbol')
        if symbol and symbol not in result:
            result[symbol] = item
    return result


def _extract_bars_map(resp: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    data = _unwrap_data(resp) or []
    result: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(data, list):
        return result
    for entry in data:
        symbol = entry.get('symbol')
        items = entry.get('items', [])
        if symbol:
            result[symbol] = items
    return result


def _quote_status(resp: dict[str, Any]) -> dict[str, Any]:
    body = resp.get('body', {})
    return {
        'http_status': resp.get('http_status'),
        'code': body.get('code'),
        'message': body.get('message'),
        'ok': body.get('code') == 0,
    }


def _cycle_id() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _state_dir(app: AppConfig) -> Path:
    state_dir = Path(app.raw.get('system', {}).get('state_dir', './state'))
    if not state_dir.is_absolute():
        state_dir = Path(__file__).resolve().parents[2] / state_dir
    return state_dir


def _resolve_trading_day(asset_snapshot: dict[str, Any] | None) -> str:
    snapshot = asset_snapshot or {}
    for key in ('trading_day', 'tradingDay', 'date'):
        value = snapshot.get(key)
        if value:
            return str(value)[:10]
    return datetime.now(timezone.utc).date().isoformat()


def _resolve_timestamp(asset_snapshot: dict[str, Any] | None) -> str:
    snapshot = asset_snapshot or {}
    for key in ('timestamp', 'ts', 'updated_at', 'as_of'):
        value = snapshot.get(key)
        if value:
            return str(value)
    return datetime.now(timezone.utc).isoformat()


def _log_dir(app: AppConfig) -> Path:
    env_logs_dir = os.environ.get('ENGINE_LOGS_DIR')
    if env_logs_dir:
        return Path(env_logs_dir) / 'audit'
    log_dir = Path(app.raw.get('system', {}).get('audit_log_dir', './logs'))
    if not log_dir.is_absolute():
        log_dir = Path(__file__).resolve().parents[2] / log_dir
    return log_dir


def fetch_cycle_raw(client: BrokerClient, app: AppConfig) -> dict[str, Any]:
    symbols_by_market: dict[str, list[str]] = {}
    for item in app.symbols:
        symbols_by_market.setdefault(item['market'], []).append(item['symbol'])

    result: dict[str, Any] = {
        'accounts': client.get_accounts(),
        'assets': client.get_assets(),
        'positions': client.get_positions(),
        'active_orders': client.get_active_orders(),
        'quote_permissions': client.get_quote_permission(),
        'market_state': {},
        'delay_quotes': {},
        'briefs': {},
        'bars': {},
        'contracts': {},
    }

    for market, symbols in symbols_by_market.items():
        result['market_state'][market] = client.get_market_state(market)
        result['delay_quotes'][market] = client.get_delay_quotes(symbols, market=market)
        result['briefs'][market] = client.get_briefs(symbols, market=market)
        result['bars'][market] = client.get_bars(symbols, period=app.timeframe, limit=int(app.signal.get('lookback_bars', 30)))
        result['contracts'][market] = {symbol: client.get_contract(symbol, market) for symbol in symbols}

    return result


def run_readonly_cycle(client: BrokerClient, app: AppConfig) -> dict[str, Any]:
    raw = fetch_cycle_raw(client, app)
    return summarize_cycle(raw)


def run_strategy_cycle(client: BrokerClient, app: AppConfig) -> dict[str, Any]:
    raw = fetch_cycle_raw(client, app)
    return build_strategy_summary(raw, app)


def run_dry_run_cycle(client: BrokerClient, app: AppConfig, write_logs: bool = True) -> dict[str, Any]:
    raw = fetch_cycle_raw(client, app)
    summary = build_execution_summary(raw, app)
    summary['execution_submit'] = {
        'items': [],
        'count': 0,
        'mode': 'dry-run',
    }
    if write_logs:
        logger = AuditLogger(_log_dir(app))
        summary['audit_logs'] = logger.write_summary(summary)
    return summary


def run_execution_cycle(client: BrokerClient, app: AppConfig, write_logs: bool = True) -> dict[str, Any]:
    control = ControlPlane(_state_dir(app))
    try:
        raw = fetch_cycle_raw(client, app)
        summary = build_execution_summary(raw, app)
        summary['control'] = control.status()
        adapter = LiveExecutionAdapter(app.raw, client)
        preview_results = [item.to_dict() for item in adapter.preview_intents(summary['order_intents']['items'], summary.get('contracts', {}))]
        summary['execution_preview_check'] = {
            'items': preview_results,
            'count': len(preview_results),
        }
        summary['risk']['preview_blockers'] = [
            {
                'intent_id': item.get('intent_id'),
                'symbol': item.get('symbol'),
                'reason': item.get('reason'),
                'warning_text': item.get('warning_text'),
            }
            for item in preview_results
            if not item.get('ok')
        ]

        gate_ok, gate_reason = control.can_trade()
        if not gate_ok:
            submit_results = [
                {
                    'intent_id': item.get('intent_id'),
                    'symbol': item.get('symbol'),
                    'submitted': False,
                    'mode': app.raw.get('execution', {}).get('submit_mode', 'guarded'),
                    'reason': gate_reason,
                    'response': None,
                }
                for item in summary['order_intents']['items']
            ]
            sync_results = []
            summary['risk']['preview_blockers'].append({
                'intent_id': None,
                'symbol': None,
                'reason': gate_reason,
                'warning_text': control.status().get('reason'),
            })
        else:
            submit_results = [item.to_dict() for item in adapter.submit_intents(summary['order_intents']['items'], summary.get('contracts', {}))]
            sync_results = adapter.sync_submitted_orders()

        summary['execution_submit'] = {
            'items': submit_results,
            'count': len(submit_results),
            'mode': app.raw.get('execution', {}).get('submit_mode', 'guarded'),
        }
        summary['order_sync'] = {
            'items': sync_results,
            'count': len(sync_results),
        }
        if write_logs:
            logger = AuditLogger(_log_dir(app))
            summary['audit_logs'] = logger.write_summary(summary)
        return summary
    except Exception as e:
        if bool(app.raw.get('system', {}).get('stop_on_exception', True)):
            control.lock(f'execution_exception:{type(e).__name__}:{e}', updated_by='system')
        raise


def build_strategy_summary(raw: dict[str, Any], app: AppConfig) -> dict[str, Any]:
    summary = summarize_cycle(raw)
    bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for market in raw['bars'].values():
        bars_by_symbol.update(_extract_bars_map(market))
    positions_map = _extract_positions_map(raw['positions'])
    
    # Check if rule engine is enabled
    use_rule_engine = app.raw.get('strategy', {}).get('use_rule_engine', False)
    rules_path = app.raw.get('strategy', {}).get('rules_path')
    
    signals = []
    engine_type = 'legacy'
    
    if use_rule_engine and rules_path:
        # Use new rule engine
        try:
            rules_file = Path(rules_path)
            if not rules_file.is_absolute():
                rules_file = Path(__file__).resolve().parents[2] / rules_file
            
            rule_engine = RuleEngine(rules_file)
            engine_type = 'rule_engine'
            
            for item in app.symbols:
                symbol = item['symbol']
                market = item['market']
                bars = bars_by_symbol.get(symbol, [])
                position = positions_map.get(symbol)
                
                rule_signals = rule_engine.evaluate_symbol(symbol, market, bars, position)
                for signal in rule_signals:
                    signals.append(signal.to_dict())
        except Exception as e:
            print(f'[build_strategy_summary] Rule engine failed, falling back to legacy: {e}')
            use_rule_engine = False
    
    if not use_rule_engine:
        # Use legacy strategy engine
        engine = StrategyEngine(app)
        signals = [signal.to_dict() for signal in engine.generate(bars_by_symbol=bars_by_symbol, positions=positions_map)]
    
    summary['strategy'] = {
        'timeframe': app.timeframe,
        'signals': signals,
        'engine': engine_type,
    }
    return summary


def build_execution_summary(raw: dict[str, Any], app: AppConfig) -> dict[str, Any]:
    summary = build_strategy_summary(raw, app)
    risk_manager = RiskManager(app.raw)
    executor = DryRunExecutor(app.raw)
    notifier = NotificationBuilder(app.raw)
    intent_builder = IntentBuilder(app.raw)
    control = ControlPlane(_state_dir(app))
    cycle_id = _cycle_id()

    decisions = risk_manager.evaluate(
        signals=summary['strategy']['signals'],
        asset_snapshot=summary.get('asset_snapshot'),
        market_state=summary.get('market_state', {}),
        contracts=summary.get('contracts', {}),
        positions_map=_extract_positions_map(raw['positions']),
        active_orders_map=_extract_active_orders_map(raw['active_orders']),
    )
    decision_dicts = [item.to_dict() for item in decisions]
    previews = [item.to_dict() for item in executor.build_previews(
        signals=summary['strategy']['signals'],
        risk_decisions=decision_dicts,
        contracts=summary.get('contracts', {}),
    )]
    trade_limit_store = TradeLimitStore(_state_dir(app))
    trading_day = _resolve_trading_day(summary.get('asset_snapshot'))
    recorded_at = _resolve_timestamp(summary.get('asset_snapshot'))
    for preview in previews:
        trade_limit_store.record_trade(
            trading_day,
            symbol=preview['symbol'],
            side=preview['side'],
            ts=recorded_at,
        )
    intents = [item.to_dict() for item in intent_builder.build(previews, cycle_id=cycle_id)]

    summary['cycle_id'] = cycle_id
    summary['control'] = control.status()
    summary['risk'] = {
        'decisions': decision_dicts,
        'allowed_count': sum(1 for item in decisions if item.allowed),
    }
    summary['execution_preview'] = {
        'orders': previews,
        'count': len(previews),
        'mode': 'dry-run',
    }
    summary['order_intents'] = {
        'items': intents,
        'count': len(intents),
        'mode': app.raw.get('execution', {}).get('submit_mode', 'guarded'),
    }
    notifications = [item.to_dict() for item in notifier.build_from_summary(summary)]
    dispatch_requests = notifier.build_dispatch_requests(notifications)
    summary['notification_preview'] = {
        'items': notifications,
        'count': len(notifications),
        'mode': 'preview-only' if app.raw.get('notify', {}).get('telegram_preview_only', True) else 'send-enabled',
    }
    summary['notification_dispatch'] = {
        'items': dispatch_requests,
        'count': len(dispatch_requests),
        'enabled': bool(app.raw.get('notify', {}).get('telegram_send_enabled', False)),
    }
    return summary


def summarize_cycle(raw: dict[str, Any]) -> dict[str, Any]:
    assets_data = _unwrap_data(raw['assets']) or {}
    positions_data = _unwrap_data(raw['positions']) or {}
    active_orders_data = _unwrap_data(raw['active_orders']) or {}

    summary = {
        'account_ok': raw['accounts']['body'].get('code') == 0,
        'assets_ok': raw['assets']['body'].get('code') == 0,
        'positions_ok': raw['positions']['body'].get('code') == 0,
        'active_orders_ok': raw['active_orders']['body'].get('code') == 0,
        'quote_permissions': _unwrap_data(raw['quote_permissions']) or [],
        'quote_access': {},
        'market_state': {},
        'delay_quotes': {},
        'bars': {},
        'contracts': {},
        'asset_snapshot': None,
        'position_count': len(positions_data.get('items', [])) if isinstance(positions_data, dict) else None,
        'active_order_count': len(active_orders_data.get('items', [])) if isinstance(active_orders_data, dict) else None,
    }

    if isinstance(assets_data, dict) and isinstance(assets_data.get('items'), list) and assets_data['items']:
        item = assets_data['items'][0]
        summary['asset_snapshot'] = {
            'account': item.get('account'),
            'netLiquidation': item.get('netLiquidation'),
            'cashValue': item.get('cashValue'),
            'buyingPower': item.get('buyingPower'),
            'grossPositionValue': item.get('grossPositionValue'),
            'unrealizedPnL': item.get('unrealizedPnL'),
            'realizedPnL': item.get('realizedPnL'),
        }

    for market, resp in raw['market_state'].items():
        summary['market_state'][market] = _unwrap_data(resp)

    for market, resp in raw['delay_quotes'].items():
        summary['quote_access'][market] = {
            'quote_delay': _quote_status(resp),
            'brief': _quote_status(raw['briefs'][market]),
            'bars': _quote_status(raw['bars'][market]),
        }
        summary['delay_quotes'][market] = _unwrap_data(resp)
        summary['bars'][market] = _extract_bars_map(raw['bars'][market])

    for market, contracts in raw['contracts'].items():
        summary['contracts'][market] = {}
        for symbol, resp in contracts.items():
            summary['contracts'][market][symbol] = _unwrap_data(resp)

    return summary


def fetch_cycle_raw_with_provider(client: BrokerClient | None, data: Any, app: AppConfig) -> dict[str, Any]:
    """Fetch cycle data using a DataProvider for market data.

    Trade operations (accounts/positions/orders) still use the broker client.
    Market data (bars/quotes/contracts) uses the DataProvider.
    If client is None, trade operations return empty/error responses.
    """
    symbols_by_market: dict[str, list[str]] = {}
    for item in app.symbols:
        symbols_by_market.setdefault(item['market'], []).append(item['symbol'])

    if client:
        result: dict[str, Any] = {
            'accounts': client.get_accounts(),
            'assets': client.get_assets(),
            'positions': client.get_positions(),
            'active_orders': client.get_active_orders(),
            'quote_permissions': client.get_quote_permission(),
        }
    else:
        result = {
            'accounts': {'http_status': 200, 'body': {'code': 0, 'data': {'items': []}}},
            'assets': {'http_status': 200, 'body': {'code': 0, 'data': {'items': []}}},
            'positions': {'http_status': 200, 'body': {'code': 0, 'data': {'items': []}}},
            'active_orders': {'http_status': 200, 'body': {'code': 0, 'data': {'items': []}}},
            'quote_permissions': {'http_status': 200, 'body': {'code': 0, 'data': []}},
        }

    result['market_state'] = {}
    result['delay_quotes'] = {}
    result['briefs'] = {}
    result['bars'] = {}
    result['contracts'] = {}

    for market, symbols in symbols_by_market.items():
        result['market_state'][market] = data.get_market_state(market)
        result['delay_quotes'][market] = data.get_delay_quotes(symbols, market=market)
        result['briefs'][market] = data.get_briefs(symbols, market=market)
        result['bars'][market] = data.get_bars(symbols, period=app.timeframe, limit=int(app.signal.get('lookback_bars', 30)))
        result['contracts'][market] = {symbol: data.get_contract(symbol, market) for symbol in symbols}

    return result


def run_cycle(mode: str, client: BrokerClient | None, data: Any, app: AppConfig) -> dict[str, Any]:
    """Run a cycle with pluggable data provider.

    Args:
        mode: 'readonly' | 'strategy' | 'dry-run' | 'execution'
        client: broker client for trade ops (None for data-only mode)
        data: DataProvider for market data
        app: AppConfig
    """
    raw = fetch_cycle_raw_with_provider(client, data, app)

    if mode == 'readonly':
        return summarize_cycle(raw)
    elif mode == 'strategy':
        return build_strategy_summary(raw, app)
    elif mode == 'dry-run':
        return build_execution_summary(raw, app)
    elif mode == 'execution':
        if client is None:
            return {'error': 'execution mode requires broker client'}
        return run_execution_cycle(client, app)
    else:
        return {'error': f'unknown mode: {mode}'}
