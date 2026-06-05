# Logs 目录

这是 `agent-trading` 的统一观测入口。

目标：

- 从项目根目录直接查看系统运行状态
- 统一汇总最新快照、审计日志、服务日志与调试总览
- 将“可巡检内容”与 `runtime/state`、`runtime/outbox` 这类运行状态文件分开

目录约定：

- `latest/`：最新快照
- `audit/`：系统行为审计日志
- `service/`：组件运行日志
- `agents/`：按 agent 聚合的运行日志（历史产物后续迁出）
- `manifests/`：索引与保留策略

当前调试时最有用的入口：

- `logs/latest/logs_overview.json`
  - 当前日志目录、各 section 文件、最新快照同步状态、agent 状态总览
- `logs/latest/agents_status.json`
  - watcher / newswire / strategist / executor / scout / closer 的输出与日志存在性
- `logs/latest/engine_cycle.json`
  - 最近一轮 engine cycle 快照
- `logs/latest/control_state.json`
  - 当前控制平面状态
- `logs/latest/execution_state.json`
  - 当前执行状态
- `logs/latest/market_context.json`
  - 当前市场上下文

Dashboard 调试接口：

- `/api/logs-list`
  - 列出可读日志文件
- `/api/logs/{name}`
  - 读取单个日志
- `/api/audit`
  - 查看近期审计记录
- `/api/logs-overview`
  - 生成并返回调试总览，同时刷新 `logs/latest/*.json`

详细设计见：

- `docs/runtime-observability-layout.md`
