# Strategist 输出 Schema v1

## 概述

Strategist 每次运行产出 `artifacts/strategist/strategy_plan_latest.json`，并追加到 `artifacts/strategist/strategy_plan_history.jsonl`。
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
        "baseline_fee_drag_pct": 0.18,
        "new_fee_drag_pct": 0.14,
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
  "fee_model_confidence": {
    "level": "high | observe | low",
    "label": "可信 | 观察 | 不可信",
    "reason": "一句话说明当前静态手续费模型可信度"
  },
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
        "baseline_fee_drag_pct": 0.22,
        "new_fee_drag_pct": 0.17,
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
  },
  "fee_model_confidence": {
    "level": "high | observe | low",
    "label": "可信 | 观察 | 不可信",
    "reason": "根据 fee_calibration_summary 对静态净收益可信度的判断"
  }
}
```

`learning_log` 在语义上属于 strategist 的长期产物集合，建议配合 [docs/strategist-memory-contract.md](../docs/strategist-memory-contract.md) 一起使用。
实际落点建议统一收进 `artifacts/strategist/`，记录可复用的经验、拒绝原因与后续假设，而不是临时备注或原始聊天全文。

## 输出文件路径

```
artifacts/strategist/
├── strategy_plan_latest.json       # 最新一次运行结果
├── strategy_plan_history.jsonl     # 历史追加
├── memory/
│   ├── latest.json
│   └── history.jsonl
├── proposals.jsonl
├── rejections.jsonl
└── iterations/
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
对比基线净绩效（return、sharpe、max_drawdown、win_rate、fee_drag）
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
| fee_drag_pct | 新方案 ≤ 基线 |

全部满足才 approved = true。任一指标恶化超过阈值则拒绝。

## 手续费模型可信度

Strategist 在盘后分析时应读取 `artifacts/broker/fee_calibration_summary.json`，并在计划输出中写入 `fee_model_confidence`：

- `high / 可信`：近期真实费用偏差可接受，可正常参考静态净收益结果
- `observe / 观察`：近期记录不足或偏差中等，需要保守解读净收益改进
- `low / 不可信`：近期偏差较大，不应仅凭静态净收益做大幅参数调整
