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

- `docs/tasks/*_TASK_V*.md`
  - 某个任务的正式版本
  - 例如 `NEWSWIRE_TASK_V3.md`
  - 如果有明确演进版本，优先看最新版

- `docs/tasks/*_ITERATION_TASK.md`
  - 某个 agent 的专项流程模板
  - 例如 strategist 的迭代/回测流程

## 使用建议

1. cron 调度任务时，优先读取 `docs/tasks/cron/*.md`
2. 需要给 subagent 派工时，优先读取对应 `*_TASK_TEMPLATE.md`
3. 看到 `V2 / V3` 时，优先使用版本号更高、且正文中明确标注“已替代”的文件
4. 如果任务正文变更，只改 `docs/tasks/` 下的文本，不改 `cron/*.json`

## 当前目录里常见文件

- `NEWSWIRE_TASK_V3.md`：newswire 的正式任务版本
- `STRATEGIST_TASK_V2.md`：strategist 的较完整版本说明
- `STRATEGIST_ITERATION_TASK.md`：strategist 的回测/迭代专用模板
- `WATCHER_TASK_TEMPLATE.md`：watcher 通用模板
- `EXECUTOR_TASK_TEMPLATE.md`：executor 通用模板
- `CLOSER_TASK_TEMPLATE.md`：closer 通用模板
- `cron/`：cron 正文

## 术语

- `template`：可复用模板
- `task body`：具体执行正文
- `versioned task`：带版本的正式任务说明
- `iteration task`：专项流程说明

如果你在这里感到混乱，优先看两份索引：

- `docs/orchestration-directory-contract.md`
- `docs/tasks/cron/README.md`
