# GPT Pro 项目交接文档

更新时间：2026-04-20

这份文档的目标是把 `agent-trading` 当前项目状态压缩成一份可直接交给 GPT Pro 的单文件说明，减少它在旧文档、历史路径和多层目录契约之间来回跳转的成本。

这不是“愿景文档”，而是**当前实现 + 当前约束 + 当前问题**的交接说明。  
如果与更早期文档发生冲突，请优先以本文件列出的真相源为准。

---

## 1. 一句话概述

`agent-trading` 是一个以 **Engine 负责机械执行**、**agent 负责判断与治理** 为核心原则的 paper-trading 自动化项目。

当前系统已经具备：

- 基于规则引擎的信号生成
- 风控、订单预览、受控提交、状态同步
- Dashboard 可视化
- `watcher / newswire / strategist / closer / applier` 等岗位化 agent
- strategist 的 `L3a` 代码提案能力
- strategist `L3b` 的最小审批/应用治理骨架
- broker-specific 手续费模型、真实费用校准与 fee confidence 反馈链

当前系统**还没有**进入“自动 live 发布”或“完全自治的策略工程师”状态。

---

## 2. 先读哪些文件

如果 GPT Pro 需要分析当前项目，请按下面顺序建立上下文。

### 第一层：当前真相源

1. `docs/project-handoff-for-gpt-pro.md`
2. `docs/orchestration-directory-contract.md`
3. `docs/strategist-capability-contract.md`
4. `docs/strategist-l3-evolution-plan.md`
5. `docs/strategist-l3b-approval-contract.md`
6. `docs/tasks/STRATEGIST_TASK.md`
7. `specs/strategist-output-schema-v1.md`
8. `rules/rules.json`
9. `config/app.defaults.json`
10. `agents/strategist.yaml`

### 第二层：实现层入口

1. `system/engine/src/engine/rule_engine.py`
2. `system/engine/src/engine/strategy.py`
3. `system/engine/src/engine/indicators.py`
4. `system/engine/src/engine/backtest.py`
5. `system/engine/src/engine/strategist_artifacts.py`
6. `system/engine/src/engine/applier.py`
7. `dashboard/main.py`
8. `dashboard/static/strategy.html`

### 第三层：辅助理解

1. `docs/broker-fee-model.md`
2. `docs/agent-artifacts-inventory.md`
3. `docs/runtime-observability-layout.md`
4. `docs/notification-routing-contract.md`
5. `cron/SYNC_TO_LIVE.md`
6. `FIX_TASKLIST.md`

### 应谨慎对待的历史文档

- `PROJECT_PLAN.md`
  - 有参考价值，但存在部分历史口径，不能单独当作当前真相源
- 根目录 `README.md`
  - 适合作为概览，不适合作为策略/权限/目录边界的最终依据

### 安全打包建议

如果需要把当前项目交给外部模型或外部审查方，请优先使用：

- `scripts/make_safe_handoff.sh`

这个脚本会生成一个安全 zip，只保留：

- `docs/`
- `rules/`
- `config/app.defaults.json`
- `config/app_config.docker.json`
- `config/*.example.json`
- `agents/`
- `cron/`
- `system/engine/src/`
- `system/engine/tests/`
- `dashboard/`

并显式排除：

- `.env`
- `.env.*`
- `properties/*`
- `runtime/*`
- `logs/latest/execution_state.json`
- `logs/latest/control_state.json`
- `artifacts/broker/*`
- `*.pem`
- `*.key`
- `*token*`
- `*secret*`

也就是说，这份 handoff 包适合交给 GPT Pro 或外部审查者做结构与代码分析，但**不应**包含真实凭据、broker properties、运行态 state 或 broker 费用校准原始数据。

---

## 3. 项目设计原则

项目当前最核心的原则有 6 条：

1. **信号由 Engine 代码产生，agent 不直接“拍脑袋出信号”**
2. **strategist 管理规则与策略演化，不直接下单**
3. **参数更新和代码提案必须经过验证链**
4. **subagent 不直发 Telegram，由主 agent 做二次判断**
5. **运行日志、业务产物、内部状态必须分目录治理**
6. **当前默认是 paper + guarded，不直接进入 live 自动交易**

可以把系统理解成两条路径：

### 热路径：机械执行链

