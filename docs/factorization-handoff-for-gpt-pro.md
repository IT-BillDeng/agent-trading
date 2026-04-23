# GPT Pro Factorization Analysis Handoff

更新时间：2026-04-23

这份文档用于把 `agent-trading` 的 `factor-researcher` 分支当前因子化状态，压缩成一份可直接交给 GPT Pro 的分析 handoff。

目标不是让 GPT Pro 继续盲目开发，而是让它基于当前真相源，评估：

- 当前因子化设计是否已经完整
- 还有哪些结构性缺口、隐性风险、测试盲区
- 这些缺口是否影响合并 `main`
- 下一步最小补完路线应该是什么

如果旧文档、历史计划与当前代码发生冲突，请优先以本文件列出的真相源和当前实现为准。

---

## 1. 一句话概述

`factor-researcher` 分支已经把 `agent-trading` 从纯规则驱动，扩展成了一个 **shadow-first、governance-first、默认不改交易行为** 的因子化基础设施分支。

当前状态不是“因子直接驱动交易”，而是：

- 因子引擎已存在
- registry / store / attribution / dashboard / proposal-applier 链路已存在
- 默认仍然是 `paper + guarded`
- 默认仍然是 `factor_engine.mode=shadow`
- 默认仍然是 `allow_actionable_consumption=false`

也就是说，这是一套 **可观测、可治理、可回滚、默认不改变热路径行为** 的因子化 v1.1 基础设施，而不是一个已打开 live / actionable 因子交易的系统。

---

## 2. 先读哪些文件

### 第一层：当前因子化真相源

1. `docs/factorization-handoff-for-gpt-pro.md`
2. `docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md`
3. `docs/factor-system-contract.md`
4. `docs/factorization-merge-readiness.md`
5. `docs/factor-system-rollback.md`
6. `docs/factor-researcher-role-contract.md`
7. `specs/factor-registry-schema-v1.md`
8. `factors/registry.json`

### 第二层：当前实现入口

1. `system/engine/src/engine/factors/catalog.py`
2. `system/engine/src/engine/factors/schema.py`
3. `system/engine/src/engine/factors/registry.py`
4. `system/engine/src/engine/factors/builtins.py`
5. `system/engine/src/engine/factors/engine.py`
6. `system/engine/src/engine/factors/store.py`
7. `system/engine/src/engine/factors/attribution.py`
8. `system/engine/src/engine/runtime.py`
9. `system/engine/src/engine/rule_schema.py`
10. `system/engine/src/engine/rule_engine.py`
11. `system/engine/src/engine/backtest.py`
12. `system/engine/src/engine/proposal_schema.py`
13. `system/engine/src/engine/applier.py`
14. `system/engine/src/engine/strategist_artifacts.py`
15. `dashboard/main.py`
16. `dashboard/static/strategy.html`

### 第三层：相关测试

1. `system/engine/tests/test_factor_registry_schema.py`
2. `system/engine/tests/test_factor_builtins.py`
3. `system/engine/tests/test_factor_engine_shadow.py`
4. `system/engine/tests/test_factor_store.py`
5. `system/engine/tests/test_runtime_factor_shadow.py`
6. `system/engine/tests/test_rule_engine_factors.py`
7. `system/engine/tests/test_factor_attribution.py`
8. `system/engine/tests/test_backtest_factor_attribution.py`
9. `system/engine/tests/test_factor_proposal_schema.py`
10. `system/engine/tests/test_applier_factor_apply.py`
11. `tests/test_strategy_overview_api.py`
12. `tests/test_strategy_page_structure.py`
13. `tests/test_factor_researcher_structure.py`

### 背景总览

如果 GPT Pro 需要更大的项目背景，再读：

1. `docs/project-handoff-for-gpt-pro.md`
2. `README.md`

---

## 3. 当前已完成的因子化范围

### FR-00 到 FR-10

