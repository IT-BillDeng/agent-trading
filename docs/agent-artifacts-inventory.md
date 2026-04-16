# Agent Artifacts Inventory

更新时间：2026-04-16

## 目的

梳理 `agent-trading` 中各个 agent 当前会产生哪些文件、这些文件分别有什么用途、应该归类到：

- `logs/`
- `artifacts/`
- `runtime/state/`
- `runtime/outbox/`

同时评估 `agents/` 目录中的配置文件当前是否仍可作为可信配置来源。

本文档的目标不是直接修改代码，而是先冻结一份“产物语义清单”，作为后续目录整理、`agents/` 校准与 Dashboard 观测设计的依据。

---

## 一、分类原则

### 1. `logs/`

只放运行状态与诊断信息。

典型特征：

- 用于判断系统是否正常运行
- 以时间序列追加为主
- 内容偏“发生了什么”
- 适合巡检和排障

例如：

- `logs/audit/execution.jsonl`
- `logs/service/watcher.jsonl`

### 2. `artifacts/`

放 agent 的业务输出与历史产物。

典型特征：

- 是系统真正生成的“结果”
- 给其他 agent、Dashboard 或 Operator 消费
- 更偏“产出了什么”

例如：

- `artifacts/strategist/strategy_plan_latest.json`
- `artifacts/newswire/latest.json`
- `artifacts/strategist/iterations/*.json`

### 3. `runtime/state/`

放系统内部控制状态。

典型特征：

- 可变状态
- 不是日志
- 不是业务输出

例如：

- `control_state.json`
- `execution_state.json`
- `watcher_state.json`

### 4. `runtime/outbox/`

放待发送或待消费消息。

典型特征：

- 消息队列语义
- 不是日志
- 不是状态
- 也不是最终业务报告

例如：

- `closer_outbox.json`

---

## 二、当前 Agent 产物清单

下面的“建议目标位置”是语义上的目标，不代表代码已全部迁移完成。

### 1. `watcher`

职责：

- 系统健康检查
- 引擎运行状态巡检
- 风险/锁定状态观察

当前已知产物：

| 产物 | 当前路径 | 当前用途 | 建议归类 | 建议目标位置 |
|------|----------|----------|----------|--------------|
| watcher 运行日志 | `logs/service/watcher.jsonl` | 记录每次 watcher 检查结果 | `logs` | `logs/service/watcher.jsonl` |
| watcher 兼容旧日志 | `runtime/engine/logs/watcher_YYYYMMDD.jsonl` | 旧路径兼容 | `logs` | 兼容保留，后续下线 |
| watcher 最新结果 | `runtime/engine/watcher/latest.json` | 给人工/脚本读取最近检查结果 | `artifacts` | `artifacts/watcher/latest.json` |
| watcher 历史结果 | `runtime/engine/watcher/history.jsonl` | 结构化巡检历史 | `artifacts` | `artifacts/watcher/history.jsonl` |
| watcher 内部状态 | `runtime/engine/state/watcher_state.json` | 记录连续错误、冷却等内部状态 | `state` | `runtime/state/watcher_state.json` |

主要消费者：

- Operator
- Watcher 自身
- Dashboard（部分）

判断：

- `watcher.jsonl` 放在 `logs/` 是合理的
- `latest.json` / `history.jsonl` 不应放在 `logs/`

### 2. `newswire`

职责：

- 采集个股/宏观/行业新闻
- 输出结构化新闻输入给 Strategist 和 Dashboard

当前已知产物：

| 产物 | 当前路径 | 当前用途 | 建议归类 | 建议目标位置 |
|------|----------|----------|----------|--------------|
| 最新新闻批次 | `runtime/engine/newswire/latest.json` | 给 Strategist / Dashboard 读取当前新闻输入 | `artifacts` | `artifacts/newswire/latest.json` |
| 新闻历史 | `runtime/engine/newswire/history.jsonl` | 保存历次结构化新闻结果 | `artifacts` | `artifacts/newswire/history.jsonl` |
| 去重状态 | `runtime/engine/newswire/dedupe.json` | 防止重复扫描和重复写入 | `state` | `runtime/state/newswire_dedupe.json` |
| 上一版快照 | `runtime/engine/newswire/latest_prev.json` | 旧快照/对比用途 | `artifacts` | `artifacts/newswire/latest_prev.json` |

