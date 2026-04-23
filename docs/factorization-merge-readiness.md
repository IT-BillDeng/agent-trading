# Factorization Merge Readiness

更新时间：2026-04-22

## 目标

这份文档用于汇总 `factor-researcher` 分支在 FR-00 到 FR-09 已完成的能力、默认开关、风险边界、测试命令和合并 `main` 的准入标准。

它不是功能设计文档，也不授予任何新的交易权限。

## FR-00 到 FR-09 能力汇总

| Batch | 已完成能力 | 默认行为 |
|---|---|---|
| FR-00 | 容器测试基线与安全边界确认 | 只做基线检查，不改交易逻辑 |
| FR-01 | 因子契约文档、registry 骨架、artifacts 目录骨架 | `factors/registry.json` 初始为 metadata-only，`actionable=false` |
| FR-02 | `engine.factors.registry` / `schema`，registry 加载与校验 | 非法 registry 会被拒绝 |
| FR-03 | Factor Engine shadow mode 与内置 builtins：`rsi`、`bollinger_zscore`、`volume_ratio`、`premarket_gap_pct` | 只做 shadow 计算，不接入交易主循环决策 |
| FR-04 | Factor Store，runtime shadow path，latest cycle `factor_engine` 摘要 | Factor Engine 失败时不改变 `strategy.signals`、`risk.decisions`、`execution_preview`、`order_intents` |
| FR-05 | Strategy overview API 和 `/strategy` 页面只读展示 `Factor Engine Shadow / Factor Health Matrix` | 不新增写 API，不新增编辑 factor/rules 的按钮 |
| FR-06 | rule schema / rule engine 兼容 factor condition，signal diagnostics 增加 `used_factors`、`factor_values`、`factor_readiness` | 现有 `rules/rules.json` 默认行为不变 |
| FR-07 | backtest `factor_attribution` / IC 基础统计 | 不改变 `return_pct`、`sharpe`、`max_drawdown`、`win_rate`、`fee_drag` 的语义 |
| FR-08 | `factor-researcher` subagent、afterhours cron desired state、角色契约 | 冷路径研究员，不同步到 live，不具备 broker/execution 权限 |
| FR-09 | proposal schema、approval / applier 接入 factor proposals | `factor_config` hot apply，`factor_rule_link` hot apply 但双 schema 校验，`factor_code` cold/manual |

## 默认开关与安全默认值

当前默认安全开关应保持如下：

| 项目 | 默认值 | 说明 |
|---|---|---|
| `execution.submit_mode` | `guarded` | 不允许默认进入 live submit |
| `execution.live_submit` | `false` | 默认关闭真实提交 |
| `factor_engine.enabled` | `true` | 因子引擎默认开启，但仅限 shadow |
| `factor_engine.mode` | `shadow` | 只计算，不进入 BUY/HOLD/EXIT 热路径 |
| `factor_engine.allow_actionable_consumption` | `false` | 默认不允许因子直接驱动 actionable path |
| `factor_engine.regular_session_only_for_indicators` | `true` | regular technical factors 只消费 regular-session completed bars |
| registry defaults mode | `shadow` | registry 侧默认仍是 shadow |
| registry defaults allow actionable | `false` | registry 侧默认不允许 actionable consumption |

## 风险边界

合并 `main` 前，这些边界必须继续成立：

- Factor Engine 只能处于 `shadow` 或显式 `disabled` 状态，不能直接驱动 BUY/HOLD/EXIT。
- `premarket_gap_pct` 和 extended-hours 因子默认只能作为 `context_only`，不能直接触发 actionable BUY。
- Dashboard 只允许只读展示 factor 状态，不新增直接修改 `factors/registry.json` 或 `rules/rules.json` 的写入口。
- `factor_code` 只能 `cold/manual`，不得被 applier 自动写入 engine source。
- `factor_config` hot apply 只能改 `factors/registry.json`。
- `factor_rule_link` hot apply 只能改 `rules/rules.json`，并且必须同时通过 rule schema 与 factor registry schema。
- v1 的 hot `factor_rule_link` 只允许 diagnostic / disabled-rule binding；任何对已启用规则的 promotion 或行为改写都必须走 manual/cold。
- factor-based conditions 在 schema 上是兼容的，但 v1 默认 runtime 仍然保持 shadow-only，不代表默认开启 actionable factor trading。
- `factor_rule_link` 只表示规则可以引用已批准 factor id；在 `allow_actionable_consumption=false` 下，不意味着因子可直接进入 actionable BUY。
- Factor Engine 在 runtime 中必须 fail-open：即使因子侧报错，也不改变 `strategy.signals`、`risk.decisions`、`execution_preview`、`order_intents`。
- 不得恢复 Dashboard scheduler 的 submit 权限。
- 不得修改 live gate，不得新增 broker submit 路径，不得让 `submit_mode=live` 或 `live_submit=true` 成为默认值。
- `factor-researcher` 仍然只是冷路径 subagent，不是主 agent，不是交易员，不是发布员。
- `factor-research-afterhours` 只是 desired state，不得自动同步到 live。若要启用，必须由主 agent 单独审批。
- `.env`、`properties/`、`runtime/`、`logs/latest/`、`artifacts/broker/` 仍视为 protected paths。
- 运行生成的 `artifacts/factors/*`、`artifacts/factor_research/*`、`artifacts/strategist/*` 不得提交到 git。

