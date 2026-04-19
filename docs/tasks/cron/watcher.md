# 系统健康监护人 - 每 15 分钟通过 API 检查系统状态

- 来源 cron: `trading-watcher.json`
- taskFile: `/workspace/agent-trading/docs/tasks/cron/watcher.md`
- 调度名: `trading-watcher`

## 任务正文

执行系统健康检查：

工作目录：`/workspace/agent-trading/`

1. 运行脚本：`python3 ./system/engine/src/engine/watcher_api.py`
2. 解析输出的 JSON 报告
3. 根据级别处理：
   - `info`: 仅记录，不通知
   - `warning`: 记录并观察
   - `critical`: 通过 `sessions_send` 汇报主 agent（包含检查详情）
   - `emergency`: 汇报主 agent + 自动调用 `/api/control/lock` 锁定引擎

## 正式输出路径

本任务的正式输出只允许写到以下位置：

- `./artifacts/watcher/latest.json`
- `./artifacts/watcher/history.jsonl`
- `./runtime/state/watcher_state.json`

如需补充结构化健康状态，也只能写入上述 canonical 路径。

## 禁止事项

- 不得修改本任务文件自身
- 不得把运行记录写入 `./memory/`
- 不得在项目根目录新建临时 markdown 日志
- 不得把巡检结论写到 `docs/`、`cron/`、`agents/` 目录

## 说明

- API 地址：`http://host.docker.internal:8088`
- cron 只应引用这个文件；任务正文改动时，无需再修改 cron JSON
- 如果需要长期保留巡检历史，应追加到 `./artifacts/watcher/history.jsonl`，而不是生成自由格式笔记
