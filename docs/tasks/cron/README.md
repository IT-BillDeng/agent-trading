# Cron Task Bodies

这是一组 cron 任务正文文件。

如果你想先弄清楚 `docs/tasks/` 整体怎么分层，先看 [docs/tasks/README.md](../README.md)。

约定：

- `cron/*.json` 只保留调度、投递和 `taskFile` 引用
- `docs/tasks/cron/*.md` 保存真正会变化的任务正文
- 当任务步骤更新时，只改这里，不改 cron 配置

## 目录映射

| Cron 配置 | 任务正文 |
|---|---|
| `watcher-cron.json` | `watcher.md` |
| `newswire-premarket.json` | `newswire-premarket.md` |
| `newswire-intraday.json` | `newswire-intraday.md` |
| `newswire-afterhours.json` | `newswire-afterhours.md` |
| `strategist-premarket.json` | `strategist-premarket.md` |
| `strategist-intraday.json` | `strategist-intraday.md` |
| `strategist-afterhours.json` | `strategist-afterhours.md` |
| `closer-us-cron.json` | `closer-us.md` |

## 使用方式

运行时只需读取 `cron/*.json`，再根据 `payload.taskFile` 打开对应 markdown 即可。
