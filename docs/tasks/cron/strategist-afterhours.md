# US 盘后信号质量分析 + 明日策略调整

- 来源 cron: `trading-strategist-afterhours.json`
- taskFile: `docs/tasks/cron/strategist-afterhours.md`
- 调度名: `trading-strategist-afterhours`

## 任务正文

你是 Strategist。执行盘后分析。

工作目录：/workspace/agent-trading/
参考文档：docs/tasks/STRATEGIST_TASK.md
能力等级：L3a（允许在白名单目录内做代码提案，不自动上线 live）

## 步骤
1. 先查询 `curl -s "http://host.docker.internal:8088/api/trading-day?market=US"`，确认 `is_trading_day=true`
2. 若 `is_trading_day=false`，回复“非交易日，跳过盘后策略分析”后结束
3. 读取 ./rules/rules.json
4. 读取 ./artifacts/newswire/latest.json（优先）
5. 读取 ./logs/latest/market_context.json — 当前市场上下文
6. 读取 ./logs/latest/engine_cycle.json（优先）
7. 如有必要，可兼容读取旧快照（如存在）
8. 分析今日信号质量：总信号数、胜率、PnL、false signal、missed opportunity
9. 提出明日策略迭代方案（参数/因子调整）
10. 对每个方案用 exec 调回测 API 验证：
curl -s -X POST http://host.docker.internal:8088/api/backtest/batch -H "Content-Type: application/json" -d '{"symbols":["AAPL","MSFT","NVDA"],"start_date":"2026-01-07","end_date":"2026-04-14","param_sets":[...]}'
11. 通过的方案可用 exec PUT 到 /api/rules 做规则层变更，拒绝的记录原因单独写入长期产物
12. 如识别出明确代码级策略假设，可进入 `docs/tasks/STRATEGIST_CODE_CHANGE_TASK.md` 流程，在白名单目录内修改策略代码与测试代码
13. 代码级提案必须写入：
    - ./artifacts/strategist/code_change_proposals.jsonl
    - ./artifacts/strategist/code_change_results.jsonl
    - ./artifacts/strategist/rollback_notes.jsonl
14. 写入 ./artifacts/strategist/strategy_plan_latest.json（shift=afterhours, type=analysis）
15. 记录到 ./artifacts/strategist/iterations/

禁止：
- 不扩张股票池
- 不直接下单
- 不自动部署或自动上线 live

输出格式参见 docs/tasks/STRATEGIST_TASK.md 的输出格式章节。

有调整时汇报主 agent（sessions_send sessionKey=${ENGINE_MAIN_AGENT_SESSION_KEY}），无调整不通知。

## 说明

cron 只应引用这个文件；任务正文改动时，无需再修改 cron JSON。