这些内容已经落地，并且已有文档：

- FR-00：容器测试基线与安全边界确认
- FR-01：因子系统契约文档与目录骨架
- FR-02：factor registry schema / loader / validation
- FR-03：Factor Engine shadow mode 与第一批 builtins
- FR-04：Factor Store + runtime shadow summary
- FR-05：Dashboard 只读展示 `Factor Engine Shadow / Factor Health Matrix`
- FR-06：rule schema / rule engine 兼容 factor-based condition
- FR-07：backtest factor attribution / IC 基础统计
- FR-08：factor-researcher subagent + afterhours cron desired state
- FR-09：factor proposal / approval / applier 接入
- FR-10：merge readiness / rollback 文档

### FR-11A 到 FR-11E

这些是 FR-10 之后已经完成、但主迁移计划文档里尚未系统化归档的补完：

- FR-11A：收紧 factor implementation contract
  - `schema` 和 builtin handler 改为单一事实源
  - 消除 “registry 校验通过但 runtime implementation_not_available” 的半闭环
- FR-11B：打通 dashboard 容器内 `pytest -q`
  - `docker compose run --rm dashboard ... python -m pytest -q` 已可直接执行
- FR-11C：新增 factor proposal 质量门槛
  - 覆盖 `ic / coverage / missing_rate / paper_shadow_required_days`
- FR-11D：增强 factor observability
  - 增加 `schema_valid / schema_errors / schema_warnings`
  - 增加 `implementation_summary`
  - 增加 `registry_hash_source`
  - 增加 `last_apply`
  - 每个 factor payload 增加 `implementation_available`
- FR-11E：扩展 shadow builtin coverage
  - 新增 `builtin:afterhours_move_pct`
  - 新增 `builtin:overnight_return_pct`
  - 新增 `builtin:atr_pct`
  - 新增 `builtin:return`
  - 当前 `factors/registry.json` 已扩到 8 个因子

---

## 4. 当前默认安全边界

以下默认边界必须被视为硬约束，不应在分析中被轻易建议打破：

- `execution.submit_mode = guarded`
- `execution.live_submit = false`
- `factor_engine.mode = shadow`
- `factor_engine.allow_actionable_consumption = false`
- `factor_engine.regular_session_only_for_indicators = true`
- Dashboard scheduler 仍然是 preview-only
- Dashboard 不提供直接写 `factors/registry.json` 或 `rules/rules.json` 的入口
- `factor_code` 仍然必须 `cold/manual`
- `factor-researcher` 只是冷路径研究员，不是主 agent，不是交易员，不是发布员
- `factor-researcher` 不应同步到 live，除非主 agent 单独审批

protected paths 仍然包括：

- `.env`
- `properties/*`
- `runtime/*`
- `logs/latest/*`
- `artifacts/broker/*`

---

## 5. 当前 registry / builtin 状态

当前 registry 默认配置：

- `schema_version = 1`
- `defaults.mode = shadow`
- `defaults.allow_actionable_consumption = false`
- `defaults.regular_session_only_for_indicators = true`
- `defaults.default_timezone = America/New_York`

当前已登记因子：

1. `rsi_14_30m`
2. `bollinger_zscore_20_2_30m`
3. `volume_ratio_20_30m`
4. `premarket_gap_pct`
5. `afterhours_move_pct`
6. `overnight_return_pct`
7. `atr_pct_14_30m`
8. `return_5_30m`

当前 builtin implementation catalog：

1. `builtin:rsi`
2. `builtin:bollinger_zscore`
3. `builtin:volume_ratio`
4. `builtin:premarket_gap_pct`
5. `builtin:afterhours_move_pct`
6. `builtin:overnight_return_pct`
7. `builtin:atr_pct`
8. `builtin:return`

所有当前 registry 因子都保持：

- `actionable = false`
- extended-hours 仍然是 `context_only` / `risk_hint_candidate`
- regular technical factors 只消费 regular-session completed bars

