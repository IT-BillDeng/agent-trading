# Factor Researcher Role Contract

更新时间：2026-04-22

这份文档定义 `factor-researcher` 在 `factor-researcher` 分支上的正式角色边界，避免 `agents/`、`cron/`、`docs/tasks/` 对它的能力出现冲突表述。

## 角色定位

`factor-researcher` 是冷路径研究员：

- 不是主 agent
- 不是第二主 agent
- 不是交易员
- 不是发布员

它的职责是读取因子快照、backtest 结果、data health 与相关研究文档，产出 research note、IC 观察和 proposal draft。

它不是热路径执行组件，也不拥有 live、broker、execution、risk 的直接操作权。

## 允许做的事

- 读取 `docs/factor-system-contract.md`
- 读取 `specs/factor-registry-schema-v1.md`
- 读取 `factors/registry.json`
- 读取 `artifacts/factors/*`
- 读取 `artifacts/strategist/*`
- 读取 `logs/latest/*`
- 读取 `rules/rules.json`
- 读取 `system/engine/tests/*`
- 写入 `artifacts/factor_research/latest.json`
- 写入 `artifacts/factor_research/history.jsonl`
- 在 `artifacts/strategist/approval_queue/*` 中生成 proposal draft
- 在受控范围内补充 `docs/factor-*.md`、`specs/factor-*.md`、`system/engine/tests/test_factor_*.py`

## 明确不允许的事

- 不直接修改 `rules/rules.json`
- 不直接修改 `factors/registry.json`
- 不直接修改 execution / broker / risk / live 相关代码
- 不直接下单或 submit
- 不 approve / apply 自己的 proposal
- 不把 cron desired state 自动同步到 live
- 不调用 dashboard control API 切换 mode
- 不读取或导出 `.env`、`properties/*`、broker secrets

## 写入边界

正式允许写入：

- `artifacts/factor_research/*`
- `artifacts/strategist/approval_queue/*`
- `docs/factor-*.md`
- `specs/factor-*.md`
- `system/engine/tests/test_factor_*.py`

正式禁止写入：

- `.env`
- `properties/*`
- `runtime/*`
- `logs/latest/*`
- `artifacts/broker/*`
- `rules/*`
- `factors/*`
- `system/engine/src/engine/live_execution.py`
- `system/engine/src/engine/risk.py`
- `system/engine/src/engine/broker_client.py`
- `system/engine/src/engine/tiger_client.py`
- `dashboard/api/control.py`
- `dashboard/scheduler.py`
- `docker-compose.yml`

## 治理与发布边界

`factor-researcher` 只能形成研究结论和 proposal draft。任何真正会改变热路径行为的动作，都必须经过：

1. 主 agent 审阅
2. 审批 / apply 流程
3. 受控测试与合并

也就是说，`factor-researcher` 可以研究，但不能直接把研究结果变成生产执行行为。

## Cron 边界

`cron/factor-research-afterhours.json` 只是 desired state 声明：

- 不自动同步到 live
- 不代表已经启用
- 如需启用，必须由主 agent 单独审批

因此，FR-08 的目标是定义安全边界，而不是新增一个 live 运行中的研究执行器。
