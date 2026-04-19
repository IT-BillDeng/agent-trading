# Main Agent Cron Playbook

更新时间：2026-04-16

这是一份给主 agent / 管理 agent 的简短操作约定，用来把仓库里的 `cron/` 当成调度的 **desired state**。

## 核心原则

1. `cron/*.json` 是调度声明，不是任务正文。
2. `docs/tasks/cron/*.md` 是任务正文唯一来源。
3. 主 agent 配 cron 时，优先参考仓库里的 `cron/`，再和当前 live 环境做 reconcile。
4. 如果 live 环境里存在旧任务，而仓库里已经没有对应定义，应优先停用或迁移旧任务。
5. 仓库侧优先用 `name` 作为稳定标识，`id` 只作为 live 映射的可选字段。
6. `payload.taskFile` 在 live 环境中优先使用绝对项目路径，例如 `/workspace/agent-trading/docs/tasks/cron/strategist-premarket.md`。
7. 主 agent 只读取仓库中的 desired state 与任务正文，不应把同步结果回写到仓库定义文件。

## 推荐流程

1. 读取 `cron/*.json`。
2. 读取每个 `payload.taskFile` 指向的正文。不要依赖当前工作目录去猜 repo root。
3. 检查 live 任务是否与仓库定义一致：
   - 时区
   - 模型
   - 是否启用
   - 任务正文路径
   - `name` 是否一致
   - `id` 是否需要保留为现有 live job 的映射键
4. 对齐时只做最小变更：
   - 正文变化，只改 `docs/tasks/cron/*.md`
   - 调度变化，只改 `cron/*.json`
   - 如果 live 环境曾错误地从 `/workspace/docs/tasks/cron/` 读取，应优先修成绝对项目路径，而不是兼容错误根目录
5. 如果发现遗留旧任务，例如旧时区、旧模型名、旧路径或旧 job id，先停用它，再让新定义接管。
6. 如果 live 环境已有任务但仓库里缺少 `id`，可以先按 `name` 对齐，再在 live 侧补回映射，不要求仓库强制拥有 `id`。
7. 如果投递目标是敏感值，不要硬编码在仓库里，优先写成 `${ENGINE_TELEGRAM_TARGET}` 这类占位符，由私有环境变量注入。
8. 同步完成后的结果应通过主会话直接汇报；如需持久审计，使用 live 环境自身的任务/审计系统，而不是写回仓库 markdown。

## 对主 agent 的约束

- 不要把任务正文塞回 `cron/*.json`
- 不要把运行结果写回 `cron/*.json`
- 不要把 live 同步结果写回 `docs/tasks/cron/*.md`
- 不要在项目根目录新建自由格式 markdown / json 同步笔记
- 不要把同步过程写进 `docs/`、`cron/`、`agents/` 目录
- 不要假设 live 环境一定已经跟仓库同步
- 不要同时修改调度和正文，除非确实需要联动变更

## 适用范围

- `watcher`
- `newswire`
- `strategist`
- `closer`

这四类任务都应优先按该流程维护。
