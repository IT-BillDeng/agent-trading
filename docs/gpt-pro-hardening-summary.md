# GPT Pro 硬化变更摘要

更新时间：2026-04-20

这份文档的用途不是介绍项目愿景，而是**告诉 GPT Pro：相对 `origin/master`，这次硬化到底改了什么、为什么改、现在系统处于什么状态、下一步该重点审什么**。

建议和 [project-handoff-for-gpt-pro.md](/Users/openclaw/.openclaw/workspace-yuuka/agent-trading/docs/project-handoff-for-gpt-pro.md) 配合阅读：

- `project-handoff-for-gpt-pro.md`
  - 讲当前项目整体结构、职责边界、目录契约
- `gpt-pro-hardening-summary.md`
  - 讲这一轮硬化相对旧基线的具体改动

---

## 1. 变更范围

基线范围：

- base: `origin/master` = `168fd1a`
- head: `HEAD` = `552dfed`

这意味着 GPT Pro 当前看到的是：

- 一套已经完成了 **P0/P1/P2/P3/P4/P5/P6/P7 关键骨架** 的 hardened 版本
- 但仍然是 **paper + guarded 默认态**
- 不是一个默认允许自动 live submit 的系统

相对 `origin/master`，主要新增/变更包括：

- 执行安全基线与测试入口
- canonical ControlPlane schema
- live submit 最后一道 hard gate
- risk hard stops 与 cooldown/limits
- rule engine 穿越与冲突裁决修复
- rule schema validation
- DataHealthReport 与 bars provider fallback
- backtest 指标修复
- strategist/applier 的 fee confidence gate
- proposal review API + Dashboard proposal review 页面
- applier hot apply 真正落地，cold proposal 保持人工执行
- dashboard 路由拆分与 scheduler 权限降级
- live readiness checklist gate
- safe handoff 打包脚本

---

## 2. 为什么要做这轮硬化

旧基线中最危险的问题不是“策略不够聪明”，而是：

1. Dashboard scheduler 对执行层有越权能力
2. control state 语义分裂，UI/engine/scheduler 不一致
3. live gate 不只一处，且某些地方能被绕过
4. 风控字段存在，但没有真正形成硬阻断
5. rule engine 的 `cross_above / cross_below` 不是“真实穿越”
6. `rsi_reversal` 曾经接近自相矛盾
7. 数据链路表面正常，不等于策略真正有 bars 可用
8. strategist/applier 的审批链只有文档骨架，产品化不足

这一轮硬化的核心目标不是增强收益，而是把系统改成：

- 安全闸门可信
- 数据链路可诊断
- 策略逻辑可验证
- agent 治理链可落地
- live 进入条件可审计

---

## 3. 变更分组总览

### A. 执行安全与控制状态

重点提交：

- `fb528f0` test(engine): add P0 execution safety baseline
- `e6485ec` fix(control): canonicalize control plane schema
- `a902a61` fix(execution): add hard live submit gate
- `9057955` test(control): lock suspended symbol gates
- `f1b90ad` fix(dashboard): split execution state reset endpoint
- `89a9c16` fix(dashboard): demote scheduler controls
- `552dfed` feat(control): add live readiness checklist gate

关键结果：

- `control_state.json` 统一为 canonical schema
- canonical `global.mode` 变为：
  - `off`
  - `signal_only`
  - `paper_trade`
  - `live_trade`
- 旧 `trading_mode` / `paper_live` 仅作兼容读取，不再作为 live 升级依据
- `LiveExecutionAdapter` 自身拥有最后一道 hard gate
- Dashboard 内置 scheduler 只能 preview，不再直接 submit order
- 进入 `live_trade` 必须通过 readiness checklist

重点文件：

- `system/engine/src/engine/control.py`
- `system/engine/src/engine/live_execution.py`
- `dashboard/scheduler.py`
- `dashboard/api/control.py`
- `docs/live-readiness-checklist.md`