```text
行情数据 -> 规则引擎 -> 信号 -> 风控 -> 订单预览/提交 -> 同步状态 -> Dashboard
```

### 冷路径：agent 治理链

```text
newswire / watcher / strategist / closer -> 产出 artifacts/logs -> 主 agent 汇总判断
```

---

## 4. 当前目录语义

目录职责以 `docs/orchestration-directory-contract.md` 为准。最重要的边界如下：

### `cron/`

作用：**调度声明**

包含：

- 任务名
- cron 表达式
- 时区
- 模型
- `taskFile`

不包含：

- 任务正文
- 运行记录
- 业务产物

### `agents/`

作用：**角色配置与权限边界**

包含：

- agent 使用的模型
- 允许的工具
- input/output files
- write scopes / protected paths

### `docs/tasks/`

作用：**任务正文**

包含：

- 执行步骤
- 输入/输出要求
- 禁止事项
- 汇报要求

`docs/tasks/cron/` 专门存放 cron 任务正文。

### `logs/`

作用：**运行状态与诊断**

只用于：

- 审计
- 服务运行日志
- 最新状态快照
- Dashboard 诊断页

### `artifacts/`

作用：**agent 业务产物与学习成果**

例如：

- `artifacts/newswire/*`
- `artifacts/strategist/*`
- `artifacts/closer/*`
- `artifacts/watcher/*`
- `artifacts/broker/*`

### `runtime/state/`

作用：**内部控制状态**

例如：

- 去重
- 锁定
- 冷却
- 执行态

### `runtime/outbox/`

作用：**待发送 / 待消费消息**

---

## 5. 当前配置体系

当前配置已做分层，避免把用户态、Docker 覆盖和默认配置混在一个文件里。

### 主配置层

- `config/app.defaults.json`
  - 项目默认配置
- `config/app_config.docker.json`
  - Docker/容器覆盖层
- `config/user.settings.json`
  - 本地用户设置，不进 git
- `.env`
  - 敏感变量和本地环境变量

### 配置优先级

```text
app.defaults.json
  <- app_config.docker.json
  <- user.settings.json
  <- environment variables
```

### 当前关键配置事实

从 `config/app.defaults.json` 看，当前默认状态是：

- `mode = paper`
- `broker.platform = tiger`
- `strategy.timeframe = 30min`
- `strategy.use_rule_engine = true`
- `execution.submit_mode = guarded`
- `execution.live_submit = false`
- `notify.telegram_target = ${ENGINE_TELEGRAM_TARGET}`

即：

- 项目当前仍然以 Tiger 为默认 broker 平台
- 但文档和架构已经朝 broker-neutral 演进
- 当前不会默认进入真正 live submit

---

## 6. 当前运行架构

系统运行中最重要的三个层次：

### 6.1 Engine

负责：

- 读取配置
- 拉行情/读持仓/读订单
- 规则引擎评估
- 风控
- 订单预览/提交
- 状态同步

关键代码：

- `system/engine/src/engine/strategy.py`
- `system/engine/src/engine/rule_engine.py`
- `system/engine/src/engine/risk.py`
- `system/engine/src/engine/live_execution.py`
- `system/engine/src/engine/sync.py`
- `system/engine/src/engine/backtest.py`

### 6.2 Dashboard

负责：

- 提供 API
- 承载主可视化页面
- 暴露回测、策略、日志、配置等接口

关键页面：

- `/`
- `/strategy`
- `/logs`

### 6.3 Agent orchestration

通过 `cron/` + `docs/tasks/cron/*.md` + `agents/*.yaml` 驱动各个 subagent。

当前已被清理过的关键点：

- `taskFile` 使用绝对路径锚定到 `/workspace/agent-trading/...`
- 仓库中的 `cron/*.json` 不再持有 `enabled` 和 `id`
- live 环境启停由主 agent 对齐管理

---

## 7. 当前策略系统

这是 GPT Pro 最需要理解的部分。

### 7.1 策略是谁产生的

**信号不是 strategist 自己生成的，而是 Engine 代码根据规则生成的。**

也就是说：

- strategist 不直接输出 `BUY / EXIT`
- strategist 管的是：
  - 当前有哪些规则
  - 这些规则是否启用
  - 参数是多少
  - 哪些该暂停/恢复
  - 是否提出代码级新策略提案

