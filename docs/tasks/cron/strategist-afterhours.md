# US 盘后信号质量分析 + 明日策略调整

- 来源 cron: `strategist-afterhours.json`
- taskFile: `docs/tasks/cron/strategist-afterhours.md`
- 调度名: `trading-strategist-afterhours`

## 任务正文

你是 Tiger Strategist。执行盘后分析。

工作目录：/workspace/agent-trading/
参考文档：docs/tasks/STRATEGIST_TASK_V2.md

## 步骤
1. 读取 rules/rules.json
2. 读取 runtime/engine/newswire/latest.json
3. 读取 runtime/engine/.last_execution_cycle.json（如存在）
4. 分析今日信号质量：总信号数、胜率、PnL、false signal、missed opportunity
5. 提出明日策略迭代方案（参数/因子调整）
6. 对每个方案用 exec 调回测 API 验证：
curl -s -X POST http://host.docker.internal:8088/api/backtest/batch -H "Content-Type: application/json" -d '{"symbols":["AAPL","MSFT","NVDA"],"start_date":"2026-01-07","end_date":"2026-04-14","param_sets":[...]}'
7. 通过的方案用 exec PUT 到 /api/rules，拒绝的记录原因
8. 写入 runtime/engine/strategy_plan_latest.json（shift=afterhours, type=analysis）
9. 记录到 runtime/engine/strategist_iterations/

输出格式参见 docs/tasks/STRATEGIST_TASK_V2.md 的输出格式章节。

有调整时通知先生（sessions_send sessionKey=agent:yuuka:main），无调整不通知。

## 说明

cron 只应引用这个文件；任务正文改动时，无需再修改 cron JSON。
