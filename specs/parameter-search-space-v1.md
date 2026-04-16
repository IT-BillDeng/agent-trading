# 参数搜索空间 Schema v1

## 概述

每个规则参数可定义搜索空间（min/max/step），Strategist 用于系统性搜索最优参数。

## 搜索空间定义

在 rules.json 的每个规则中增加 `search_space` 字段：

```json
{
  "rule_id": "trend_follow_30m",
  "search_space": {
    "entry.conditions.items[0].params.period": {"min": 3, "max": 10, "step": 1, "type": "int"},
    "entry.conditions.items[1].params.period": {"min": 5, "max": 20, "step": 5, "type": "int"},
    "entry.conditions.items[2].params.period": {"min": 10, "max": 30, "step": 5, "type": "int"},
    "entry.conditions.items[3].params.period": {"min": 2, "max": 5, "step": 1, "type": "int"},
    "entry.conditions.items[3].compare.value": {"min": 0.001, "max": 0.005, "step": 0.001, "type": "float"},
    "entry.conditions.items[4].compare.value": {"min": 0.02, "max": 0.06, "step": 0.01, "type": "float"}
  }
}
```

## 搜索策略

### 网格搜索（Grid Search）
对每个参数遍历 min→max（step），笛卡尔积产生所有组合。
适合参数少（≤3）的场景。

### 随机搜索（Random Search）
随机采样 N 个组合。适合参数多的场景。

## 安全护栏（硬约束）

任何参数组合必须满足：
- SMA 周期：短 < 中 < 长（不交叉）
- 动量阈值：> 0
- 波动率阈值：> 0

## 迭代记录格式

每次搜索结果写入 `artifacts/strategist/iterations/`：

```json
{
  "iteration_id": "iter_20260407_001",
  "rule_id": "trend_follow_30m",
  "timestamp": "ISO-8601",
  "search_type": "grid",
  "total_combinations": 50,
  "tested_combinations": 50,
  "baseline": {
    "return_pct": 0,
    "sharpe": 0,
    "max_drawdown_pct": 0,
    "win_rate": 0,
    "trades": 0
  },
  "best_result": {
    "params": {"SMA_short": 5, "SMA_mid": 10, "SMA_long": 15, "momentum": 0.002, "bar_range": 0.03},
    "return_pct": 2.5,
    "sharpe": 1.2,
    "max_drawdown_pct": -1.5,
    "win_rate": 0.6,
    "trades": 25,
    "approved": true,
    "improvement": "return +2.5%, sharpe +1.2, win_rate +60%"
  },
  "top_5": [...],
  "rejected_reasons": [...]
}
```