### 7.2 当前规则层真相源

真相源是：

- `rules/rules.json`

当前规则状态：

1. `trend_follow_30m`
   - `enabled: false`
   - 30 分钟趋势跟随
   - 基于 SMA、momentum、bar range
   - 有 `search_space`

2. `rsi_reversal`
   - `enabled: true`
   - RSI 超卖反转

3. `bollinger_breakout`
   - `enabled: true`
   - 布林带上轨突破 + 成交量放大

### 7.3 策略代码层真相源

实现层主要在：

- `system/engine/src/engine/strategy.py`
- `system/engine/src/engine/rule_engine.py`
- `system/engine/src/engine/indicators.py`

需要注意：

- `strategy.py` 是较传统的信号引擎入口
- 当前项目已经明显向 `rule_engine` 驱动演进
- strategist 的代码提案白名单，也主要指向这三个文件

### 7.4 策略时间框架

当前默认时间框架是：

- `30min`

虽然很多文档会提未来多周期，但当前正式运行事实仍以 30 分钟为核心。

### 7.5 新策略能力的当前状态

当前项目已经支持：

- 调整现有策略参数
- 启停现有策略
- 新增代码型策略提案

例如最近已经进入代码层的能力包括：

- `ema_slope` 指标
- `ema_slope_momentum` 方向的测试/提案能力

但要强调：

- **“支持写代码提案” != “已经默认上线了新策略”**
- 当前 strategist 仍是受治理的研发角色，不是自由发布者

---

## 8. strategist 当前等级与能力

当前 strategist 的正式等级是：

- **L3a**

真相源：

- `docs/strategist-capability-contract.md`
- `agents/strategist.yaml`

### L3a 允许的能力

- 读取长期记忆
- 调参
- 启停/暂停/恢复规则
- 调回测 API
- 修改白名单目录中的策略代码和测试
- 执行验证链
- 生成代码变更提案
- 写策略记忆、提案、拒绝记录

### L3a 明确不允许

- 直接下单
- 自动上线 live
- 修改 broker / execution / deploy / infra
- 扩大股票池
- 绕过验证链

### strategist 白名单目录

允许写：

- `rules/`
- `system/engine/src/engine/strategy.py`
- `system/engine/src/engine/rule_engine.py`
- `system/engine/src/engine/indicators.py`
- `system/engine/tests/`
- `tests/`
- `specs/`
- `artifacts/strategist/`

禁止碰：

- `live_execution.py`
- `broker_client.py`
- `tiger_client.py`
- `notifier.py`
- `dashboard/`
- `docker-compose.yml`

---

## 9. strategist 的三层更新机制

这是当前项目里最重要的治理结构之一。

### 9.1 规则层更新（L2/L3a 共同支持）

特点：

- 调整现有规则参数
- enable / disable / pause / resume
- 更新 `rules/rules.json`
- 必须经过回测验证

这是**热更新优先**的部分。

### 9.2 代码提案层更新（L3a）

特点：

- 改策略代码或指标逻辑
- 改策略测试
- 产出 proposal/result/rollback 产物
- 不能自动上线

关键文档：

- `docs/tasks/STRATEGIST_CODE_CHANGE_TASK.md`

关键 artifacts：

- `artifacts/strategist/code_change_proposals.jsonl`
- `artifacts/strategist/code_change_results.jsonl`
- `artifacts/strategist/rollback_notes.jsonl`

### 9.3 审批与应用层（L3b 最小骨架）

项目已经具备最小 `L3b` 治理骨架，但还不等于 fully autonomous。

当前已存在：

- `artifacts/strategist/approval_queue/`
- `artifacts/strategist/approval_decisions.jsonl`
- `artifacts/strategist/deployment_records.jsonl`
- 审批状态机
- hot/cold apply gate
- 最小 `applier`

关键实现：

- `system/engine/src/engine/strategist_artifacts.py`
- `system/engine/src/engine/applier.py`

### 当前审批状态机

```text
draft -> validated -> awaiting_approval -> approved -> applied
```

或：

```text
draft / validated / awaiting_approval -> rejected
```

### 更新模式

- `hot`
  - 只改 `rules/`
  - 不需要 restart
- `cold`
  - 改策略代码
  - 默认需要 restart

### 当前角色分工

- `strategist`
  - 研究、验证、提案