主要消费者：

- Strategist
- Dashboard
- Operator

判断：

- 这类内容本质是“情报产物”，不是 log
- 建议整体收进 `artifacts/newswire/`

### 3. `strategist`

职责：

- 生成策略计划
- 盘中异常监控
- 盘后迭代与参数回测

本节以 `artifacts/strategist/` 作为 strategist 的主产物目录；`runtime/engine/` 与 `logs/` 中的相关文件仅作为兼容镜像或历史遗留。

当前已知产物：

| 产物 | 当前路径 | 当前用途 | 建议归类 | 建议目标位置 |
|------|----------|----------|----------|--------------|
| 最新策略计划 | `artifacts/strategist/strategy_plan_latest.json` | 给 Operator / Dashboard 读取当前策略计划 | `artifacts` | `artifacts/strategist/strategy_plan_latest.json` |
| 策略计划历史 | `artifacts/strategist/strategy_plan_history.jsonl` | 保存历次策略计划 | `artifacts` | `artifacts/strategist/strategy_plan_history.jsonl` |
| 策略记忆最新摘要 | `artifacts/strategist/memory/latest.json` | strategist 当前记忆快照 | `artifacts` | `artifacts/strategist/memory/latest.json` |
| 策略记忆历史 | `artifacts/strategist/memory/history.jsonl` | strategist 长期学习记录 | `artifacts` | `artifacts/strategist/memory/history.jsonl` |
| 策略提案历史 | `artifacts/strategist/proposals.jsonl` | 变更提案记录 | `artifacts` | `artifacts/strategist/proposals.jsonl` |
| 策略拒绝历史 | `artifacts/strategist/rejections.jsonl` | 被拒绝提案记录 | `artifacts` | `artifacts/strategist/rejections.jsonl` |
| 策略迭代历史 | `artifacts/strategist/iterations/*.json` | 盘后回测与迭代记录 | `artifacts` | `artifacts/strategist/iterations/` |

主要消费者：

- Operator
- Strategist 自身
- Dashboard（潜在）

判断：

- `strategist` 的长期学习与迭代产物统一收进 `artifacts/strategist/`
- `strategist` 记忆统一收进 `artifacts/strategist/`
- 旧的镜像路径仅保留为兼容读写镜像，后续可逐步下线

### 4. `executor`

职责：

- 把计划转成执行检查单
- 对参数和执行条件做核验

当前已知产物：

| 产物 | 当前路径 | 当前用途 | 建议归类 | 建议目标位置 |
|------|----------|----------|----------|--------------|
| 最新检查单 | `runtime/engine/executor_checklist_latest.json` | 当前执行检查结果 | `artifacts` | `artifacts/executor/checklist_latest.json` |
| 检查单历史 | `runtime/engine/executor_checklist_history.jsonl` | 历史核验结果 | `artifacts` | `artifacts/executor/checklist_history.jsonl` |

主要消费者：

- Operator
- Executor

判断：

- 这类产物不是运行日志，应该进 `artifacts/`

### 5. `scout`

职责：

- 扫描候选标的
- 输出异常波动/候选结果

当前已知产物：

| 产物 | 当前路径 | 当前用途 | 建议归类 | 建议目标位置 |
|------|----------|----------|----------|--------------|
| 最新候选列表 | `runtime/engine/scout_candidates_latest.json` | 当前候选结果 | `artifacts` | `artifacts/scout/candidates_latest.json` |
| 候选历史 | `runtime/engine/scout_candidates_history.jsonl` | 历史扫描结果 | `artifacts` | `artifacts/scout/candidates_history.jsonl` |

主要消费者：

- Operator
- Scout

判断：

- 这类是标准业务产物，不应并入 `logs/`

### 6. `closer`

职责：

- 收盘总结
- 输出复盘与次日关注

当前已知产物：

| 产物 | 当前路径 | 当前用途 | 建议归类 | 建议目标位置 |
|------|----------|----------|----------|--------------|
| 最新收盘总结 | `runtime/engine/closer_summary_latest.json` | 当前市场收盘总结 | `artifacts` | `artifacts/closer/summary_latest.json` |
| 收盘总结历史 | `runtime/engine/closer_summary_history.jsonl` | 历史收盘总结 | `artifacts` | `artifacts/closer/summary_history.jsonl` |
| 待发送消息 | `runtime/outbox/closer_outbox.json` | 待发送或待消费消息 | `outbox` | `runtime/outbox/closer_outbox.json` |

