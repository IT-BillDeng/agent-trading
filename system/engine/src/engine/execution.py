from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any


@dataclass
class ExecutionPreview:
    symbol: str
    market: str
    side: str
    order_type: str
    quantity: int
    tif: str
    limit_price: float | None
    stop_price: float | None
    meta: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DryRunExecutor:
    def __init__(self, app_config: dict[str, Any]):
        execution = dict(app_config.get('execution', {}))
        self.tif = str(execution.get('tif', 'DAY'))
        self.default_entry_order_type = 'LMT'
        self.default_exit_order_type = 'MKT'

    def build_previews(
        self,
        signals: list[dict[str, Any]],
        risk_decisions: list[dict[str, Any]],
        contracts: dict[str, dict[str, dict[str, Any]]],
    ) -> list[ExecutionPreview]:
        decisions_by_symbol = {item['symbol']: item for item in risk_decisions}
        previews: list[ExecutionPreview] = []
        for signal in signals:
            decision = decisions_by_symbol.get(signal['symbol'])
            if not decision or not decision.get('allowed'):
                continue
            contract = contracts.get(signal['market'], {}).get(signal['symbol'], {})
            tick_sizes = contract.get('tickSizes', [])
            last_close = signal.get('last_close')
            if signal['action'] == 'BUY':
                limit_price = self._round_to_tick((last_close or 0) * 1.001, tick_sizes, mode='nearest') if last_close else None
                stop_price = self._round_to_tick(signal.get('stop_loss'), tick_sizes, mode='floor') if signal.get('stop_loss') else None
                previews.append(ExecutionPreview(
                    symbol=signal['symbol'],
                    market=signal['market'],
                    side='BUY',
                    order_type=signal.get('suggested_order_type') or self.default_entry_order_type,
                    quantity=int(decision['quantity']),
                    tif=self.tif,
                    limit_price=limit_price if (signal.get('suggested_order_type') or self.default_entry_order_type) == 'LMT' else None,
                    stop_price=stop_price,
                    meta={
                        'reason': signal.get('reason'),
                        'estimated_notional': decision.get('estimated_notional'),
                        'estimated_notional_usd': decision.get('estimated_notional_usd'),
                        'take_profit': signal.get('take_profit'),
                    },
                ))
            elif signal['action'] == 'EXIT':
                previews.append(ExecutionPreview(
                    symbol=signal['symbol'],
                    market=signal['market'],
                    side='SELL',
                    order_type=self.default_exit_order_type,
                    quantity=int(decision['quantity']),
                    tif=self.tif,
                    limit_price=None,
                    stop_price=None,
                    meta={
                        'reason': signal.get('reason'),
                        'estimated_notional': decision.get('estimated_notional'),
                        'estimated_notional_usd': decision.get('estimated_notional_usd'),
                    },
                ))
        return previews

    def _round_to_tick(self, price: float | None, tick_sizes: list[dict[str, Any]], mode: str = 'nearest') -> float | None:
        if price is None:
            return None
        tick = self._resolve_tick(price, tick_sizes)
        if tick <= 0:
            return float(price)
        decimal_price = Decimal(str(price))
        decimal_tick = Decimal(str(tick))
        if mode == 'floor':
            rounded = (decimal_price / decimal_tick).to_integral_value(rounding=ROUND_FLOOR) * decimal_tick
        else:
            rounded = (decimal_price / decimal_tick).to_integral_value(rounding=ROUND_HALF_UP) * decimal_tick
        return float(rounded)

    def _resolve_tick(self, price: float, tick_sizes: list[dict[str, Any]]) -> float:
        if not tick_sizes:
            return 0.01
        for item in tick_sizes:
            begin = self._parse_bound(item.get('begin'))
            end = self._parse_bound(item.get('end'))
            if begin <= price <= end:
                return float(item.get('tickSize', 0.01))
        return float(tick_sizes[-1].get('tickSize', 0.01))

    def _parse_bound(self, value: Any) -> float:
        if value in (None, 'Infinity'):
            return float('inf') if value == 'Infinity' else 0.0
        try:
            return float(value)
        except Exception:
            return 0.0