- `人工或主 agent`
  - 审批
- `applier`
  - 应用已批准更新
- `executor`
  - 不负责代码发布

---

## 10. strategist 的记忆系统

当前项目已经把 strategist 记忆从“根目录自由格式 learning_log”收口为正式结构化产物。

真相源：

- `docs/strategist-memory-contract.md`
- `artifacts/strategist/README.md`

关键落点：

- `artifacts/strategist/memory/latest.json`
- `artifacts/strategist/memory/history.jsonl`
- `artifacts/strategist/proposals.jsonl`
- `artifacts/strategist/rejections.jsonl`
- `artifacts/strategist/iterations/`

这意味着：

- strategist 的“自我进化”依赖显式可审计记忆
- 不依赖聊天上下文式隐式记忆

---

## 11. 手续费 / 成本模型

当前项目已经把“净收益优先”接入 strategist 评估口径。

真相源：

- `docs/broker-fee-model.md`
- `config/broker_fee.tiger.json`
- `system/engine/src/engine/backtest.py`

### 当前已实现

1. broker-specific 静态 fee model（Tiger 最小 US 模型）
2. 回测结果带：
   - `commission_total`
   - `slippage_total`
   - `transaction_cost_total`
   - `fee_drag_pct`
3. Dashboard `/strategy` 页面展示 fee drag
4. 同步链读取 broker 真实 `charges`
5. 费用校准写入：
   - `artifacts/broker/fee_calibration.jsonl`
   - `artifacts/broker/fee_calibration_summary.json`
6. strategist 盘后读取 fee calibration summary，并输出：
   - `fee_model_confidence`

### 这意味着什么

strategist 当前不再只比较毛收益，而是应优先比较：

- `return_pct`
- `sharpe`
- `max_drawdown`
- `win_rate`
- `fee_drag_pct`

并且在真实费用偏差过大时，应降低对静态净收益结论的信任度。

---

## 12. 当前通知架构

当前通知设计已经收口过一次。

真相源：

- `docs/notification-routing-contract.md`

当前原则：

- subagent **不直发 Telegram**
- subagent 先写产物并向主 agent 汇报
- 主 agent 再做二次判断
- 是否外发 Telegram 由主 agent 决定

这套设计的好处：

- 通知去重
- 通知标准统一
- 避免每个 subagent 自己噪音化

---

## 13. Dashboard 当前页面结构

主要页面：

- `/`
  - 总览页
- `/strategy`
  - 策略中心
- `/logs`
  - 日志与诊断

### `/strategy` 当前职责

这是分析 strategist 和策略系统最重要的页面。

它当前承载：

- 启用/停用策略
- 股票与策略触发信号
- strategist 最新调整
- strategist 时间线
- 回测结果
- 手续费拖累
- broker fee calibration
- fee model confidence

### `/logs` 当前职责

- 运行日志
- latest snapshots
- 诊断入口

### 首页 `/`

当前首页已被收口成总览页，不再承担完整回测分析职责。

---

## 14. 当前 agent 与 cron 设计

当前 cron 设计原则：

- `cron/*.json` 只保留调度声明
- 任务正文在 `docs/tasks/cron/*.md`
- `taskFile` 使用绝对路径 `/workspace/agent-trading/...`

strategist 当前三段式调度：

1. `trading-strategist-premarket`
   - `09:05 ET`
   - 模型：`openai-codex/gpt-5.4`
2. `trading-strategist-intraday`
   - `1h`
   - 模型：`openai-codex/gpt-5.4-mini`
3. `trading-strategist-afterhours`
   - `16:30 ET`
   - 模型：`openai-codex/gpt-5.4`

这三段职责不同：

- 盘前：复盘 + 准备
- 盘中：监控 + 暂停/恢复
- 盘后：分析 + 提案 + 记忆沉淀

---

## 15. 当前 canonical 输出边界

项目已经显式收紧过“不要乱写产物路径”。

当前原则：

- 运行日志 -> `logs/`
- 业务产物 -> `artifacts/`
- 内部状态 -> `runtime/state/`
- outbox -> `runtime/outbox/`
- 不允许写：
  - 根目录 `memory/`
  - `docs/`
  - `cron/`
  - `agents/`
  - 任务正文自身

这条边界已对：

- subagent
- main agent

