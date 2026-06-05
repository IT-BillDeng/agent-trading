# Factor-First Rewrite Guardrails

更新时间：2026-04-23

## 目的

这份文档是 `factor-researcher` 分支进入 factor-first rewrite 之前的基线冻结说明。

它只做三件事：

- 汇总当前 canonical 边界
- 明确后续重写不可破坏的默认安全值
- 记录 FF-00 的容器测试基线

它不是新的功能设计文档，也不授权任何新的交易、submit、broker 或 live 能力。

## Canonical 来源

FF-00 的 guardrails 以以下文档为准：

- `docs/factor-system-contract.md`
- `docs/factorization-merge-readiness.md`
- `docs/factor-researcher-role-contract.md`
- `docs/gpt-pro-hardening-summary.md`

## 当前 canonical 边界汇总

### 1. 执行与 live 边界

- 默认执行模式必须保持 `execution.submit_mode=guarded`
- 默认必须保持 `execution.live_submit=false`
- 不允许因为 factor rewrite 打开新的 broker submit path
- Dashboard scheduler 必须继续 preview-only
- live gate 仍然由现有 hard gate / readiness gate 控制，FF-00 不得削弱

### 2. Factor Engine 边界

- `factor_engine.enabled=true` 可以保留，但只允许 shadow 运行
- `factor_engine.mode` 必须保持 `shadow`
- `factor_engine.allow_actionable_consumption` 必须保持 `false`
- registry defaults 必须保持 `mode=shadow`
- registry defaults 必须保持 `allow_actionable_consumption=false`
- v1 默认不允许 factor 直接进入 actionable BUY hot path
- factor-based condition 目前只是 schema-compatible，不代表默认开启 factor trading

### 3. Registry 与 runtime 边界

- 当前 v1 registry 仍应保持 non-actionable
- `factor.actionable` 不应在默认基线中变成 `true`
- `usage` 不应出现 `actionable`
- extended-hours / context 因子不能默认进入 BUY 决策
- Factor Engine 即使失败，也不应改变 `strategy.signals`、`risk.decisions`、`execution_preview`、`order_intents`

### 4. Dashboard 与治理边界

- Dashboard 只能只读展示 factor 状态
- 不新增直接写 `factors/registry.json` 或 `rules/rules.json` 的 Dashboard endpoint
- Dashboard scheduler 不恢复 submit 权限
- `factor_rule_link` 不意味着默认可行动因子交易
- `factor_code` 仍然只能 cold/manual，不能被自动 apply

### 5. Factor Researcher 边界

- `factor-researcher` 是冷路径研究员，不是主 agent，不是交易员，不是发布员
- 不得获得 execution / broker / risk / live 权限
- 不得直接修改 `rules/*` 或 `factors/*`
- `factor-research-afterhours` 仍然只是 desired state，不自动同步到 live

## Rewrite 期间不可破坏的冻结项

下列项是 FF-00 显式冻结的 rewrite guardrails：

| Guardrail | 当前冻结值 | 不可破坏原因 |
|---|---|---|
| `execution.submit_mode` | `guarded` | 防止默认执行路径升级到 live submit |
| `execution.live_submit` | `false` | 防止真实下单默认开启 |
| `factor_engine.mode` | `shadow` | 保持 factor 只读、只算、不默认改写交易行为 |
| `factor_engine.allow_actionable_consumption` | `false` | 防止 factor 默认进入 actionable BUY |
| registry `defaults.mode` | `shadow` | registry 与 runtime 保持一致的 shadow-only 边界 |
| registry `defaults.allow_actionable_consumption` | `false` | registry 层禁止开启 actionable consumption |
| Dashboard scheduler | `preview-only` | 防止 Dashboard 越权触发 submit |

## FF-00 明确不做的事

- 不新增因子
- 不新增策略
- 不改变 BUY/HOLD/EXIT 行为
- 不修改 live gate
- 不新增 broker submit 路径
- 不修改 `.env`、`properties/*`、`runtime/*`、`logs/latest/*`、`artifacts/broker/*`
- 不让 factor 默认进入 actionable BUY
- 不让 `factor-researcher` 获得 execution / broker 权限

## Baseline Validation

FF-00 的容器验证命令固定为：

```bash
docker compose build dashboard

docker compose run --rm dashboard sh -lc '
  cd /app &&
  PYTHONPATH=/app:/app/system/engine/src python -m pytest -q
'
```

### 2026-04-23 Baseline Result

- 分支：`factor-researcher`
- 结果：`273 passed, 23 subtests passed in 0.73s`
- 结论：容器基线通过，可以作为 factor-first rewrite 的冻结起点

## 后续 batch 的使用方式

后续任何 factor-first rewrite batch，在声称“只做重构、不改行为”之前，至少应继续满足：

1. 本文中的冻结项未改变
2. 容器全量测试通过
3. Dashboard scheduler 仍然 preview-only
4. 默认配置仍然是 `guarded + live_submit=false + shadow-only`

如果任一项不满足，就不应把该批次描述为“仅重构”或“安全可合并”。
