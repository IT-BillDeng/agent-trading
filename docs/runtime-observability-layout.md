# Runtime Observability / Log 目录设计

更新时间：2026-04-16

## 目的

为 `agent-trading` 建立一套更清晰的运行期观测目录规范，解决当前：

- 日志、状态、agent 产物混放
- 同类信息散落在多个目录
- 巡检系统状态时缺少统一入口
- `runtime/engine/` 与 `runtime/engine/tiger_engine/` 存在路径漂移

本文档的核心建议是：

> 在项目根目录新增统一观测入口：`logs/`

以后所有“为了看系统是否正常运行而读取的内容”，都尽量从这里进入。

---

## 一、当前现状

当前仓库内已经存在运行期记录，但边界并不统一。

### 1. 审计日志

当前主要位于：

- `runtime/engine/logs/execution.jsonl`
- `runtime/engine/logs/dispatch_queue.jsonl`

代码来源：

- `system/engine/src/engine/audit.py`
- `system/engine/src/engine/runtime.py`

这类文件更像“系统行为审计日志”。

### 2. 组件日志

当前可见：

- `runtime/engine/logs/watcher_YYYYMMDD.jsonl`

代码来源：

- `system/engine/src/engine/watcher.py`

这类文件更像“组件运行日志 / 健康检查日志”。

### 3. Agent 历史输出

当前分散在：

- `runtime/engine/newswire/history.jsonl`
- `runtime/engine/watcher/history.jsonl`
- `runtime/engine/strategy_plan_history.jsonl`
- `runtime/engine/executor_checklist_history.jsonl`
- `runtime/engine/scout_candidates_history.jsonl`
- `runtime/engine/strategist_iterations/*.json`

这类文件不是传统 log，更接近“结构化业务产物历史”。

### 4. 状态快照

当前分散在：

- `runtime/engine/.last_execution_cycle.json`
- `runtime/engine/state/control_state.json`
- `runtime/engine/state/execution_state.json`
- `runtime/engine/market_context.json`

这类文件不是日志，而是“当前状态 / 最新快照”。

### 5. 其他运行产物

例如：

- `runtime/outbox/closer_outbox.json`
- `runtime/state/watcher_state.json`

说明当前还存在运行目录职责边界不完全统一的问题。

---

## 二、设计目标

新的目录规范应满足：

1. 有一个统一入口，方便人工巡检
2. 明确区分：
   - 审计日志
   - 组件日志
   - 最新状态
   - agent 历史产物
   - 运行控制状态
3. 文件名和目录名能表达“用途”，而不是只能靠上下文猜
4. Dashboard、cron、subagent、engine 后续都能复用同一规范
5. 保留 JSON / JSONL 为主，方便机器读取和后续可视化

---

## 三、推荐高一级总入口

建议新增：

```text
logs/
```

它的职责不是替代全部运行目录，而是成为“系统巡检总入口”。

也就是说：

- `runtime/state/` 仍然保留控制态
- `runtime/outbox/` 仍然保留待发送产物
- 但凡是“需要被看、被查、被诊断”的内容，尽量归拢到根目录 `logs/`

---

## 四、推荐目录结构

建议目标结构如下：

```text
logs/
  latest/
    engine_cycle.json
    market_context.json
    control_state.json
    execution_state.json
    agents_status.json
    logs_overview.json

  audit/
    cycles.jsonl
    strategy.jsonl
    risk.jsonl
    intents.jsonl
    notifications.jsonl
    dispatch_queue.jsonl
    execution.jsonl

  service/
    scheduler.jsonl
    watcher.jsonl
    dashboard.jsonl

  agents/
    strategist/
      run.jsonl
      strategy_plan_history.jsonl
      iterations/
    newswire/
      run.jsonl
      history.jsonl
    watcher/
      run.jsonl
      history.jsonl
    executor/
      run.jsonl
      checklist_history.jsonl
    scout/
      run.jsonl
      candidates_history.jsonl
    closer/
      run.jsonl
      summary_history.jsonl

  manifests/
    log_index.json
    retention_policy.json
    sources.json

runtime/
  state/
    control_state.json
    execution_state.json
    watcher_state.json

  outbox/
    closer_outbox.json
```

---

## 五、目录职责定义

### 1. `logs/latest/`

放“最新状态快照”。

适合人工第一眼查看：

- 最近一轮引擎执行结果
- 当前 market context
- 当前 control / execution 状态
- 当前 agents 状态
- 当前 logs 总览

特点：

- 只保留最新版本
- 文件名固定
- 可直接被 Dashboard 或 CLI 巡检脚本消费

### 2. `logs/audit/`

放“系统行为审计日志”。

适合回答：

- 这一轮产生了哪些 signal
- 风控为何放行 / 阻断
- 订单意图是否被提交
- 通知是否进入 dispatch queue

特点：

- 统一 JSONL
- 一行一条结构化记录
- 主要由 engine 代码自动写入

### 3. `logs/service/`

放“组件运行日志”。

适合回答：

- scheduler 有没有报错
- watcher 本轮检查发生了什么
- dashboard 服务启动或刷新时是否异常

特点：

- 偏服务运行层
- 允许带 `level`
- 与审计日志分开，避免行为记录和报错混在一起

### 4. `logs/agents/`

放“agent 级运行日志”。

适合回答：

