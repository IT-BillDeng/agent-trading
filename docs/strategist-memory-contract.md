# Strategist Memory Contract

更新时间：2026-04-17

这份文档定义 strategist 的长期记忆应该怎么存、怎么读、怎么更新。

目标不是保留聊天全文，而是保留 **可审计、可回放、可继续迭代** 的结构化学习记录。

---

## 一、为什么要有 memory

如果 strategist 想真正做到：

- 自我总结
- 自我调整
- 经验沉淀
- 跨 Session 继承历史判断

就不能依赖模型的隐式记忆，而要显式写入文件。

这里的 memory 不是“脑内记忆”，而是：

- 当前策略状态
- 重要经验结论
- 被拒绝的提案
- 新的假设与后续实验
- 与规则版本绑定的判断依据

---

## 二、推荐分层

### 1. 最新摘要

建议路径：

- `artifacts/strategist/memory/latest.json`

用途：

- 给 strategist 盘前 / 盘中快速读取
- 让 Dashboard / Operator 看到“当前 strategist 认为最重要的几件事”

建议内容：

- `generated_at`
- `rules_snapshot_hash`
- `current_regime`
- `active_hypotheses`
- `active_risks`
- `top_lessons`
- `next_actions`

### 2. 学习历史

建议路径：

- `artifacts/strategist/memory/history.jsonl`

用途：

- 追加保存每次有价值的经验总结
- 记录“为什么这次改了 / 为什么这次没改”
- 方便后面回放某次调参决策的上下文

建议内容：

- `generated_at`
- `shift`
- `cycle_id`
- `regime`
- `insight`
- `evidence`
- `decision`
- `action`
- `rejected_reason`
- `follow_up`

### 3. 提案与拒绝记录

建议路径：

- `artifacts/strategist/proposals.jsonl`
- `artifacts/strategist/rejections.jsonl`

用途：

- 分离“提案”和“复盘结论”
- 避免所有东西都堆进一条长日志里

建议内容：

- `proposal_id`
- `target_rule`
- `before`
- `after`
- `backtest`
- `approved`
- `rejection_reason`

---

## 三、写入时机

### 盘前

更新：

- `artifacts/strategist/memory/latest.json`
- 必要时追加 `artifacts/strategist/memory/history.jsonl`

盘前重点：

- 今天要关注什么
- 哪些规则继续保持
- 哪些风险事件需要提前 gate

### 盘中

只有在出现重要事件时才写：

- high importance 新闻触发暂停
- 异常波动触发规则切换
- 连续 false signal 触发临时保护

普通“无变化”不必刷 memory 历史。

### 盘后

必须更新：

- `artifacts/strategist/memory/latest.json`
- `artifacts/strategist/memory/history.jsonl`
- 如有提案，写入 proposal / rejection 记录

盘后是 strategist 最重要的学习沉淀点。

---

## 四、读取顺序

strategist 在新一轮运行时，推荐按这个顺序读取：

1. `artifacts/strategist/memory/latest.json`
2. `artifacts/strategist/strategy_plan_latest.json`
3. `artifacts/strategist/strategy_plan_history.jsonl`
4. `rules/rules.json`
5. `artifacts/strategist/memory/history.jsonl`
6. 最近的 proposal / rejection 记录

这样可以把“当前状态”和“长期经验”一起纳入判断。

---

## 五、字段建议

建议 strategist memory 至少包含这些语义块：

- `current_state`
  - 当前启用/暂停的规则
  - 最近一次调整原因
- `lessons`
  - 已确认有效的经验
- `rejected_proposals`
  - 被拒绝的提案及原因
- `active_hypotheses`
  - 目前还在观察、尚未证实的假设
- `regime_tags`
  - 例如 `high_vol`, `news_driven`, `range_bound`
- `next_actions`
  - 下一轮要做的事

不建议保存：

- 原始聊天全文
- 冗长思考过程
- 已过期且没有复用价值的临时判断

---

## 六、迁移说明

早期可能存在本地草稿式学习记录。现在不建议继续扩展这种独立目录；如果要正式化，统一迁移到：

- `artifacts/strategist/memory/latest.json`
- `artifacts/strategist/memory/history.jsonl`
- `artifacts/strategist/proposals.jsonl`
- `artifacts/strategist/rejections.jsonl`

---

## 七、最小落地原则

先保留三件事就够：

1. 最新摘要
2. 学习历史
3. 提案 / 拒绝记录

这三类已经足够让 strategist 形成持续迭代，而不需要保留完整对话。
