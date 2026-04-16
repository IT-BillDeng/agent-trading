# Task Texts

`docs/tasks/` 里放的是会被主 agent 或 subagent 直接读取的任务文本。  
它不是单纯的“说明文档目录”，而是**可版本化的执行契约**。

## 目录分工

- `docs/tasks/cron/`
  - cron 触发时真正要执行的任务正文
  - 对应 `cron/*.json` 里的 `payload.taskFile`
  - 适合放会随执行策略变化的正文，不用改 cron 配置本身

- `docs/tasks/*_TASK_TEMPLATE.md`
  - 面向 subagent 的通用任务模板
  - 适合派工时复用

- `docs/tasks/*_TASK.md`
  - 某个任务的当前正文
  - 例如 `NEWSWIRE_TASK.md`、`STRATEGIST_TASK.md`

- `docs/tasks/*_ITERATION_TASK.md`
  - 某个 agent 的专项流程模板
  - 例如 strategist 的迭代/回测流程

- `docs/tasks/archive/`
  - 明确废弃、仅供回溯的旧版本任务文本

## 使用建议

1. cron 调度任务时，优先读取 `docs/tasks/cron/*.md`
2. 需要给 subagent 派工时，优先读取对应 `*_TASK_TEMPLATE.md`
3. 如果看到历史版本文件，优先使用无版本号的当前任务正文
4. 如果任务正文变更，只改 `docs/tasks/` 下的文本，不改 `cron/*.json`

## 当前目录里常见文件

- `NEWSWIRE_TASK.md`：newswire 的当前任务正文
- `STRATEGIST_TASK.md`：strategist 的当前任务正文
- `STRATEGIST_ITERATION_TASK.md`：strategist 的回测/迭代专用模板
- `WATCHER_TASK_TEMPLATE.md`：watcher 通用模板
- `EXECUTOR_TASK_TEMPLATE.md`：executor 通用模板
- `CLOSER_TASK_TEMPLATE.md`：closer 通用模板
- `cron/`：cron 正文
- `archive/`：废弃版本，仅用于历史回溯

## 术语

- `template`：可复用模板
- `task body`：具体执行正文
- `versioned task`：带版本的正式任务说明
- `iteration task`：专项流程说明

如果你在这里感到混乱，优先看两份索引：

- `docs/orchestration-directory-contract.md`
- `docs/tasks/cron/README.md`
