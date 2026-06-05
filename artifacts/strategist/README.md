# Strategist Artifacts

更新时间：2026-04-17

`artifacts/strategist/` 是 strategist 的长期产物目录。

推荐内容：

- `strategy_plan_latest.json`
- `strategy_plan_history.jsonl`
- `memory/latest.json`
- `memory/history.jsonl`
- `proposals.jsonl`
- `rejections.jsonl`
- `code_change_proposals.jsonl`
- `code_change_results.jsonl`
- `rollback_notes.jsonl`
- `approval_queue/`
- `approval_decisions.jsonl`
- `deployment_records.jsonl`
- `iterations/`
- `backtests/`
- `experiments/`

原则：

- 保留可审计、可回放、可继续迭代的结构化结果
- 不保留原始聊天全文
- 不保留一次性临时思考过程
- `L3a` 代码提案相关产物也统一收进这里
- `L3b` 审批与更新记录也统一收进这里
