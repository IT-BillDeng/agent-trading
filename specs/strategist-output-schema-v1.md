# Tiger Strategist 输出 Schema v1

## 概述

Strategist 每次运行产出 `strategy_plan_latest.json`，追加到 `strategy_plan_history.jsonl`。
消费方：Executor agent、Dashboard 策略面板、回测框架。

## 三班输出结构

### 盘前输出 (09:00 ET)

```json
{
  "generated_at": "ISO-8601",
  "shift": "premarket",
  "type": "daily_setup",
  "summary": "一句话结论",
  "yesterday_review": {
    "cycle_count": 10,
    "signal_count": 6,
    "buy_signals": 2,
    "exit_signals": 1,
    "hold_signals": 3,
    "signal_accuracy": "基于实际 PnL 评估",
    "issues": ["问题1", "问题2"]
  },
  "today_adjustments": [
    {
      "rule_id": "trend_follow_30m",
      "action": "adjust | enable | disable",
      "changes": {
        "entry.conditions.rsi_threshold": {"from": 70, "to": 65},
        "reason": "昨日 RSI 过高导致漏掉 2 次入场机会"
      },
      "backtest": {
        "ran": true,
        "baseline_return_pct": 2.5,
        "new_return_pct": 3.1,
        "improvement_pct": 24,
        "approved": true
      }
    }
  ],
  "focus_symbols": [
    {
      "symbol": "AAPL",
      "reason": "MacBook Neo 首发售罄 + BofA 目标价 $320",
      "news_importance": "medium",
      "action": "watch | prepare_buy | avoid"
    }
  ],
  "risk_notes": ["今日 CPI 公布，建议盘中暂停高风险规则"],
  "rules_snapshot": "当前 rules.json 的 hash，用于追踪变更"
}
```

### 盘中输出 (q15min)

```json
{
  "generated_at": "ISO-8601",
  "shift": "intraday",
  "type": "monitor",
  "summary": "一句话结论",
  "alerts": [
    {
      "symbol": "NVDA",
      "type": "volatility_spike | news_catalyst | volume_anomaly",
      "severity": "pause | resume | info",
      "action": "pause_rule: trend_follow_30m",
      "reason": "NVDA 波动率突增 3x，暂停趋势跟踪规则"
    }
  ],
  "market_status": {
    "spy_chg_pct": -0.5,
    "sentiment": "fear | neutral | greed",
    "vix_level": null
  },
  "actions_taken": ["暂停 trend_follow_30m 对 NVDA"],
  "actions_pending": []
}
```

### 盘后输出 (16:30 ET)

```json
{
  "generated_at": "ISO-8601",
  "shift": "afterhours",
  "type": "analysis",
  "summary": "一句话结论",
  "signal_quality": {
    "total_signals": 12,
    "buy_signals": 3,
    "exit_signals": 2,
    "false_signals": 1,
    "missed_opportunities": 2,
    "win_rate": "67%",
    "avg_pnl_pct": 0.8
  },
  "tomorrow_proposals": [
    {
      "proposal_id": "prop_20260407_01",
      "description": "调整 RSI 超卖阈值从 30 到 35",
      "target_rule": "rsi_reversal",
      "changes": {"exit.conditions.rsi_oversold": {"from": 30, "to": 35}},
      "reason": "今日 2 次过早出场，RSI 35 以下的反转会更早止盈",
      "backtest": {
        "period": "2026-03-01 to 2026-04-07",
        "symbols": ["AAPL", "MSFT", "NVDA"],
        "baseline_return_pct": 3.2,
        "new_return_pct": 3.8,
        "baseline_sharpe": 1.1,
        "new_sharpe": 1.3,
        "max_drawdown_pct": -2.1,
        "win_rate": "71%",
        "approved": true
      }
    }
  ],
  "proposals_rejected": [
    {
      "proposal_id": "prop_20260406_03",
      "reason": "回测 Sharpe 从 1.2 降至 0.9，收益增加但风险增加更多"
    }
  ],
  "learning_log": {
    "insight": "NVDA 在 GTC 期间波动率异常，此类事件应触发规则暂停而非参数调整",
    "action": "新增规则：当 news_importance=high 时自动暂停 trend_follow"
  }
}
```

## 输出文件路径

```
runtime/engine/
├── strategy_plan_latest.json       # 最新一次运行结果
├── strategy_plan_history.jsonl     # 历史追加
└── strategist_iterations/
    ├── prop_20260407_01_backtest.json  # 提案回测结果
    └── prop_20260407_02_backtest.json
```

## 回测验证流程

```
Strategist 提出变更提案
    ↓
组装 BacktestConfig（标的、时间窗口、新参数）
    ↓
调用 /api/backtest 执行回测
    ↓
对比基线绩效（return、sharpe、max_drawdown、win_rate）
    ↓
approved = true  → 写入 rules.json，记录到 history
approved = false → 记录拒绝原因，保留回测数据
```

## 基线对比规则

| 指标 | 通过条件 |
|------|---------|
| total_return_pct | 新方案 ≥ 基线 |
| sharpe_ratio | 新方案 ≥ 基线 |
| max_drawdown_pct | 新方案 ≤ 基线（绝对值） |
| win_rate | 新方案 ≥ 基线 - 5% |

全部满足才 approved = true。任一指标恶化超过阈值则拒绝。
