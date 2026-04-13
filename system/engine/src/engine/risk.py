from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor
from typing import Any


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
        self.max_order_notional_usd = float(risk.get('max_order_notional_usd', 10000))
        self.max_total_exposure_usd = float(risk.get('max_total_exposure_usd', 1000000))
        self.daily_loss_limit_pct = float(risk.get('daily_loss_limit_pct', 5))
        self.fx_rates_to_usd = dict(risk.get('fx_rates_to_usd', {'USD': 1.0}))
        self.disable_leverage = bool(risk.get('disable_leverage', False))

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
            )
            decisions.append(decision)
            if decision.allowed and decision.action == 'BUY' and decision.estimated_notional_usd:
                projected_exposure += float(decision.estimated_notional_usd)
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
        })

        if action == 'HOLD':
            reasons.append('no_trade_action')
            return RiskDecision(symbol, market, action, False, 0, None, None, reasons, diagnostics)

        if not diagnostics['market_tradeable']:
            reasons.append('market_not_regular_session')

        if action == 'BUY':
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
