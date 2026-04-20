# Strategist L3b Approval Contract

更新时间：2026-04-17

这份文档定义 strategist 从 `L3a` 进入 `L3b` 时，代码提案如何被批准、如何应用、以及热更新与冷更新如何区分。

相关文档：

- `docs/strategist-capability-contract.md`
- `docs/strategist-l3-evolution-plan.md`
- `docs/tasks/STRATEGIST_CODE_CHANGE_TASK.md`

---

## 一、目标

`L3b` 的目标不是让 strategist 自己决定上线，而是让它：

- 自动生成并验证代码提案
- 自动提交受控 commit
- 进入显式审批队列
- 由人工或上层 agent 决定是否应用更新

因此，`L3b` 的本质是：

- `自动研究 + 自动验证 + 受控审批`

不是：

- `自动研究 + 自动上线`

---

## 二、角色分工

### 1. Strategist

负责：

- 生成代码提案
- 修改白名单目录内的策略代码与测试
- 跑验证链
- 写入 proposal / result / rollback artifacts
- 给出建议的更新模式

不负责：

- 最终批准上线
- 直接部署 live
- 修改执行链、broker 或 infra

### 2. 人工审批者

可以是项目维护者。

负责：

- 阅读提案摘要
- 检查测试、dry-run、回测结果
- 决定 `approved / rejected`
- 必要时补充理由

### 3. 上层 agent

可以替代人工做第一层审阅，但不应默认绕过所有人工闸门。

负责：

- 读取 strategist proposal
- 做结构化检查
- 写回批准结论
- 如被授权，可触发受控 apply 流程

---

## 三、审批对象

每一次代码级策略变更，都应形成一个独立 proposal。

建议最小字段：

- `proposal_id`
- `generated_at`
- `hypothesis`
- `target_files`
- `change_summary`
- `change_intent`
- `turnover_profile`
- `tests_passed`
- `dry_run_passed`
- `backtest_delta`
- `recommended_update_mode`
- `requires_restart`
- `status`

其中：

- `recommended_update_mode` 取值：`hot | cold`
- `requires_restart` 取值：`true | false`
- `change_intent` 建议显式标记：
  - `enable_new_buy_rule`
  - `paper_shadow`
  - `disable_rule`
  - `reduce_risk`
  - `lower_frequency`
  - `lower_position_size`
  - `tighten_filters`
- `turnover_profile` 建议取值：
  - `low | medium | high`
- `status` 取值：
  - `draft`
  - `validated`
  - `awaiting_approval`
  - `approved`
  - `rejected`
  - `applied`

---

## 四、审批入口

建议新增这些 artifacts：

- `artifacts/strategist/approval_queue/`
- `artifacts/strategist/approval_decisions.jsonl`
- `artifacts/strategist/deployment_records.jsonl`

### 1. `approval_queue/`

每个待审批 proposal 一个 json 文件。

示例：

- `artifacts/strategist/approval_queue/prop_20260417_01.json`

用途：

- 给人工或上层 agent 读取
- 明确“当前有哪些提案正在等批准”

### 2. `approval_decisions.jsonl`

记录审批动作。

建议字段：

- `proposal_id`
- `decided_at`
- `decider_type`
- `decider_id`
- `decision`
- `reason`

### 3. `deployment_records.jsonl`

记录批准后的实际应用结果。

建议字段：

- `proposal_id`
- `applied_at`
- `operator_type`
- `operator_id`
- `update_mode`
- `success`
- `rollback_target`

---

## 五、批准流程

推荐标准流程：

1. strategist 生成代码提案
2. strategist 完成验证链
3. strategist 将 proposal 状态写成 `awaiting_approval`
4. proposal 进入 `approval_queue/`
5. 人工或上层 agent 审批
6. 审批结果写入 `approval_decisions.jsonl`
7. 如通过，再由 `applier` 这类独立执行者应用更新
8. 应用结果写入 `deployment_records.jsonl`

注意：

- strategist 自己不应同时扮演“提案者”和“最终批准者”
- 审批者或上层 agent 也不应把审批记录写回 `docs/`、`cron/`、`agents/` 或项目根自由格式笔记
- 持久审批记录只允许进入 `artifacts/strategist/approval_queue/`、`approval_decisions.jsonl`、`deployment_records.jsonl`

---

## 六、热更新与冷更新规则

### 1. 热更新

适用于：

- 仅修改 `rules/`
- 仅变更规则参数
- enable / disable / pause / resume

要求：

- 不改 Python 策略代码
- 不改执行链
- dry-run / backtest 通过

建议标记：

- `recommended_update_mode: hot`
- `requires_restart: false`

### 2. 冷更新

适用于：

- 修改 `strategy.py`
- 修改 `rule_engine.py`
- 修改 `indicators.py`
- 任何策略逻辑代码变化

原因：

- Python 代码可能已被当前进程加载
- 缓存、对象状态、模块加载状态可能不一致
- 没有成熟热替换框架时，代码更新默认应视为冷更新

建议标记：

- `recommended_update_mode: cold`
- `requires_restart: true`

### 3. 禁止 strategist 决定的更新

以下不应由 strategist 进入更新流程：

- broker client 改动
- live execution 改动
- notifier 改动
- deploy / infra 改动

这些不属于 strategist 的批准范围。

---

## 七、L3b 的最低批准条件

一个 proposal 至少满足以下条件，才允许进入 `approved`：

1. 白名单目录内改动
2. 语法检查通过
3. 相关单元测试通过
4. dry-run 通过
5. 回测对比结果可接受
6. 已写 proposal / result / rollback artifacts
7. 已给出 `recommended_update_mode`

额外建议：

- 必须有简洁的 rollback 说明
- 必须标明是否需要 restart
- 应结合 `artifacts/broker/fee_calibration_summary.json` 写入 fee confidence snapshot

### Fee Confidence Gate

审批 / apply 前应读取 `artifacts/broker/fee_calibration_summary.json`，并将其归一化为：

- `high`
- `medium`（来自 `observe`）
- `low`
- `missing`

最低 gate：

- `high`：允许正常参数 / 规则 apply
- `medium`：允许低换手策略调参；不允许新增高换手 BUY 规则
- `low / missing`：不允许启用新 BUY 规则；只允许 `paper_shadow`、禁用规则、降低频率、降低仓位、收紧过滤器等降风险变更

---

## 八、apply 执行原则

即便 proposal 已批准，也建议由独立执行者应用：

- 人工
- 主 agent
- 或专门的 `applier` agent

不要默认由 strategist 自己直接应用。

### 应用规则

- `hot` 更新：只改规则层文件
- `cold` 更新：applier 只记录 `manual_code_apply_required`，保留 proposal 为 `approved`，不得自动 patch 代码
- 真正的 `cold` 代码落地必须通过后续明确任务，进入更强 sandbox、diff review、test runner、rollback 流程
- deployment record 应写入 `fee_confidence_snapshot`

---

## 九、当前建议

当前项目建议：

- 先维持 strategist 在 `L3a`
- 同时把 `L3b` 的 artifacts 与审批流程准备好
- 配置变更允许热更新
- 策略代码变更默认冷更新

也就是说，近期最合理的方向是：

- `strategist` 自动研究与验证
- `人工或上层 agent` 批准
- `独立执行者` 应用更新

---

## 十、结论

`L3b` 的关键不是让 strategist 更自由，而是让它更受控。

需要明确三件事：

1. 谁批准
2. 什么能热更，什么必须冷更
3. 谁真正执行应用更新

只要这三件事写清楚，`L3b` 就会是一个可治理的阶段，而不是“半自动上线”的危险过渡态。
