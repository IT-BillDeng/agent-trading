# Tiger Rule Engine Schema v1

> 目标：将策略逻辑参数化，Strategist 改配置 = 改策略，零重启

## 1. 设计原则

1. **声明式配置**：规则用 JSON 描述，不写代码
2. **组合式条件**：支持 AND/OR 逻辑组合
3. **指标驱动**：条件基于技术指标计算结果
4. **独立 timeframe**：每条规则可指定自己的评估周期
5. **热更新**：配置文件变更自动生效

## 2. 规则配置文件结构

### 2.1 顶层结构

```json
{
  "version": "1.0",
  "updated_at": "2026-04-07T04:00:00+08:00",
  "rules": [...],
  "global_settings": {...}
}
```

### 2.2 规则定义

```json
{
  "rule_id": "trend_follow_30m",
  "name": "30分钟趋势跟随",
  "enabled": true,
  "priority": 1,
  "timeframe": "30min",
  "symbols": ["*"],  // "*" 表示所有标的，或指定 ["AAPL", "MSFT"]
  "markets": ["US", "HK"],
  
  "entry": {
    "conditions": {
      "operator": "AND",
      "items": [
        {
          "type": "indicator",
          "indicator": "sma",
          "params": {"period": 5},
          "compare": {
            "field": "close",
            "operator": "above"
          }
        },
        {
          "type": "indicator",
          "indicator": "sma",
          "params": {"period": 5},
          "compare": {
            "field": "sma",
            "params": {"period": 10},
            "operator": "above"
          }
        }
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
        {
          "type": "indicator",
          "indicator": "sma",
          "params": {"period": 5},
          "compare": {
            "field": "close",
            "operator": "below"
          }
        },
        {
          "type": "stop_loss",
          "threshold_pct": 0.03
        },
        {
          "type": "take_profit",
          "threshold_pct": 0.06
        }
      ]
    },
    "action": "EXIT",
    "order_type": "MKT"
  }
}
```

## 3. 条件类型

### 3.1 指标条件

基于技术指标的比较：

```json
{
  "type": "indicator",
  "indicator": "sma",
  "params": {"period": 5},
  "compare": {
    "field": "close",           // 与收盘价比较
    // 或与其他指标比较：
    // "indicator": "sma",
    // "params": {"period": 10},
    "operator": "above"         // above / below / equal / cross_above / cross_below
  },
  "threshold": null             // 可选：与固定值比较
}
```

支持的指标：
- `sma` - 简单移动平均
- `ema` - 指数移动平均
- `rsi` - 相对强弱指数
- `bollinger` - 布林带（upper/middle/lower）
- `macd` - MACD（macd/signal/histogram）
- `atr` - 平均真实波幅
- `momentum` - 动量
- `volume_ratio` - 量比

### 3.2 价格条件

```json
{
  "type": "price",
  "field": "close",
  "operator": "above",
  "value": 100.0
}
```

### 3.3 成交量条件

```json
{
  "type": "volume",
  "operator": "above_avg",
  "ratio": 1.5
}
```

### 3.4 止损/止盈条件

```json
{
  "type": "stop_loss",
  "threshold_pct": 0.03
}
```

```json
{
  "type": "take_profit",
  "threshold_pct": 0.06
}
```

### 3.5 时间条件

```json
{
  "type": "time",
  "operator": "before_close",
  "minutes": 15
}
```

## 4. 逻辑组合

### 4.1 AND 组合

所有子条件必须同时满足：

```json
{
  "operator": "AND",
  "items": [condition1, condition2, ...]
}
```

### 4.2 OR 组合

任一子条件满足即可：

```json
{
  "operator": "OR",
  "items": [condition1, condition2, ...]
}
```

### 4.3 嵌套组合

```json
{
  "operator": "AND",
  "items": [
    condition1,
    {
      "operator": "OR",
      "items": [condition2, condition3]
    }
  ]
}
```

## 5. 默认规则（等价当前硬编码策略）

```json
{
  "version": "1.0",
  "updated_at": "2026-04-07T04:00:00+08:00",
  "rules": [
    {
      "rule_id": "trend_follow_30m",
      "name": "30分钟趋势跟随",
      "enabled": true,
      "priority": 1,
      "timeframe": "30min",
      "symbols": ["*"],
      "markets": ["US", "HK"],
      "entry": {
        "conditions": {
          "operator": "AND",
          "items": [
            {"type": "indicator", "indicator": "sma", "params": {"period": 5}, "compare": {"field": "close", "operator": "above"}},
            {"type": "indicator", "indicator": "sma", "params": {"period": 5}, "compare": {"indicator": "sma", "params": {"period": 10}, "operator": "above"}},
            {"type": "indicator", "indicator": "sma", "params": {"period": 10}, "compare": {"indicator": "sma", "params": {"period": 20}, "operator": "above"}},
            {"type": "indicator", "indicator": "momentum", "params": {"period": 3}, "compare": {"operator": "above", "value": 0.003}},
            {"type": "indicator", "indicator": "bar_range_pct", "compare": {"operator": "below", "value": 0.04}}
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
            {"type": "indicator", "indicator": "sma", "params": {"period": 5}, "compare": {"field": "close", "operator": "below"}},
            {"type": "indicator", "indicator": "sma", "params": {"period": 5}, "compare": {"indicator": "sma", "params": {"period": 10}, "operator": "below"}}
          ]
        },
        "action": "EXIT",
        "order_type": "MKT"
      }
    }
  ],
  "global_settings": {
    "min_score": 4,
    "max_rules_per_symbol": 3,
    "conflict_resolution": "highest_priority"
  }
}
```

## 6. 文件位置

- 规则配置：`/app/config/rules.json`
- 备份目录：`/app/config/rules_backup/`
- 验证 Schema：`/app/specs/rule-schema.json`

## 7. API 端点

### GET /api/rules
获取当前规则配置

### PUT /api/rules
更新规则配置（需验证）

### POST /api/rules/validate
验证规则配置格式

### POST /api/rules/test
测试规则（回测单条规则）

### GET /api/rules/history
获取规则变更历史

## 8. 变更日志

| 日期 | 变更 |
|------|------|
| 2026-04-07 | 初始版本 |
