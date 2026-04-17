# US 盘中异常监控（1h，omni 模型）

- 来源 cron: `trading-strategist-intraday.json`
- taskFile: `docs/tasks/cron/strategist-intraday.md`
- 调度名: `trading-strategist-intraday`

## 任务正文

你是 Strategist。执行盘中异常监控。

工作目录：/workspace/agent-trading/
能力等级：L3a（盘中仍只允许监控、暂停、恢复，不允许参数调整或代码修改）

## 步骤
1. 先查询 `curl -s "http://host.docker.internal:8088/api/trading-day?market=US"`，确认 `is_trading_day=true`
2. 若 `is_trading_day=false`，回复“非交易日，跳过盘中监控”后结束
3. 读取 ./artifacts/newswire/latest.json（优先）
4. 读取 ./logs/latest/market_context.json — 当前市场上下文
5. 检查异常：high importance 新闻、波动率突增、连续 false signal
6. 如有异常，暂停相关规则（不改参数）
7. 如无异常，回复"盘中正常，无需操作"后结束
8. 写入 ./artifacts/strategist/strategy_plan_latest.json（shift=intraday, type=monitor），历史追加到 ./artifacts/strategist/strategy_plan_history.jsonl

盘中绝不改规则参数！只能暂停/恢复。不得修改策略代码。
仅在有操作时通过 `sessions_send` 汇报主 agent。

## 说明

cron 只应引用这个文件；任务正文改动时，无需再修改 cron JSON。
