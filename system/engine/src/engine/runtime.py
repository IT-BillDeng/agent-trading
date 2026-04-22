from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
from .data_provider import create_data_provider, fetch_bars_with_fallback
from .factors import FactorEngine
from .factors.store import FactorStore
from .market_sessions import (
    analyze_symbol_bars,
    market_data_policy,
    resolve_now_for_market,
    resolve_trading_day_for_market,
    session_config,
)

ET_ZONE = ZoneInfo("America/New_York")

FACTOR_ENGINE_DEFAULTS = {
    "enabled": False,
    "mode": "shadow",
    "registry_path": "factors/registry.json",
    "write_artifacts": False,
    "allow_actionable_consumption": False,
    "regular_session_only_for_indicators": True,
}


SUPPORTED_PROVIDER_TIMEFRAMES: dict[str, set[str]] = {
    "tiger": {"1min", "5min", "15min", "30min", "1hour", "1day", "1week", "1month"},
    "yfinance": {"1min", "5min", "15min", "30min", "60min", "1day"},
}


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


def _response_ok(resp: dict[str, Any] | None) -> bool:
    if not isinstance(resp, dict):
        return False
    body = resp.get("body", {})
    return resp.get("http_status", 500) < 400 and body.get("code") == 0


def _find_symbol_entry(resp: dict[str, Any] | None, symbol: str) -> dict[str, Any] | None:
    data = _unwrap_data(resp or {}) or []
    if not isinstance(data, list):
        return None
    for entry in data:
        if isinstance(entry, dict) and entry.get("symbol") == symbol:
            return entry
    return None


def _latest_bar_time(bars: list[dict[str, Any]]) -> str | None:
    if not bars:
        return None
    last_bar = bars[-1]
    for key in ("time", "timestamp", "date", "datetime"):
        value = last_bar.get(key)
        if value:
            return str(value)
    return None


