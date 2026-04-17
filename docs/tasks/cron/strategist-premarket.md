# US 盘前策略复盘 + 设定今日参数

- 来源 cron: `trading-strategist-premarket.json`
- taskFile: `docs/tasks/cron/strategist-premarket.md`
- 调度名: `trading-strategist-premarket`

## 任务正文

你是 Strategist。执行盘前 Daily Setup。

工作目录：/workspace/agent-trading/
参考文档：docs/tasks/STRATEGIST_TASK.md
能力等级：L3a（盘前允许规则层调整；代码级提案仅可读取待批准结果，不在盘前直接改代码）

## 步骤
1. 先查询 `curl -s "http://host.docker.internal:8088/api/trading-day?market=US"`，确认 `is_trading_day=true`
2. 若 `is_trading_day=false`，回复“非交易日，跳过盘前 Daily Setup”后结束，不做规则调整
3. 读取 ./rules/rules.json — 当前规则
4. 读取 ./artifacts/newswire/latest.json — 盘前新闻（优先）
5. 读取 ./logs/latest/market_context.json — 当前市场上下文
6. 读取 ./data/watchlist.json — 标的白名单
7. 读取 ./logs/latest/engine_cycle.json（优先）
8. 如有必要，可兼容读取旧快照
9. 复盘昨日信号质量
10. 从 newswire 提取 high importance 新闻，判断对规则的影响
11. 如需调整，用 exec 调回测 API 验证（curl http://host.docker.internal:8088/api/backtest）
12. 如方案通过，可在规则层落地参数 / 启停变更
13. 写入 ./artifacts/strategist/strategy_plan_latest.json（shift=premarket, type=daily_setup），历史追加到 ./artifacts/strategist/strategy_plan_history.jsonl

说明：
- 盘前不直接做新的代码级策略改动
- 如存在上一轮 afterhours 已验证的代码提案，只能读取其结果，不得在盘前临时扩张变更范围

输出格式参见 docs/tasks/STRATEGIST_TASK.md 的输出格式章节。

仅在有策略调整时汇报主 agent（sessions_send sessionKey=${ENGINE_MAIN_AGENT_SESSION_KEY}）。无调整则不通知。

## 说明

cron 只应引用这个文件；任务正文改动时，无需再修改 cron JSON。