---

## 6. 当前已知重要实现特征

GPT Pro 在分析时，建议特别关注这些已经落地的特征：

### 因子契约与运行一致性

- `system/engine/src/engine/factors/catalog.py` 是 builtin implementation 的单一事实源
- `schema.py` 的 `SUPPORTED_IMPLEMENTATIONS` 与 builtin handler 已对齐
- runtime 启动时如果 catalog 与 handler 集不一致，会直接抛错

### Shadow-first 运行特征

- Factor Engine 只支持 `shadow`
- runtime 已接 factor shadow path，但 factor failure 必须 fail-open
- factor failure 不得改变：
  - `strategy.signals`
  - `risk.decisions`
  - `execution_preview`
  - `order_intents`

### Rule Engine 集成边界

- rule engine 已支持 factor condition
- 但默认生产 `rules/rules.json` 不应被自动改成 factor-based
- `allow_actionable_consumption=false` 时，factor 不应直接生成 actionable BUY

### Dashboard 状态

- `/strategy` 已有：
  - `Factor Engine Shadow`
  - `Factor Health Matrix`
- 当前这两个区块已经被改成上下两个全宽窗格
- 页面仍然是只读，不提供 factor/rules 直接写入口

### Proposal / Governance

- `factor_config` 可 hot apply 到 `factors/registry.json`
- `factor_rule_link` 可 hot apply 到 `rules/rules.json`
- 但必须同时通过 rule schema 和 factor registry schema
- `factor_code` 必须 `manual_code_apply_required`

### Attribution / Backtest

- backtest 输出已增加 `factor_attribution`
- IC 计算遵循 no-lookahead
- 样本不足输出 `null + reason`
- 旧绩效指标语义保持不变

---

## 7. 当前验证状态

当前分支最近一轮关键验证结论：

- `docker compose build dashboard` 可通过
- `docker compose run --rm dashboard sh -lc 'cd /app && PYTHONPATH=/app:/app/system/engine/src python -m pytest -q'` 可通过
- 最近一次通过结果为：
  - `263 passed, 19 subtests passed in 0.76s`

也就是说，之前 “dashboard runtime 镜像里没有 pytest” 这个阻塞，已经被修复。

---

## 8. 最近关键提交

近期与因子化完成度最相关的提交：

1. `8ecac3d refactor(factors): align builtin implementation contract`
2. `052655b build(dashboard): make runtime image pytest-ready`
3. `8ece806 feat(governance): add factor proposal quality gates`
4. `27ec769 feat(observability): enrich factor shadow health metadata`
5. `e7be3d5 feat(factors): extend shadow builtin coverage`
6. `27f64dc style(dashboard): make factor panels full width`

如果 GPT Pro 需要做近期差异分析，优先围绕这些提交建立上下文。

---

## 9. 希望 GPT Pro 重点分析的问题

请 GPT Pro 不要泛泛而谈“可以更模块化”，而是围绕下面这些问题给出具体结论：

1. 当前因子化设计是否已经形成完整闭环？
   - 契约闭环
   - 运行闭环
   - 治理闭环
   - 可观测性闭环
   - 回滚闭环

2. 当前设计还有哪些“隐藏的不一致”或“潜在半闭环”？
   - schema 与 runtime
   - registry 与 dashboard
   - proposal 与 applier
   - shadow runtime 与 attribution/backtest

3. 当前默认边界下，是否仍存在“因子间接影响交易热路径”的隐性风险？

4. 当前测试集是否足够支撑合并 `main`？
   - 哪些关键路径已覆盖
   - 哪些关键路径仍明显缺测试

5. 目前这套设计距离“可安全合入 main”还有哪几项阻塞？
   - 按严重度排序
   - 按修复成本排序

6. 如果只允许继续做最小侵入补完，下一阶段最值得做的 3 到 5 项是什么？

