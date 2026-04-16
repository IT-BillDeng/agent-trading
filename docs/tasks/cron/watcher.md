# Tiger 系统健康监护人 - 每 15 分钟通过 API 检查系统状态

- 来源 cron: `watcher-cron.json`
- taskFile: `docs/tasks/cron/watcher.md`
- 调度名: `watcher`

## 任务正文

执行 Tiger Watcher 健康检查：

工作目录：`/workspace/agent-trading/`

1. 运行脚本：python3 ./system/engine/src/engine/watcher_api.py
2. 解析输出的 JSON 报告
3. 根据级别处理：
   - info: 仅记录，不通知
   - warning: 记录并观察
   - critical: 通知先生（包含检查详情）
   - emergency: 通知先生 + 自动调用 /api/control/lock 锁定引擎

注意：API 地址 http://host.docker.internal:8088，通过 sandbox 内的 curl 可达

## 说明

cron 只应引用这个文件；任务正文改动时，无需再修改 cron JSON。
