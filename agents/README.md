# Agent Trading Subagents

本目录包含 Agent Trading 项目的 6 个 subagent 配置文件。

统一的目录职责规范见：[docs/orchestration-directory-contract.md](../docs/orchestration-directory-contract.md)

当前建议把 `agents/` 理解为：

- OpenClaw subagent 的参考配置目录
- 当前 agent 职责与 I/O 的近似说明

它仍然有用，但不是系统运行时的唯一真相来源。当前真实状态还需要结合以下位置一起判断：

- `cron/`：谁在什么时点触发
- `docs/tasks/cron/`：cron 任务正文
- `docs/tasks/` 与 `docs/roles/`：agent 实际执行模板与上下文
- `logs/`：运行状态与诊断日志
- `runtime/engine/` 与 `runtime/outbox/`：状态、历史产物与待发送消息
- `docs/agent-artifacts-inventory.md`：各 agent 产物的语义归类

如果 `agents/*.yaml` 与上述位置冲突，应优先以实际运行链路和新文档为准，再回头校准 yaml。

## Agent 列表

| Agent | 职责 | 频率 | 模型 |
|-------|------|------|------|
| watcher | 系统健康监控 | 每 15 分钟 | `xiaomi/mimo-v2-omni` |
| newswire | 新闻/催化扫描 | US 盘前 / 盘中 q30 / 盘后 q2h | `xiaomi/mimo-v2-omni` |
| strategist | 交易计划草案 / 参数迭代 | 信号触发或定时 | `xiaomi/mimo-v2-pro` |
| executor | 执行检查单/参数校验 | 策略完成后触发 | `xiaomi/mimo-v2-omni` |
| scout | 候选标的/异常波动扫描 | 按需或定时 | `xiaomi/mimo-v2-omni` |
| closer | 收盘总结/复盘/明日关注 | 每市场收盘后 | `xiaomi/mimo-v2-omni` |

## Main Agent / yuuka 中枢

主 agent 不是 subagent，但负责统筹整条协作链路：

- 读取 `cron/` 与 `docs/tasks/cron/`
- 决定何时触发 watcher / newswire / strategist / executor / scout / closer
- 负责协调 subagent 之间的交接
- 负责调度、审批、风险把关与对用户汇报
- 作为默认汇报目标 `agent:yuuka:main`

如果你在看的是“谁来发起任务、谁来收集结果、谁来做总协调”，那就是主 agent 的职责。
主 agent 的 cron 配置流程见：[docs/main-agent-cron-playbook.md](../docs/main-agent-cron-playbook.md)。

## 运行入口

- `subagents action=list`：查看当前 subagent 状态
- `subagents action=kill target=<agent>`：停止单个 subagent
- `subagents action=kill target=<agent>` 重复执行即可依次停止全部 subagent

说明：

- `cron/*.json` 现在只保留调度信息和 `taskFile` 引用
- 真正会变化的任务正文已经迁到 `docs/tasks/cron/`
- 如果任务正文变更，不需要再改 cron 配置

## 配置文件说明

- `watcher.yaml`：watcher 配置
- `newswire.yaml`：newswire 配置
- `strategist.yaml`：strategist 配置
- `executor.yaml`：executor 配置
- `scout.yaml`：scout 配置
- `closer.yaml`：closer 配置

## Tool 权限说明

下表反映的是当前 `yaml` 中声明的权限，不代表运行时一定严格按此执行。

| Agent | Tool 权限 |
|-------|-----------|
| watcher | `read`, `write`, `exec`, `sessions_send` |
| newswire | `read`, `write`, `web_search`, `browser`, `exec` |
| strategist | `read`, `write`, `exec`, `web_search` |
| executor | `read`, `write`, `exec`, `sessions_send` |
| scout | `read`, `write`, `browser`, `web_search`, `web_fetch`, `sessions_send` |
| closer | `read`, `write`, `sessions_send` |

## 汇报目标

所有 agent 默认汇报给 `agent:yuuka:main`（yuuka 中枢）。

## 当前已知漂移

截至 `2026-04-16`，至少有这些位置仍未完全校准：

- 多个 `yaml` 和 `docs/roles/*` 仍在引用旧的 `runtime/engine/logs/*` 路径，而系统正在把运行日志收口到根目录 `logs/`
- agent 业务产物和运行日志的目录边界仍在整理中，后续应逐步区分 `logs/` 与 `artifacts/`
- `agents/` 仍包含少量历史路径引用，需要继续校准到 `docs/tasks/cron/` 与根目录 `logs/`

更完整的盘点见：

- `docs/agent-artifacts-inventory.md`
- `docs/runtime-observability-layout.md`
