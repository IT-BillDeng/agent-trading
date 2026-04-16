# US 盘前策略复盘 + 设定今日参数

- 来源 cron: `trading-strategist-premarket.json`
- taskFile: `docs/tasks/cron/strategist-premarket.md`
- 调度名: `trading-strategist-premarket`

## 任务正文

你是 Strategist。执行盘前 Daily Setup。

工作目录：/workspace/agent-trading/
参考文档：docs/tasks/STRATEGIST_TASK.md

## 步骤
1. 读取 ./rules/rules.json — 当前规则
2. 读取 ./artifacts/newswire/latest.json — 盘前新闻（优先）
3. 兼容读取 ./runtime/engine/newswire/latest.json
4. 读取 ./data/watchlist.json — 标的白名单
5. 读取 ./logs/latest/engine_cycle.json（优先）
6. 兼容读取 ./runtime/engine/.last_execution_cycle.json
7. 复盘昨日信号质量
8. 从 newswire 提取 high importance 新闻，判断对规则的影响
9. 如需调整，用 exec 调回测 API 验证（curl http://host.docker.internal:8088/api/backtest）
10. 写入 ./artifacts/strategist/strategy_plan_latest.json（shift=premarket, type=daily_setup），历史追加到 ./artifacts/strategist/strategy_plan_history.jsonl

输出格式参见 docs/tasks/STRATEGIST_TASK.md 的输出格式章节。

仅在有策略调整时通知先生（sessions_send sessionKey=agent:yuuka:main）。无调整则不通知。

## 说明

cron 只应引用这个文件；任务正文改动时，无需再修改 cron JSON。
