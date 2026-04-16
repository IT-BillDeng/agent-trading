# Applier Task

给 `applier` 派工时，优先使用这份任务正文。

---

目标：读取已批准的 strategist proposal，并按 `hot / cold` 规则应用更新。

工作目录：`/workspace/agent-trading/`

输入：
- `./artifacts/strategist/approval_queue/`
- `./artifacts/strategist/approval_decisions.jsonl`
- `./artifacts/strategist/deployment_records.jsonl`
- `./artifacts/strategist/code_change_results.jsonl`
- `./runtime/state/control_state.json`
- `./config/app.defaults.json`
- `./config/app_config.docker.json`
- `./config/user.settings.json`（如存在）

要求：
- 只处理已 `approved` 的 proposal
- 必须先通过 apply gate 判断更新模式
- `hot` 更新只允许规则层变更
- `cold` 更新默认需要 restart / reload
- apply 结果必须写入 `deployment_records.jsonl`
- 如失败，必须写 rollback 说明

边界：
- 不生成策略提案
- 不负责审批
- 不越权修改 broker / execution / infra
- 不直接下单

结构化落盘要求：
- 应用成功后，写入 `./artifacts/strategist/deployment_records.jsonl`
- 如需补充回滚信息，写入 `./artifacts/strategist/rollback_notes.jsonl`

输出格式：
1. 一句话 apply 结论
2. proposal_id
3. update_mode
4. 是否成功
5. 下一步是否需要人工跟进
