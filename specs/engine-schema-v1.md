# Tiger Engine Schema v1

> 目标：为 watcher / newswire / strategist / Operator review / executor / closer 建立统一的数据契约。
> 原则：结构化优先、可追踪、可审计、可扩展到更高频和多周期。

---

## 1. 设计原则

统一遵循以下规则：

1. 每类对象都有唯一 id
2. 每条记录都有时间字段（`generated_at` / `created_at`）
3. `latest.json` 存当前快照，`history.jsonl` 存历史记录
4. 跨岗位交接尽量传 id，不复制整块文本
5. 先结构化字段，再附带简短自然语言摘要
6. 执行相关对象都必须可追溯到 signal / review / task

---

## 2. 推荐目录结构

```text
runtime/engine/
  watcher/
    latest.json
    history.jsonl
  newswire/
    latest.json
    history.jsonl
  strategist/
    latest_signal.json
    signals.jsonl
  decision/
    latest_decision.json
    decisions.jsonl
  executor/
    latest_task.json
    tasks.jsonl
    latest_result.json
    results.jsonl
  closer/
    us_latest.json
    history.jsonl
  state/
    control_state.json
    execution_state.json
```

---

## 3. watcher schema

### 用途
记录行情观察、异常、状态变化，不直接做最终交易决策。

### 文件
- `runtime/engine/watcher/latest.json`
- `runtime/engine/watcher/history.jsonl`

### 推荐结构

```json
{
  "watch_id": "watch_20260313_093000_001",
  "generated_at": "2026-03-13T09:30:00+08:00",
  "market_session": "US_REGULAR",
  "window": "5m",
  "universe_version": "watchlist_20260313_v1",
  "symbols": [
    {
      "symbol": "MSFT",
      "last_price": 412.3,
      "change_pct": 1.8,
      "volume_ratio": 1.6,
      "volatility_score": 0.72,
      "watch_flags": ["breakout_candidate", "volume_spike"],
      "signal_relevance": "high",
      "state_change": {
        "changed": true,
        "previous_flags": ["near_breakout"],
        "current_flags": ["breakout_candidate", "volume_spike"]
      },
      "note": "price near intraday high"
    }
  ],
  "summary": {
    "hot_symbols": ["MSFT", "NVDA"],
    "risk_flags": ["broad_market_weak"],
    "market_regime": "risk_on"
  }
}
```

### 必填字段
- `watch_id`
- `generated_at`
- `market_session`
- `window`
- `symbols[]`
- `summary`

---

## 4. newswire schema

### 用途
收集新闻与催化，形成结构化情报输入，不直接给最终交易结论。

### 文件
- `runtime/engine/newswire/latest.json`
- `runtime/engine/newswire/history.jsonl`

### 推荐结构

```json
{
  "news_batch_id": "news_20260313_100000_intraday",
  "generated_at": "2026-03-13T10:00:00+08:00",
  "window": "intraday_30m",
  "market_session": "US_REGULAR",
  "items": [
    {
      "news_id": "news_nvda_20260313_0942_partnership",
      "symbol": "NVDA",
      "headline": "NVIDIA expands partnership ...",
      "source": "Yahoo Finance",
      "url": "https://example.com",
      "published_at": "2026-03-13T09:42:00+08:00",
      "priority": "high",
      "sentiment": "positive",
      "relevance_score": 0.87,
      "tags": ["ai", "partnership", "catalyst"],
      "brief": "Potential demand catalyst for AI server chain.",
      "dedupe_key": "nvda_partnership_20260313"
    }
  ],
  "summary": {
    "high_priority_symbols": ["NVDA"],
    "market_risks": ["macro_rate_headline"]
  }
}
```

### 必填字段
- `news_batch_id`
- `generated_at`
- `window`
- `items[].news_id`
- `items[].symbol`
- `items[].source`
- `items[].published_at`
- `items[].priority`
- `items[].dedupe_key`

---

## 5. strategist signal schema

### 用途
融合 watcher / newswire / 历史与策略规则，产出候选交易信号。

### 文件
- `runtime/engine/strategist/latest_signal.json`
- `runtime/engine/strategist/signals.jsonl`

### 推荐结构