def _decorate_signal_with_bar_context(
    signal: dict[str, Any],
    bar_context: dict[str, Any] | None,
    *,
    policy: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(signal)
    diagnostics = dict(enriched.get("diagnostics") or {})
    block_reason = None
    actionable = True

    if bar_context:
        if enriched.get("action") == "BUY":
            block_reason = bar_context.get("actionable_block_reason")
            actionable = block_reason is None
        elif enriched.get("action") == "EXIT":
            context_block = bar_context.get("actionable_block_reason")
            if context_block in {
                "first_30m_bar_not_closed",
                "latest_regular_bar_stale",
                "first_regular_bar_missing",
                "extended_context_only",
            }:
                block_reason = "technical_exit_bar_not_ready"
                actionable = False

    diagnostics["market_data_boundary"] = {
        "actionable": actionable,
        "reason": block_reason,
        "regular_session_only_for_indicators": policy["regular_session_only_for_indicators"],
        "extended_hours_usage": policy["extended_hours_usage"],
        "raw_bars_count": int((bar_context or {}).get("raw_bars_count", 0)),
        "regular_bars_count": int((bar_context or {}).get("regular_bars_count", 0)),
        "regular_completed_bars_count": int((bar_context or {}).get("regular_completed_bars_count", 0)),
        "extended_bars_count": int((bar_context or {}).get("extended_bars_count", 0)),
    }
    enriched["diagnostics"] = diagnostics
    enriched["actionable"] = actionable
    if block_reason:
        enriched["actionable_reason"] = block_reason
    return enriched


def _market_closed(market_state: Any) -> bool:
    candidates: list[str] = []
    if isinstance(market_state, list):
        for item in market_state:
            if isinstance(item, dict):
                candidates.extend(
                    str(item.get(key, "")).strip().lower()
                    for key in ("marketStatus", "status", "state")
                    if item.get(key) is not None
                )
    elif isinstance(market_state, dict):
        candidates.extend(
            str(market_state.get(key, "")).strip().lower()
            for key in ("marketStatus", "status", "state")
            if market_state.get(key) is not None
        )
    return any("closed" in value for value in candidates)


def _symbol_disabled_reason(app: AppConfig, market: str, symbol: str) -> str | None:
    control_path = _state_dir(app) / "control_state.json"
    if not control_path.exists():
        return None
    try:
        state = json.loads(control_path.read_text())
    except Exception:
        return None

    markets_cfg = state.get("markets", {})
    if isinstance(markets_cfg, dict) and not markets_cfg.get(market, True):
        return "symbol_disabled"

    symbols_cfg = state.get("symbols", {})
    if not isinstance(symbols_cfg, dict):
        return None
    symbol_cfg = symbols_cfg.get(symbol, True)
    if isinstance(symbol_cfg, dict):
        if not symbol_cfg.get("enabled", True) or symbol_cfg.get("suspended", False):
            return "symbol_disabled"
        return None
    if not bool(symbol_cfg):
        return "symbol_disabled"
    return None


def _legacy_required_bars(app: AppConfig) -> int:
    signal = app.signal
    return max(
        int(signal.get("fast_sma", 5)),
        int(signal.get("slow_sma", 10)),
        int(signal.get("trend_sma", 20)),
        4,
    )


def _required_bars_for_symbol(
    app: AppConfig,
    symbol: str,
    market: str,
    *,
    engine_type: str,
    rule_engine: RuleEngine | None,
) -> int:
    if engine_type == "rule_engine" and rule_engine is not None:
        applicable_rules = rule_engine.get_enabled_rules(symbol=symbol, market=market)
        if applicable_rules:
            return max(rule_engine._get_min_bars_required(rule) for rule in applicable_rules)
    return _legacy_required_bars(app)


def _build_data_health_report(
    raw: dict[str, Any],
    summary: dict[str, Any],
    app: AppConfig,
    *,
    engine_type: str,
    rule_engine: RuleEngine | None,
    raw_bars_by_symbol: dict[str, list[dict[str, Any]]],
    symbol_bar_contexts: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    default_provider = str(raw.get("_provider") or app.signal.get("provider") or app.broker_platform or "unknown")
    report: dict[str, dict[str, Any]] = {}
    policy = market_data_policy(app.raw)

    for item in app.symbols:
        symbol = item["symbol"]
        market = item["market"]
        bars_meta = raw.get("_bars_meta", {}).get(market, {}).get("symbols", {}).get(symbol, {})
        provider = str(bars_meta.get("provider") or default_provider)
        provider_path = str(bars_meta.get("provider_path") or provider)
        provider_status = str(bars_meta.get("status") or "unknown")
        fallback_used = bool(bars_meta.get("fallback_used"))
        supported_timeframes = SUPPORTED_PROVIDER_TIMEFRAMES.get(provider, set())
        bars_status = summary.get("quote_access", {}).get(market, {}).get("bars", {})
        brief_status = summary.get("quote_access", {}).get(market, {}).get("brief", {})
        delay_status = summary.get("quote_access", {}).get(market, {}).get("quote_delay", {})

        quote_status = "unknown"
        if fallback_used:
            quote_status = "fallback"
        elif bars_status.get("ok") is False or brief_status.get("ok") is False:
            quote_status = "failed"
        elif provider == "yfinance" or delay_status.get("ok"):
            quote_status = "delayed"
        elif bars_status.get("ok") or brief_status.get("ok"):
            quote_status = "ok"

        contract_resp = raw.get("contracts", {}).get(market, {}).get(symbol)
        contract_data = summary.get("contracts", {}).get(market, {}).get(symbol)
        if contract_resp is None or contract_data in (None, "", {}):
            contract_status = "missing"
        elif not _response_ok(contract_resp):
            contract_status = "failed"
        else:
            contract_status = "ok"

        bars_resp = raw.get("bars", {}).get(market)
        bars_entry = _find_symbol_entry(bars_resp, symbol)
        raw_items = bars_entry.get("items") if isinstance(bars_entry, dict) else None
        raw_bars_count = int(bars_meta.get("bars_count") or (len(raw_items) if isinstance(raw_items, list) else 0))
        raw_bars = list(raw_bars_by_symbol.get(symbol, []))
        bar_context = symbol_bar_contexts.get(symbol) or analyze_symbol_bars(
            raw_bars,
            asset_snapshot=summary.get("asset_snapshot"),
            market=market,
            timeframe=app.timeframe,
            app_config=app.raw,
            provider=provider,
        )
        normalized_bars = list(bar_context.get("regular_completed_bars", []))
        normalized_bars_count = len(normalized_bars)
        latest_bar_time = bar_context.get("latest_regular_bar_time")
        required_bars = _required_bars_for_symbol(
            app,
            symbol,
            market,
            engine_type=engine_type,
            rule_engine=rule_engine,
        )

        reason: str | None = None
        if supported_timeframes and app.timeframe not in supported_timeframes:
            reason = "unsupported_timeframe"
        elif _symbol_disabled_reason(app, market, symbol):
            reason = "symbol_disabled"
        elif bars_meta.get("reason") in {"provider_error", "bars_normalization_failed"}:
            reason = str(bars_meta.get("reason"))
        elif bars_entry is not None and raw_items is not None and not isinstance(raw_items, list):
            reason = "bars_normalization_failed"
        elif bars_status.get("ok") is False or brief_status.get("ok") is False:
            reason = "provider_error"
        elif contract_status == "missing":
            reason = "contract_missing"
        elif contract_status == "failed":
            reason = "provider_error"
        elif normalized_bars_count == 0 and _market_closed(summary.get("market_state", {}).get(market)):
            reason = "market_closed"
        elif bars_meta.get("reason") == "bars_empty":
            reason = "bars_empty"
        elif normalized_bars_count == 0:
            reason = "bars_empty"
        elif normalized_bars_count < required_bars:
            reason = "insufficient_bars"

        report[symbol] = {
            "market": market,
            "provider": provider,
            "provider_path": provider_path,
            "provider_status": provider_status,
            "fallback_used": fallback_used,
            "quote_status": quote_status,
            "contract_status": contract_status,
            "raw_bars_count": raw_bars_count,
            "regular_bars_count": int(bar_context.get("regular_bars_count", 0)),
            "extended_bars_count": int(bar_context.get("extended_bars_count", 0)),
            "normalized_bars_count": normalized_bars_count,
            "required_bars": required_bars,
            "latest_bar_time": latest_bar_time,
            "latest_raw_bar_time": bar_context.get("latest_raw_bar_time"),
            "latest_regular_bar_time": latest_bar_time,
            "latest_regular_bar_is_complete": bool(bar_context.get("latest_regular_bar_is_complete", False)),
            "latest_regular_bar_is_stale": bool(bar_context.get("latest_regular_bar_is_stale", False)),
            "first_regular_30m_bar_completed": bool(bar_context.get("first_regular_30m_bar_completed", False)),
            "timeframe": app.timeframe,
            "strategy_ready": reason is None,
            "reason": reason or None,
            "actionable_ready": bool(bar_context.get("actionable_ready", False)) and reason is None,
            "actionable_block_reason": bar_context.get("actionable_block_reason"),
            "extended_context": dict(bar_context.get("extended_context", {})),
            "market_data_policy": {
                "include_extended_hours": policy["include_extended_hours"],
                "extended_hours_usage": policy["extended_hours_usage"],
                "regular_session_only_for_indicators": policy["regular_session_only_for_indicators"],
                "require_completed_bar_for_actionable_signal": policy["require_completed_bar_for_actionable_signal"],
            },
        }

    return report


def _cycle_id() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _state_dir(app: AppConfig) -> Path:
    state_dir = Path(app.raw.get('system', {}).get('state_dir', './state'))
    if not state_dir.is_absolute():
        state_dir = Path(__file__).resolve().parents[2] / state_dir
    return state_dir


def _runtime_dir(app: AppConfig) -> Path:
    return _state_dir(app).parent


def _factor_engine_config(app: AppConfig) -> dict[str, Any]:
    config = dict(FACTOR_ENGINE_DEFAULTS)
    raw_config = app.raw.get("factor_engine")
    if isinstance(raw_config, dict):
        config.update(raw_config)

    config["enabled"] = bool(config.get("enabled", False))
    config["mode"] = str(config.get("mode", "shadow"))
    config["registry_path"] = str(config.get("registry_path", "factors/registry.json"))
    config["write_artifacts"] = bool(config.get("write_artifacts", False))
    config["allow_actionable_consumption"] = bool(config.get("allow_actionable_consumption", False))
    config["regular_session_only_for_indicators"] = bool(
        config.get("regular_session_only_for_indicators", True)
    )
    return config


def _resolve_factor_registry_path(registry_path: str | Path) -> Path:
    path = Path(registry_path)
    if path.is_absolute():
        return path
    return (_project_root() / path).resolve()


def _factor_symbol_summary(factor_snapshot: dict[str, Any] | None = None, *, error_reason: str | None = None) -> dict[str, Any]:
    if error_reason is not None:
        return {
            "factors_ready": 0,
            "factors_total": 0,
            "blocking": False,
            "reasons": [error_reason],
        }

    factors = dict((factor_snapshot or {}).get("factors", {}))
    reasons = sorted(
        {
            str(payload.get("reason"))
            for payload in factors.values()
            if isinstance(payload, dict) and payload.get("reason") not in (None, "", "ok")
        }
    )
    return {
        "factors_ready": sum(
            1
            for payload in factors.values()
            if isinstance(payload, dict) and bool(payload.get("ready"))
        ),
        "factors_total": len(factors),
        "blocking": False,
        "reasons": reasons,
    }


def _record_factor_shadow_error(summary: dict[str, Any], symbol: str, reason: str) -> None:
    data_health = summary.get("data_health")
    if not isinstance(data_health, dict):
        return
    symbol_health = data_health.get(symbol)
    if not isinstance(symbol_health, dict):
        return
    symbol_health["factor_shadow_error"] = reason


def _attach_factor_shadow(
    summary: dict[str, Any],
    raw: dict[str, Any],
    app: AppConfig,
    *,
    raw_bars_by_symbol: dict[str, list[dict[str, Any]]],
) -> None:
    config = _factor_engine_config(app)
    if not config["enabled"]:
        return

    factor_summary: dict[str, Any] = {
        "enabled": True,
        "mode": config["mode"],
        "allow_actionable_consumption": config["allow_actionable_consumption"],
        "registry_hash": None,
        "symbols": {},
    }
    summary["factor_engine"] = factor_summary

    symbol_items = list(app.symbols)
    if config["mode"] != "shadow":
        error_reason = "invalid_mode"
        factor_summary["error"] = error_reason
        for item in symbol_items:
            symbol = item["symbol"]
            factor_summary["symbols"][symbol] = _factor_symbol_summary(error_reason=error_reason)
            _record_factor_shadow_error(summary, symbol, error_reason)
        return
    if config["allow_actionable_consumption"]:
        error_reason = "allow_actionable_consumption_must_be_false"
        factor_summary["error"] = error_reason
        for item in symbol_items:
            symbol = item["symbol"]
            factor_summary["symbols"][symbol] = _factor_symbol_summary(error_reason=error_reason)
            _record_factor_shadow_error(summary, symbol, error_reason)
        return

    try:
        engine = FactorEngine(_resolve_factor_registry_path(config["registry_path"]))
        factor_summary["registry_hash"] = engine.registry.config_hash
        snapshot = {
            "timestamp": _resolve_timestamp(summary.get("asset_snapshot")),
            "registry_hash": engine.registry.config_hash,
            "mode": engine.mode,
            "symbols": {},
        }

        for item in symbol_items:
            symbol = item["symbol"]
            market = item["market"]
            provider = (
                raw.get("_bars_meta", {}).get(market, {}).get("symbols", {}).get(symbol, {}).get("provider")
                or raw.get("_provider")
                or app.broker_platform
            )
            symbol_snapshot = engine.evaluate_symbol(
                symbol,
                raw_bars_by_symbol.get(symbol, []),
                evaluation_time=snapshot["timestamp"],
                market=market,
                asset_snapshot=summary.get("asset_snapshot"),
                provider=str(provider),
            )
            snapshot["symbols"][symbol] = symbol_snapshot
            factor_summary["symbols"][symbol] = _factor_symbol_summary(symbol_snapshot)

        if config["write_artifacts"]:
            try:
                paths = FactorStore(base_dir=_runtime_dir(app)).write_snapshot(snapshot)
                factor_summary["artifacts"] = {
                    "latest": str(paths["latest"]),
                    "history": str(paths["history"]),
                }
            except Exception as exc:
                factor_summary["store_error"] = f"{type(exc).__name__}:{exc}"
    except Exception as exc:
        error_reason = f"factor_shadow_error:{type(exc).__name__}"
        factor_summary["error"] = error_reason
        factor_summary["message"] = str(exc)
        for item in symbol_items:
            symbol = item["symbol"]
            factor_summary["symbols"][symbol] = _factor_symbol_summary(error_reason=error_reason)
            _record_factor_shadow_error(summary, symbol, error_reason)


def _resolve_trading_day(asset_snapshot: dict[str, Any] | None) -> str:
    snapshot = asset_snapshot or {}
    for key in ('trading_day', 'tradingDay', 'date'):
        value = snapshot.get(key)
        if value:
            return str(value)[:10]
    timestamp = _resolve_timestamp(snapshot)
    parsed = _parse_timestamp(timestamp)
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ET_ZONE).date().isoformat()
    return datetime.now(ET_ZONE).date().isoformat()


def _resolve_timestamp(asset_snapshot: dict[str, Any] | None) -> str:
    snapshot = asset_snapshot or {}
    for key in (
        'trading_timestamp',
        'tradingTimestamp',
        'account_timestamp',
        'accountTimestamp',
        'broker_timestamp',
        'brokerTimestamp',
        'timestamp',
        'ts',
        'updated_at',
        'as_of',
    ):
        value = snapshot.get(key)
        if value:
            return str(value)
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith('Z'):
        text = text[:-1] + '+00:00'
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


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
        '_provider': app.broker_platform,
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
    raw_bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for market in raw['bars'].values():
        raw_bars_by_symbol.update(_extract_bars_map(market))
    positions_map = _extract_positions_map(raw['positions'])
    bars_by_symbol: dict[str, list[dict[str, Any]]] = {}
    symbol_bar_contexts: dict[str, dict[str, Any]] = {}
    policy = market_data_policy(app.raw)

    for item in app.symbols:
        symbol = item["symbol"]
        market = item["market"]
        provider = raw.get("_bars_meta", {}).get(market, {}).get("symbols", {}).get(symbol, {}).get("provider") or raw.get("_provider")
        context = analyze_symbol_bars(
            raw_bars_by_symbol.get(symbol, []),
            asset_snapshot=summary.get("asset_snapshot"),
            market=market,
            timeframe=app.timeframe,
            app_config=app.raw,
            provider=str(provider or app.broker_platform),
        )
        symbol_bar_contexts[symbol] = context
        if policy["regular_session_only_for_indicators"]:
            bars_by_symbol[symbol] = list(context.get("regular_completed_bars", []))
        else:
            bars_by_symbol[symbol] = list(context.get("raw_bars", []))
    
    # Check if rule engine is enabled
    use_rule_engine = app.raw.get('strategy', {}).get('use_rule_engine', False)
    rules_path = app.raw.get('strategy', {}).get('rules_path')
    
    signals = []
    engine_type = 'legacy'
    rule_engine: RuleEngine | None = None
    symbol_profile_overview: dict[str, Any] = {}

    if use_rule_engine and rules_path:
        # Use new rule engine
        try:
            rules_file = Path(rules_path)
            if not rules_file.is_absolute():
                rules_file = Path(__file__).resolve().parents[2] / rules_file

            rule_engine = RuleEngine(
                rules_file,
                symbol_universe=[item["symbol"] for item in app.symbols],
            )
            engine_type = 'rule_engine'
            symbol_profile_overview = rule_engine.get_symbol_profile_overview(
                [item["symbol"] for item in app.symbols],
                market_by_symbol={item["symbol"]: item["market"] for item in app.symbols},
            )
            
            for item in app.symbols:
                symbol = item['symbol']
                market = item['market']
                bars = bars_by_symbol.get(symbol, [])
                position = positions_map.get(symbol)
                
                rule_signals = rule_engine.evaluate_symbol(symbol, market, bars, position)
                for signal in rule_signals:
                    signals.append(
                        _decorate_signal_with_bar_context(
                            signal.to_dict(),
                            symbol_bar_contexts.get(symbol),
                            policy=policy,
                        )
                    )
        except Exception as e:
            print(f'[build_strategy_summary] Rule engine failed, falling back to legacy: {e}')
            use_rule_engine = False
    
    if not use_rule_engine:
        # Use legacy strategy engine
        engine = StrategyEngine(app)
        signals = [
            _decorate_signal_with_bar_context(
                signal.to_dict(),
                symbol_bar_contexts.get(signal.symbol),
                policy=policy,
            )
            for signal in engine.generate(bars_by_symbol=bars_by_symbol, positions=positions_map)
        ]

    summary['strategy'] = {
        'timeframe': app.timeframe,
        'signals': signals,
        'engine': engine_type,
        'symbol_profiles': symbol_profile_overview if engine_type == 'rule_engine' else {},
        'market_data': {
            'extended_hours_usage': policy["extended_hours_usage"],
            'regular_session_only_for_indicators': policy["regular_session_only_for_indicators"],
            'require_completed_bar_for_actionable_signal': policy["require_completed_bar_for_actionable_signal"],
        },
    }
    summary['data_health'] = _build_data_health_report(
        raw,
        summary,
        app,
        engine_type=engine_type,
        rule_engine=rule_engine,
        raw_bars_by_symbol=raw_bars_by_symbol,
        symbol_bar_contexts=symbol_bar_contexts,
    )
    _attach_factor_shadow(
        summary,
        raw,
        app,
        raw_bars_by_symbol=raw_bars_by_symbol,
    )
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
        data_health=summary.get('data_health', {}),
    )
    decision_dicts = [item.to_dict() for item in decisions]
    previews = [item.to_dict() for item in executor.build_previews(
        signals=summary['strategy']['signals'],
        risk_decisions=decision_dicts,
        contracts=summary.get('contracts', {}),
    )]
    trade_limit_store = TradeLimitStore(_state_dir(app))
    first_symbol = app.symbols[0] if app.symbols else {"market": "US", "symbol": None}
    first_symbol_bars = raw.get("bars", {}).get(first_symbol.get("market"), {})
    raw_bars_for_day = _extract_bars_map(first_symbol_bars).get(first_symbol.get("symbol"), [])
    trading_day = resolve_trading_day_for_market(
        summary.get('asset_snapshot'),
        raw_bars_for_day,
        timezone_name=session_config(app.raw, first_symbol.get("market", "US"))["timezone"],
    )
    recorded_at = resolve_now_for_market(
        summary.get('asset_snapshot'),
        raw_bars_for_day,
        timezone_name=session_config(app.raw, first_symbol.get("market", "US"))["timezone"],
    ).isoformat()
    intents = [item.to_dict() for item in intent_builder.build(previews, cycle_id=cycle_id)]
    for intent in intents:
        trade_limit_store.record_trade(
            trading_day,
            symbol=intent['symbol'],
            side=intent['side'],
            ts=recorded_at,
            idempotency_key=intent.get('idempotency_key'),
        )

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
            'trading_day': item.get('trading_day'),
            'tradingDay': item.get('tradingDay'),
            'timestamp': item.get('timestamp'),
            'ts': item.get('ts'),
            'account_timestamp': item.get('account_timestamp'),
            'accountTimestamp': item.get('accountTimestamp'),
            'broker_timestamp': item.get('broker_timestamp'),
            'brokerTimestamp': item.get('brokerTimestamp'),
            'updated_at': item.get('updated_at'),
            'as_of': item.get('as_of'),
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
            '_provider': getattr(data, 'name', app.broker_platform),
            'accounts': client.get_accounts(),
            'assets': client.get_assets(),
            'positions': client.get_positions(),
            'active_orders': client.get_active_orders(),
            'quote_permissions': client.get_quote_permission(),
        }
    else:
        result = {
            '_provider': getattr(data, 'name', app.broker_platform),
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
    result['_bars_meta'] = {}

    provider_cfg = app.strategy.get("data_provider", {})
    configured_primary = str(provider_cfg.get("primary") or getattr(data, "name", result.get("_provider")))
    configured_fallback = provider_cfg.get("fallback")
    fail_on_empty_bars = bool(provider_cfg.get("fail_on_empty_bars", False))

    for market, symbols in symbols_by_market.items():
        result['market_state'][market] = data.get_market_state(market)
        result['delay_quotes'][market] = data.get_delay_quotes(symbols, market=market)
        result['briefs'][market] = data.get_briefs(symbols, market=market)
        fallback_provider = None
        fallback_name = str(configured_fallback) if configured_fallback else None
        if fallback_name and fallback_name != configured_primary:
            if client is not None and fallback_name == app.broker_platform:
                fallback_provider = client
            elif fallback_name != getattr(data, "name", None):
                try:
                    fallback_provider = create_data_provider(fallback_name)
                except Exception:
                    fallback_provider = None

        bars_resp, bars_meta = fetch_bars_with_fallback(
            data,
            symbols,
            period=app.timeframe,
            limit=int(app.signal.get('lookback_bars', 30)),
            fallback_provider=fallback_provider,
            primary_name=configured_primary,
            fallback_name=fallback_name,
            fail_on_empty_bars=fail_on_empty_bars,
        )
        result['bars'][market] = bars_resp
        result['_bars_meta'][market] = bars_meta
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
