# Newswire Task Template

给 `newswire` 派工时，使用当前任务正文 [NEWSWIRE_TASK.md](./NEWSWIRE_TASK.md)。简要要点：

工作目录：`/workspace/agent-trading/`

---

目标：为本地股票清单提供一轮新闻与催化扫描。

输入：
- `./data/watchlist.json`（本地用户状态）
- `./news/newswire_sources.json`

**采集优先级：**
1. web_fetch RSS（免费）→ 2. web_fetch 页面（免费）→ 3. web_search 批量（≤2次/轮）

**硬约束：**
- 单轮搜索 ≤ 2 次
- 距上次 < 20 分钟且非 shift 切换 → 跳过本轮
- 不运行 Python / 不对外发送 / 不修改配置

输出：
- `./runtime/engine/newswire/latest.json`
- `./runtime/engine/newswire/history.jsonl`
- `./runtime/engine/newswire/dedupe.json`

详见 [NEWSWIRE_TASK.md](./NEWSWIRE_TASK.md) 完整执行步骤。