- strategist 这一轮是否触发
- newswire 本轮是否跳过
- closer 是否成功生成总结

注意：

- 这里存的是“运行日志”
- 不是最终业务产物本身

### 5. `logs/agents/<agent_name>/`

既放 agent 运行日志，也放对应的结构化业务历史产物。

例如：

- newswire 历史结果
- strategist 计划历史与迭代结果
- watcher 历史检查结果
- executor checklist 历史

特点：

- 一个 agent 一处目录
- 便于人工巡检
- 便于后续按 agent 做 retention 和索引

### 6. `runtime/state/`

放“系统控制状态”。

例如：

- control plane 状态
- execution 状态
- watcher 内部状态

这类内容不建议混入 log 目录，因为它们是可变状态，不是时间序列日志。

### 7. `runtime/outbox/`

放“待发送 / 待消费产物”。

例如：

- closer 待发消息
- 未来可能的通知 outbox

这类目录也不建议并入 log 目录，因为它们承担的是消息流转职责。

---

## 六、推荐日志分类规范

后续建议统一把“日志”至少分成以下三类：

### A. 审计日志

关注系统做了什么。

示例：

- cycle
- strategy
- risk
- intents
- execution
- notifications

### B. 组件日志

关注系统运行得是否正常。

示例：

- scheduler
- watcher
- dashboard
- quote provider

### C. Agent 运行日志

关注 agent 本轮是否执行成功。

示例：

- strategist
- newswire
- closer
- scout
- executor

### D. 业务产物历史

严格说不是 log，但必须纳入观测体系。

示例：

- strategy plan history
- strategist iterations
- newswire history
- watcher history

---

## 七、命名建议

### 1. 文件命名

优先使用稳定语义名，而不是临时名：

- 推荐：`execution.jsonl`
- 推荐：`strategy.jsonl`
- 推荐：`watcher.jsonl`
- 不推荐：`log1.json`
- 不推荐：`latest_log.json`

### 2. 时间策略

默认优先：

- 审计日志：长期追加写入同一个 JSONL 文件
- 服务日志：按天切分，例如 `watcher-20260416.jsonl`
- 历史产物：按固定名字的 `history.jsonl` 或单轮 `iter_*.json`

### 3. 时间字段

所有结构化记录统一建议带：

- `ts`
- `source`
- `kind`
- `run_id` 或 `cycle_id` 或 `iteration_id`

---

## 八、建议新增的总览文件

为了方便“视察系统运行状态”，建议在 `logs/` 下增加两个总览文件：

### 1. `logs/latest/agents_status.json`

建议汇总：

- 每个 agent 最近一次更新时间
- 最近状态：`ok / skipped / warning / failed`
- 最近输出文件路径
- 最近错误摘要

### 2. `logs/latest/logs_overview.json`

建议汇总：

- `logs_root` / `latest_dir`
- `audit / service / legacy` 三类日志的存在性、修改时间、最近时间戳
- `engine_cycle / market_context / control_state / execution_state` 的同步状态
- `agents_status.json` 的路径与摘要

这样人工排障时，只要先看这一份文件，就能知道该往哪一层继续钻。

### 3. `logs/manifests/log_index.json`

建议汇总：

- 当前有哪些日志文件
- 每类日志对应的写入模块
- 每类日志的用途
- Dashboard 可否直接查看

这样做的好处是：

- 你不需要记忆目录
- 管理脚本、巡检脚本、Dashboard 都可以从这里发现文件

---

## 九、迁移建议

建议分三步做，不要一次性硬迁：

### Step 1：先建立规范与映射

先新增根目录 `logs/`，但允许底层实现暂时仍写旧路径。

先完成：

- 文档明确
- manifest 明确
- Dashboard/巡检脚本知道“看哪里”

### Step 2：新写入统一走新目录

对新增功能或新日志，直接写到：

- `logs/audit/...`
- `logs/service/...`
- `logs/agents/...`
- `logs/latest/...`

当前已经落地的 `logs/latest` 文件包括：

- `engine_cycle.json`
- `market_context.json`
- `control_state.json`
- `execution_state.json`
- `agents_status.json`
- `logs_overview.json`

### Step 3：逐步迁移旧路径

逐步把：

- `runtime/engine/logs/*`
- `runtime/engine/newswire/*`
- `runtime/engine/watcher/*`
- `runtime/engine/strategy_plan_*`

迁到根目录 `logs/` 结构下，并保留一段时间兼容读取。

---

## 十、当前建议

就当前项目阶段，我建议优先做这三件事：

1. 在 `docs/` 中冻结本规范
2. 在项目根目录引入 `logs/` 作为统一巡检入口
3. 后续把 `Phase 2.3` 和 `Phase 3.1` 以这份规范为准推进

如果只做最小一步，也建议先做到：

```text
logs/
  latest/
  audit/
  service/
  agents/
```

这已经能显著改善系统可观测性。

---

## 十一、结论

当前项目不是没有 log，而是：

- 已经有日志
- 也有状态快照
- 还有 agent 历史产物
- 但缺少统一的观测入口和分类规则

因此，建议不是“补一个日志文件”，而是：

> 建立项目根目录 `logs/` 作为更高一级的总入口目录，
> 统一管理日志、最新状态和 agent 历史产物，提升系统巡检与问题排查效率。
