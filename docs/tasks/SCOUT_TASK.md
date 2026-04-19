# Scout Task

给 `scout` 派工时，优先使用这份任务正文。

---

目标：扫描候选标的与异常波动，并输出结构化候选列表供主 agent 或 strategist 参考。

工作目录：`/workspace/agent-trading/`

输入：
- `./data/watchlist.json`
- `./logs/latest/engine_cycle.json`
- `./logs/latest/market_context.json`
- `./artifacts/newswire/latest.json`
- `./artifacts/strategist/strategy_plan_latest.json`

结构化落盘要求：
- 覆盖写入 `./artifacts/scout/candidates_latest.json`
- 历史追加到 `./artifacts/scout/candidates_history.jsonl`

产物边界：
- 只允许写入 `./artifacts/scout/candidates_latest.json`
- 只允许追加 `./artifacts/scout/candidates_history.jsonl`
- 不得修改本任务文件自身
- 不得把运行记录写入 `./memory/`
- 不得在项目根目录新建自由格式 markdown / json 临时记录
- 不得把运行结果写入 `docs/`、`cron/`、`agents/`

边界：
- 不直接下单
- 不直接修改股票池
- 不直接修改规则
- 只输出候选信息与风险提示

输出格式：
1. 一句话结论
2. 1~3 个候选标的
3. 每个候选的触发原因
4. 1 个最重要的风险提醒
