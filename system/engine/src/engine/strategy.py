from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import AppConfig
from .indicators import bar_range_pct, pct_change, sma

# FF-01 compatibility shim:
# keep ``engine.strategy`` as the legacy module while allowing
# ``engine.strategy.bindings`` / ``engine.strategy.evaluator`` style imports.
__path__ = [str(Path(__file__).with_suffix(""))]


@dataclass
class StrategySignal:
    symbol: str
    market: str
    action: str
    score: int
    reason: str
    suggested_order_type: str
    last_close: float | None
    stop_loss: float | None
    take_profit: float | None
    risk_per_share: float | None
    suggested_quantity: int | None
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StrategyEngine:
    def __init__(self, app: AppConfig):
        self.app = app
        signal = app.signal
        self.lookback_bars = int(signal.get('lookback_bars', 30))
        self.fast_sma = int(signal.get('fast_sma', 5))
        self.slow_sma = int(signal.get('slow_sma', 10))
        self.trend_sma = int(signal.get('trend_sma', 20))
        self.min_momentum_3bars = float(signal.get('min_momentum_3bars', 0.003))
        self.max_bar_range_pct = float(signal.get('max_bar_range_pct', 0.04))

    def generate(self, bars_by_symbol: dict[str, list[dict[str, Any]]], positions: dict[str, dict[str, Any]] | None = None) -> list[StrategySignal]:
        positions = positions or {}
        signals: list[StrategySignal] = []
        for item in self.app.symbols:
            symbol = item['symbol']
            market = item['market']
            bars = bars_by_symbol.get(symbol, [])
            position = positions.get(symbol)
            signals.append(self.evaluate_symbol(symbol=symbol, market=market, bars=bars, position=position))
        return signals

    def evaluate_symbol(self, symbol: str, market: str, bars: list[dict[str, Any]], position: dict[str, Any] | None = None) -> StrategySignal:
        min_required = max(self.fast_sma, self.slow_sma, self.trend_sma, 4)
        if len(bars) < min_required:
            return StrategySignal(
                symbol=symbol,
                market=market,
                action='HOLD',
                score=0,
                reason='insufficient_bars',
                suggested_order_type='LMT',
                last_close=bars[-1]['close'] if bars else None,
                stop_loss=None,
                take_profit=None,
                risk_per_share=None,
                suggested_quantity=None,
                diagnostics={'bar_count': len(bars), 'required': min_required},
            )

        closes = [float(bar['close']) for bar in bars]
        last_bar = bars[-1]
        last_close = closes[-1]
        fast = sma(closes, self.fast_sma)
        slow = sma(closes, self.slow_sma)
        trend = sma(closes, self.trend_sma)
        momentum3 = pct_change(last_close, closes[-4])
        last_range_pct = bar_range_pct(float(last_bar['high']), float(last_bar['low']), last_close)

        checks = {
            'close_above_fast': bool(fast is not None and last_close > fast),
            'fast_above_slow': bool(fast is not None and slow is not None and fast > slow),
            'slow_above_trend': bool(slow is not None and trend is not None and slow > trend),
            'momentum_positive': bool(momentum3 is not None and momentum3 >= self.min_momentum_3bars),
            'range_not_extreme': bool(last_range_pct is not None and last_range_pct <= self.max_bar_range_pct),
        }
        score = sum(1 for ok in checks.values() if ok)

        diagnostics = {
            'bar_count': len(bars),
            'fast_sma': fast,
            'slow_sma': slow,
            'trend_sma': trend,
            'momentum_3bars': momentum3,
            'last_bar_range_pct': last_range_pct,
            'checks': checks,
            'has_position': bool(position),
        }

        if position:
            if fast is not None and slow is not None and (last_close < fast or fast < slow):
                return StrategySignal(
                    symbol=symbol,
                    market=market,
                    action='EXIT',
                    score=score,
                    reason='trend_weakened_with_position',
                    suggested_order_type='MKT',
                    last_close=last_close,
                    stop_loss=None,
                    take_profit=None,
                    risk_per_share=None,
                    suggested_quantity=None,
                    diagnostics=diagnostics,
                )
            return StrategySignal(
                symbol=symbol,
                market=market,
                action='HOLD',
                score=score,
                reason='position_open_waiting',
                suggested_order_type='LMT',
                last_close=last_close,
                stop_loss=round(last_close * 0.97, 4),
                take_profit=round(last_close * 1.06, 4),
                risk_per_share=round(last_close * 0.03, 4),
                suggested_quantity=None,
                diagnostics=diagnostics,
            )

        if score >= 4:
            return StrategySignal(
                symbol=symbol,
                market=market,
                action='BUY',
                score=score,
                reason='trend_follow_30m_candidate',
                suggested_order_type='LMT',
                last_close=last_close,
                stop_loss=round(last_close * 0.97, 4),
                take_profit=round(last_close * 1.06, 4),
                risk_per_share=round(last_close * 0.03, 4),
                suggested_quantity=None,
                diagnostics=diagnostics,
            )

        return StrategySignal(
            symbol=symbol,
            market=market,
            action='HOLD',
            score=score,
            reason='setup_not_ready',
            suggested_order_type='LMT',
            last_close=last_close,
            stop_loss=None,
            take_profit=None,
            risk_per_share=None,
            suggested_quantity=None,
            diagnostics=diagnostics,
        )
