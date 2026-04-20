from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .control import ControlPlane
from .state import TradeLimitStore


@dataclass
class RiskDecision:
    symbol: str
    market: str
    action: str
    allowed: bool
    quantity: int
    estimated_notional: float | None
    estimated_notional_usd: float | None
    reasons: list[str]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RiskManager:
    def __init__(self, app_config: dict[str, Any]):
        risk = dict(app_config.get('risk', {}))
        system = dict(app_config.get('system', {}))
        self.max_order_notional_usd = float(risk.get('max_order_notional_usd', 10000))
        self.max_total_exposure_usd = float(risk.get('max_total_exposure_usd', 1000000))
        self.daily_loss_limit_pct = float(risk.get('daily_loss_limit_pct', 5))
        self.max_trades_per_day = int(risk.get('max_trades_per_day', 10))
        self.max_trades_per_symbol_per_day = int(risk.get('max_trades_per_symbol_per_day', 3))
        self.symbol_cooldown_minutes_after_order = int(risk.get('symbol_cooldown_minutes_after_order', 30))
        self.symbol_cooldown_minutes_after_loss = int(risk.get('symbol_cooldown_minutes_after_loss', 120))
        self.fx_rates_to_usd = dict(risk.get('fx_rates_to_usd', {'USD': 1.0}))
        self.disable_leverage = bool(risk.get('disable_leverage', False))
        state_dir = Path(system.get('state_dir', './state'))
        if not state_dir.is_absolute():
            state_dir = Path(__file__).resolve().parents[2] / state_dir
        self.control = ControlPlane(state_dir)
        self.trade_limits = TradeLimitStore(state_dir)

    def evaluate(
        self,
        signals: list[dict[str, Any]],
        asset_snapshot: dict[str, Any] | None,
        market_state: dict[str, Any],
        contracts: dict[str, dict[str, dict[str, Any]]],
        positions_map: dict[str, dict[str, Any]],
        active_orders_map: dict[str, dict[str, Any]],
    ) -> list[RiskDecision]:
        decisions: list[RiskDecision] = []
        risk_state = self._refresh_daily_loss_state(asset_snapshot or {})
        trading_day = self._resolve_trading_day(asset_snapshot or {})
        now_ts = self._resolve_timestamp(asset_snapshot or {})
        trade_limit_state = self.trade_limits.snapshot(trading_day)
        projected_total_trades = int(trade_limit_state.get('total_trades', 0))
        projected_symbol_state = {
            symbol: {
                'trade_count': int((data or {}).get('trade_count', 0)),
                'last_order_at': (data or {}).get('last_order_at'),
                'last_loss_at': (data or {}).get('last_loss_at'),
            }
            for symbol, data in dict(trade_limit_state.get('symbols', {})).items()
        }
        current_exposure = self._estimate_current_exposure_usd(positions_map, contracts)
        projected_exposure = current_exposure
        for signal in signals:
            decision = self._evaluate_one(
                signal=signal,
                asset_snapshot=asset_snapshot or {},
                market_state=market_state,
                contracts=contracts,
                positions_map=positions_map,
                active_orders_map=active_orders_map,
                current_exposure_usd=projected_exposure,
                risk_state=risk_state,
                projected_total_trades=projected_total_trades,
                projected_symbol_state=projected_symbol_state,
                now_ts=now_ts,
            )
            decisions.append(decision)
            if decision.allowed and decision.action == 'BUY' and decision.estimated_notional_usd:
                projected_exposure += float(decision.estimated_notional_usd)
            if decision.allowed and decision.action in {'BUY', 'EXIT'}:
                projected_total_trades += 1
                symbol_state = projected_symbol_state.setdefault(
                    decision.symbol,
                    {'trade_count': 0, 'last_order_at': None, 'last_loss_at': None},
                )
                symbol_state['trade_count'] = int(symbol_state.get('trade_count', 0)) + 1
                symbol_state['last_order_at'] = now_ts
        return decisions

    def _evaluate_one(
        self,
        signal: dict[str, Any],
        asset_snapshot: dict[str, Any],
        market_state: dict[str, Any],
        contracts: dict[str, dict[str, dict[str, Any]]],
        positions_map: dict[str, dict[str, Any]],
        active_orders_map: dict[str, dict[str, Any]],
        current_exposure_usd: float,
        risk_state: dict[str, Any],
        projected_total_trades: int,
        projected_symbol_state: dict[str, dict[str, Any]],
        now_ts: str,
    ) -> RiskDecision:
        symbol = signal['symbol']
        market = signal['market']
        action = signal['action']
        reasons: list[str] = []
        diagnostics: dict[str, Any] = {'current_exposure_usd': current_exposure_usd}

        contract = contracts.get(market, {}).get(symbol, {})
        currency = contract.get('currency', 'USD')
        last_close = signal.get('last_close')
        fx_rate = float(self.fx_rates_to_usd.get(currency, 0.0))
        position = positions_map.get(symbol)
        active_order = active_orders_map.get(symbol)

        diagnostics.update({
            'currency': currency,
            'fx_rate_to_usd': fx_rate,
            'has_position': bool(position),
            'has_active_order': bool(active_order),
            'market_tradeable': self._market_tradeable(market_state.get(market)),
            'daily_loss_locked': bool(risk_state.get('daily_loss_locked', False)),
            'daily_loss_pct': risk_state.get('daily_loss_pct'),
            'reduce_only': bool(risk_state.get('reduce_only', False)),
            'reduce_only_reason': risk_state.get('reduce_only_reason'),
            'emergency_flatten': bool(risk_state.get('emergency_flatten', False)),
            'projected_total_trades': projected_total_trades,
            'projected_symbol_trades': int(projected_symbol_state.get(symbol, {}).get('trade_count', 0)),
        })

        if action == 'HOLD':
            reasons.append('no_trade_action')
            return RiskDecision(symbol, market, action, False, 0, None, None, reasons, diagnostics)

        if not diagnostics['market_tradeable']:
            reasons.append('market_not_regular_session')

        if action == 'BUY':
            if risk_state.get('emergency_flatten', False):
                reasons.append('emergency_flatten_active')
            if risk_state.get('reduce_only', False) and risk_state.get('reduce_only_reason') != 'daily_loss_limit_exceeded':
                reasons.append('reduce_only_active')
            if risk_state.get('daily_loss_locked', False):
                reasons.append('daily_loss_limit_exceeded')
            reasons.extend(
                self._trade_limit_reasons(
                    symbol=symbol,
                    projected_total_trades=projected_total_trades,
                    projected_symbol_state=projected_symbol_state.get(symbol, {}),
                    now_ts=now_ts,
                )
            )
            if position:
                reasons.append('position_already_exists')
            if active_order:
                reasons.append('active_order_exists')
            if last_close in (None, 0):
                reasons.append('missing_last_close')
            if fx_rate <= 0:
                reasons.append('missing_fx_rate')

            quantity = 0
            estimated_notional = None
            estimated_notional_usd = None
            if not reasons:
                suggested_qty = signal.get('suggested_quantity')
                risk_per_share = signal.get('risk_per_share')

                # Leverage-free cash cap
                cash_cap = None
                if self.disable_leverage:
                    net_liq = float(asset_snapshot.get('netLiquidation') or 0)
                    gross_pos = float(asset_snapshot.get('grossPositionValue') or 0)
                    effective_cash = net_liq - gross_pos
                    diagnostics['leverage_free_cash'] = effective_cash
                    if effective_cash <= 0:
                        reasons.append('leverage_blocked_no_cash')
                    else:
                        cash_cap = effective_cash

                quantity, estimated_notional, estimated_notional_usd = self._size_buy(
                    last_close, fx_rate,
                    suggested_quantity=suggested_qty,
                    risk_per_share=risk_per_share,
                    cash_cap=cash_cap,
                )
                diagnostics.update({
                    'sizing_last_close': last_close,
                    'sizing_raw_notional_usd_limit': self.max_order_notional_usd,
                    'sizing_method': 'risk_based' if risk_per_share else 'max_limit',
                    'sizing_risk_per_share': risk_per_share,
                    'sizing_suggested_qty': suggested_qty,
                    'sizing_cash_cap': cash_cap,
                })
                if quantity <= 0:
                    reasons.append('order_too_small')
                if estimated_notional_usd:
                    diagnostics['post_trade_exposure_usd'] = current_exposure_usd + estimated_notional_usd
                    diagnostics['max_total_exposure_usd'] = self.max_total_exposure_usd
                    if current_exposure_usd + estimated_notional_usd > self.max_total_exposure_usd:
                        reasons.append('exposure_limit_exceeded')

            return RiskDecision(
                symbol=symbol,
                market=market,
                action=action,
                allowed=not reasons,
                quantity=quantity,
                estimated_notional=estimated_notional,
                estimated_notional_usd=estimated_notional_usd,
                reasons=reasons,
                diagnostics=diagnostics,
            )

        if action == 'EXIT':
            quantity = self._position_quantity(position)
            if not position:
                reasons.append('no_position_to_exit')
            if quantity <= 0:
                reasons.append('invalid_position_quantity')
            estimated_notional = float(last_close * quantity) if last_close else None
            estimated_notional_usd = float(estimated_notional * fx_rate) if estimated_notional is not None and fx_rate > 0 else None
            return RiskDecision(
                symbol=symbol,
                market=market,
                action=action,
                allowed=not reasons,
                quantity=max(quantity, 0),
                estimated_notional=estimated_notional,
                estimated_notional_usd=estimated_notional_usd,
                reasons=reasons,
                diagnostics=diagnostics,
            )

        reasons.append('unknown_action')
        return RiskDecision(symbol, market, action, False, 0, None, None, reasons, diagnostics)

    def _refresh_daily_loss_state(self, asset_snapshot: dict[str, Any]) -> dict[str, Any]:
        current_equity = self._optional_float(asset_snapshot.get('netLiquidation'))
        state = self.control.status()
        risk_state = dict(state.get('risk', {}))

        if current_equity is None or current_equity <= 0:
            return risk_state

        trading_day = self._resolve_trading_day(asset_snapshot)
        previous_day = risk_state.get('trading_day')
        updates: dict[str, Any] = {}

        if trading_day != previous_day:
            updates = {
                'trading_day': trading_day,
                'day_start_equity_usd': current_equity,
                'last_equity_usd': current_equity,
                'daily_loss_pct': 0.0,
                'daily_loss_locked': False,
            }
            if risk_state.get('reduce_only_reason') == 'daily_loss_limit_exceeded':
                updates['reduce_only'] = False
                updates['reduce_only_reason'] = None
            return self.control.update_risk(updates, updated_by='risk_manager', action='daily_loss_reset')['risk']

        day_start = self._optional_float(risk_state.get('day_start_equity_usd'))
        if day_start is None or day_start <= 0:
            day_start = current_equity
            updates['day_start_equity_usd'] = current_equity
            if not risk_state.get('trading_day'):
                updates['trading_day'] = trading_day

        daily_loss_pct = max(0.0, ((day_start - current_equity) / day_start) * 100.0) if day_start > 0 else 0.0
        updates['last_equity_usd'] = current_equity
        updates['daily_loss_pct'] = daily_loss_pct

        if daily_loss_pct >= self.daily_loss_limit_pct and not risk_state.get('daily_loss_locked', False):
            updates['daily_loss_locked'] = True
            updates['reduce_only'] = True
            updates['reduce_only_reason'] = 'daily_loss_limit_exceeded'

        if updates:
            return self.control.update_risk(updates, updated_by='risk_manager', action='daily_loss_update')['risk']
        return risk_state

    def _size_buy(
        self,
        last_close: float,
        fx_rate: float,
        suggested_quantity: int | None = None,
        risk_per_share: float | None = None,
        cash_cap: float | None = None,
    ) -> tuple[int, float | None, float | None]:
        if last_close <= 0 or fx_rate <= 0:
            return 0, None, None

        # Max quantity from notional limit
        max_quantity = int(self.max_order_notional_usd / (last_close * fx_rate))

        # Risk-based quantity (if signal provides risk_per_share)
        risk_quantity = None
        if risk_per_share and risk_per_share > 0:
            risk_budget = self.max_order_notional_usd * 0.01  # 1% of max order as risk budget
            risk_quantity = int(risk_budget / (risk_per_share * fx_rate))

        # Cash-only cap (disable_leverage)
        cash_quantity = None
        if cash_cap is not None and cash_cap > 0:
            cash_quantity = int(cash_cap / (last_close * fx_rate))

        # Pick the most conservative
        candidates = [max_quantity]
        if suggested_quantity and suggested_quantity > 0:
            candidates.append(int(suggested_quantity))
        if risk_quantity and risk_quantity > 0:
            candidates.append(risk_quantity)
        if cash_quantity is not None and cash_quantity > 0:
            candidates.append(cash_quantity)
        quantity = min(candidates)

        if quantity <= 0:
            return 0, None, None
        notional = last_close * quantity
        return quantity, float(notional), float(notional * fx_rate)

    def _estimate_current_exposure_usd(self, positions_map: dict[str, dict[str, Any]], contracts: dict[str, dict[str, dict[str, Any]]]) -> float:
        total = 0.0
        for symbol, position in positions_map.items():
            qty = self._position_quantity(position)
            latest = float(position.get('latestPrice') or position.get('marketPrice') or position.get('averageCost') or 0)
            market = position.get('market') or self._infer_market(symbol, contracts)
            contract = contracts.get(market or '', {}).get(symbol, {})
            currency = contract.get('currency', 'USD')
            fx_rate = float(self.fx_rates_to_usd.get(currency, 0.0))
            if qty > 0 and latest > 0 and fx_rate > 0:
                total += qty * latest * fx_rate
        return total

    def _infer_market(self, symbol: str, contracts: dict[str, dict[str, dict[str, Any]]]) -> str | None:
        for market, market_contracts in contracts.items():
            if symbol in market_contracts:
                return market
        return None

    def _position_quantity(self, position: dict[str, Any] | None) -> int:
        if not position:
            return 0
        raw = position.get('position') or position.get('quantity') or 0
        try:
            return int(float(raw))
        except Exception:
            return 0

    def _market_tradeable(self, state: Any) -> bool:
        if not isinstance(state, list) or not state:
            return False
        item = state[0]
        status = str(item.get('status', '')).upper()
        market_status = str(item.get('marketStatus', '')).lower()
        blocked_keywords = ('POST', 'PRE', 'CLOSE', 'NOT_YET', 'HALT', 'SUSPEND', 'LUNCH')
        if any(key in status for key in blocked_keywords):
            return False
        if any(word in market_status for word in ('post', 'pre', 'close', 'not yet', 'halt', 'suspend', 'lunch')):
            return False
        positive = ('TRADING', 'OPEN', 'MORNING', 'AFTERNOON')
        return any(word in status for word in positive) or 'trading' in market_status or 'open' in market_status

    def _resolve_trading_day(self, asset_snapshot: dict[str, Any]) -> str:
        for key in ('trading_day', 'tradingDay', 'date'):
            value = asset_snapshot.get(key)
            if value:
                return str(value)[:10]
        return datetime.now(timezone.utc).date().isoformat()

    def _resolve_timestamp(self, asset_snapshot: dict[str, Any]) -> str:
        for key in ('timestamp', 'ts', 'updated_at', 'as_of'):
            value = asset_snapshot.get(key)
            if value:
                return str(value)
        return datetime.now(timezone.utc).isoformat()

    def _optional_float(self, value: Any) -> float | None:
        if value in (None, ''):
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _trade_limit_reasons(
        self,
        *,
        symbol: str,
        projected_total_trades: int,
        projected_symbol_state: dict[str, Any],
        now_ts: str,
    ) -> list[str]:
        reasons: list[str] = []
        if self.max_trades_per_day > 0 and projected_total_trades >= self.max_trades_per_day:
            reasons.append('max_trades_per_day_exceeded')

        symbol_trade_count = int(projected_symbol_state.get('trade_count', 0) or 0)
        if self.max_trades_per_symbol_per_day > 0 and symbol_trade_count >= self.max_trades_per_symbol_per_day:
            reasons.append(f'max_trades_per_symbol_exceeded:{symbol}')

        now_dt = self._parse_timestamp(now_ts)
        last_order_at = self._parse_timestamp(projected_symbol_state.get('last_order_at'))
        if (
            now_dt
            and last_order_at
            and self.symbol_cooldown_minutes_after_order > 0
            and (now_dt - last_order_at).total_seconds() < self.symbol_cooldown_minutes_after_order * 60
        ):
            reasons.append(f'symbol_cooldown_active:{symbol}')

        last_loss_at = self._parse_timestamp(projected_symbol_state.get('last_loss_at'))
        if (
            now_dt
            and last_loss_at
            and self.symbol_cooldown_minutes_after_loss > 0
            and (now_dt - last_loss_at).total_seconds() < self.symbol_cooldown_minutes_after_loss * 60
        ):
            reasons.append(f'symbol_loss_cooldown_active:{symbol}')

        return reasons

    def _parse_timestamp(self, value: Any):
        if not value:
            return None
        text = str(value)
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        try:
            return datetime.fromisoformat(text)
        except Exception:
            return None
