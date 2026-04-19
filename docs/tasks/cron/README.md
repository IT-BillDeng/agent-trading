# Cron Task Bodies

这是一组 cron 任务正文文件。

如果你想先弄清楚 `docs/tasks/` 整体怎么分层，先看 [docs/tasks/README.md](../README.md)。

约定：

- `cron/*.json` 只保留调度、投递和 `taskFile` 引用
- `name` 是仓库侧稳定标识，`id` 只是 live 映射的可选字段
- `docs/tasks/cron/*.md` 保存真正会变化的任务正文
- 当任务步骤更新时，只改这里，不改 cron 配置
- 运行时的 `payload.taskFile` 优先写成绝对项目路径：`/workspace/agent-trading/docs/tasks/cron/*.md`
- 对美股盘前、盘中、盘后、收盘总结类任务，默认先查询 `http://host.docker.internal:8088/api/trading-day?market=US`
- 若返回 `is_trading_day=false`，对应任务应直接跳过，不再自行用 weekday 近似判断
- 每份任务正文都应明确 canonical 输出路径，并显式禁止写入 `./memory/`、项目根临时笔记、`docs/`、`cron/`、`agents/`

## 目录映射

| Cron 配置 | 任务正文 |
|---|---|
| `trading-watcher.json` | `watcher.md` |
| `trading-newswire-premarket.json` | `newswire-premarket.md` |
| `trading-newswire-intraday.json` | `newswire-intraday.md` |
| `trading-newswire-afterhours.json` | `newswire-afterhours.md` |
| `trading-strategist-premarket.json` | `strategist-premarket.md` |
| `trading-strategist-intraday.json` | `strategist-intraday.md` |
| `trading-strategist-afterhours.json` | `strategist-afterhours.md` |
| `trading-closer-us.json` | `closer-us.md` |

## 使用方式

运行时只需读取 `cron/*.json`，再根据 `payload.taskFile` 打开对应 markdown 即可。

如果 live 环境的当前目录不是 `/workspace/agent-trading/`，也不应依赖相对路径推断任务正文位置。