```json
{
  "signal_id": "sig_20260313_msft_breakout_001",
  "generated_at": "2026-03-13T10:05:00+08:00",
  "symbol": "MSFT",
  "action": "BUY",
  "priority": "high",
  "confidence": 0.74,
  "timeframe": "intraday",
  "strategy_family": "breakout_momentum",
  "trigger_context": {
    "watch_ids": ["watch_20260313_100000_001"],
    "news_batch_ids": ["news_20260313_100000_intraday"]
  },
  "thesis": [
    "price breakout with relative volume expansion",
    "positive catalyst in recent news flow",
    "broad market regime acceptable"
  ],
  "risk_points": [
    "near resistance extension risk",
    "macro event later today"
  ],
  "invalidation": [
    "fall back below breakout level",
    "volume confirmation disappears"
  ],
  "suggested_execution": {
    "order_type": "limit",
    "entry_zone": [409.8, 410.5],
    "stop_zone": [404.5, 405.0],
    "take_profit_zone": [418.0, 421.0],
    "max_holding_horizon": "intraday"
  },
  "requires_operator_review": true,
  "summary_text": "MSFT breakout candidate with news support."
}
```

### 必填字段
- `signal_id`
- `generated_at`
- `symbol`
- `action`
- `priority`
- `confidence`
- `trigger_context`
- `thesis`
- `risk_points`
- `requires_operator_review`

### 说明
- strategist 只产出候选信号
- 不直接调用 executor
- 必须经过 Operator review

---

## 6. decision schema

### 用途
对 strategist 信号做二次裁决，决定是否进入执行阶段。

### 文件
- `runtime/engine/decision/latest_decision.json`
- `runtime/engine/decision/decisions.jsonl`

### 推荐结构

```json
{
  "decision_id": "decision_20260313_100700_001",
  "generated_at": "2026-03-13T10:07:00+08:00",
  "signal_id": "sig_20260313_msft_breakout_001",
  "symbol": "MSFT",
  "decision": "approved",
  "decision_confidence": 0.78,
  "reason_codes": [
    "signal_supported_by_market_context",
    "risk_within_limits",
    "session_valid"
  ],
  "decision_notes": [
    "news support is useful but not sole basis",
    "prefer limit entry rather than market order"
  ],
  "constraints": {
    "submit_mode": "guarded",
    "max_qty": 5,
    "must_use_limit_order": true
  },
  "followup": {
    "create_executor_task": true,
    "wake_executor": true
  }
}
```

### decision 枚举建议
- `approved`
- `rejected`
- `deferred`
- `needs_human_confirmation`

### 必填字段
- `decision_id`
- `signal_id`
- `decision`
- `reason_codes`
- `constraints`

---

## 7. executor task schema

### 用途
把 Operator 的审核结果转换成明确执行任务。

### 文件
- `runtime/engine/executor/latest_task.json`
- `runtime/engine/executor/tasks.jsonl`

### 推荐结构

```json
{
  "task_id": "exec_task_20260313_001",
  "created_at": "2026-03-13T10:08:00+08:00",
  "decision_id": "decision_20260313_100700_001",
  "signal_id": "sig_20260313_msft_breakout_001",
  "symbol": "MSFT",
  "action": "BUY",
  "execution_plan": {
    "order_type": "limit",
    "qty": 5,
    "limit_price": 410.2,
    "time_in_force": "DAY"
  },
  "risk_constraints": {
    "submit_mode": "guarded",
    "must_pass_preview": true,
    "cancel_if_rejected": true
  },
  "status": "pending"
}
```

### 必填字段
- `task_id`
- `decision_id`
- `signal_id`
- `symbol`
- `action`
- `execution_plan`
- `status`

---

## 8. executor result schema

### 用途
记录实际执行结果，无论成功失败都必须写入。

### 文件
- `runtime/engine/executor/latest_result.json`
- `runtime/engine/executor/results.jsonl`

### 推荐结构

```json
{
  "result_id": "exec_result_20260313_001",
  "generated_at": "2026-03-13T10:08:20+08:00",
  "task_id": "exec_task_20260313_001",
  "decision_id": "decision_20260313_100700_001",
  "signal_id": "sig_20260313_msft_breakout_001",
  "symbol": "MSFT",
  "status": "preview_blocked",
  "broker_response": {
    "order_id": null,
    "preview_passed": false,
    "error_code": "BUYING_POWER_LIMIT",
    "error_message": "insufficient buying power"
  },
  "execution_summary": {
    "submitted": false,
    "filled_qty": 0,
    "avg_fill_price": null
  },
  "next_action": "return_to_operator"
}
```

### status 枚举建议
- `preview_blocked`
- `submitted`
- `partially_filled`
- `filled`
- `cancelled`
- `failed`

---

## 9. closer summary schema

### 用途
在 US 收盘后生成总结，再由 Operator 汇总给用户。

### 文件
- `runtime/engine/closer/us_latest.json`
- `runtime/engine/closer/history.jsonl`

### 推荐结构

