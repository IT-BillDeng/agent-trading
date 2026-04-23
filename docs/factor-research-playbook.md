# Factor Research Playbook

更新时间：2026-04-23

这份 playbook 用于定义 `factor-researcher` / `factor-validator` 在冷路径中的协作方式，让因子研究可以在 **shadow-only、proposal-only** 的前提下，稳定地产出下一批候选。

## 目标

FF-06 的目标不是让因子 agent 直接改热路径，而是让它们能基于下列证据自动形成下一批候选：

- factor history
- factor attribution
- market context
- data health

## 角色分工

### factor-researcher

`factor-researcher` 是冷路径研究员：

- 读取 factor latest / history
- 读取 factor attribution 与 strategist iteration
- 读取 market context 与 data health
- 形成 research note 与 proposal draft
- 可以写 `artifacts/factor_research/*`
- 可以把 draft 写到 `artifacts/strategist/approval_queue/*`

它不是交易员，不是发布员，不是 apply 执行器。

### factor-validator

`factor-validator` 是冷路径只读验证员：

- 读取 `factor-researcher` 的候选与证据
- 核验 schema 完整性、证据链质量、shadow-only 边界
- 只通过 `sessions_send` 向主 agent 汇报结论
- 不直接修改 proposal queue
- 不 approve / apply

它不是第二主 agent，也不是发布员。

## 研究输入优先级

每轮研究或验证，优先按下面顺序取证：

1. `./artifacts/factors/latest.json`
2. `./artifacts/factors/history/`
3. 最新可用 `factor_attribution` 摘要
4. `./logs/latest/engine_cycle.json` 中的 `factor_engine`、`data_health`
5. `./logs/latest/market_context.json`
6. `./artifacts/strategist/strategy_plan_history.jsonl`
7. `./artifacts/factor_research/latest.json` 与 `history.jsonl`

如果上述证据不足，允许输出 `factor_reject`，但不允许跳过证据链直接推送可热应用的提案。

## Proposal Draft Schema

所有冷路径草案都使用统一 envelope：

```json
{
  "draft_type": "factor_candidate | factor_binding_candidate | factor_reject",
  "draft_id": "draft_20260423_001",
  "created_at": "2026-04-23T17:45:00Z",
  "created_by": "factor-researcher",
  "factor_id": "rsi_14_30m",
  "summary": "一句话概述",
  "evidence": {
    "factor_history": {},
    "factor_attribution": {},
    "market_context": {},
    "data_health": {}
  },
  "shadow_only": true
}
```

### 1. `factor_candidate`

用于表达“候选因子本身值得进入下一步研究/配置准备”。

必含字段：

- `draft_type = "factor_candidate"`
- `hypothesis`
- `implementation`
- `session`
- `timeframe`
- `inputs`
- `params`
- `usage`
- `actionable = false`
- `research_basis.factor_history`
- `research_basis.factor_attribution`
- `research_basis.market_context`
- `research_basis.data_health`
- `validation_plan`
- `recommended_next_step`

示例：

```json
{
  "draft_type": "factor_candidate",
  "factor_id": "overnight_return_pct_1d",
  "hypothesis": "隔夜收益在 gap continuation 日更有解释力",
  "implementation": "builtin:overnight_return_pct",
  "session": "extended_hours",
  "timeframe": "1d",
  "usage": ["context_only"],
  "actionable": false,
  "research_basis": {
    "factor_history": {"missing_rate": 0.03},
    "factor_attribution": {"rank_ic": 0.08},
    "market_context": {"regime": "gap_follow_through"},
    "data_health": {"AAPL": {"ready": true}}
  },
  "validation_plan": {"paper_shadow_required_days": 20},
  "recommended_next_step": "prepare_factor_config"
}
```

### 2. `factor_binding_candidate`

用于表达“候选 factor 与规则绑定值得进入受控评审”，但 v1 仍然只能处于 `diagnostic / disabled_rule / manual_promotion` 语义。

必含字段：

- `draft_type = "factor_binding_candidate"`
- `factor_id`
- `target_rule_id`
- `binding_mode`
- `expected_behavior = "no_default_rule_change"`
- `backtest_delta`
- `fee_cost_impact`
- `correlation_with_existing`
- `paper_shadow_required_days`

约束：

- `binding_mode` 只能是 `diagnostic`、`disabled_rule`、`manual_promotion`
- 默认不得改写当前已启用生产规则行为
- 当 `allow_actionable_consumption = false` 时，它不代表可以直接触发 actionable factor trading

示例：

```json
{
  "draft_type": "factor_binding_candidate",
  "factor_id": "atr_pct_14_30m",
  "target_rule_id": "factor_shadow_probe",
  "binding_mode": "disabled_rule",
  "expected_behavior": "no_default_rule_change",
  "backtest_delta": {"return_pct": 0.0},
  "fee_cost_impact": {"estimated_bps": 0.0},
  "correlation_with_existing": 0.21,
  "paper_shadow_required_days": 20
}
```

### 3. `factor_reject`

用于表达“本轮不建议继续推进某个因子/绑定候选”。

必含字段：

- `draft_type = "factor_reject"`
- `factor_id`
- `reject_reason`
- `blocking_evidence`
- `next_unblock_check`

示例：

```json
{
  "draft_type": "factor_reject",
  "factor_id": "premarket_gap_pct",
  "reject_reason": "context_only factor with unstable coverage",
  "blocking_evidence": {
    "factor_attribution": {"rank_ic": null, "reason": "insufficient_samples"},
    "data_health": {"TSLA": {"reason": "bars_empty"}}
  },
  "next_unblock_check": "wait_for_20_shadow_days"
}
```

## 自动产出下一批候选的最低要求

`factor-researcher` 每轮都应尝试自动产出下一批候选，且必须显式说明其依据来自：

- factor history
- factor attribution
- market context
- data health

如果四类输入中任一类严重缺失，应优先产出 `factor_reject` 或“继续观察”结论，而不是直接推动可热应用 proposal。

## 冷路径硬边界

- `no submit`: 不得调用 execution submit，不得下单，不得触发 broker / execution / order-submit 路径
- `no apply`: 不得 approve / apply，不得直接修改 `rules/rules.json` 或 `factors/registry.json`
- `no secrets`: 不得读取、复制、回显 `.env`、`properties/*`、runtime credentials、token、secret、broker 凭据
- cron 仍为 desired state，不自动同步到 live

## validator 检查清单

`factor-validator` 的只读验证至少覆盖：

- draft_type 是否属于 `factor_candidate` / `factor_binding_candidate` / `factor_reject`
- evidence 是否同时覆盖 factor history / factor attribution / market context / data health
- `factor_binding_candidate` 是否维持 `shadow_only = true`
- 是否存在暗中扩大到 execution / broker / apply 的迹象
- 是否错误暗示 `allow_actionable_consumption = true`

发现问题时，只能通过 `sessions_send` 汇报主 agent，不得自行修改或 apply。
