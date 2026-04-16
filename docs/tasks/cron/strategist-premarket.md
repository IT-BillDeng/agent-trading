# US 盘前策略复盘 + 设定今日参数

- 来源 cron: `strategist-premarket.json`
- taskFile: `docs/tasks/cron/strategist-premarket.md`
- 调度名: `trading-strategist-premarket`

## 任务正文

你是 Tiger Strategist。执行盘前 Daily Setup。

工作目录：/workspace/agent-trading/
参考文档：docs/tasks/STRATEGIST_TASK_V2.md

## 步骤
1. 读取 rules/rules.json — 当前规则
2. 读取 runtime/engine/newswire/latest.json — 盘前新闻
3. 读取 data/watchlist.json — 标的白名单
4. 读取 runtime/engine/.last_execution_cycle.json（如存在）
5. 复盘昨日信号质量
6. 从 newswire 提取 high importance 新闻，判断对规则的影响
7. 如需调整，用 exec 调回测 API 验证（curl http://host.docker.internal:8088/api/backtest）
8. 写入 runtime/engine/strategy_plan_latest.json（shift=premarket, type=daily_setup）

输出格式参见 docs/tasks/STRATEGIST_TASK_V2.md 的输出格式章节。

仅在有策略调整时通知先生（sessions_send sessionKey=agent:yuuka:main）。无调整则不通知。

## 说明

cron 只应引用这个文件；任务正文改动时，无需再修改 cron JSON。
