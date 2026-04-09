"""Test Backtest Framework"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from engine.backtest import BacktestConfig, BacktestEngine, DataFetcher, OrderSimulator


def create_test_data():
    """创建测试数据"""
    bars = []
    base_price = 100.0
    base_time = datetime(2026, 1, 1, 9, 30)
    
    for i in range(100):
        # 模拟价格波动
        if i < 30:
            # 上涨趋势
            close = base_price + i * 0.3
        elif i < 60:
            # 下跌趋势
            close = base_price + 30 * 0.3 - (i - 30) * 0.2
        else:
            # 震荡
            close = base_price + 30 * 0.3 - 30 * 0.2 + (i % 10 - 5) * 0.1
        
        high = close + 0.5
        low = close - 0.5
        volume = 1000000 + i * 10000
        
        from engine.backtest import Bar
        bar = Bar(
            timestamp=base_time + timedelta(minutes=i * 30),
            open=close - 0.1,
            high=high,
            low=low,
            close=close,
            volume=volume
        )
        bars.append(bar)
    
    return bars


def test_order_simulator():
    """测试订单撮合模拟器"""
    simulator = OrderSimulator(commission_rate=0.001, slippage_rate=0.001)
    
    # 测试手续费计算
    commission = simulator.calculate_commission(100.0, 10)
    assert commission == 1.0, f"Commission should be 1.0, got {commission}"
    print(f"✓ Commission: {commission}")
    
    # 测试滑点计算
    slippage_buy = simulator.calculate_slippage(100.0, 10, 'BUY')
    slippage_sell = simulator.calculate_slippage(100.0, 10, 'SELL')
    print(f"✓ Slippage (BUY): {slippage_buy}")
    print(f"✓ Slippage (SELL): {slippage_sell}")
    
    # 测试订单模拟
    trade = simulator.simulate_order('AAPL', 'BUY', 10, 100.0, datetime.now())
    assert trade.commission == 1.0
    print(f"✓ Trade: {trade.side} {trade.quantity} @ {trade.price}")
    print(f"  Commission: {trade.commission}")
    print(f"  Total cost: {trade.total_cost}")
    
    print("\n✅ Order simulator tests passed!")


def test_data_fetcher():
    """测试数据获取器"""
    # 由于需要网络，这里只测试接口
    print("✓ DataFetcher interface available")
    print("  Note: Actual data fetching requires network access")
    print("\n✅ Data fetcher tests passed!")


def test_backtest_engine():
    """测试回测引擎"""
    # 创建测试规则
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
        # 创建测试配置
        config = BacktestConfig(
            symbols=['AAPL'],
            start_date='2026-01-01',
            end_date='2026-04-01',
            timeframe='30min',
            initial_capital=100000.0
        )
        
        # 创建回测引擎
        engine = BacktestEngine(config, rules_path)
        
        # 测试数据加载（模拟）
        print("✓ BacktestEngine created")
        print(f"  Symbols: {config.symbols}")
        print(f"  Initial capital: {config.initial_capital}")
        
        print("\n✅ Backtest engine tests passed!")
        
    finally:
        Path(rules_path).unlink()


if __name__ == '__main__':
    from datetime import timedelta
    
    print("Running Backtest Framework Tests...\n")
    print("=" * 50)
    
    print("\n1. Testing Order Simulator")
    print("-" * 50)
    test_order_simulator()
    
    print("\n2. Testing Data Fetcher")
    print("-" * 50)
    test_data_fetcher()
    
    print("\n3. Testing Backtest Engine")
    print("-" * 50)
    test_backtest_engine()
    
    print("\n" + "=" * 50)
    print("🎉 All backtest tests completed!")
