# TIGER Watcher Task Template

给 `watcher` 派工时，优先使用这份模板。

---

目标：执行一轮只读高频行情监控，并写入结构化 watcher 输出。

输入：
- `./data/watchlist.json`
- `./runtime/engine/.last_execution_cycle.json`
- `./runtime/engine/logs/dispatch_queue.jsonl`
- `./runtime/engine/logs/execution.jsonl`
- `./runtime/engine/state/control_state.json`

要求：
- 优先关注共享清单中 `enabled=true` 的标的
- 关注市场状态、候选变化、preview blocker、锁定状态、行情可用性
- 重点识别：新 BUY 候选、候选数量突变、连续多轮强势、异常波动、权限异常
- 信息不足时明确说明
- 不直接建议真实下单

边界：
- 不运行 Python
- 不对外发送消息
- 不修改股票池或配置

结构化落盘要求（MVP v1）：
- 写入 `./runtime/engine/watcher/latest.json`
- 追加 `./runtime/engine/watcher/history.jsonl`
- 即使无明显变化，也要写结构化空结果或低变化结果

最小字段要求：
- `watch_id`
- `generated_at`
- `market_session`
- `window`
- `symbols`
- `summary`

输出格式：
1. 一句话结论
2. 3 个关键观察
3. 1 个下一步建议
4. 并写入结构化 watcher 输出
