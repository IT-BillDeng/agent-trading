"""Rule Engine - 基于配置的规则评估引擎"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from .indicators import (
    sma,
    ema,
    ema_slope,
    rsi,
    bollinger,
    macd,
    atr,
    pct_change,
    bar_range_pct,
    volume_ratio as calc_volume_ratio,
)


@dataclass
class RuleSignal:
    """规则引擎产生的信号"""
    rule_id: str
    symbol: str
    market: str
    action: str  # BUY / EXIT / HOLD
    order_type: str
    score: int
    reason: str
    stop_loss: float | None
    take_profit: float | None
    last_close: float | None
    suggested_quantity: int | None = None
    risk_per_share: float | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IndicatorCalculator:
    """指标计算器 - 根据名称和参数计算技术指标"""
    
    def __init__(self):
        self._indicators: dict[str, Callable] = {
            'sma': self._calc_sma,
            'ema': self._calc_ema,
            'ema_slope': self._calc_ema_slope,
            'rsi': self._calc_rsi,
            'bollinger': self._calc_bollinger,
            'macd': self._calc_macd,
            'atr': self._calc_atr,
            'momentum': self._calc_momentum,
            'volume_ratio': self._calc_volume_ratio,
            'bar_range_pct': self._calc_bar_range_pct,
        }
    
    def calculate(self, indicator: str, params: dict[str, Any], 
                  bars: list[dict[str, Any]]) -> Any:
        """计算指标值"""
        calc_func = self._indicators.get(indicator)
        if not calc_func:
            return None
        return calc_func(params, bars)
    
    def _calc_sma(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> float | None:
        period = params.get('period', 20)
        closes = [float(bar['close']) for bar in bars]
        return sma(closes, period)
    
    def _calc_ema(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> float | None:
        period = params.get('period', 20)
        closes = [float(bar['close']) for bar in bars]
        return ema(closes, period)

    def _calc_ema_slope(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> float | None:
        period = params.get('period', 20)
        lookback = params.get('lookback', 3)
        closes = [float(bar['close']) for bar in bars]
        return ema_slope(closes, period, lookback)
    
    def _calc_rsi(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> float | None:
        period = params.get('period', 14)
        closes = [float(bar['close']) for bar in bars]
        return rsi(closes, period)
    
    def _calc_bollinger(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, float] | None:
        period = params.get('period', 20)
        std_dev = params.get('std_dev', 2)
        closes = [float(bar['close']) for bar in bars]
        
        upper, middle, lower = bollinger(closes, period, std_dev)
        if upper is None:
            return None
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower
        }
    
    def _calc_macd(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, float] | None:
        closes = [float(bar['close']) for bar in bars]
        
        macd_line, signal_line, histogram = macd(closes, closes)
        if macd_line is None:
            return None
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        }
    
    def _calc_atr(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> float | None:
        period = params.get('period', 14)
        highs = [float(bar['high']) for bar in bars]
        lows = [float(bar['low']) for bar in bars]
        closes = [float(bar['close']) for bar in bars]
        return atr(highs, lows, closes, period)
    
    def _calc_momentum(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> float | None:
        period = params.get('period', 3)
        closes = [float(bar['close']) for bar in bars]
        if len(closes) < period + 1:
            return None
        return pct_change(closes[-1], closes[-period-1])
    
    def _calc_volume_ratio(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> float | None:
        period = params.get('period', 20)
        volumes = [float(bar.get('volume', 0)) for bar in bars]
        return calc_volume_ratio(volumes, period)
    
    def _calc_bar_range_pct(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> float | None:
        if not bars:
            return None
        last_bar = bars[-1]
        return bar_range_pct(float(last_bar['high']), float(last_bar['low']), float(last_bar['close']))


class ConditionEvaluator:
    """条件评估器 - 评估规则条件"""
    
    def __init__(self, indicator_calc: IndicatorCalculator):
        self.indicator_calc = indicator_calc
    
    def evaluate(self, condition: dict[str, Any], bars: list[dict[str, Any]], 
                 position: dict[str, Any] | None = None) -> tuple[bool, dict[str, Any]]:
        """
        评估单个条件
        返回 (是否满足, 诊断信息)
        """
        cond_type = condition.get('type')
        
        if cond_type == 'indicator':
            return self._eval_indicator(condition, bars)
        elif cond_type == 'price':
            return self._eval_price(condition, bars)
        elif cond_type == 'volume':
            return self._eval_volume(condition, bars)
        elif cond_type == 'stop_loss':
            return self._eval_stop_loss(condition, bars, position)
        elif cond_type == 'take_profit':
            return self._eval_take_profit(condition, bars, position)
        elif cond_type == 'time':
            return self._eval_time(condition, bars)
        elif 'operator' in condition and 'items' in condition:
            # 组合条件 (AND/OR)
            return self._eval_compound(condition, bars, position)
        
        return False, {'error': f'unknown condition type: {cond_type}'}
    
    def _eval_indicator(self, condition: dict[str, Any], bars: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
        """评估指标条件"""
        indicator = condition.get('indicator')
        params = condition.get('params', {})
        compare = condition.get('compare', {})
        
        # 计算指标值
        value = self.indicator_calc.calculate(indicator, params, bars)
        if value is None:
            return False, {'indicator': indicator, 'value': None, 'reason': 'insufficient_data'}
        
        # 获取比较值
        compare_value = None
        compare_field = compare.get('field')
        compare_indicator = compare.get('indicator')
        compare_value_const = compare.get('value')
        
        if compare_field == 'close':
            compare_value = float(bars[-1]['close']) if bars else None
        elif compare_indicator:
            compare_params = compare.get('params', {})
            compare_value = self.indicator_calc.calculate(compare_indicator, compare_params, bars)
        elif compare_value_const is not None:
            compare_value = compare_value_const
        
        if compare_value is None:
            return False, {'indicator': indicator, 'value': value, 'compare_value': None, 'reason': 'no_compare_value'}
        
        operator = compare.get('operator', 'above')
        prev_value = None
        prev_compare_value = None

        if operator in {'cross_above', 'cross_below'}:
            prev_bars = bars[:-1]
            if not prev_bars:
                return False, {
                    'indicator': indicator,
                    'value': value,
                    'compare_value': compare_value,
                    'reason': 'insufficient_data_for_cross',
                }

            prev_value = self.indicator_calc.calculate(indicator, params, prev_bars)
            if prev_value is None:
                return False, {
                    'indicator': indicator,
                    'value': value,
                    'compare_value': compare_value,
                    'reason': 'insufficient_data_for_cross',
                }

            if compare_field == 'close':
                prev_compare_value = float(prev_bars[-1]['close']) if prev_bars else None
            elif compare_indicator:
                compare_params = compare.get('params', {})
                prev_compare_value = self.indicator_calc.calculate(compare_indicator, compare_params, prev_bars)
            elif compare_value_const is not None:
                prev_compare_value = compare_value_const

            if prev_compare_value is None:
                return False, {
                    'indicator': indicator,
                    'value': value,
                    'compare_value': compare_value,
                    'reason': 'insufficient_data_for_cross',
                }

        # 执行比较
        result = self._compare(
            value,
            compare_value,
            operator,
            bars,
            indicator,
            prev_value=prev_value,
            prev_compare_value=prev_compare_value,
        )

        diagnostics = {
            'indicator': indicator,
            'params': params,
            'value': value,
            'operator': operator,
            'compare_value': compare_value,
            'prev_value': prev_value,
            'prev_compare_value': prev_compare_value,
            'result': result
        }
        
        return result, diagnostics
    
    def _compare(
        self,
        value: Any,
        compare_value: Any,
        operator: str,
        bars: list[dict[str, Any]],
        indicator: str,
        prev_value: Any = None,
        prev_compare_value: Any = None,
    ) -> bool:
        """执行比较操作"""
        if operator == 'above':
            if isinstance(value, dict):
                # 布林带等返回字典的指标
                return value.get('middle', 0) > compare_value if isinstance(compare_value, (int, float)) else False
            return value > compare_value
        
        elif operator == 'below':
            if isinstance(value, dict):
                return value.get('middle', 0) < compare_value if isinstance(compare_value, (int, float)) else False
            return value < compare_value
        
        elif operator == 'equal':
            return abs(value - compare_value) < 1e-6 if isinstance(value, (int, float)) else False
        
        elif operator == 'above_upper':
            if isinstance(value, dict):
                close = float(bars[-1]['close']) if bars else 0
                return close > value.get('upper', 0)
            return False
        
        elif operator == 'below_lower':
            if isinstance(value, dict):
                close = float(bars[-1]['close']) if bars else 0
                return close < value.get('lower', 0)
            return False
        
        elif operator == 'above_middle':
            if isinstance(value, dict):
                close = float(bars[-1]['close']) if bars else 0
                return close > value.get('middle', 0)
            return False
        
        elif operator == 'below_middle':
            if isinstance(value, dict):
                close = float(bars[-1]['close']) if bars else 0
                return close < value.get('middle', 0)
            return False
        
        elif operator == 'cross_above':
            return (
                isinstance(value, (int, float))
                and isinstance(compare_value, (int, float))
                and isinstance(prev_value, (int, float))
                and isinstance(prev_compare_value, (int, float))
                and prev_value <= prev_compare_value
                and value > compare_value
            )
        
        elif operator == 'cross_below':
            return (
                isinstance(value, (int, float))
                and isinstance(compare_value, (int, float))
                and isinstance(prev_value, (int, float))
                and isinstance(prev_compare_value, (int, float))
                and prev_value >= prev_compare_value
                and value < compare_value
            )
        
        return False
    
    def _eval_price(self, condition: dict[str, Any], bars: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
        """评估价格条件"""
        field = condition.get('field', 'close')
        operator = condition.get('operator')
        value = condition.get('value')
        
        if not bars:
            return False, {'reason': 'no_bars'}
        
        current_price = float(bars[-1].get(field, 0))
        
        if operator == 'above':
            result = current_price > value
        elif operator == 'below':
            result = current_price < value
        else:
            result = False
        
        return result, {'field': field, 'current': current_price, 'threshold': value, 'result': result}
    
    def _eval_volume(self, condition: dict[str, Any], bars: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
        """评估成交量条件"""
        operator = condition.get('operator')
        ratio = condition.get('ratio', 1.5)
        
        volume_ratio_val = self.indicator_calc.calculate('volume_ratio', {'period': 20}, bars)
        if volume_ratio_val is None:
            return False, {'reason': 'insufficient_data'}
        
        if operator == 'above_avg':
            result = volume_ratio_val > ratio
        else:
            result = False
        
        return result, {'volume_ratio': volume_ratio_val, 'threshold': ratio, 'result': result}
    
    def _eval_stop_loss(self, condition: dict[str, Any], bars: list[dict[str, Any]], 
                        position: dict[str, Any] | None) -> tuple[bool, dict[str, Any]]:
        """评估止损条件"""
        if not position:
            return False, {'reason': 'no_position'}
        
        threshold_pct = condition.get('threshold_pct', 0.03)
        entry_price = position.get('avg_cost', 0)
        current_price = float(bars[-1]['close']) if bars else 0
        
        if entry_price == 0:
            return False, {'reason': 'no_entry_price'}
        
        loss_pct = (entry_price - current_price) / entry_price
        result = loss_pct >= threshold_pct
        
        return result, {
            'entry_price': entry_price,
            'current_price': current_price,
            'loss_pct': loss_pct,
            'threshold_pct': threshold_pct,
            'result': result
        }
    
    def _eval_take_profit(self, condition: dict[str, Any], bars: list[dict[str, Any]], 
                          position: dict[str, Any] | None) -> tuple[bool, dict[str, Any]]:
        """评估止盈条件"""
        if not position:
            return False, {'reason': 'no_position'}
        
        threshold_pct = condition.get('threshold_pct', 0.06)
        entry_price = position.get('avg_cost', 0)
        current_price = float(bars[-1]['close']) if bars else 0
        
        if entry_price == 0:
            return False, {'reason': 'no_entry_price'}
        
        profit_pct = (current_price - entry_price) / entry_price
        result = profit_pct >= threshold_pct
        
        return result, {
            'entry_price': entry_price,
            'current_price': current_price,
            'profit_pct': profit_pct,
            'threshold_pct': threshold_pct,
            'result': result
        }
    
    def _eval_time(self, condition: dict[str, Any], bars: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
        """评估时间条件"""
        # 简化实现，实际需要考虑市场时间
        return True, {'result': True, 'reason': 'time_check_simplified'}
    
    def _eval_compound(self, condition: dict[str, Any], bars: list[dict[str, Any]], 
                       position: dict[str, Any] | None) -> tuple[bool, dict[str, Any]]:
        """评估组合条件 (AND/OR)"""
        operator = condition.get('operator', 'AND')
        items = condition.get('items', [])
        
        results = []
        diagnostics = []
        
        for item in items:
            result, diag = self.evaluate(item, bars, position)
            results.append(result)
            diagnostics.append(diag)
        
        if operator == 'AND':
            final_result = all(results)
        elif operator == 'OR':
            final_result = any(results)
        else:
            final_result = False
        
        return final_result, {
            'operator': operator,
            'item_results': results,
            'diagnostics': diagnostics,
            'final_result': final_result
        }


class RuleEngine:
    """规则引擎 - 加载配置并评估规则"""
    
    def __init__(self, rules_path: str | Path):
        self.rules_path = Path(rules_path)
        self.indicator_calc = IndicatorCalculator()
        self.condition_eval = ConditionEvaluator(self.indicator_calc)
        self.rules_config = self._load_rules()
    
    def _load_rules(self) -> dict[str, Any]:
        """加载规则配置"""
        if not self.rules_path.exists():
            return {'rules': [], 'global_settings': {}}
        
        try:
            return json.loads(self.rules_path.read_text())
        except Exception as e:
            print(f"[RuleEngine] Failed to load rules: {e}")
            return {'rules': [], 'global_settings': {}}
    
    def reload(self):
        """重新加载规则配置"""
        self.rules_config = self._load_rules()
    
    def get_enabled_rules(self) -> list[dict[str, Any]]:
        """获取启用的规则"""
        return [r for r in self.rules_config.get('rules', []) if r.get('enabled', True)]
    
    def evaluate_symbol(self, symbol: str, market: str, bars: list[dict[str, Any]], 
                        position: dict[str, Any] | None = None) -> list[RuleSignal]:
        """
        评估标的的所有适用规则
        返回信号列表
        """
        signals = []
        enabled_rules = self.get_enabled_rules()
        
        for rule in enabled_rules:
            # 检查规则是否适用于此标的
            if not self._rule_applies(rule, symbol, market):
                continue
            
            signal = self._evaluate_rule(rule, symbol, market, bars, position)
            if signal:
                signals.append(signal)
        
        return signals
    
    def _rule_applies(self, rule: dict[str, Any], symbol: str, market: str) -> bool:
        """检查规则是否适用于标的"""
        rule_symbols = rule.get('symbols', ['*'])
        rule_markets = rule.get('markets', [])
        
        # 检查市场
        if rule_markets and market not in rule_markets:
            return False
        
        # 检查标的
        if '*' in rule_symbols:
            return True
        
        return symbol in rule_symbols
    
    def _evaluate_rule(self, rule: dict[str, Any], symbol: str, market: str,
                       bars: list[dict[str, Any]], position: dict[str, Any] | None) -> RuleSignal | None:
        """评估单条规则"""
        rule_id = rule.get('rule_id', 'unknown')
        
        # 检查数据充足性
        min_bars = self._get_min_bars_required(rule)
        if len(bars) < min_bars:
            return RuleSignal(
                rule_id=rule_id,
                symbol=symbol,
                market=market,
                action='HOLD',
                order_type='LMT',
                score=0,
                reason=f'insufficient_bars ({len(bars)}/{min_bars})',
                stop_loss=None,
                take_profit=None,
                last_close=bars[-1]['close'] if bars else None,
                diagnostics={'bar_count': len(bars), 'required': min_bars}
            )
        
        last_close = float(bars[-1]['close'])
        
        # 评估出场条件（如果有持仓）
        if position:
            exit_config = rule.get('exit', {})
            if exit_config:
                exit_conditions = exit_config.get('conditions', {})
                exit_result, exit_diag = self.condition_eval.evaluate(exit_conditions, bars, position)
                
                if exit_result:
                    return RuleSignal(
                        rule_id=rule_id,
                        symbol=symbol,
                        market=market,
                        action='EXIT',
                        order_type=exit_config.get('order_type', 'MKT'),
                        score=1,
                        reason=f'exit_condition_met',
                        stop_loss=None,
                        take_profit=None,
                        last_close=last_close,
                        diagnostics={'exit': exit_diag}
                    )
        
        # 评估入场条件（如果没有持仓）
        if not position:
            entry_config = rule.get('entry', {})
            if entry_config:
                entry_conditions = entry_config.get('conditions', {})
                entry_result, entry_diag = self.condition_eval.evaluate(entry_conditions, bars, None)
                
                if entry_result:
                    stop_loss_pct = entry_config.get('stop_loss_pct', 0.03)
                    take_profit_pct = entry_config.get('take_profit_pct', 0.06)
                    stop_loss = round(last_close * (1 - stop_loss_pct), 4)
                    take_profit = round(last_close * (1 + take_profit_pct), 4)
                    risk_per_share = round(last_close * stop_loss_pct, 4)
                    # 默认风险预算: $1,000 (max_order $100K × 1%)
                    risk_budget = float(entry_config.get('risk_budget', 1000))
                    suggested_qty = int(risk_budget / risk_per_share) if risk_per_share > 0 else None
                    # 额外约束: 单笔不超过 $100K
                    max_qty = int(100000 / last_close) if last_close > 0 else None
                    if max_qty and suggested_qty:
                        suggested_qty = min(suggested_qty, max_qty)
                    
                    return RuleSignal(
                        rule_id=rule_id,
                        symbol=symbol,
                        market=market,
                        action='BUY',
                        order_type=entry_config.get('order_type', 'LMT'),
                        score=1,
                        reason=f'entry_condition_met',
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        last_close=last_close,
                        suggested_quantity=suggested_qty,
                        risk_per_share=risk_per_share,
                        diagnostics={'entry': entry_diag, 'risk_budget': risk_budget, 'suggested_qty': suggested_qty}
                    )
        
        # 默认 HOLD
        return RuleSignal(
            rule_id=rule_id,
            symbol=symbol,
            market=market,
            action='HOLD',
            order_type='LMT',
            score=0,
            reason='no_condition_met',
            stop_loss=None,
            take_profit=None,
            last_close=last_close,
            diagnostics={}
        )
    
    def _get_min_bars_required(self, rule: dict[str, Any]) -> int:
        """计算规则所需的最少 K 线数量"""
        max_period = 0  # 从0开始，由实际指标周期决定
        
        def scan_periods(conditions: dict[str, Any]):
            nonlocal max_period
            
            if 'indicator' in conditions:
                params = conditions.get('params', {})
                period = params.get('period', 20)
                lookback = params.get('lookback', 0)
                max_period = max(max_period, period + lookback)
            
            if 'items' in conditions:
                for item in conditions['items']:
                    scan_periods(item)
        
        entry_conditions = rule.get('entry', {}).get('conditions', {})
        exit_conditions = rule.get('exit', {}).get('conditions', {})
        
        scan_periods(entry_conditions)
        scan_periods(exit_conditions)
        
        return max(max_period + 5, 10)  # 最少10根，额外buffer=5
