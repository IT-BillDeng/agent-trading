"""Test Rule Engine"""

import json
import tempfile
import unittest
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from engine.rule_engine import RuleEngine, IndicatorCalculator, ConditionEvaluator


def create_test_bars(count=30, trend='up'):
    """Create test bar data"""
    bars = []
    base_price = 100.0
    
    for i in range(count):
        if trend == 'up':
            close = base_price + i * 0.5
        elif trend == 'down':
            close = base_price - i * 0.5
        else:
            close = base_price + (i % 5 - 2) * 0.3
        
        high = close + 0.5
        low = close - 0.5
        volume = 1000000 + i * 10000
        
        bars.append({
            'open': close - 0.2,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
    
    return bars


def test_indicator_calculator():
    """Test indicator calculations"""
    calc = IndicatorCalculator()
    bars = create_test_bars(30, 'up')
    
    # Test SMA
    sma = calc.calculate('sma', {'period': 5}, bars)
    assert sma is not None, "SMA should return a value"
    print(f"✓ SMA(5) = {sma:.2f}")
    
    # Test EMA
    ema = calc.calculate('ema', {'period': 12}, bars)
    assert ema is not None, "EMA should return a value"
    print(f"✓ EMA(12) = {ema:.2f}")

    # Test EMA slope
    ema_slope = calc.calculate('ema_slope', {'period': 8, 'lookback': 3}, bars)
    assert ema_slope is not None, "EMA slope should return a value"
    assert ema_slope > 0, "EMA slope should be positive for uptrend"
    print(f"✓ EMA Slope(8,3) = {ema_slope:.4f}")
    
    # Test RSI
    rsi = calc.calculate('rsi', {'period': 14}, bars)
    assert rsi is not None, "RSI should return a value"
    assert 0 <= rsi <= 100, "RSI should be between 0 and 100"
    print(f"✓ RSI(14) = {rsi:.2f}")
    
    # Test Bollinger
    bollinger = calc.calculate('bollinger', {'period': 20, 'std_dev': 2}, bars)
    assert bollinger is not None, "Bollinger should return a value"
    assert 'upper' in bollinger, "Bollinger should have upper band"
    assert 'lower' in bollinger, "Bollinger should have lower band"
    print(f"✓ Bollinger: upper={bollinger['upper']:.2f}, lower={bollinger['lower']:.2f}")
    
    # Test ATR
    atr = calc.calculate('atr', {'period': 14}, bars)
    assert atr is not None, "ATR should return a value"
    print(f"✓ ATR(14) = {atr:.4f}")
    
    # Test Momentum
    momentum = calc.calculate('momentum', {'period': 3}, bars)
    assert momentum is not None, "Momentum should return a value"
    print(f"✓ Momentum(3) = {momentum:.4f}")
    
    # Test Volume Ratio
    vol_ratio = calc.calculate('volume_ratio', {'period': 20}, bars)
    assert vol_ratio is not None, "Volume ratio should return a value"
    print(f"✓ Volume Ratio = {vol_ratio:.2f}")
    
    print("\n✅ All indicator tests passed!")


def test_condition_evaluator():
    """Test condition evaluation"""
    calc = IndicatorCalculator()
    evaluator = ConditionEvaluator(calc)
    bars = create_test_bars(30, 'up')
    
    # Test indicator condition
    condition = {
        'type': 'indicator',
        'indicator': 'sma',
        'params': {'period': 5},
        'compare': {'field': 'close', 'operator': 'above'}
    }
    result, diag = evaluator.evaluate(condition, bars)
    print(f"✓ Indicator condition: {result}")
    
    # Test AND combination
    and_condition = {
        'operator': 'AND',
        'items': [
            {'type': 'indicator', 'indicator': 'sma', 'params': {'period': 5}, 
             'compare': {'field': 'close', 'operator': 'above'}},
            {'type': 'indicator', 'indicator': 'sma', 'params': {'period': 5}, 
             'compare': {'indicator': 'sma', 'params': {'period': 10}, 'operator': 'above'}}
        ]
    }
    result, diag = evaluator.evaluate(and_condition, bars)
    print(f"✓ AND condition: {result}")
    
    # Test OR combination
    or_condition = {
        'operator': 'OR',
        'items': [
            {'type': 'indicator', 'indicator': 'rsi', 'params': {'period': 14}, 
             'compare': {'operator': 'below', 'value': 30}},
            {'type': 'indicator', 'indicator': 'rsi', 'params': {'period': 14}, 
             'compare': {'operator': 'above', 'value': 70}}
        ]
    }
    result, diag = evaluator.evaluate(or_condition, bars)
    print(f"✓ OR condition: {result}")
    
    print("\n✅ All condition evaluator tests passed!")


def test_rule_engine():
    """Test full rule engine"""
    # Create temporary rules file
    rules_config = {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "test_rule",
                "name": "Test Rule",
                "enabled": True,
                "priority": 1,
                "timeframe": "30min",
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "conditions": {
                        "operator": "AND",
                        "items": [
                            {"type": "indicator", "indicator": "sma", "params": {"period": 5}, 
                             "compare": {"field": "close", "operator": "above"}},
                            {"type": "indicator", "indicator": "sma", "params": {"period": 5}, 
                             "compare": {"indicator": "sma", "params": {"period": 10}, "operator": "above"}}
                        ]
                    },
                    "action": "BUY",
                    "order_type": "LMT",
                    "stop_loss_pct": 0.03,
                    "take_profit_pct": 0.06
                },
                "exit": {
                    "conditions": {
                        "operator": "OR",
                        "items": [
                            {"type": "indicator", "indicator": "sma", "params": {"period": 5}, 
                             "compare": {"field": "close", "operator": "below"}}
                        ]
                    },
                    "action": "EXIT",
                    "order_type": "MKT"
                }
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(rules_config, f)
        rules_path = f.name
    
    try:
        engine = RuleEngine(rules_path)
        bars = create_test_bars(30, 'up')
        
        # Test signal generation
        signals = engine.evaluate_symbol('AAPL', 'US', bars, None)
        assert len(signals) > 0, "Should generate at least one signal"
        
        signal = signals[0]
        print(f"✓ Generated signal: {signal.action} for {signal.symbol}")
        print(f"  Rule ID: {signal.rule_id}")
        print(f"  Score: {signal.score}")
        print(f"  Reason: {signal.reason}")
        
        # Test with position
        position = {'avg_cost': 95.0, 'quantity': 100}
        signals = engine.evaluate_symbol('AAPL', 'US', bars, position)
        print(f"✓ With position: {len(signals)} signals")
        
        print("\n✅ Rule engine tests passed!")
        
    finally:
        Path(rules_path).unlink()


def test_rule_engine_supports_ema_slope_momentum_strategy():
    rules_config = {
        "version": "1.0",
        "rules": [
            {
                "rule_id": "ema_slope_momentum",
                "name": "EMA Slope Momentum",
                "enabled": True,
                "priority": 1,
                "timeframe": "30min",
                "symbols": ["*"],
                "markets": ["US"],
                "entry": {
                    "conditions": {
                        "operator": "AND",
                        "items": [
                            {
                                "type": "indicator",
                                "indicator": "ema_slope",
                                "params": {"period": 8, "lookback": 3},
                                "compare": {"operator": "above", "value": 0.002},
                            },
                            {
                                "type": "indicator",
                                "indicator": "momentum",
                                "params": {"period": 3},
                                "compare": {"operator": "above", "value": 0.01},
                            },
                            {
                                "type": "indicator",
                                "indicator": "bar_range_pct",
                                "compare": {"operator": "below", "value": 0.02},
                            },
                        ],
                    },
                    "action": "BUY",
                    "order_type": "LMT",
                    "stop_loss_pct": 0.025,
                    "take_profit_pct": 0.05,
                },
                "exit": {
                    "conditions": {
                        "operator": "OR",
                        "items": [
                            {
                                "type": "indicator",
                                "indicator": "ema_slope",
                                "params": {"period": 8, "lookback": 3},
                                "compare": {"operator": "below", "value": 0.0},
                            }
                        ],
                    },
                    "action": "EXIT",
                    "order_type": "MKT",
                },
            }
        ],
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(rules_config, f)
        rules_path = f.name

    try:
        engine = RuleEngine(rules_path)
        bars = create_test_bars(30, 'up')
        signals = engine.evaluate_symbol('AAPL', 'US', bars, None)
        assert len(signals) == 1
        signal = signals[0]
        assert signal.rule_id == 'ema_slope_momentum'
        assert signal.action == 'BUY'
        assert signal.reason == 'entry_condition_met'
    finally:
        Path(rules_path).unlink()


def test_rsi_reversal_rule_uses_real_cross_logic_and_can_trigger_once():
    rules_path = Path(__file__).resolve().parents[3] / 'rules' / 'rules.json'
    engine = RuleEngine(rules_path)

    closes = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 86, 87, 91]
    bars = [
        {
            'open': close,
            'high': close + 0.5,
            'low': close - 0.5,
            'close': close,
            'volume': 1000000,
        }
        for close in closes
    ]

    signals = engine.evaluate_symbol('AAPL', 'US', bars, None)
    signal = next((item for item in signals if item.rule_id == 'rsi_reversal'), None)

    assert signal is not None, "rsi_reversal should be present in enabled rules"
    assert signal.action == 'BUY', f"expected BUY, got {signal.action}"
    cross_diag = signal.diagnostics['entry']['diagnostics'][0]
    assert cross_diag['operator'] == 'cross_above'
    assert cross_diag['prev_value'] <= 30
    assert cross_diag['value'] > 30


def test_rsi_reversal_rule_does_not_trigger_without_cross():
    rules_path = Path(__file__).resolve().parents[3] / 'rules' / 'rules.json'
    engine = RuleEngine(rules_path)

    closes = [100, 99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 86, 87, 88]
    bars = [
        {
            'open': close,
            'high': close + 0.5,
            'low': close - 0.5,
            'close': close,
            'volume': 1000000,
        }
        for close in closes
    ]

    signals = engine.evaluate_symbol('AAPL', 'US', bars, None)
    signal = next((item for item in signals if item.rule_id == 'rsi_reversal'), None)

    assert signal is not None, "rsi_reversal should be present in enabled rules"
    assert signal.action != 'BUY', "rsi_reversal should not trigger without a true cross"


class RuleEngineUnittestBridge(unittest.TestCase):
    def test_indicator_calculator_bridge(self):
        test_indicator_calculator()

    def test_ema_slope_strategy_bridge(self):
        test_rule_engine_supports_ema_slope_momentum_strategy()

    def test_rsi_reversal_cross_bridge(self):
        test_rsi_reversal_rule_uses_real_cross_logic_and_can_trigger_once()

    def test_rsi_reversal_non_cross_bridge(self):
        test_rsi_reversal_rule_does_not_trigger_without_cross()


class _FakeCrossIndicatorCalculator:
    def __init__(self, mapping):
        self.mapping = mapping

    def calculate(self, indicator, params, bars):
        return self.mapping.get((indicator, len(bars)))


class ConditionEvaluatorCrossTests(unittest.TestCase):
    def _bars(self, closes):
        return [
            {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1000}
            for close in closes
        ]

    def test_cross_above_threshold_uses_previous_and_current_value(self):
        evaluator = ConditionEvaluator(
            _FakeCrossIndicatorCalculator({
                ("rsi", 2): 31.0,
                ("rsi", 1): 29.0,
            })
        )
        condition = {
            "type": "indicator",
            "indicator": "rsi",
            "params": {"period": 14},
            "compare": {"operator": "cross_above", "value": 30},
        }

        result, diag = evaluator.evaluate(condition, self._bars([100, 101]))

        self.assertTrue(result)
        self.assertEqual(diag["prev_value"], 29.0)
        self.assertEqual(diag["compare_value"], 30)
        self.assertEqual(diag["prev_compare_value"], 30)

    def test_cross_above_threshold_requires_actual_cross(self):
        evaluator = ConditionEvaluator(
            _FakeCrossIndicatorCalculator({
                ("rsi", 2): 32.0,
                ("rsi", 1): 31.0,
            })
        )
        condition = {
            "type": "indicator",
            "indicator": "rsi",
            "params": {"period": 14},
            "compare": {"operator": "cross_above", "value": 30},
        }

        result, diag = evaluator.evaluate(condition, self._bars([100, 101]))

        self.assertFalse(result)
        self.assertEqual(diag["prev_value"], 31.0)
        self.assertEqual(diag["value"], 32.0)

    def test_cross_below_threshold_uses_previous_and_current_value(self):
        evaluator = ConditionEvaluator(
            _FakeCrossIndicatorCalculator({
                ("rsi", 2): 29.0,
                ("rsi", 1): 31.0,
            })
        )
        condition = {
            "type": "indicator",
            "indicator": "rsi",
            "params": {"period": 14},
            "compare": {"operator": "cross_below", "value": 30},
        }

        result, diag = evaluator.evaluate(condition, self._bars([100, 99]))

        self.assertTrue(result)
        self.assertEqual(diag["prev_value"], 31.0)
        self.assertEqual(diag["value"], 29.0)

    def test_cross_with_compare_indicator_uses_previous_values(self):
        evaluator = ConditionEvaluator(
            _FakeCrossIndicatorCalculator({
                ("ema_fast", 2): 101.0,
                ("ema_fast", 1): 99.0,
                ("ema_slow", 2): 100.0,
                ("ema_slow", 1): 100.0,
            })
        )
        condition = {
            "type": "indicator",
            "indicator": "ema_fast",
            "params": {"period": 5},
            "compare": {
                "operator": "cross_above",
                "indicator": "ema_slow",
                "params": {"period": 10},
            },
        }

        result, diag = evaluator.evaluate(condition, self._bars([100, 101]))

        self.assertTrue(result)
        self.assertEqual(diag["prev_value"], 99.0)
        self.assertEqual(diag["prev_compare_value"], 100.0)
        self.assertEqual(diag["value"], 101.0)
        self.assertEqual(diag["compare_value"], 100.0)

    def test_cross_returns_false_with_insufficient_previous_indicator_data(self):
        evaluator = ConditionEvaluator(
            _FakeCrossIndicatorCalculator({
                ("rsi", 2): 31.0,
                ("rsi", 1): None,
            })
        )
        condition = {
            "type": "indicator",
            "indicator": "rsi",
            "params": {"period": 14},
            "compare": {"operator": "cross_above", "value": 30},
        }

        result, diag = evaluator.evaluate(condition, self._bars([100, 101]))

        self.assertFalse(result)
        self.assertEqual(diag["reason"], "insufficient_data_for_cross")

    def test_stop_loss_and_take_profit_support_broker_avg_cost_aliases(self):
        evaluator = ConditionEvaluator(IndicatorCalculator())
        stop_loss_condition = {"type": "stop_loss", "threshold_pct": 0.03}
        take_profit_condition = {"type": "take_profit", "threshold_pct": 0.06}
        alias_positions = [
            {"averageCost": 100.0, "quantity": 10},
            {"avgCost": 100.0, "quantity": 10},
            {"average_cost": 100.0, "quantity": 10},
            {"costPrice": 100.0, "quantity": 10},
        ]

        stop_bars = [{"close": 95.0}]
        profit_bars = [{"close": 107.0}]

        for position in alias_positions:
            stop_result, stop_diag = evaluator.evaluate(stop_loss_condition, stop_bars, position)
            profit_result, profit_diag = evaluator.evaluate(take_profit_condition, profit_bars, position)

            self.assertTrue(stop_result)
            self.assertEqual(stop_diag["entry_price"], 100.0)
            self.assertTrue(profit_result)
            self.assertEqual(profit_diag["entry_price"], 100.0)


if __name__ == '__main__':
    print("Running Rule Engine Tests...\n")
    print("=" * 50)
    
    print("\n1. Testing Indicator Calculator")
    print("-" * 50)
    test_indicator_calculator()
    
    print("\n2. Testing Condition Evaluator")
    print("-" * 50)
    test_condition_evaluator()
    
    print("\n3. Testing Rule Engine")
    print("-" * 50)
    test_rule_engine()
    
    print("\n" + "=" * 50)
    print("🎉 All tests completed successfully!")