GPT Pro 重点应审：

- 旧字段兼容是否还有隐性越权入口
- live gate 是否在所有执行路径都一致
- reset / unlock / checklist 之间是否还存在不一致状态

---

### B. 风控硬限制

重点提交：

- `d54bd07` feat(risk): add daily loss hard stop
- `12c6a27` feat(risk): add trade limits and symbol cooldown
- `d0e543f` feat(risk): add reduce-only and emergency flatten modes

关键结果：

- `daily_loss_limit_pct` 现在会形成真正的 same-day hard stop
- 新增：
  - `max_trades_per_day`
  - `max_trades_per_symbol_per_day`
  - `symbol_cooldown_minutes_after_order`
  - `symbol_cooldown_minutes_after_loss`
- `reduce_only` 与 `emergency_flatten` 已成为真实 BUY gate
- `EXIT` 不会被这些 BUY-side 阻断误伤

重点文件：

- `system/engine/src/engine/risk.py`
- `system/engine/src/engine/state.py`

GPT Pro 重点应审：

- daily loss reset 的日界线是否足够稳
- trade count 当前是按 preview/paper intent 记数，是否符合最终业务预期
- reduce-only / emergency flatten 是否需要更细粒度 market/symbol override

---

### C. 规则引擎正确性

重点提交：

- `3383c66` fix(rule-engine): implement true cross operators
- `4474df2` test(rule-engine): lock rsi reversal cross behavior
- `f6a933d` feat(rule-engine): arbitrate final signal per symbol
- `623cf34` feat(rules): add schema validation for hot apply

关键结果：

- `cross_above / cross_below` 现在是上一根 + 当前根的真实穿越
- `rsi_reversal` 语义被锁定为真实 RSI 反转，不再要求矛盾条件
- 同一 symbol 的多个 signal 会通过 `SignalArbiter` 收敛成一个最终动作
- rules hot apply 前会做 schema validation

重点文件：

- `system/engine/src/engine/rule_engine.py`
- `system/engine/src/engine/signal_arbiter.py`
- `system/engine/src/engine/rule_schema.py`
- `rules/rules.json`

GPT Pro 重点应审：

- `SignalArbiter` 的裁决优先级是否符合预期
- `rule_schema` 是否还缺少风险参数/compound nesting 的校验项
- 真实穿越实现是否需要更多 multi-indicator edge case 测试

---

### D. 数据链路与数据健康

重点提交：

- `bc003ed` feat(strategy): add data health report
- `d1dd20d` feat(data): add bars provider fallback health reporting

关键结果：

- `strategy_overview` 里现在有 `data_health`
- 每个 symbol 会暴露：
  - provider
  - quote/contract status
  - raw/normalized bars count
  - required bars
  - readiness
  - reason
- bars provider 支持 primary/fallback 路径
- primary/fallback 都失败时可显式失败，不再默默当成“正常无信号”

重点文件：

- `system/engine/src/engine/runtime.py`
- `system/engine/src/engine/data_provider.py`
- `dashboard/static/strategy.html`

GPT Pro 重点应审：

- `required_bars` 计算是否在 rule-engine/legacy 两条路径都足够准确
- fallback 逻辑是否存在 provider drift 或时间框不一致问题
- `market_closed` / `bars_empty` / `provider_error` 的边界条件是否还需细分

---

### E. 回测可信度

重点提交：

- `45461ae` fix(backtest): compute win rate from closed trades
- `689e7b1` fix(backtest): align multisymbol runs by timestamp

这之前本项目还完成了 fee model/fee calibration/fee confidence 链路，这一轮又补了可靠性：

- `win_rate` 现在按 closed trades 算
- 多 symbol 回测按 timestamp 对齐，不再用 index 粗对齐

重点文件：

- `system/engine/src/engine/backtest.py`

GPT Pro 重点应审：

