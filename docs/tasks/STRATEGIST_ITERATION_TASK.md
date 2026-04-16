# Strategist — 自主迭代任务模板

## 核心原则
1. 每次策略变更必须回测验证
2. 新方案必须优于基线才上线
3. 每次尝试都记录到 ./runtime/engine/strategist_iterations/

工作目录：`/workspace/agent-trading/`

## 迭代流程

### Step 1: 读取基线
```bash
# 读取当前规则
curl http://host.docker.internal:8088/api/rules

# 读取最近迭代结果
ls ./runtime/engine/strategist_iterations/
cat ./runtime/engine/strategist_iterations/latest.json
```

### Step 2: 识别问题
分析基线回测结果：
- 交易数太少 → 条件太严格，放宽参数
- 胜率太低 → 入场信号不准确，调整阈值
- 回报为负 → 策略方向错误，换因子
- Sharpe 太低 → 波动太大，增加过滤条件

### Step 3: 生成参数组合
基于搜索空间定义，生成参数组合：

**RSI 均值回归：**
```json
[
  {"label": "rsi_X_tY", "params": {"rsi_period": X, "rsi_oversold": Y}}
]
```

**SMA 趋势跟踪：**
```json
[
  {"label": "sma_X_Y_Z", "params": {"sma_short": X, "sma_mid": Y, "sma_long": Z, "momentum_threshold": M}}
]
```

**布林带突破：**
```json
[
  {"label": "bb_X_Y", "params": {"bb_period": X, "bb_std": Y, "volume_ratio": V}}
]
```

### Step 4: 批量回测
```bash
curl -X POST http://host.docker.internal:8088/api/backtest/batch \
  -H "Content-Type: application/json" \
  -d '{
    "symbols": ["AAPL", "NVDA", "MSFT"],
    "start_date": "2026-01-07",
    "end_date": "2026-04-07",
    "param_sets": [...]
  }'
```

### Step 5: 对比基线
| 指标 | 通过条件 |
|------|---------|
| return_pct | 新方案 > 基线 |
| sharpe | 新方案 > 基线 |
| max_drawdown_pct | 新方案 < 基线 |
| win_rate | 新方案 >= 基线 - 5% |

全部满足 → approved = true
任一恶化 → rejected，记录原因

### Step 6: 上线 approved 方案
```bash
# 读取当前规则
# 应用参数覆盖
# PUT 到 /api/rules
curl -X PUT http://host.docker.internal:8088/api/rules \
  -H "Content-Type: application/json" \
  -d '{修改后的 rules}'
```

### Step 7: 记录迭代
迭代结果自动保存到 `./runtime/engine/strategist_iterations/iter_YYYYMMDD_HHMMSS.json`

### Step 8: 通知先生
每次策略调整通知 Telegram，格式：
```
📊 策略迭代结果

迭代: iter_XXX
测试: N 个方案
最优: {label} → {return}% | {trades} 笔 | 胜率 {win_rate}%
状态: approved/rejected
变更: {具体参数变更}
```

## 当前最佳方案（基线）

| 规则 | 参数 | 回报 | 交易数 | 胜率 | Sharpe |
|------|------|------|--------|------|--------|
| rsi_reversal | RSI14, 阈值30 | +0.21% | 24 | 25% | 0.38 |
| bollinger_breakout | BB20, vol=1.5 | +0.21% | 24 | 25% | 0.38 |

## 搜索空间

**RSI 均值回归：**
- period: 7, 10, 14
- oversold: 25, 30, 35, 40
- overbought: 60, 65, 70, 75

**布林带：**
- period: 10, 15, 20
- std_dev: 1.5, 2.0, 2.5
- volume_ratio: 1.0, 1.2, 1.5

**SMA 趋势：**
- sma_short: 2, 3, 5
- sma_mid: 5, 7, 10
- sma_long: 10, 14, 20
- momentum: 0, 0.001, 0.002