```json
{
  "close_summary_id": "close_us_20260313",
  "generated_at": "2026-03-13T16:12:00-04:00",
  "market": "US",
  "date": "2026-03-13",
  "market_summary": [
    "Nasdaq strong, semis led gains",
    "Broad risk appetite improved into close"
  ],
  "news_summary": [
    "NVDA partnership headline remained main catalyst"
  ],
  "execution_summary": {
    "signals_reviewed": 3,
    "tasks_created": 1,
    "orders_submitted": 0,
    "preview_blocked": 1
  },
  "watchlist_focus_next": ["MSFT", "NVDA"],
  "risk_points_next": ["macro event tomorrow pre-open"],
  "summary_text": "Strong tape, but execution stayed disciplined."
}
```

---

## 10. 事件唤醒建议 schema

### 用途
为 strategist → Operator、Operator → executor 这种非纯 cron 的唤醒链路提供轻量事件对象。

### 推荐结构

```json
{
  "event_id": "event_20260313_100600_001",
  "event_type": "strategist_signal_ready",
  "created_at": "2026-03-13T10:06:00+08:00",
  "priority": "high",
  "refs": {
    "signal_id": "sig_20260313_msft_breakout_001"
  },
  "message": "High-priority strategist signal ready for Operator review."
}
```

### 推荐事件类型
- `watcher_alert`
- `newswire_alert`
- `strategist_signal_ready`
- `review_approved`
- `review_rejected`
- `executor_result_ready`

---

## 11. id 设计建议

建议使用可读 id：

- watcher：`watch_YYYYMMDD_HHMMSS_xxx`
- news batch：`news_YYYYMMDD_HHMM_window`
- signal：`sig_YYYYMMDD_symbol_pattern_xxx`
- review：`review_YYYYMMDD_HHMMSS_xxx`
- executor task：`exec_task_YYYYMMDD_xxx`
- executor result：`exec_result_YYYYMMDD_xxx`
- closer：`close_<market>_YYYYMMDD`

---

## 12. 推荐触发关系

### watcher
- 盘中固定频率触发
- 写入 `watcher/latest.json`
- 若出现高优先级变化，可额外产出事件对象

### newswire
- 盘中 / 盘后按班次触发
- 写入 `newswire/latest.json`
- 高优先级新闻可附带事件对象

### strategist
- 定时 + 高优先级事件唤醒
- 读取 watcher / newswire 结构化输入
- 写入 `strategist/signals.jsonl`
- 写事件 `strategist_signal_ready`

### Operator review
- 被 strategist 信号唤醒
- 读取 signal，做二次裁决
- 写入 `decision/decisions.jsonl`

### executor
- 仅在 decision=`approved` 时被派发
- 读取 task，执行后写 result

### closer
- 收盘后触发
- 汇总全链路对象，生成总结

---

## 13. MVP 落地建议

若要快速推进，建议先只落这 4 类：

1. `watcher/latest.json`
2. `newswire/latest.json`
3. `strategist/latest_signal.json`
4. `decision/latest_decision.json`

这样先把：
- 观察层
- 情报层
- 信号层
- 决策层

完整串起来。

executor / closer 可以作为第二批严格结构化。

---

## 14. control_state health schema

### 用途
引擎每次执行后写入健康状态，供 watcher 外部监控服务健康。

### 文件
- `runtime/engine/state/control_state.json`

### health 字段

```json
{
  "health": {
    "last_heartbeat": "2026-04-03T00:15:00+08:00",
    "last_exit_code": 0,
    "last_run_at": "2026-04-03T00:15:00+08:00",
    "consecutive_failures": 0
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 | watcher 判断逻辑 |
|------|------|------|-----------------|
| `last_heartbeat` | string (ISO 8601) | 引擎最近一次成功写入的时间戳 | 超过 2 个周期（60min）未更新 → 预警 |
| `last_exit_code` | int | 最近一次执行的退出码 | ≠ 0 → 预警 |
| `last_run_at` | string (ISO 8601) | 最近一次执行开始时间 | 与 heartbeat 对比可判断执行是否卡住 |
| `consecutive_failures` | int | 连续失败次数 | ≥ 3 → 升级为严重预警 |

### 引擎写入规则

1. 执行开始时写入 `last_run_at`
2. 执行成功结束时写入 `last_heartbeat`（更新时间戳）和 `last_exit_code = 0`，重置 `consecutive_failures = 0`
3. 执行失败时写入 `last_exit_code = 非零值`，递增 `consecutive_failures`
4. 异常崩溃时不更新 `last_heartbeat`，下次启动时检测超时

---

## 15. 一句话总结

**Tiger Engine Schema v1 的核心思想是：watcher 产观察对象、newswire 产情报对象、strategist 产信号对象、decision 层产裁决对象、executor 产执行对象、closer 产总结对象，全部通过 id 串联。**