- 当前 portfolio equity 更新是否足够贴近事件驱动模型
- 仍有哪些回测指标是“可用但不完美”
- 是否需要更进一步拆分 fill model / slippage model / fee confidence weighting

---

### F. Strategist / Applier / Approval gate

重点提交：

- `fecf3de` feat(strategist): gate hot apply on fee confidence
- `a81eeb6` feat(dashboard): add proposal review api
- `8b31eaf` feat(applier): execute hot rules apply
- `f582716` fix(applier): keep cold proposals manual only
- `f4b8076` feat(dashboard): add proposal review page

关键结果：

- proposal review API 已可用
- `/strategy` 页面已有 proposal review UI
- hot proposal 现在可以真正 apply 到 `rules/`
- cold proposal 仍然只记录为 `manual_code_apply_required`
- fee confidence 已接入 strategist/applier approval gate

重点文件：

- `system/engine/src/engine/strategist_artifacts.py`
- `system/engine/src/engine/applier.py`
- `dashboard/api/proposals.py`
- `dashboard/static/strategy.html`
- `docs/strategist-l3b-approval-contract.md`

GPT Pro 重点应审：

- hot apply 的 rollback/backup 粒度是否足够
- fee confidence gate 是否过严或过松
- proposal validation 字段是否已经足够支撑人工 review
- cold proposal 现在“只记录不自动改代码”的契约是否还有越权路径

---

### G. Dashboard 架构与权限降级

重点提交：

- `c92f608` refactor(dashboard): split proposal routes module
- `14643b6` refactor(dashboard): split remaining api routes
- `89a9c16` fix(dashboard): demote scheduler controls

关键结果：

- `dashboard/main.py` 的 routes 已按类别拆到：
  - `dashboard/api/market.py`
  - `dashboard/api/control.py`
  - `dashboard/api/config.py`
  - `dashboard/api/strategy.py`
  - `dashboard/api/backtest.py`
  - `dashboard/api/logs.py`
  - `dashboard/api/proposals.py`
- scheduler 只读、preview-only
- Dashboard 现在更接近“控制台/可视化层”，而不是执行权中心

重点文件：

- `dashboard/main.py`
- `dashboard/api/*.py`
- `dashboard/scheduler.py`

GPT Pro 重点应审：

- 现在残留在 `main.py` 的共享 helper 是否还应该继续下沉
- scheduler preview-only 模式是否彻底切断了 submit 路径
- API 模块化后是否还缺 service layer

---

### H. 安全 handoff

重点提交：

- `2e867c1` feat(handoff): add safe packaging script

关键结果：

- 项目现在可以安全导出 zip 供 GPT Pro 或外部审查方使用
- 默认排除：
  - `.env`
  - `properties/*`
  - `runtime/*`
  - `logs/latest/*`
  - `artifacts/broker/*`
  - 常见 secret/token/key 文件

重点文件：

- `scripts/make_safe_handoff.sh`

GPT Pro 重点应知道：

- 它拿到的 handoff 包故意不含真实 broker state / secrets / runtime
- 因此关于 live runtime 的问题只能做代码与架构层分析，不能假设包里有真实运行现场

---

## 4. 关键测试面

这轮硬化新增了大量测试。GPT Pro 如果要快速确认“系统哪里被认真加固了”，应优先看这些：

### 执行安全

- `system/engine/tests/test_control_plane.py`
- `system/engine/tests/test_live_execution_gates.py`
- `system/engine/tests/test_dashboard_scheduler_safety.py`

### 风控

- `system/engine/tests/test_risk_daily_loss.py`
- `system/engine/tests/test_risk_trade_limits.py`
- `system/engine/tests/test_reduce_only.py`

### 规则引擎

- `system/engine/tests/test_rule_engine.py`
- `system/engine/tests/test_rule_schema.py`
- `system/engine/tests/test_signal_arbiter.py`

### 数据健康

- `system/engine/tests/test_data_health.py`
- `system/engine/tests/test_data_provider_health.py`

