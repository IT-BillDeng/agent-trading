# Executor Task Template

给 `executor` 派工时，优先使用这份模板。

---

目标：审查当前 paper 执行链的准备度，并把计划转成最短执行检查单。

工作目录：`/workspace/agent-trading/`

输入：
- `./data/watchlist.json`（本地用户状态）
- `./system/engine/README.md`
- `./config/app.defaults.json`
- `./config/app_config.docker.json`
- `./config/user.settings.json`（如存在）
- `./logs/latest/engine_cycle.json`
- `./logs/audit/execution.jsonl`
- `./logs/audit/dispatch_queue.jsonl`
- `./runtime/state/control_state.json`
- `./artifacts/strategist/strategy_plan_latest.json`

要求：
- 优先只看本地清单中 `enabled=true` 的标的
- 检查当前执行链是否与本地清单一致
- 重点检查：
  - preview_check
  - guarded/live mode
  - control.locked
  - notification_dispatch
  - risk.preview_blockers
  - 最大总暴露与单笔上限是否一致

边界：
- 只读
- 不运行 Python
- 不对外发送消息
- 不真实提交订单
- 不修改股票池或配置

结构化落盘要求：
- 读取执行准备度时优先参考 `./artifacts/strategist/strategy_plan_latest.json`
- 检查完成后，如需输出检查单，写入 `./artifacts/executor/checklist_latest.json`
- 历史追加到 `./artifacts/executor/checklist_history.jsonl`

产物边界：
- 只允许写入 `./artifacts/executor/checklist_latest.json`
- 只允许追加 `./artifacts/executor/checklist_history.jsonl`
- 不得修改本任务文件自身
- 不得把运行记录写入 `./memory/`
- 不得在项目根目录新建自由格式 markdown / json 临时记录
- 不得把运行结果写入 `docs/`、`cron/`、`agents/`

输出格式：
1. 一句话结论
2. 3 个已就绪项
3. 3 个剩余风险 / 缺口
4. 1 份最短执行检查单（5 条内）

---

可选附加要求：
- 如果本地清单与 `.last_execution_cycle.json` 中的标的不一致，必须明确指出
- 如果发现执行链已具备 paper guarded 观察条件，请明确说明“可以继续 guarded 观察”
- 如果发现任何会导致误下单或漏通知的点，请把它放在第一优先级