7. 当前 `factor-researcher` 冷路径设计是否足够安全？
   - write scope
   - approval/apply 边界
   - cron/live sync 边界

8. 当前 Factor Dashboard 展示层，是否已经足够支撑运维排障？
   - 如果不够，最小缺什么

---

## 10. 希望 GPT Pro 输出的格式

请 GPT Pro 输出尽量采用下面结构：

### A. 总结判断

- 当前设计成熟度结论
- 是否建议合并 `main`
- 是否建议继续补完后再合并

### B. Findings

按严重度排序：

- `critical`
- `high`
- `medium`
- `low`

每条 finding 尽量包含：

- 问题描述
- 为什么重要
- 对应文件
- 是否影响合并 `main`
- 最小修复建议

### C. 测试与验证评估

- 已覆盖
- 缺失覆盖
- 是否存在“测试通过但设计仍有风险”的地方

### D. 最小补完路线

只给 3 到 5 项最值得做的后续工作，按优先级排序。

---

## 11. 可直接粘贴给 GPT Pro 的 Prompt

```text
请把自己当作一个负责架构审计与合并评估的高级工程师，而不是继续无边界开发的 coding agent。

我会给你一个项目 `agent-trading` 的 factorization 分支 handoff。请你基于当前文档和代码，分析这套因子化设计是否已经完整、安全、可合并到 main。

请优先阅读这些文件：

1. docs/factorization-handoff-for-gpt-pro.md
2. docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md
3. docs/factor-system-contract.md
4. docs/factorization-merge-readiness.md
5. docs/factor-system-rollback.md
6. docs/factor-researcher-role-contract.md
7. specs/factor-registry-schema-v1.md
8. factors/registry.json
9. system/engine/src/engine/factors/catalog.py
10. system/engine/src/engine/factors/schema.py
11. system/engine/src/engine/factors/registry.py
12. system/engine/src/engine/factors/builtins.py
13. system/engine/src/engine/factors/engine.py
14. system/engine/src/engine/factors/store.py
15. system/engine/src/engine/factors/attribution.py
16. system/engine/src/engine/runtime.py
17. system/engine/src/engine/rule_schema.py
18. system/engine/src/engine/rule_engine.py
19. system/engine/src/engine/proposal_schema.py
20. system/engine/src/engine/applier.py
21. dashboard/main.py
22. dashboard/static/strategy.html

分析要求：

1. 判断当前因子化设计是否已经形成完整闭环：
   - 契约
   - 运行
   - 治理
   - 可观测性
   - 回滚

2. 找出仍然存在的隐藏风险、设计不一致、半闭环和测试盲区。

3. 重点判断：
   - 是否仍可能间接影响交易热路径
   - 是否已经满足安全合并 main 的条件
   - 如果不满足，阻塞项是什么

4. 不要泛泛地给“以后可以更模块化”这种空泛建议。
   请尽量给出：
   - 具体问题
   - 对应文件
   - 严重度
   - 是否阻塞 main merge
   - 最小修复建议

5. 默认安全边界不能随便打破：
   - 不要建议直接打开 live gate
   - 不要建议让 factor 直接默认驱动 BUY
   - 不要建议恢复 scheduler submit 权限
   - 不要建议把 factor-researcher 变成有 execution / broker 权限的 agent

输出格式请严格按以下结构：

A. 总结判断
B. Findings（按严重度排序）
C. 测试与验证评估
D. 最小补完路线（3-5项）
```

---

## 12. 备注

这份 handoff 文档的目标是让 GPT Pro 直接进入“分析 / 审计 / merge readiness review”模式，而不是重新猜项目边界。

如果 GPT Pro 给出的建议明显突破以下边界，应视为低质量建议：

- 默认不改交易行为
- 默认不打开 live
- 默认不让因子直接进入 actionable path
- Dashboard 保持只读
- factor-researcher 保持冷路径