主要消费者：

- Operator
- Telegram / message delivery
- Closer

判断：

- `summary_*` 应归到 `artifacts`
- `outbox` 应继续保留在 `runtime/outbox/`

---

## 三、当前共享系统产物

这些不是某一个 agent 独占，但会被多个 agent 依赖。

| 产物 | 当前路径 | 作用 | 建议归类 | 建议目标位置 |
|------|----------|------|----------|--------------|
| 最近引擎周期 | `runtime/engine/.last_execution_cycle.json` | 作为 watcher / strategist / closer / scout 的共同输入 | `state` 或 `latest snapshot` | 可保留在 `runtime/state/`，也可镜像到 `logs/latest/engine_cycle.json` |
| market context | `runtime/engine/market_context.json` | 共享上下文 | `artifacts` 或 `latest snapshot` | 建议镜像到 `logs/latest/market_context.json` |
| control state | `runtime/engine/state/control_state.json` | 控制平面状态 | `state` | `runtime/state/control_state.json` |
| execution state | `runtime/engine/state/execution_state.json` | 执行与去重状态 | `state` | `runtime/state/execution_state.json` |

---

## 四、`agents/` 目录当前是否可信

结论：

> `agents/` 目录仍然有用，但不能视为当前系统行为的唯一可信来源。

### 仍然有用的部分

| 文件类型 | 用途 | 价值 |
|----------|------|------|
| `*.yaml` | 记录每个 agent 的职责、输入输出、工具权限 | 有价值，但需要校准 |
| `deploy_*.sh` / `stop_*.sh` | 部署/停止 subagent 的运维脚本 | 有操作价值 |
| `README.md` | 人类可读入口文档 | 有价值 |

### 已出现漂移的部分

| 文件 | 问题 |
|------|------|
| `agents/strategist.yaml` | `backtest_endpoint` 仍指向 `/api/backtest`，与当前 batch 迭代方向不一致 |
| `agents/watcher.yaml` | 输入日志路径仍指向旧 `runtime/engine/logs/*` |
| `agents/README.md` | 旧的停止脚本入口已移除，改为直接使用 `subagents action=kill` |
| 多个 `*.yaml` | 输出文件仍大多指向旧 `runtime/engine/...` 路径，尚未反映新的 `logs/` 入口或未来的 `artifacts/` 设计 |

### 当前建议定位

建议把 `agents/` 目录定位为：

- `有用的配置与运维参考目录`
- `但需要校准`

不建议直接把它当成：

- 当前运行真相的唯一来源

当前更接近真实运行状态的来源是：

- `cron/`
- `dashboard/main.py`
- `system/engine/src/engine/*`
- `logs/`
- `runtime/state/`
- `runtime/engine/` 中仍未迁移的历史产物

---

## 五、建议下一步

建议按下面顺序继续推进：

1. 先冻结一套目录语义：
   - `logs/` 只放运行状态与诊断
   - `artifacts/` 放 agent 业务产物
   - `runtime/state/` 放控制状态
   - `runtime/outbox/` 放待发送消息
2. 逐个 agent 迁移产物：
   - `watcher`：已开始把运行日志迁到 `logs/service/`
   - `strategist`：应把 `iterations` 从 `logs/` 迁到未来的 `artifacts/strategist/`
   - `newswire / scout / executor / closer`：后续统一迁到 `artifacts/`
3. 再回头校准 `agents/*.yaml` 与 `agents/README.md`

---

## 六、结论

当前系统里，各 agent 的产物确实有各自独立用途。

因此后续目录整理不应只围绕“日志路径”展开，而应先明确：

- 这是不是日志
- 这是不是业务产物
- 这是不是内部状态
- 这是不是消息队列

从这个角度看：

- `logs/` 应聚焦“运行状态与诊断”
- `artifacts/` 应承接 agent 的业务输出
- `agents/` 目录当前仍有用，但需要校准后才能恢复为可信配置目录
