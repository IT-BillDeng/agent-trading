# Closer Task Template

给 `closer` 派工时，优先使用这份模板。

---

目标：为指定市场生成收盘总结，覆盖行情、新闻、执行状态与明日关注点。

工作目录：`/workspace/agent-trading/`

输入：
- `./data/watchlist.json`（本地用户状态）
- `./runtime/engine/.last_execution_cycle.json`
- `./runtime/engine/logs/execution.jsonl`
- `./runtime/engine/logs/notifications.jsonl`
- `./runtime/engine/logs/dispatch_queue.jsonl`
- `./runtime/engine/state/control_state.json`

要求：
- 优先只看本地清单中 `enabled=true` 的标的
- 高优先级（`priority=high`）标的优先写入总结
- 包含当日新闻/催化；若信息不足，必须明确说明
- 区分 US / HK 市场，不要混写

边界：
- 不直接下单
- 不运行 Python
- 不对外发送消息（若由 cron announce，则仅输出总结本体）
- 不修改股票池或配置

输出格式：
1. 一句话结论
2. 今日行情摘要（2~4 条）
3. 今日新闻/催化摘要（1~3 条）
4. 执行与风控摘要（2~3 条）
5. 明日关注（1~2 个标的 + 1 个风险点）

---

可选附加要求：
- 若某个标的在当日多次成为 BUY 候选，请单独点名
- 若出现 `control.locked=true`，必须放到总结最前面
- 若新闻数据不足，明确写“新闻信息不足，暂不下结论”
