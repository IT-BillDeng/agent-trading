"""Rule Engine - 基于配置的规则评估引擎"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from .factors.builtins import (
    build_regular_session_analysis,
    compute_atr_value,
    compute_bollinger_bands_value,
    compute_bollinger_zscore_value,
    compute_return_value,
    compute_rsi_value,
    compute_volume_ratio_value,
)
from .factors.registry import FactorRegistry, load_factor_registry
from .indicators import (
    sma,
    ema,
    ema_slope,
    macd,
    bar_range_pct,
)
from .rule_profiles import (
    build_symbol_profile_overview,
    resolve_rule_state,
    rule_applies_to_symbol,
)
from .rule_schema import validate_rules_config
from .signal_arbiter import SignalArbiter
from .strategy.evaluator import (
    CompatibilityLegacyConditionEvaluator,
    FactorConditionEvaluator,
    StructuralConditionEvaluator,
    normalize_condition_to_factor_binding_view,
    normalize_rule_to_factor_binding_view,
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
    priority: int | None
    stop_loss: float | None
    take_profit: float | None
    last_close: float | None
    suggested_quantity: int | None = None
    risk_per_share: float | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    base_rule_id: str | None = None
    primary_rule_id: str | None = None
    source_rule_ids: list[str] = field(default_factory=list)
    symbol_profile: str | None = None
    effective_config_hash: str | None = None
    effective_config_hashes: list[str] = field(default_factory=list)
    overrides_applied: dict[str, Any] = field(default_factory=dict)

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
        value, _, _ = compute_rsi_value(
            build_regular_session_analysis(bars),
            period=int(period),
        )
        return value

    def _calc_bollinger(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> dict[str, float] | None:
        period = params.get('period', 20)
        std_dev = params.get('std_dev', 2)
        value, _, _ = compute_bollinger_bands_value(
            build_regular_session_analysis(bars),
            period=int(period),
            std_dev=float(std_dev),
        )
        return value
    
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
        value, _, _ = compute_atr_value(
            build_regular_session_analysis(bars),
            period=int(period),
        )
        return value

    def _calc_momentum(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> float | None:
        period = params.get('period', 3)
        value, _, _ = compute_return_value(
            build_regular_session_analysis(bars),
            period=int(period),
        )
        return value

    def _calc_volume_ratio(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> float | None:
        period = params.get('period', 20)
        value, _, _ = compute_volume_ratio_value(
            build_regular_session_analysis(bars),
            period=int(period),
        )
        return value
    
    def _calc_bar_range_pct(self, params: dict[str, Any], bars: list[dict[str, Any]]) -> float | None:
        if not bars:
            return None
        last_bar = bars[-1]
        return bar_range_pct(float(last_bar['high']), float(last_bar['low']), float(last_bar['close']))


class FactorAccessor:
    _INDICATOR_IMPL = {
        'rsi': 'builtin:rsi',
        'bollinger': 'builtin:bollinger_zscore',
        'volume_ratio': 'builtin:volume_ratio',
        'atr': 'builtin:atr_pct',
        'momentum': 'builtin:return',
    }

    def __init__(
        self,
        factor_registry: FactorRegistry | None,
        *,
        compatibility_mode: bool = True,
    ):
        self.factor_registry = factor_registry
        self.compatibility_mode = bool(compatibility_mode)

    def supports_indicator(self, indicator: str) -> bool:
        return indicator in self._INDICATOR_IMPL

    def resolve_numeric_indicator(
        self,
        indicator: str,
        params: dict[str, Any],
        bars: list[dict[str, Any]],
        *,
        factor_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        factor_def = self._matching_factor_definition(indicator, params)
        if factor_def is not None:
            payload = self._factor_payload(factor_snapshot, factor_def.factor_id)
            value = self._payload_to_numeric_value(indicator, payload, bars)
            if value is not None:
                return {
                    'ready': True,
                    'value': value,
                    'source': 'factor_snapshot',
                    'reason': 'ok',
                    'factor_id': factor_def.factor_id,
                    'config_hash': payload.get('config_hash') if isinstance(payload, dict) else factor_def.config_hash,
                    'payload': payload,
                }
            if isinstance(payload, dict) and not bool(payload.get('ready')):
                if not self.compatibility_mode:
                    return {
                        'ready': False,
                        'value': None,
                        'source': 'factor_snapshot',
                        'reason': str(payload.get('reason') or 'factor_not_ready'),
                        'factor_id': factor_def.factor_id,
                        'config_hash': payload.get('config_hash') or factor_def.config_hash,
                        'payload': payload,
                    }

        if not self.compatibility_mode:
            return {
                'ready': False,
                'value': None,
                'source': 'factor_compatibility_disabled',
                'reason': 'factor_snapshot_unavailable',
                'factor_id': factor_def.factor_id if factor_def is not None else None,
                'config_hash': factor_def.config_hash if factor_def is not None else None,
                'payload': None,
            }

        value, reason = self._compute_compatibility_numeric(indicator, params, bars)
        return {
            'ready': value is not None,
            'value': value,
            'source': 'compatibility_factor_builtin',
            'reason': reason,
            'factor_id': factor_def.factor_id if factor_def is not None else None,
            'config_hash': factor_def.config_hash if factor_def is not None else self._compatibility_hash(indicator, params),
            'payload': None,
        }

    def resolve_bollinger_bands(
        self,
        params: dict[str, Any],
        bars: list[dict[str, Any]],
    ) -> dict[str, Any]:
        period = int(params.get('period', 20))
        std_dev = float(params.get('std_dev', 2.0))
        value, reason, _ = compute_bollinger_bands_value(
            build_regular_session_analysis(bars),
            period=period,
            std_dev=std_dev,
        )
        return {
            'ready': value is not None,
            'value': value,
            'source': 'compatibility_factor_builtin',
            'reason': reason,
            'factor_id': None,
            'config_hash': self._compatibility_hash('bollinger', params),
            'payload': None,
        }

    def resolve_bollinger_zscore(
        self,
        params: dict[str, Any],
        bars: list[dict[str, Any]],
        *,
        factor_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        factor_def = self._matching_factor_definition('bollinger', params)
        if factor_def is not None:
            payload = self._factor_payload(factor_snapshot, factor_def.factor_id)
            value = self._payload_to_numeric_value('bollinger', payload, bars)
            if value is not None:
                return {
                    'ready': True,
                    'value': value,
                    'source': 'factor_snapshot',
                    'reason': 'ok',
                    'factor_id': factor_def.factor_id,
                    'config_hash': payload.get('config_hash') if isinstance(payload, dict) else factor_def.config_hash,
                    'payload': payload,
                }
            if isinstance(payload, dict) and not bool(payload.get('ready')) and not self.compatibility_mode:
                return {
                    'ready': False,
                    'value': None,
                    'source': 'factor_snapshot',
                    'reason': str(payload.get('reason') or 'factor_not_ready'),
                    'factor_id': factor_def.factor_id,
                    'config_hash': payload.get('config_hash') or factor_def.config_hash,
                    'payload': payload,
                }

        if not self.compatibility_mode:
            return {
                'ready': False,
                'value': None,
                'source': 'factor_compatibility_disabled',
                'reason': 'factor_snapshot_unavailable',
                'factor_id': factor_def.factor_id if factor_def is not None else None,
                'config_hash': factor_def.config_hash if factor_def is not None else None,
                'payload': None,
            }

        period = int(params.get('period', 20))
        std_dev = float(params.get('std_dev', 2.0))
        value, reason, _ = compute_bollinger_zscore_value(
            build_regular_session_analysis(bars),
            period=period,
            std_dev=std_dev,
        )
        return {
            'ready': value is not None,
            'value': value,
            'source': 'compatibility_factor_builtin',
            'reason': reason,
            'factor_id': factor_def.factor_id if factor_def is not None else None,
            'config_hash': factor_def.config_hash if factor_def is not None else self._compatibility_hash('bollinger', params),
            'payload': None,
        }

    def build_parity_report(
        self,
        bars: list[dict[str, Any]],
        *,
        factor_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entries = {
            'rsi_14_30m': self._build_numeric_parity_entry(
                'rsi',
                {'period': 14},
                bars,
                factor_snapshot=factor_snapshot,
            ),
            'bollinger_zscore_20_2_30m': self._build_numeric_parity_entry(
                'bollinger',
                {'period': 20, 'std_dev': 2.0},
                bars,
                factor_snapshot=factor_snapshot,
            ),
            'volume_ratio_20_30m': self._build_numeric_parity_entry(
                'volume_ratio',
                {'period': 20},
                bars,
                factor_snapshot=factor_snapshot,
            ),
            'atr_pct_14_30m': self._build_numeric_parity_entry(
                'atr',
                {'period': 14},
                bars,
                factor_snapshot=factor_snapshot,
            ),
            'return_5_30m': self._build_numeric_parity_entry(
                'momentum',
                {'period': 5},
                bars,
                factor_snapshot=factor_snapshot,
            ),
        }
        ready_entries = [entry for entry in entries.values() if bool(entry.get('ready'))]
        return {
            'ready_count': len(ready_entries),
            'total_count': len(entries),
            'entries': entries,
        }

    def _build_numeric_parity_entry(
        self,
        indicator: str,
        params: dict[str, Any],
        bars: list[dict[str, Any]],
        *,
        factor_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved = self.resolve_numeric_indicator(
            indicator,
            params,
            bars,
            factor_snapshot=factor_snapshot,
        ) if indicator != 'bollinger' else self.resolve_bollinger_zscore(
            params,
            bars,
            factor_snapshot=factor_snapshot,
        )

        legacy_value, legacy_reason = self._compute_compatibility_numeric(indicator, params, bars)
        if resolved['value'] is None or legacy_value is None:
            return {
                'ready': False,
                'indicator': indicator,
                'params': dict(params),
                'legacy_value': legacy_value,
                'factor_value': resolved['value'],
                'diff': None,
                'factor_source': resolved['source'],
                'factor_reason': resolved['reason'],
                'legacy_reason': legacy_reason,
            }
        return {
            'ready': True,
            'indicator': indicator,
            'params': dict(params),
            'legacy_value': legacy_value,
            'factor_value': resolved['value'],
            'diff': float(resolved['value']) - float(legacy_value),
            'factor_source': resolved['source'],
            'factor_reason': resolved['reason'],
            'legacy_reason': legacy_reason,
        }

    def _compute_compatibility_numeric(
        self,
        indicator: str,
        params: dict[str, Any],
        bars: list[dict[str, Any]],
    ) -> tuple[float | None, str]:
        analysis = build_regular_session_analysis(bars)
        period = int(params.get('period', 20))
        if indicator == 'rsi':
            value, reason, _ = compute_rsi_value(analysis, period=period)
            return value, reason
        if indicator == 'volume_ratio':
            value, reason, _ = compute_volume_ratio_value(analysis, period=period)
            return value, reason
        if indicator == 'atr':
            value, reason, _ = compute_atr_value(analysis, period=period)
            return value, reason
        if indicator == 'momentum':
            value, reason, _ = compute_return_value(analysis, period=period)
            return value, reason
        if indicator == 'bollinger':
            std_dev = float(params.get('std_dev', 2.0))
            value, reason, _ = compute_bollinger_zscore_value(
                analysis,
                period=period,
                std_dev=std_dev,
            )
            return value, reason
        return None, 'unsupported_indicator'

    def _payload_to_numeric_value(
        self,
        indicator: str,
        payload: dict[str, Any] | None,
        bars: list[dict[str, Any]],
    ) -> float | None:
        if not isinstance(payload, dict) or not payload.get('ready'):
            return None
        raw_value = payload.get('value')
        if raw_value is None:
            return None
        if indicator == 'atr':
            if not bars:
                return None
            last_close = float(bars[-1].get('close', 0) or 0)
            if last_close == 0:
                return None
            return float(raw_value) * last_close
        return float(raw_value)

    def _matching_factor_definition(self, indicator: str, params: dict[str, Any]):
        if self.factor_registry is None:
            return None
        implementation = self._INDICATOR_IMPL.get(indicator)
        if implementation is None:
            return None
        normalized_params = self._normalized_indicator_params(indicator, params)
        for factor_id, factor_def in self.factor_registry.factors.items():
            if factor_def.implementation != implementation:
                continue
            if self._normalized_indicator_params(indicator, factor_def.params) != normalized_params:
                continue
            return factor_def
        return None

    def _normalized_indicator_params(self, indicator: str, params: dict[str, Any]) -> dict[str, Any]:
        if indicator == 'bollinger':
            return {
                'period': int(params.get('period', 20)),
                'std_dev': float(params.get('std_dev', 2.0)),
            }
        if indicator in {'rsi', 'volume_ratio', 'atr', 'momentum'}:
            return {'period': int(params.get('period', 14 if indicator != 'momentum' else 3))}
        return {}

    def _factor_payload(self, factor_snapshot: dict[str, Any] | None, factor_id: str) -> dict[str, Any] | None:
        if not isinstance(factor_snapshot, dict):
            return None
        factors = factor_snapshot.get('factors')
        if not isinstance(factors, dict):
            return None
        payload = factors.get(factor_id)
        return payload if isinstance(payload, dict) else None

    def _compatibility_hash(self, indicator: str, params: dict[str, Any]) -> str:
        payload = {'indicator': indicator, 'params': self._normalized_indicator_params(indicator, params)}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode('utf-8')).hexdigest()


class ConditionEvaluator:
    """条件评估器 - 评估规则条件"""
    
    def __init__(
        self,
        indicator_calc: IndicatorCalculator,
        *,
        factor_registry: FactorRegistry | None = None,
        allow_actionable_consumption: bool | None = None,
        factor_compatibility_mode: bool = True,
    ):
        self.indicator_calc = indicator_calc
        self.factor_registry = factor_registry
        self.factor_accessor = FactorAccessor(
            factor_registry,
            compatibility_mode=factor_compatibility_mode,
        )
        self.factor_only_accessor = FactorAccessor(
            factor_registry,
            compatibility_mode=False,
        )
        if allow_actionable_consumption is None:
            allow_actionable_consumption = bool(
                factor_registry.defaults.get("allow_actionable_consumption", False)
            ) if factor_registry is not None else False
        self.allow_actionable_consumption = bool(allow_actionable_consumption)
        self.factor_condition_evaluator = FactorConditionEvaluator(
            factor_registry=self.factor_registry,
            compare_fn=self._compare,
            factor_payload_getter=self._factor_payload,
            factor_allowed_for_actionable_buy=self._factor_allowed_for_actionable_buy,
            factor_binding_value_resolver=self._resolve_factor_binding_value,
        )
        self.compatibility_legacy_evaluator = CompatibilityLegacyConditionEvaluator(
            indicator_calc=self.indicator_calc,
            compare_fn=self._compare,
        )
        self.structural_condition_evaluator = StructuralConditionEvaluator(
            router=self.evaluate,
            position_avg_cost_resolver=self._position_avg_cost,
        )
    
    def evaluate(
        self,
        condition: dict[str, Any],
        bars: list[dict[str, Any]],
        position: dict[str, Any] | None = None,
        *,
        factor_snapshot: dict[str, Any] | None = None,
        previous_factor_snapshot: dict[str, Any] | None = None,
        intent_action: str | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """
        评估单个条件
        返回 (是否满足, 诊断信息)
        """
        view = normalize_condition_to_factor_binding_view(
            condition,
            factor_accessor=self.factor_only_accessor,
        )

        if view.kind == "structural_condition":
            return self.structural_condition_evaluator.evaluate(
                view,
                bars=bars,
                position=position,
                factor_snapshot=factor_snapshot,
                previous_factor_snapshot=previous_factor_snapshot,
                intent_action=intent_action,
            )

        if view.kind == "factor_condition":
            result, diagnostics = self.factor_condition_evaluator.evaluate(
                view,
                bars=bars,
                factor_snapshot=factor_snapshot,
                previous_factor_snapshot=previous_factor_snapshot,
                intent_action=intent_action,
            )
            if (
                not result
                and bool(view.metadata.get("compatibility_fallback"))
                and self.factor_accessor.compatibility_mode
                and diagnostics.get("reason")
                not in {
                    "factor_actionable_consumption_disabled",
                    "factor_not_actionable",
                    "factor_context_only",
                    "unknown_factor",
                }
            ):
                fallback_result, fallback_diagnostics = self.compatibility_legacy_evaluator.evaluate(
                    condition,
                    bars,
                )
                fallback_diagnostics["fallback_from_factor"] = True
                fallback_diagnostics["binding_factor_id"] = view.metadata.get("factor_id")
                return fallback_result, fallback_diagnostics
            return result, diagnostics

        return self.compatibility_legacy_evaluator.evaluate(condition, bars)
    
    def _eval_indicator(
        self,
        condition: dict[str, Any],
        bars: list[dict[str, Any]],
        *,
        factor_snapshot: dict[str, Any] | None,
        previous_factor_snapshot: dict[str, Any] | None,
    ) -> tuple[bool, dict[str, Any]]:
        """评估指标条件"""
        indicator = condition.get('indicator')
        params = condition.get('params', {})
        compare = condition.get('compare', {})
        operator = compare.get('operator', 'above')
        current_value, current_meta = self._resolve_indicator_value(
            indicator,
            params,
            bars,
            compare=compare,
            factor_snapshot=factor_snapshot,
        )
        if current_value is None:
            diagnostics = {
                'indicator': indicator,
                'params': params,
                'value': None,
                'operator': operator,
                'compare_value': None,
                'prev_value': None,
                'prev_compare_value': None,
                'result': False,
            }
            diagnostics.update(current_meta)
            diagnostics['reason'] = current_meta.get('feature_reason', 'insufficient_data')
            return False, diagnostics

        if indicator == 'bollinger' and operator in {'above_upper', 'below_lower', 'above_middle', 'below_middle'}:
            std_dev = float(params.get('std_dev', 2.0))
            compare_value = {
                'above_upper': std_dev,
                'below_lower': -std_dev,
                'above_middle': 0.0,
                'below_middle': 0.0,
            }.get(operator)
            compare_meta = {'source': 'bollinger_threshold'}
        else:
            compare_value, compare_meta = self._resolve_compare_value(
                compare,
                bars,
                factor_snapshot=factor_snapshot,
            )
        if compare_value is None:
            diagnostics = {
                'indicator': indicator,
                'params': params,
                'value': current_value,
                'operator': operator,
                'compare_value': None,
                'prev_value': None,
                'prev_compare_value': None,
                'result': False,
            }
            diagnostics.update(current_meta)
            diagnostics.update(compare_meta)
            diagnostics['reason'] = 'no_compare_value'
            return False, diagnostics

        prev_value = None
        prev_compare_value = None
        if operator in {'cross_above', 'cross_below'}:
            prev_bars = bars[:-1]
            if not prev_bars:
                diagnostics = {
                    'indicator': indicator,
                    'params': params,
                    'value': current_value,
                    'operator': operator,
                    'compare_value': compare_value,
                    'prev_value': None,
                    'prev_compare_value': None,
                    'result': False,
                    'reason': 'insufficient_data_for_cross',
                }
                diagnostics.update(current_meta)
                return False, diagnostics

            prev_value, prev_meta = self._resolve_indicator_value(
                indicator,
                params,
                prev_bars,
                compare=compare,
                factor_snapshot=previous_factor_snapshot,
            )
            if prev_value is None:
                diagnostics = {
                    'indicator': indicator,
                    'params': params,
                    'value': current_value,
                    'operator': operator,
                    'compare_value': compare_value,
                    'prev_value': None,
                    'prev_compare_value': None,
                    'result': False,
                    'reason': 'insufficient_data_for_cross',
                }
                diagnostics.update(current_meta)
                diagnostics.update({f'prev_{key}': value for key, value in prev_meta.items()})
                return False, diagnostics

            prev_compare_value, prev_compare_meta = self._resolve_compare_value(
                compare,
                prev_bars,
                factor_snapshot=previous_factor_snapshot,
            )
            if prev_compare_value is None:
                diagnostics = {
                    'indicator': indicator,
                    'params': params,
                    'value': current_value,
                    'operator': operator,
                    'compare_value': compare_value,
                    'prev_value': prev_value,
                    'prev_compare_value': None,
                    'result': False,
                    'reason': 'insufficient_data_for_cross',
                }
                diagnostics.update(current_meta)
                diagnostics.update({f'prev_compare_{key}': value for key, value in prev_compare_meta.items()})
                return False, diagnostics

        result = self._compare(
            current_value,
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
            'value': current_value,
            'operator': operator,
            'compare_value': compare_value,
            'prev_value': prev_value,
            'prev_compare_value': prev_compare_value,
            'result': result,
            'reason': 'ok' if result else 'condition_false',
        }
        diagnostics.update(current_meta)
        if compare_meta:
            diagnostics['compare_meta'] = compare_meta
        return result, diagnostics

    def _eval_factor(
        self,
        condition: dict[str, Any],
        *,
        factor_snapshot: dict[str, Any] | None,
        previous_factor_snapshot: dict[str, Any] | None,
        intent_action: str | None,
    ) -> tuple[bool, dict[str, Any]]:
        factor_id = str(condition.get('factor_id') or '')
        compare = condition.get('compare', {})
        operator = compare.get('operator', 'above')
        compare_value = compare.get('value')
        factor_def = self.factor_registry.factors.get(factor_id) if self.factor_registry is not None else None
        payload = self._factor_payload(factor_snapshot, factor_id)
        diagnostics = {
            'indicator': 'factor',
            'factor_id': factor_id,
            'operator': operator,
            'compare_value': compare_value,
            'value': payload.get('value') if isinstance(payload, dict) else None,
            'prev_value': None,
            'prev_compare_value': compare_value if operator in {'cross_above', 'cross_below'} else None,
            'ready': bool(payload.get('ready')) if isinstance(payload, dict) else False,
            'actionable': bool(payload.get('actionable')) if isinstance(payload, dict) else (
                bool(factor_def.actionable) if factor_def is not None else False
            ),
            'source': payload.get('source') if isinstance(payload, dict) else None,
            'config_hash': payload.get('config_hash') if isinstance(payload, dict) else (
                factor_def.config_hash if factor_def is not None else None
            ),
        }

        if factor_def is None:
            diagnostics['reason'] = 'unknown_factor'
            diagnostics['result'] = False
            return False, diagnostics

        if intent_action == 'BUY':
            allowed, gate_reason = self._factor_allowed_for_actionable_buy(factor_def)
            if not allowed:
                diagnostics['reason'] = gate_reason
                diagnostics['result'] = False
                return False, diagnostics

        if not isinstance(payload, dict):
            diagnostics['reason'] = 'factor_unavailable'
            diagnostics['result'] = False
            return False, diagnostics

        if not payload.get('ready'):
            diagnostics['reason'] = 'factor_not_ready'
            diagnostics['factor_reason'] = payload.get('reason')
            diagnostics['result'] = False
            return False, diagnostics

        value = payload.get('value')
        if value is None:
            diagnostics['reason'] = 'factor_value_missing'
            diagnostics['result'] = False
            return False, diagnostics

        prev_value = None
        prev_compare_value = None
        if operator in {'cross_above', 'cross_below'}:
            previous_payload = self._factor_payload(previous_factor_snapshot, factor_id)
            if not isinstance(previous_payload, dict) or not previous_payload.get('ready'):
                diagnostics['reason'] = 'insufficient_factor_history'
                diagnostics['result'] = False
                diagnostics['prev_value'] = None
                diagnostics['prev_compare_value'] = compare_value
                return False, diagnostics
            prev_value = previous_payload.get('value')
            prev_compare_value = compare_value
            if prev_value is None:
                diagnostics['reason'] = 'insufficient_factor_history'
                diagnostics['result'] = False
                diagnostics['prev_value'] = None
                diagnostics['prev_compare_value'] = compare_value
                return False, diagnostics

        result = self._compare(
            value,
            compare_value,
            operator,
            [],
            'factor',
            prev_value=prev_value,
            prev_compare_value=prev_compare_value,
        )
        diagnostics['prev_value'] = prev_value
        diagnostics['prev_compare_value'] = prev_compare_value
        diagnostics['reason'] = 'ok' if result else 'condition_false'
        diagnostics['result'] = result
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
            if indicator == 'bollinger' and isinstance(value, (int, float)) and isinstance(compare_value, (int, float)):
                return float(value) > float(compare_value)
            return False
        
        elif operator == 'below_lower':
            if isinstance(value, dict):
                close = float(bars[-1]['close']) if bars else 0
                return close < value.get('lower', 0)
            if indicator == 'bollinger' and isinstance(value, (int, float)) and isinstance(compare_value, (int, float)):
                return float(value) < float(compare_value)
            return False
        
        elif operator == 'above_middle':
            if isinstance(value, dict):
                close = float(bars[-1]['close']) if bars else 0
                return close > value.get('middle', 0)
            if indicator == 'bollinger' and isinstance(value, (int, float)):
                return float(value) > 0.0
            return False
        
        elif operator == 'below_middle':
            if isinstance(value, dict):
                close = float(bars[-1]['close']) if bars else 0
                return close < value.get('middle', 0)
            if indicator == 'bollinger' and isinstance(value, (int, float)):
                return float(value) < 0.0
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
    
    def _eval_volume(
        self,
        condition: dict[str, Any],
        bars: list[dict[str, Any]],
        *,
        factor_snapshot: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """评估成交量条件"""
        operator = condition.get('operator')
        ratio = condition.get('ratio', 1.5)

        volume_ratio_val, meta = self._resolve_indicator_value(
            'volume_ratio',
            {'period': 20},
            bars,
            compare={},
            factor_snapshot=factor_snapshot,
        )
        if volume_ratio_val is None:
            diagnostics = {'reason': meta.get('feature_reason', 'insufficient_data')}
            diagnostics.update(meta)
            return False, diagnostics
        
        if operator == 'above_avg':
            result = volume_ratio_val > ratio
        else:
            result = False

        diagnostics = {
            'volume_ratio': volume_ratio_val,
            'threshold': ratio,
            'result': result,
        }
        diagnostics.update(meta)
        return result, diagnostics

    def _resolve_indicator_value(
        self,
        indicator: str,
        params: dict[str, Any],
        bars: list[dict[str, Any]],
        *,
        compare: dict[str, Any],
        factor_snapshot: dict[str, Any] | None,
    ) -> tuple[Any, dict[str, Any]]:
        operator = compare.get('operator', 'above')

        if self.factor_registry is None:
            value = self.indicator_calc.calculate(indicator, params, bars)
            return value, {
                'feature_source': 'legacy_indicator_calculator',
                'feature_reason': 'ok' if value is not None else 'insufficient_data',
                'factor_id': None,
                'config_hash': None,
            }

        if indicator == 'bollinger':
            if operator in {'above_upper', 'below_lower', 'above_middle', 'below_middle'}:
                resolved = self.factor_accessor.resolve_bollinger_zscore(
                    params,
                    bars,
                    factor_snapshot=factor_snapshot,
                )
                return resolved.get('value'), {
                    'feature_source': resolved.get('source'),
                    'feature_reason': resolved.get('reason'),
                    'factor_id': resolved.get('factor_id'),
                    'config_hash': resolved.get('config_hash'),
                }

            resolved = self.factor_accessor.resolve_bollinger_bands(params, bars)
            return resolved.get('value'), {
                'feature_source': resolved.get('source'),
                'feature_reason': resolved.get('reason'),
                'factor_id': resolved.get('factor_id'),
                'config_hash': resolved.get('config_hash'),
            }

        if self.factor_accessor.supports_indicator(indicator):
            resolved = self.factor_accessor.resolve_numeric_indicator(
                indicator,
                params,
                bars,
                factor_snapshot=factor_snapshot,
            )
            return resolved.get('value'), {
                'feature_source': resolved.get('source'),
                'feature_reason': resolved.get('reason'),
                'factor_id': resolved.get('factor_id'),
                'config_hash': resolved.get('config_hash'),
            }

        value = self.indicator_calc.calculate(indicator, params, bars)
        return value, {
            'feature_source': 'legacy_indicator_calculator',
            'feature_reason': 'ok' if value is not None else 'insufficient_data',
            'factor_id': None,
            'config_hash': None,
        }

    def _resolve_compare_value(
        self,
        compare: dict[str, Any],
        bars: list[dict[str, Any]],
        *,
        factor_snapshot: dict[str, Any] | None,
    ) -> tuple[Any, dict[str, Any]]:
        compare_field = compare.get('field')
        compare_indicator = compare.get('indicator')
        compare_value_const = compare.get('value')

        if compare_field == 'close':
            return (float(bars[-1]['close']) if bars else None), {'source': 'close'}
        if compare_indicator:
            compare_params = compare.get('params', {})
            value, meta = self._resolve_indicator_value(
                compare_indicator,
                compare_params,
                bars,
                compare={},
                factor_snapshot=factor_snapshot,
            )
            meta['source'] = 'indicator'
            return value, meta
        if compare_value_const is not None:
            return compare_value_const, {'source': 'constant'}
        return None, {'source': 'missing'}

    def _resolve_factor_binding_value(
        self,
        view: Any,
        bars: list[dict[str, Any]],
        factor_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        legacy_indicator = str(view.metadata.get("legacy_indicator") or "")
        params = dict(view.metadata.get("legacy_params") or {})
        if legacy_indicator == "bollinger":
            return self.factor_only_accessor.resolve_bollinger_zscore(
                params,
                bars,
                factor_snapshot=factor_snapshot,
            )
        return self.factor_only_accessor.resolve_numeric_indicator(
            legacy_indicator,
            params,
            bars,
            factor_snapshot=factor_snapshot,
        )
    
    def _eval_stop_loss(self, condition: dict[str, Any], bars: list[dict[str, Any]], 
                        position: dict[str, Any] | None) -> tuple[bool, dict[str, Any]]:
        """评估止损条件"""
        if not position:
            return False, {'reason': 'no_position'}
        
        threshold_pct = condition.get('threshold_pct', 0.03)
        entry_price = self._position_avg_cost(position)
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
        entry_price = self._position_avg_cost(position)
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

    def _position_avg_cost(self, position: dict[str, Any]) -> float:
        for key in ('avg_cost', 'averageCost', 'avgCost', 'average_cost', 'costPrice'):
            value = position.get(key)
            if value not in (None, ''):
                try:
                    return float(value)
                except Exception:
                    continue
        return 0.0
    
    def _eval_time(self, condition: dict[str, Any], bars: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
        """评估时间条件"""
        # 简化实现，实际需要考虑市场时间
        return True, {'result': True, 'reason': 'time_check_simplified'}
    
    def _eval_compound(
        self,
        condition: dict[str, Any],
        bars: list[dict[str, Any]],
        position: dict[str, Any] | None,
        *,
        factor_snapshot: dict[str, Any] | None,
        previous_factor_snapshot: dict[str, Any] | None,
        intent_action: str | None,
    ) -> tuple[bool, dict[str, Any]]:
        """评估组合条件 (AND/OR)"""
        operator = condition.get('operator', 'AND')
        items = condition.get('items', [])
        
        results = []
        diagnostics = []
        
        for item in items:
            result, diag = self.evaluate(
                item,
                bars,
                position,
                factor_snapshot=factor_snapshot,
                previous_factor_snapshot=previous_factor_snapshot,
                intent_action=intent_action,
            )
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

    def _factor_payload(self, factor_snapshot: dict[str, Any] | None, factor_id: str) -> dict[str, Any] | None:
        if not isinstance(factor_snapshot, dict):
            return None
        factors = factor_snapshot.get('factors')
        if not isinstance(factors, dict):
            return None
        payload = factors.get(factor_id)
        return payload if isinstance(payload, dict) else None

    def _factor_allowed_for_actionable_buy(self, factor_def: FactorRegistry | Any) -> tuple[bool, str]:
        if not self.allow_actionable_consumption:
            return False, 'factor_actionable_consumption_disabled'
        if not getattr(factor_def, 'actionable', False):
            return False, 'factor_not_actionable'
        usage = set(getattr(factor_def, 'usage', ()) or ())
        if 'context_only' in usage or getattr(factor_def, 'session', None) == 'context_only':
            return False, 'factor_context_only'
        return True, 'ok'


class RuleEngine:
    """规则引擎 - 加载配置并评估规则"""
    
    def __init__(
        self,
        rules_path: str | Path,
        *,
        symbol_universe: list[str] | set[str] | tuple[str, ...] | None = None,
        factor_registry: FactorRegistry | str | Path | None = None,
    ):
        self.rules_path = Path(rules_path)
        self.symbol_universe = list(symbol_universe) if symbol_universe is not None else None
        self.factor_registry = self._load_factor_registry(factor_registry)
        self.indicator_calc = IndicatorCalculator()
        self.condition_eval = ConditionEvaluator(
            self.indicator_calc,
            factor_registry=self.factor_registry,
        )
        self.signal_arbiter = SignalArbiter()
        self.rules_config = self._load_rules()
    
    def _load_rules(self) -> dict[str, Any]:
        """加载规则配置"""
        if not self.rules_path.exists():
            return {'rules': [], 'global_settings': {}}
        
        try:
            data = json.loads(self.rules_path.read_text())
            validation = validate_rules_config(
                data,
                symbol_universe=self.symbol_universe,
                factor_registry=self.factor_registry,
            )
            if not validation["valid"]:
                print(f"[RuleEngine] Loaded rules with validation errors: {validation['errors']}")
            normalized = dict(data)
            normalized["rules"] = validation["valid_rules"]
            if not validation["valid"]:
                normalized.pop("symbol_profile_templates", None)
                normalized.pop("symbol_profiles", None)
            normalized["__validation__"] = {
                "valid": validation["valid"],
                "errors": validation["errors"],
                "warnings": validation["warnings"],
            }
            return normalized
        except Exception as e:
            print(f"[RuleEngine] Failed to load rules: {e}")
            return {'rules': [], 'global_settings': {}}

    def _load_factor_registry(
        self,
        factor_registry: FactorRegistry | str | Path | None,
    ) -> FactorRegistry | None:
        registry_ref = factor_registry
        if registry_ref is None:
            default_registry = Path(__file__).resolve().parents[4] / 'factors' / 'registry.json'
            if not default_registry.exists():
                return None
            registry_ref = default_registry

        if isinstance(registry_ref, FactorRegistry):
            return registry_ref

        try:
            return load_factor_registry(registry_ref)
        except Exception as exc:
            print(f"[RuleEngine] Failed to load factor registry: {exc}")
            return None
    
    def reload(self):
        """重新加载规则配置"""
        self.rules_config = self._load_rules()
    
    def get_enabled_rules(
        self,
        *,
        symbol: str | None = None,
        market: str | None = None,
    ) -> list[dict[str, Any]]:
        """获取启用的规则"""
        if symbol is not None:
            enabled_rules: list[dict[str, Any]] = []
            for rule in self.rules_config.get("rules", []):
                if not isinstance(rule, dict) or not rule.get("rule_id"):
                    continue
                state = resolve_rule_state(
                    self.rules_config,
                    symbol,
                    str(rule["rule_id"]),
                    market=market,
                )
                if state["enabled"] and isinstance(state["effective_rule"], dict):
                    enabled_rules.append(state["effective_rule"])
            return enabled_rules
        return [r for r in self.rules_config.get('rules', []) if r.get('enabled', True)]

    def get_symbol_profile_overview(
        self,
        symbols: list[str],
        *,
        market_by_symbol: dict[str, str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        return build_symbol_profile_overview(
            self.rules_config,
            symbols,
            market_by_symbol=market_by_symbol,
        )

    def get_rule_binding_view(self, rule: dict[str, Any]) -> dict[str, Any]:
        return normalize_rule_to_factor_binding_view(
            rule,
            factor_accessor=self.condition_eval.factor_only_accessor,
        )
    
    def evaluate_symbol(
        self,
        symbol: str,
        market: str,
        bars: list[dict[str, Any]],
        position: dict[str, Any] | None = None,
        *,
        factor_snapshot: dict[str, Any] | None = None,
        previous_factor_snapshot: dict[str, Any] | None = None,
    ) -> list[RuleSignal]:
        """
        评估标的的所有适用规则
        返回信号列表
        """
        signals = []
        enabled_rules = self.get_enabled_rules(symbol=symbol, market=market)
        
        for rule in enabled_rules:
            if factor_snapshot is None and previous_factor_snapshot is None:
                signal = self._evaluate_rule(rule, symbol, market, bars, position)
            else:
                signal = self._evaluate_rule(
                    rule,
                    symbol,
                    market,
                    bars,
                    position,
                    factor_snapshot=factor_snapshot,
                    previous_factor_snapshot=previous_factor_snapshot,
                )
            if signal:
                signals.append(signal)
        
        final_signal = self.signal_arbiter.choose(signals)
        return [final_signal] if final_signal else []
    
    def _rule_applies(self, rule: dict[str, Any], symbol: str, market: str) -> bool:
        """检查规则是否适用于标的"""
        return rule_applies_to_symbol(rule, symbol, market)
    
    def _evaluate_rule(
        self,
        rule: dict[str, Any],
        symbol: str,
        market: str,
        bars: list[dict[str, Any]],
        position: dict[str, Any] | None,
        *,
        factor_snapshot: dict[str, Any] | None = None,
        previous_factor_snapshot: dict[str, Any] | None = None,
    ) -> RuleSignal | None:
        """评估单条规则"""
        rule_id = rule.get('rule_id', 'unknown')
        profile_meta = rule.get("__rule_profile__") if isinstance(rule.get("__rule_profile__"), dict) else {}
        base_rule_id = str(profile_meta.get("base_rule_id") or rule_id)
        symbol_profile = profile_meta.get("profile_id")
        overrides_applied = profile_meta.get("overrides_applied") if isinstance(profile_meta.get("overrides_applied"), dict) else {}
        effective_config_hash = profile_meta.get("effective_config_hash")
        priority = int(rule.get('priority', 999999))
        
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
                priority=priority,
                stop_loss=None,
                take_profit=None,
                last_close=bars[-1]['close'] if bars else None,
                diagnostics={'bar_count': len(bars), 'required': min_bars},
                base_rule_id=base_rule_id,
                primary_rule_id=str(rule_id),
                source_rule_ids=[str(rule_id)],
                symbol_profile=symbol_profile,
                effective_config_hash=effective_config_hash,
                effective_config_hashes=[effective_config_hash] if effective_config_hash else [],
                overrides_applied=overrides_applied,
            )
        
        last_close = float(bars[-1]['close'])
        
        # 评估出场条件（如果有持仓）
        if position:
            exit_config = rule.get('exit', {})
            if exit_config:
                exit_conditions = exit_config.get('conditions', {})
                exit_result, exit_diag = self.condition_eval.evaluate(
                    exit_conditions,
                    bars,
                    position,
                    factor_snapshot=factor_snapshot,
                    previous_factor_snapshot=previous_factor_snapshot,
                    intent_action='EXIT',
                )
                
                if exit_result:
                    return RuleSignal(
                        rule_id=rule_id,
                        symbol=symbol,
                        market=market,
                        action='EXIT',
                        order_type=exit_config.get('order_type', 'MKT'),
                        score=1,
                        reason=f'exit_condition_met',
                        priority=priority,
                        stop_loss=None,
                        take_profit=None,
                        last_close=last_close,
                        diagnostics=self._with_factor_diagnostics({'exit': exit_diag}),
                        base_rule_id=base_rule_id,
                        primary_rule_id=str(rule_id),
                        source_rule_ids=[str(rule_id)],
                        symbol_profile=symbol_profile,
                        effective_config_hash=effective_config_hash,
                        effective_config_hashes=[effective_config_hash] if effective_config_hash else [],
                        overrides_applied=overrides_applied,
                    )
        
        # 评估入场条件（如果没有持仓）
        if not position:
            entry_config = rule.get('entry', {})
            if entry_config:
                entry_conditions = entry_config.get('conditions', {})
                entry_result, entry_diag = self.condition_eval.evaluate(
                    entry_conditions,
                    bars,
                    None,
                    factor_snapshot=factor_snapshot,
                    previous_factor_snapshot=previous_factor_snapshot,
                    intent_action='BUY',
                )
                
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
                    signal_diag = self._with_factor_diagnostics({'entry': entry_diag})
                    signal_diag.update({'risk_budget': risk_budget, 'suggested_qty': suggested_qty})
                    
                    return RuleSignal(
                        rule_id=rule_id,
                        symbol=symbol,
                        market=market,
                        action='BUY',
                        order_type=entry_config.get('order_type', 'LMT'),
                        score=1,
                        reason=f'entry_condition_met',
                        priority=priority,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        last_close=last_close,
                        suggested_quantity=suggested_qty,
                        risk_per_share=risk_per_share,
                        diagnostics=signal_diag,
                        base_rule_id=base_rule_id,
                        primary_rule_id=str(rule_id),
                        source_rule_ids=[str(rule_id)],
                        symbol_profile=symbol_profile,
                        effective_config_hash=effective_config_hash,
                        effective_config_hashes=[effective_config_hash] if effective_config_hash else [],
                        overrides_applied=overrides_applied,
                    )
        
        # 默认 HOLD
        hold_diag: dict[str, Any] = {}
        if position:
            exit_conditions = rule.get('exit', {}).get('conditions', {}) if isinstance(rule.get('exit'), dict) else {}
            if self._condition_uses_factor(exit_conditions):
                exit_result, exit_diag = self.condition_eval.evaluate(
                    exit_conditions,
                    bars,
                    position,
                    factor_snapshot=factor_snapshot,
                    previous_factor_snapshot=previous_factor_snapshot,
                    intent_action='EXIT',
                )
                if not exit_result:
                    hold_diag = self._with_factor_diagnostics({'exit': exit_diag})
        else:
            entry_conditions = rule.get('entry', {}).get('conditions', {}) if isinstance(rule.get('entry'), dict) else {}
            if self._condition_uses_factor(entry_conditions):
                entry_result, entry_diag = self.condition_eval.evaluate(
                    entry_conditions,
                    bars,
                    None,
                    factor_snapshot=factor_snapshot,
                    previous_factor_snapshot=previous_factor_snapshot,
                    intent_action='BUY',
                )
                if not entry_result:
                    hold_diag = self._with_factor_diagnostics({'entry': entry_diag})

        return RuleSignal(
            rule_id=rule_id,
            symbol=symbol,
            market=market,
            action='HOLD',
            order_type='LMT',
            score=0,
            reason='no_condition_met',
            priority=priority,
            stop_loss=None,
            take_profit=None,
            last_close=last_close,
            diagnostics=hold_diag,
            base_rule_id=base_rule_id,
            primary_rule_id=str(rule_id),
            source_rule_ids=[str(rule_id)],
            symbol_profile=symbol_profile,
            effective_config_hash=effective_config_hash,
            effective_config_hashes=[effective_config_hash] if effective_config_hash else [],
            overrides_applied=overrides_applied,
        )
    
    def _get_min_bars_required(self, rule: dict[str, Any]) -> int:
        """计算规则所需的最少 K 线数量"""
        max_period = 0  # 从0开始，由实际指标周期决定
        
        def scan_periods(conditions: dict[str, Any]):
            nonlocal max_period
            
            if conditions.get('indicator') == 'factor':
                return

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

    def _with_factor_diagnostics(self, diagnostics: dict[str, Any]) -> dict[str, Any]:
        payload = json.loads(json.dumps(diagnostics))
        factor_diags = self._collect_factor_diags(payload)
        if not factor_diags:
            return payload

        used_factors: list[str] = []
        factor_values: dict[str, Any] = {}
        factor_readiness: dict[str, bool] = {}
        for diag in factor_diags:
            factor_id = diag.get('factor_id')
            if not factor_id:
                continue
            if factor_id not in used_factors:
                used_factors.append(str(factor_id))
            factor_values[str(factor_id)] = diag.get('value')
            factor_readiness[str(factor_id)] = bool(diag.get('ready'))

        payload['used_factors'] = used_factors
        payload['factor_values'] = factor_values
        payload['factor_readiness'] = factor_readiness
        return payload

    def _collect_factor_diags(self, payload: Any) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            factor_id = payload.get('factor_id') or payload.get('binding_factor_id')
            if factor_id and (
                payload.get('indicator') == 'factor'
                or payload.get('binding_kind') == 'factor_condition'
                or payload.get('fallback_from_factor')
            ):
                factor_diag = dict(payload)
                factor_diag['factor_id'] = factor_id
                items.append(factor_diag)
            for key, value in payload.items():
                if key in {'used_factors', 'factor_values', 'factor_readiness'}:
                    continue
                items.extend(self._collect_factor_diags(value))
        elif isinstance(payload, list):
            for value in payload:
                items.extend(self._collect_factor_diags(value))
        return items

    def _condition_uses_factor(self, condition: Any) -> bool:
        if not isinstance(condition, dict):
            return False
        view = normalize_condition_to_factor_binding_view(
            condition,
            factor_accessor=self.condition_eval.factor_only_accessor,
        )
        if view.kind == "factor_condition":
            return True
        items = condition.get("items")
        if isinstance(items, list):
            return any(self._condition_uses_factor(item) for item in items)
        return False
