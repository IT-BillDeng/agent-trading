# Closer Task Template

给 `closer` 派工时，优先使用这份模板。

---

目标：为指定市场生成收盘总结，覆盖行情、新闻、执行状态与明日关注点。

工作目录：`/workspace/agent-trading/`

输入：
- `./data/watchlist.json`（本地用户状态）
- `./logs/latest/engine_cycle.json`
- `./logs/latest/market_context.json`
- `./logs/audit/execution.jsonl`
- `./logs/audit/notifications.jsonl`
- `./logs/audit/dispatch_queue.jsonl`
- `./runtime/state/control_state.json`
- `./artifacts/newswire/latest.json`
- `./artifacts/strategist/strategy_plan_latest.json`

要求：
- 优先只看本地清单中 `enabled=true` 的标的
- 高优先级（`priority=high`）标的优先写入总结
- 包含当日新闻/催化；若信息不足，必须明确说明
- 区分 US / HK 市场，不要混写

边界：
- 不直接下单
- 不自由编写或修改 Python；如具体 cron 任务要求调用既有 `closer.py`，仅允许按既有 pipeline 执行
- 不对外发送消息（若由 cron announce，则仅输出总结本体）
- 不修改股票池或配置

结构化落盘要求：
- 写入 `./runtime/outbox/closer_outbox.json`
- 写入 `./artifacts/closer/summary_latest.json`
- 追加 `./artifacts/closer/summary_history.jsonl`

产物边界：
- 只允许写入 `./runtime/outbox/closer_outbox.json`
- 只允许写入 `./artifacts/closer/summary_latest.json`
- 只允许追加 `./artifacts/closer/summary_history.jsonl`
- 不得修改本任务文件自身
- 不得把运行记录写入 `./memory/`
- 不得在项目根目录新建自由格式 markdown / json 临时记录
- 不得把运行结果写入 `docs/`、`cron/`、`agents/`

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