## Main 合并准入标准

满足以下全部条件，才允许把因子化基础设施合入 `main`：

1. FR-00 到 FR-09 的文档、测试和治理边界都已落地，且没有新增交易逻辑回归。
2. 默认配置仍满足 `submit_mode=guarded`、`live_submit=false`、`factor_engine.mode=shadow`、`allow_actionable_consumption=false`。
3. 现有 `rules/rules.json` 在默认配置下输出不变，BUY/HOLD/EXIT 结果没有被因子默认改写。
4. Dashboard 只读展示因子状态，没有新增 factor/rules 写 API 或直接写按钮。
5. `factor-researcher` 的 write scope 不包含 `rules/`、`factors/`、execution、broker、risk、live 相关路径。
6. `factor_code` 仍是 `manual_code_apply_required`，不能被 applier 自动 apply。
7. `deployment_records` / `failure_records` / rollback 文档齐备，能够审计每次 factor hot apply。
8. protected paths 未被修改或提交，运行 artifacts 未被提交。
9. 容器测试通过；如果指定的 `dashboard` pytest 命令仍因镜像缺少 `pytest` 失败，则不得宣称该项已经满足。

## 绝对禁止合并的情况

出现任一情况，必须阻止合并：

- `submit_mode=live` 出现在默认配置。
- `live_submit=true` 出现在默认配置。
- `factor_engine.allow_actionable_consumption=true` 出现在默认配置。
- extended-hours factor 可以直接触发 BUY。
- Dashboard scheduler 恢复 submit 权限。
- `factor-researcher` 可以写 broker/execution/risk/live paths。
- `factor_code` 可以被 applier 自动应用。
- 容器测试未通过。
- protected paths 或运行 artifacts 被提交。
- 缺少 rollback 文档，或无法追溯 registry hot apply 的 deployment record。

## 测试命令

合并 `main` 前，至少要执行以下容器命令：

```bash
docker compose build dashboard

docker compose run --rm dashboard sh -lc '
  cd /app &&
  PYTHONPATH=/app:/app/system/engine/src python -m pytest -q
'
```

如果需要补充定位当前镜像/测试接线问题，可额外执行：

```bash
docker compose --profile test build test-runner
docker compose --profile test run --rm test-runner
```

补充说明：

- 第一组命令是合并 `main` 的硬门槛。
- 第二组命令只能作为补充验证，不等价于第一组命令已经满足。

## 关闭 Factor Engine Shadow Mode 的标准做法

如果需要关闭当前的 shadow mode，不要把 `mode` 改成其他运行模式，也不要打开 `allow_actionable_consumption`。

标准做法是：

1. 在当前部署实际使用的配置覆盖层中，将 `factor_engine.enabled` 设为 `false`。
2. 保持 `factor_engine.allow_actionable_consumption=false`。
3. 保持 `execution.submit_mode=guarded` 和 `execution.live_submit=false`。
4. 重启相应 runtime / dashboard 进程，使配置生效。
5. 在 `strategy` overview 或 latest cycle 摘要中确认 Factor Engine 已停用，且交易信号行为未变化。

## Factor Researcher Live 同步原则

`factor-researcher` 不应同步到 live，除非主 agent 单独审批。

这条原则包括：

- 不自动同步 `cron/factor-research-afterhours.json`
- 不让 `factor-researcher` 自己 approve / apply proposal
- 不让 `factor-researcher` 直接写 `rules/`、`factors/`、execution、broker、risk、live 相关路径
- 不让 `factor-researcher` 通过 Dashboard control 或其他热路径接口切 mode

## 当前分支的结论

`factor-researcher` 分支到 FR-09 为止，定位仍然是：

- 因子化基础设施分支
- shadow-first
- governance-first
- default behavior preserving

只有在上面的合并准入标准全部满足后，才应考虑合并到 `main`。