### 回测

- `system/engine/tests/test_backtest_metrics.py`
- `system/engine/tests/test_backtest_multisymbol_alignment.py`

### strategist/applier/dashboard

- `system/engine/tests/test_fee_confidence_gate.py`
- `system/engine/tests/test_applier_hot_apply.py`
- `system/engine/tests/test_applier_cold_gate.py`
- `tests/test_proposal_review_api.py`
- `tests/test_dashboard_api_structure.py`
- `tests/test_strategy_page_structure.py`

---

## 5. 当前系统状态判断

如果 GPT Pro 要对当前项目做一句话判断，我建议它从这个前提出发：

> 这不是一个“交易能力还不够强”的项目，而是一个已经完成了一轮关键安全硬化、正在把 agent 治理链产品化的 paper/guarded 系统。

换句话说，当前最重要的不是“再加多少策略”，而是：

- 检查这些 gate 是否真的闭环
- 检查还有没有旧兼容字段能绕过新契约
- 检查 strategist/applier 的治理路径是否还缺审计或回滚
- 检查 Dashboard 是否仍有隐性执行权

---

## 6. GPT Pro 建议重点分析的问题

建议 GPT Pro 优先回答这些问题：

1. `ControlPlane + LiveExecutionAdapter + readiness checklist` 三层 gate 是否已经形成真正闭环？
2. 当前 risk hard stops 是否足以支撑长期 paper shadow，而不会错误阻断正常 EXIT？
3. `SignalArbiter + true cross + rule_schema` 是否已经把 rule engine 的主要正确性风险压住？
4. `DataHealthReport + provider fallback` 是否足以解释当前大多数“为什么没信号”的问题？
5. backtest 当前还缺哪些关键可信度修复？
6. `fee confidence -> strategist/applier gate` 的设计是否合理，是否还需要更明确的统计口径？
7. proposal review / hot apply / cold manual apply 当前是否已经具备“可审计、可回滚、不可越权”的最小产品化闭环？
8. dashboard 路由拆分后，下一步是否应该引入 service layer，而不是继续把聚合逻辑放在 `main.py`？

---

## 7. 仍然刻意没有做的事

以下内容这轮**故意没有做**，GPT Pro 不应把它们误判为“遗漏”：

- 不默认启用 live
- 不自动 apply cold code changes
- 不让 scheduler 重新获得 submit 权限
- 不把真实 secrets / runtime / broker calibration 原始数据放进 handoff 包
- 不扩大 watchlist
- 不新增 broker
- 不提高仓位与风险上限

---

## 8. 建议 GPT Pro 的阅读顺序

如果时间有限，最建议按这个顺序读：

1. `docs/project-handoff-for-gpt-pro.md`
2. `docs/gpt-pro-hardening-summary.md`
3. `system/engine/src/engine/control.py`
4. `system/engine/src/engine/live_execution.py`
5. `system/engine/src/engine/risk.py`
6. `system/engine/src/engine/rule_engine.py`
7. `system/engine/src/engine/rule_schema.py`
8. `system/engine/src/engine/runtime.py`
9. `system/engine/src/engine/data_provider.py`
10. `system/engine/src/engine/backtest.py`
11. `system/engine/src/engine/strategist_artifacts.py`
12. `system/engine/src/engine/applier.py`
13. `dashboard/scheduler.py`
14. `dashboard/api/control.py`
15. `dashboard/api/proposals.py`
16. 测试文件集合

---

## 9. 交接建议

如果把项目交给 GPT Pro，请一起提供：

- 这份文档
- `docs/project-handoff-for-gpt-pro.md`
- 由 `scripts/make_safe_handoff.sh` 生成的安全 zip

这样 GPT Pro 才能：

- 先建立结构性认知
- 再理解这轮硬化的具体改动
- 最后在不接触真实 secrets/runtime 的前提下做代码审查与改进建议