都做过约束收口。

---

## 16. 当前实现到了哪一步，没到哪一步

### 已经比较扎实的部分

- 配置分层
- cron / taskFile 契约
- artifacts / logs / runtime 边界
- strategist L3a 契约
- strategist L3b 最小治理骨架
- broker fee model
- fee calibration summary
- Dashboard `/strategy` 可视化

### 还没完全完成的部分

1. strategist 被阻塞的问题仍在任务清单中
   - 见 `FIX_TASKLIST.md`
2. runtime 各目录仍有部分历史兼容路径
3. Engine / Dashboard 结构仍偏集中
4. `L3b` 有治理骨架，但不等于自动提交流程完全成型
5. `L3c` 自动发布完全未开启，也不建议近期开启

---

## 17. GPT Pro 分析时最值得关注的问题

如果把项目交给 GPT Pro 分析，最推荐它围绕这几个问题展开：

### 1. strategist 的真实卡点是什么

不是泛泛而谈“能不能进化”，而是具体问：

- 当前 L3a / L3b 骨架还缺哪一段实现闭环
- strategist 当前最实际的阻塞点是什么

### 2. rule_engine 与 strategy.py 的双轨关系是否需要继续收口

项目已经明显向 `rule_engine` 演进，但 `strategy.py` 仍然存在并参与能力白名单。  
值得 GPT Pro 判断：

- 是否继续双轨
- 还是进一步统一到 rule engine

### 3. strategist 的新增策略能力应如何治理

尤其是：

- 新策略从 proposal 到 rule activation 的流程
- 何时需要代码级新策略，何时只应调参

### 4. L3b 是否应该进一步产品化

已有：

- approval queue
- status machine
- apply gate
- applier

但还缺：

- 更明确的审批入口
- 更清晰的人工/上层 agent 工作流

### 5. fee confidence 是否应该进一步影响策略选择

当前已经读入 strategist 输出，但可以继续分析：

- 费率偏差达到什么阈值应冻结大改动
- 是否需要把低可信度直接变成策略调整闸门

### 6. Dashboard 信息架构是否还需要继续收口

尤其：

- 首页 vs `/strategy` vs `/logs`
- 哪些应该继续下沉
- 哪些应该保留在首页

---

## 18. 建议 GPT Pro 不要误判的几点

1. **不要把 strategist 理解成“自由生成信号的交易员”**
   - 当前它仍然是策略治理者，不是直接信号源

2. **不要把已存在的 L3b 文档骨架误判成 fully autonomous deploy**
   - 当前只是治理骨架，不是自动发布系统

3. **不要把 Tiger 默认平台误判成 Tiger-only 架构**
   - 当前默认平台是 Tiger
   - 但项目叙事和一部分抽象已向 broker-neutral 迁移

4. **不要把旧文档中的历史路径、旧频率、旧命名直接当作当前真相**
   - 必须优先使用本文件第 2 节列出的真相源

5. **不要把根目录临时目录视为正式设计**
   - 例如根目录 `memory/` 已被明确移除并判定为非 canonical

---

## 19. 推荐给 GPT Pro 的分析任务

如果要把这份文档交给 GPT Pro，建议直接让它做这几类输出：

1. 当前项目架构评审
2. strategist 从 L3a 走向稳态 L3b 的具体实施建议
3. 当前策略系统的潜在设计缺陷
4. rule engine / strategy engine 的统一建议
5. fee confidence 如何纳入更正式的策略审批
6. Dashboard 信息架构优化建议
7. 当前最应该优先修复的 3 个工程问题

---

## 20. 最终结论

当前 `agent-trading` 已经不是一个“只有简单 cron + 脚本”的原型，而是一个具备以下特征的系统：

- 有明确目录契约
- 有明确 agent 职责
- 有 strategist 自我迭代能力
- 有代码提案和审批治理骨架
- 有净收益与手续费可信度闭环
- 有 Dashboard 作为主观察入口

但它仍处在：

- **可治理的半自治阶段**

而不是：

- **完全自治的自动发布型交易系统**

如果 GPT Pro 要帮助当前项目，最有价值的方向不是“再讲一遍愿景”，而是：

- 找出当前真正的卡点
- 识别哪些双轨/重复设计该收口
- 帮 strategist 从“会提案”走向“稳定受控地演进”
