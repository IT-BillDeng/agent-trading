# CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md

> 推荐放置路径：`docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md`  
> 推荐工作分支：`factor-researcher`  
> 目标：把 `agent-trading` 从「规则策略驱动」渐进迁移到「因子化驱动 + 独立因子研究冷路径」，同时保持当前交易热路径安全、可审计、默认 paper + guarded。

---

## 0. 当前项目边界

当前项目已经完成一轮关键安全硬化：canonical ControlPlane、live hard gate、risk hard stops、DataHealth、rule schema、proposal review、hot/cold apply gate、Dashboard scheduler 降权等骨架已经存在；但系统仍然是 **paper + guarded 默认态**，不是默认允许自动 live submit 的系统。

本计划必须遵守现有核心原则：

```text
Engine 负责机械执行
agent 负责判断与治理
strategist / researcher 不直接下单
Dashboard scheduler 只做 preview-only
当前默认 mode=paper, submit_mode=guarded, live_submit=false
```

这次迁移的正确方式不是推倒重写，而是：

```text
保留交易热路径
新增 Factor Engine shadow mode
新增 Factor Registry / Factor Store / Factor Attribution
新增 factor-researcher 冷路径 subagent
通过 proposal / approval / applier 把验证后的因子接入主系统
```

---

## 1. 分支与总体策略

### 1.1 创建分支

```bash
git checkout main
git pull --ff-only
git checkout -b factor-researcher
```

### 1.2 分支目标

`factor-researcher` 分支不是用来直接优化交易收益的，而是搭建因子化基础设施：

```text
FR-00  容器测试基线与安全边界确认
FR-01  因子系统契约文档与目录骨架
FR-02  Factor Registry schema + behavior-preserving 初始 registry
FR-03  Factor Engine shadow mode，计算现有规则用到的因子
FR-04  Factor Store / artifacts/factors，只写 shadow snapshot
FR-05  Dashboard / Strategy Overview 只读展示 factor health
FR-06  Rule Engine 兼容 factor-based conditions，但默认不改变现有信号
FR-07  Backtest factor attribution / IC 基础统计
FR-08  factor-researcher subagent + cron taskFile 冷路径
FR-09  Factor Proposal / Approval / Applier 接入
FR-10  合并 main 前验收与回滚文档
```

### 1.3 最高优先级约束

任何 Batch 都不得：

```text
修改 .env
修改 properties/*
修改 broker secrets
提交 runtime/*
提交 logs/latest/*
提交 artifacts/broker/*
把 execution.live_submit 改成 true
新增真实 order submit 路径
让 Dashboard scheduler 恢复 submit 权限
扩大 watchlist
新增真实交易策略
提高仓位或风险上限
让 factor-researcher 直接改 execution / broker / live gate
```

---

## 2. 容器环境测试基线

所有 Codex Batch 都必须在容器环境中测试。不要只在 host 上跑 `pytest`。

### 2.1 标准容器测试命令

在仓库根目录执行：

```bash
docker compose build dashboard

docker compose run --rm dashboard sh -lc '
  cd /app &&
  PYTHONPATH=/app:/app/system/engine/src python -m pytest -q
'
```

如果容器内缺少测试依赖，先不要随便改 Dockerfile。优先检查项目已有 requirements，再由 Codex 明确说明原因。可临时诊断：

```bash
docker compose run --rm dashboard sh -lc '
  cd /app &&
  python -V &&
  python -m pip --version &&
  PYTHONPATH=/app:/app/system/engine/src python -m pytest --version
'
```

### 2.2 每轮必须检查 protected paths

```bash
git diff --name-only | grep -E '^(\.env|properties/|runtime/|logs/latest/|artifacts/broker/)' && \
  echo 'ERROR: protected path modified' && exit 1 || true
```

### 2.3 每轮必须检查 live 配置没有被打开

```bash
python - <<'PY'
import json
from pathlib import Path
for p in [Path('config/app.defaults.json'), Path('config/app_config.docker.json')]:
    if not p.exists():
        continue
    data = json.loads(p.read_text())
    execution = data.get('execution', {})
    if execution.get('live_submit') is True:
        raise SystemExit(f'ERROR: live_submit=true in {p}')
    if execution.get('submit_mode') == 'live':
        raise SystemExit(f'ERROR: submit_mode=live in {p}')
print('live config check ok')
PY
```

### 2.4 每轮 Codex 完成报告必须包含

```text
1. 修改文件列表
2. 新增文件列表
3. 新增/修改测试列表
4. 容器测试命令与结果
5. 是否修改 protected paths：必须为否
6. 是否修改 live_submit / submit_mode：必须为否
7. 是否新增 submit path：必须为否
8. 当前 Batch 是否改变交易行为：默认必须为否，除非本计划明确允许
```

---

## 3. 总体架构目标

目标架构：

```text
冷路径：

Market / History Data
  -> Factor Researcher
  -> Candidate Factor Hypothesis
  -> Factor Validation / IC / Backtest / Correlation / Cost
  -> Factor Proposal
  -> Approval Queue
  -> Applier
  -> Approved Factor Registry / Rules

热路径：

Market Data
  -> Approved Factor Engine
  -> Rule Engine / Signal Arbiter
  -> Risk Manager
  -> Execution Preview
  -> Dashboard
```

关键边界：

```text
factor-researcher 可以探索，但不能交易
Factor Engine 可以计算，但 shadow mode 不影响交易
Rule Engine 只消费已批准的 factor definitions
Applier 只应用已批准且验证通过的 hot changes
cold factor code changes 必须人工合并或通过主 agent 明确审批
```

---

## 4. Batch FR-00：容器测试与安全基线

### 4.1 目标

建立 `factor-researcher` 分支上的测试基线，不改业务逻辑。

### 4.2 允许修改

```text
docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md  # 放入本文档
```

如需要，可新增：

```text
scripts/check_factor_branch_safety.sh
```

但不得修改交易代码。

### 4.3 Codex Prompt

```text
请读取 docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md，只执行 Batch FR-00。

任务：
1. 确认当前分支为 factor-researcher。
2. 在容器环境中运行：
   docker compose build dashboard
   docker compose run --rm dashboard sh -lc 'cd /app && PYTHONPATH=/app:/app/system/engine/src python -m pytest -q'
3. 不修改交易代码。
4. 如果测试失败，只做诊断总结，不要自动修复非 FR-00 范围的问题。
5. 检查 protected paths 未被修改。
6. 检查 config/app.defaults.json 和 config/app_config.docker.json 中 live_submit 未被打开，submit_mode 未被设为 live。
7. 输出 FR-00 completion report。

禁止：
- 不要修改 .env、properties、runtime、logs/latest、artifacts/broker。
- 不要改 live gate。
- 不要新增任何 submit path。
- 不要扩大 watchlist。

完成后停止。
```

### 4.4 验收

```text
容器 pytest 全绿，或明确记录现有失败且未扩大修改范围
protected paths 无修改
live config 未打开
```

---

## 5. Batch FR-01：因子系统契约文档与目录骨架

### 5.1 目标

先定义因子系统契约，不影响运行逻辑。

### 5.2 新增文件建议

```text
docs/factor-system-contract.md
specs/factor-registry-schema-v1.md
factors/README.md
factors/registry.json
artifacts/factors/.gitkeep
artifacts/factor_research/.gitkeep
```

注意：`artifacts/factors/` 和 `artifacts/factor_research/` 可以保留 `.gitkeep`，但不要提交运行生成的 `.jsonl` / latest 文件。

### 5.3 文档必须定义

```text
factor_id 命名规范
factor 类型：technical / session / risk / cost / fundamental / text / context_only
输入数据类型：regular_session_bars / extended_hours_bars / quotes / account / news
输出类型：numeric / boolean / categorical / vector
session 语义：regular / premarket / afterhours / context_only
是否允许 actionable：true / false
是否 point-in-time
required_bars
lookback / horizon
timezone 要求：US session 必须 America/New_York
no-lookahead 要求
extended-hours 默认只能 context_only
因子进入交易系统的 proposal / approval / applier 流程
hot factor config vs cold factor code change 的区别
```

### 5.4 初始 `factors/registry.json`

只允许 behavior-preserving metadata，不改变策略行为。例如：

```json
{
  "schema_version": 1,
  "defaults": {
    "mode": "shadow",
    "allow_actionable_consumption": false,
    "regular_session_only_for_indicators": true
  },
  "factors": {
    "rsi_14_30m": {
      "type": "technical",
      "implementation": "builtin:rsi",
      "inputs": ["regular_session_30m_bars"],
      "params": {"period": 14},
      "session": "regular",
      "timeframe": "30min",
      "output": "numeric",
      "usage": ["shadow", "rule_condition_candidate"],
      "actionable": false,
      "version": 1
    },
    "bollinger_zscore_20_2_30m": {
      "type": "technical",
      "implementation": "builtin:bollinger_zscore",
      "inputs": ["regular_session_30m_bars"],
      "params": {"period": 20, "std_dev": 2.0},
      "session": "regular",
      "timeframe": "30min",
      "output": "numeric",
      "usage": ["shadow", "rule_condition_candidate"],
      "actionable": false,
      "version": 1
    },
    "volume_ratio_20_30m": {
      "type": "technical",
      "implementation": "builtin:volume_ratio",
      "inputs": ["regular_session_30m_bars"],
      "params": {"period": 20},
      "session": "regular",
      "timeframe": "30min",
      "output": "numeric",
      "usage": ["shadow", "rule_condition_candidate"],
      "actionable": false,
      "version": 1
    },
    "premarket_gap_pct": {
      "type": "session_context",
      "implementation": "builtin:premarket_gap_pct",
      "inputs": ["extended_hours_bars", "previous_regular_close"],
      "session": "premarket",
      "timeframe": "30min",
      "output": "numeric",
      "usage": ["shadow", "context_only", "risk_hint_candidate"],
      "actionable": false,
      "version": 1
    }
  }
}
```

### 5.5 Codex Prompt

```text
请读取 docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md，只执行 Batch FR-01。

任务：
1. 新增 docs/factor-system-contract.md。
2. 新增 specs/factor-registry-schema-v1.md。
3. 新增 factors/README.md。
4. 新增 behavior-preserving 的 factors/registry.json。
5. 新增 artifacts/factors/.gitkeep 和 artifacts/factor_research/.gitkeep。
6. 不修改交易逻辑，不修改 rule_engine，不修改 risk，不修改 live execution。
7. 容器中运行 pytest -q。
8. 输出 completion report。

关键要求：
- factors/registry.json 的 defaults.mode 必须是 shadow。
- allow_actionable_consumption 必须是 false。
- extended-hours factor 默认 context_only，不得进入 actionable path。
- 本 Batch 不得改变任何 BUY/HOLD/EXIT 结果。

完成后停止。
```

### 5.6 验收

```text
只新增文档/registry/目录骨架
容器 pytest 全绿
无交易行为变化
```

---

## 6. Batch FR-02：Factor Registry Schema 与校验器

### 6.1 目标

实现 registry 的加载与 schema 校验，但不计算因子、不影响交易。

### 6.2 新增文件建议

```text
system/engine/src/engine/factors/__init__.py
system/engine/src/engine/factors/registry.py
system/engine/src/engine/factors/schema.py
system/engine/tests/test_factor_registry_schema.py
```

### 6.3 功能要求

```text
load_factor_registry(path)
validate_factor_registry(data)
FactorDefinition dataclass 或 equivalent structure
registry config hash
unknown implementation 拒绝或 warning，v1 推荐拒绝
unknown usage 拒绝
actionable=true 在 defaults.allow_actionable_consumption=false 时拒绝或降级，v1 推荐拒绝
extended-hours factor 若 usage 包含 actionable，必须拒绝
required fields 缺失必须拒绝
params 范围校验
```

### 6.4 允许的 implementation 白名单

```text
builtin:rsi
builtin:bollinger_zscore
builtin:volume_ratio
builtin:premarket_gap_pct
builtin:afterhours_move_pct
builtin:overnight_return_pct
builtin:atr_pct
builtin:return
```

v1 可以只实现 schema 对这些名字的接受，不要求全部计算。

### 6.5 Codex Prompt

```text
请读取 docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md，只执行 Batch FR-02。

任务：
1. 新增 engine.factors.registry / schema 模块。
2. 实现 factors/registry.json 的加载与校验。
3. 添加 FactorDefinition 或等价结构，包含 factor_id、type、implementation、inputs、params、session、timeframe、output、usage、actionable、version、config_hash。
4. 添加测试：
   - valid registry 通过。
   - missing required field 被拒绝。
   - unknown implementation 被拒绝。
   - extended-hours factor 设置 actionable=true 被拒绝。
   - defaults.allow_actionable_consumption=false 时 actionable factor 被拒绝。
   - invalid RSI period / Bollinger std_dev / volume period 被拒绝。
5. 不接入 rule_engine，不接入 runtime，不改变交易行为。
6. 容器运行 pytest -q。
7. 输出 completion report。

禁止：
- 不要修改 live gate。
- 不要修改 broker/execution。
- 不要提交 runtime/logs/artifacts 生成物。

完成后停止。
```

### 6.6 验收

```text
registry schema 测试通过
无 runtime 行为变化
无交易行为变化
```

---

## 7. Batch FR-03：Factor Engine Shadow Mode

### 7.1 目标

实现 Factor Engine，但只在 shadow mode 计算，不影响 rule_engine 输出。

### 7.2 新增/修改文件建议

```text
system/engine/src/engine/factors/engine.py
system/engine/src/engine/factors/builtins.py
system/engine/tests/test_factor_engine_shadow.py
system/engine/tests/test_factor_builtins.py
```

### 7.3 必须支持的内置因子

第一批只实现当前规则所需或上下文有用的因子：

```text
rsi_14_30m
bollinger_zscore_20_2_30m
volume_ratio_20_30m
premarket_gap_pct
```

其中：

```text
rsi / bollinger / volume_ratio 只使用 regular-session completed bars
premarket_gap_pct 只作为 context_only
```

### 7.4 输入输出

输入：

```text
symbol
bars
now 或 evaluation_time
registry
market/session metadata，可选
```

输出：

```json
{
  "symbol": "AAPL",
  "timestamp": "...",
  "registry_hash": "...",
  "mode": "shadow",
  "factors": {
    "rsi_14_30m": {
      "value": 42.1,
      "ready": true,
      "actionable": false,
      "source": "regular_session_completed_bars",
      "reason": "ok",
      "config_hash": "..."
    }
  }
}
```

### 7.5 关键测试

```text
因子计算不 mutate input bars
RSI 与现有 indicators.py 结果一致
Bollinger zscore 与现有逻辑一致或有明确公式测试
volume_ratio 与现有规则逻辑一致
premarket bars 不进入 RSI / Bollinger 计算
缺少 required bars 时 ready=false
```

### 7.6 Codex Prompt

```text
请读取 docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md，只执行 Batch FR-03。

任务：
1. 实现 Factor Engine shadow mode。
2. 实现 builtins：rsi、bollinger_zscore、volume_ratio、premarket_gap_pct。
3. 仅添加单元测试，不接入 runtime 主循环。
4. 确保 regular technical factors 只消费 regular-session completed bars。
5. 确保 premarket_gap_pct 只作为 context_only，actionable=false。
6. 确保因子计算结果包含 ready/reason/source/config_hash。
7. 容器运行 pytest -q。
8. 输出 completion report。

禁止：
- 不要改变 rule_engine 当前信号结果。
- 不要接入 execution path。
- 不要新增策略。
- 不要写 artifacts/factors 运行产物到 git。

完成后停止。
```

### 7.7 验收

```text
Factor Engine 可单测计算
现有 rule_engine / runtime 不受影响
容器 pytest 全绿
```

---

## 8. Batch FR-04：Factor Store 与 Runtime Shadow Snapshot

### 8.1 目标

把 Factor Engine 接入 runtime 的 shadow 分支，只写 snapshot，不影响信号/风控/preview。

### 8.2 新增/修改文件建议

```text
system/engine/src/engine/factors/store.py
system/engine/src/engine/runtime.py
system/engine/tests/test_factor_store.py
system/engine/tests/test_runtime_factor_shadow.py
```

### 8.3 配置建议

在 `config/app.defaults.json` 新增：

```json
{
  "factor_engine": {
    "enabled": true,
    "mode": "shadow",
    "registry_path": "factors/registry.json",
    "write_artifacts": true,
    "allow_actionable_consumption": false,
    "regular_session_only_for_indicators": true
  }
}
```

要求：

```text
enabled=true 可以接受，但必须 mode=shadow
allow_actionable_consumption=false
即使 Factor Engine 失败，也不能导致 live submit，最多在 DataHealth/diagnostics 标记 factor_shadow_error
```

### 8.4 Artifact 输出

运行时可写：

```text
artifacts/factors/latest.json
artifacts/factors/history/YYYY-MM-DD.jsonl
```

但这些运行产物不得提交到 git。只提交 `.gitkeep`。

### 8.5 Runtime latest cycle 字段

在 latest cycle 中增加：

```json
{
  "factor_engine": {
    "enabled": true,
    "mode": "shadow",
    "registry_hash": "...",
    "symbols": {
      "AAPL": {
        "factors_ready": 3,
        "factors_total": 4,
        "blocking": false,
        "reasons": []
      }
    }
  }
}
```

### 8.6 Codex Prompt

```text
请读取 docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md，只执行 Batch FR-04。

任务：
1. 新增 Factor Store，支持 latest.json 与 history JSONL 写入。
2. 将 Factor Engine 接入 runtime shadow path。
3. latest cycle 增加 factor_engine 摘要。
4. Factor Engine 失败不得改变 strategy.signals、risk.decisions、execution_preview、order_intents。
5. 添加测试：
   - factor snapshot 写入 temp artifacts dir。
   - runtime shadow factor failure 不影响交易信号。
   - mode=shadow 且 allow_actionable_consumption=false。
   - artifacts/factors 运行产物不提交，测试用 tempdir。
6. 容器运行 pytest -q。
7. 输出 completion report。

禁止：
- 不要把 factors 用于 BUY/HOLD/EXIT 决策。
- 不要改 live gate。
- 不要提交 artifacts/factors/latest.json 或 history 文件。

完成后停止。
```

### 8.7 验收

```text
runtime 可生成 factor shadow summary
交易输出不变
容器 pytest 全绿
```

---

## 9. Batch FR-05：Dashboard / Strategy Overview 只读展示

### 9.1 目标

在 Dashboard 只读展示 factor health，不新增编辑按钮，不新增写 endpoint。

### 9.2 修改文件建议

```text
dashboard/api/strategy.py
dashboard/static/strategy.html
tests/test_strategy_page_structure.py
tests/test_factor_strategy_api.py
```

### 9.3 API 输出建议

在 `/api/strategy-overview` 或现有 strategy API 中增加：

```json
{
  "factor_engine": {
    "enabled": true,
    "mode": "shadow",
    "registry_hash": "...",
    "symbols": {
      "AAPL": {
        "profile": null,
        "factors_ready": 3,
        "factors_total": 4,
        "factors": {
          "rsi_14_30m": {
            "value": 42.1,
            "ready": true,
            "actionable": false,
            "reason": "ok"
          }
        }
      }
    }
  }
}
```

### 9.4 UI 要求

`/strategy` 页面新增只读区块：

```text
Factor Engine Shadow
Factor Health Matrix
```

最低展示：

```text
symbol
factor_id
value
ready
reason
actionable=false
source/session
```

### 9.5 Codex Prompt

```text
请读取 docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md，只执行 Batch FR-05。

任务：
1. 在 strategy overview API 增加 factor_engine 只读数据。
2. 在 /strategy 页面增加 Factor Engine Shadow / Factor Health Matrix 展示。
3. 不新增任何可编辑 factor/rules 的 Dashboard endpoint。
4. 不新增任何按钮直接修改 factors/registry.json 或 rules/rules.json。
5. 添加测试：
   - strategy API 返回 factor_engine 字段。
   - 页面包含 Factor Engine Shadow 或 Factor Health Matrix。
   - 页面不包含直接写 factor registry 的按钮或 endpoint。
6. 容器运行 pytest -q。
7. 输出 completion report。

禁止：
- 不要新增写 API。
- 不要改 scheduler submit 权限。
- 不要改 live gate。

完成后停止。
```

### 9.6 验收

```text
Dashboard 只读展示因子
无编辑入口
容器 pytest 全绿
```

---

## 10. Batch FR-06：Rule Engine 兼容 Factor-based Conditions

### 10.1 目标

让 rule_engine 支持未来引用因子，但默认仍使用旧规则行为。此 Batch 是第一处可能接触信号逻辑，必须特别保守。

### 10.2 设计原则

```text
旧 rules.json 行为必须不变
新 factor-based rule format 仅在测试 fixture 中使用
factor_engine.allow_actionable_consumption=false 时，factor-based conditions 不应进入真实 actionable path
如果启用 factor-based condition，必须使用已批准 registry 中的 factor_id
```

### 10.3 新规则格式建议

```json
{
  "indicator": "factor",
  "factor_id": "rsi_14_30m",
  "operator": "cross_above",
  "value": 30
}
```

或者：

```json
{
  "factor": "rsi_14_30m",
  "operator": "cross_above",
  "value": 30
}
```

选择一种，并写入 schema。

### 10.4 必须添加的测试

```text
旧规则 fixture 输出不变
factor condition 可以在 isolated test 中触发
unknown factor_id 被拒绝
factor not ready 时 condition=false 且 reason=factor_not_ready
context_only / actionable=false factor 不得用于 actionable BUY condition
cross_above 对 factor 值仍使用 true cross 语义
SignalArbiter metadata 保留 used_factors
```

### 10.5 Codex Prompt

```text
请读取 docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md，只执行 Batch FR-06。

任务：
1. 扩展 rule schema，支持 factor-based condition 格式。
2. 扩展 rule_engine，使测试 fixture 可以消费 Factor Engine 输出。
3. 默认配置下，现有 rules/rules.json 不应改变信号行为。
4. factor_engine.allow_actionable_consumption=false 时，不允许 context_only 或 actionable=false factor 生成 actionable BUY。
5. signal diagnostics 增加 used_factors / factor_values / factor_readiness。
6. 添加行为等价测试：旧规则无 factor conditions 时输出不变。
7. 添加 factor condition 测试。
8. 容器运行 pytest -q。
9. 输出 completion report。

禁止：
- 不要把当前 production rules 改成 factor-based。
- 不要改变当前 BUY/HOLD/EXIT 结果。
- 不要改 live/execution/risk hard gates。

完成后停止。
```

### 10.6 验收

```text
默认规则行为不变
factor condition 能在测试中工作
context_only factor 不可 action
容器 pytest 全绿
```

---

## 11. Batch FR-07：Backtest Factor Attribution 与基础 IC

### 11.1 目标

在 backtest / research 中输出因子表现指标，但不影响交易热路径。

### 11.2 新增/修改文件建议

```text
system/engine/src/engine/factors/attribution.py
system/engine/src/engine/backtest.py
system/engine/tests/test_factor_attribution.py
system/engine/tests/test_backtest_factor_attribution.py
```

### 11.3 输出指标

最低实现：

```text
coverage
missing_rate
mean
std
rank_by_symbol 可选
future_return correlation，称为 ic
rank_ic 可选
hit_rate 可选
decay_1bar / decay_2bar 可选
factor_used_by_rules
cost_adjusted_contribution 暂可占位 null
```

Backtest 输出增加：

```json
{
  "factor_attribution": {
    "factors": {
      "rsi_14_30m": {
        "coverage": 0.91,
        "missing_rate": 0.09,
        "ic_1bar": 0.02,
        "ic_2bar": null,
        "symbols": {
          "AAPL": {"coverage": 0.95, "ic_1bar": 0.01}
        }
      }
    }
  }
}
```

### 11.4 关键要求

```text
不能有 lookahead
future_return label 必须基于 t 之后的数据
缺失数据必须显式 missing，不要填假值
样本不足时输出 null，并附 reason
默认 backtest 仍然 regular-session bars，不混入 extended-hours
```

### 11.5 Codex Prompt

```text
请读取 docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md，只执行 Batch FR-07。

任务：
1. 新增 factor attribution / IC 基础统计模块。
2. 将 backtest 输出扩展 factor_attribution 字段。
3. 不改变现有 return_pct、sharpe、max_drawdown、closed trade win_rate、fee_drag 等指标语义。
4. 确保 no-lookahead：factor_t 只能和 t 之后 future_return 计算相关性。
5. 样本不足输出 null + reason。
6. 添加测试：
   - 简单构造数据下 IC 计算正确。
   - 样本不足时 null。
   - 缺失 factor 时 missing_rate 正确。
   - backtest 原有指标仍存在。
7. 容器运行 pytest -q。
8. 输出 completion report。

禁止：
- 不要使用 factor_attribution 改变交易信号。
- 不要改变 execution path。
- 不要提交生成 artifacts。

完成后停止。
```

### 11.6 验收

```text
backtest 输出 factor_attribution
无 lookahead 测试
容器 pytest 全绿
```

---

## 12. Batch FR-08：factor-researcher subagent 冷路径

### 12.1 目标

新增独立因子研究 subagent，但它不是第二主 agent，也没有交易权限。

### 12.2 新增文件建议

```text
agents/factor_researcher.yaml
docs/tasks/cron/FACTOR_RESEARCH_AFTERHOURS.md
cron/factor-research-afterhours.json
docs/factor-researcher-role-contract.md
artifacts/factor_research/.gitkeep
```

### 12.3 Agent 权限边界

允许读取：

```text
docs/factor-system-contract.md
specs/factor-registry-schema-v1.md
factors/registry.json
artifacts/factors/*
artifacts/strategist/*
logs/latest/*
rules/rules.json
system/engine/tests/*
```

允许写：

```text
artifacts/factor_research/*
artifacts/strategist/approval_queue/*  # 仅 proposal，不直接 apply
```

建议允许写文档/测试，但不要默认允许改交易代码：

```text
docs/factor-*.md
specs/factor-*.md
system/engine/tests/test_factor_*.py
```

禁止写：

```text
.env
properties/*
runtime/*
logs/latest/*
artifacts/broker/*
system/engine/src/engine/live_execution.py
system/engine/src/engine/risk.py
system/engine/src/engine/broker_client.py
system/engine/src/engine/tiger_client.py
dashboard/api/control.py
dashboard/scheduler.py
docker-compose.yml
```

### 12.4 Cron 要求

`cron/factor-research-afterhours.json` 只做 desired state 声明，不自动启用到 live。项目 live 启停由主 agent 管理。

建议时间：

```text
US afterhours: 17:30 ET 或 18:00 ET
```

### 12.5 TaskFile 要求

`docs/tasks/cron/FACTOR_RESEARCH_AFTERHOURS.md` 必须要求：

```text
只读 factor snapshots / backtest / data health
生成 factor_research/latest.json
生成 factor_research/history.jsonl
可以生成 proposal draft，但不能 approve/apply
不得修改 rules/rules.json
不得修改 factors/registry.json，除非作为 proposal patch 内容保存
不得调用 execution submit
```

### 12.6 Codex Prompt

```text
请读取 docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md，只执行 Batch FR-08。

任务：
1. 新增 factor-researcher subagent 配置。
2. 新增 factor-research afterhours cron 声明。
3. 新增 docs/tasks/cron/FACTOR_RESEARCH_AFTERHOURS.md。
4. 新增 docs/factor-researcher-role-contract.md。
5. 明确 factor-researcher 是冷路径研究员，不是主 agent，不是交易员，不是发布员。
6. factor-researcher 可以写 artifacts/factor_research，但不能直接修改 rules/factors 或 execution。
7. 添加必要结构测试：
   - agent yaml 存在且 protected paths 不在 write scope。
   - cron taskFile 指向 docs/tasks/cron/FACTOR_RESEARCH_AFTERHOURS.md。
   - taskFile 中包含 no submit / no apply / no secrets 约束。
8. 容器运行 pytest -q。
9. 输出 completion report。

禁止：
- 不要把 factor-researcher 同步到 live。
- 不要创建 executor/order-submit 类 cron。
- 不要赋予 factor-researcher broker/execution 权限。

完成后停止。
```

### 12.7 验收

```text
factor-researcher 角色存在
权限边界清晰
无交易权限
容器 pytest 全绿
```

---

## 13. Batch FR-09：Factor Proposal / Approval / Applier 接入

### 13.1 目标

让验证后的因子可以通过现有 governance 链进入系统，但仍然禁止自动代码发布。

### 13.2 Proposal 类型

新增或扩展：

```text
proposal_type = factor_config
proposal_type = factor_rule_link
proposal_type = factor_code
```

含义：

```text
factor_config:
  只修改 factors/registry.json，hot apply 可选

factor_rule_link:
  修改 rules/rules.json，让规则引用已批准 factor，hot apply 但必须强验证

factor_code:
  新增/修改 factor implementation，cold only，manual_code_apply_required
```

### 13.3 Applier 规则

```text
factor_config 可以 hot apply 到 factors/registry.json
factor_rule_link 可以 hot apply 到 rules/rules.json，但必须 rule schema + factor schema 都通过
factor_code 必须 cold/manual，不能自动写 src 代码
所有 apply 必须写 deployment_records.jsonl
失败必须写 failure record
```

### 13.4 验证字段

proposal 必须包含：

```text
factor_id
hypothesis
input_data
session
usage
lookback/horizon
validation_results
ic / coverage / missing_rate
correlation_with_existing，可为 null 但必须显式
backtest_delta，可为 null 但必须显式
fee/cost impact，可为 null 但必须显式
paper_shadow_required_days
risk_notes
rollback_plan
```

### 13.5 Codex Prompt

```text
请读取 docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md，只执行 Batch FR-09。

任务：
1. 扩展 proposal schema，支持 factor_config / factor_rule_link / factor_code。
2. 扩展 applier：
   - factor_config 可 hot apply 到 factors/registry.json。
   - factor_rule_link 可 hot apply 到 rules/rules.json，但必须同时通过 rule schema 和 factor registry schema。
   - factor_code 必须 cold/manual，不得自动改 engine source。
3. deployment record 中记录 changed_factors / changed_rules / registry_hash / validation_summary。
4. failure record 必须记录失败原因。
5. 添加测试：
   - approved factor_config hot apply 成功。
   - invalid factor registry hot apply 失败且写 failure record。
   - factor_code 被标记 manual_code_apply_required。
   - factor_rule_link 引用 unknown factor 时失败。
   - applier 不修改 live/execution/broker 文件。
6. 容器运行 pytest -q。
7. 输出 completion report。

禁止：
- 不要自动 apply factor_code。
- 不要修改 live_execution / broker / risk gate。
- 不要允许 factor proposal 打开 live_submit。

完成后停止。
```

### 13.6 验收

```text
factor governance 接入 approval/applier
factor_code 仍 cold/manual
容器 pytest 全绿
```

---

## 14. Batch FR-10：合并前文档、回滚与主分支准入

### 14.1 目标

在准备合并 main 前，形成完整验收报告和回滚说明。

### 14.2 新增/修改文件建议

```text
docs/factorization-merge-readiness.md
docs/factor-system-rollback.md
```

### 14.3 Codex Prompt

```text
请读取 docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md，只执行 Batch FR-10。

任务：
1. 新增 docs/factorization-merge-readiness.md。
2. 新增 docs/factor-system-rollback.md。
3. 汇总 FR-00 到 FR-09 的能力、默认开关、风险边界、测试命令。
4. 明确 main 合并准入标准。
5. 明确如何关闭 Factor Engine shadow mode。
6. 明确如何回滚 factors/registry.json hot apply。
7. 明确 factor-researcher 不应同步到 live，除非主 agent 单独审批。
8. 容器运行 pytest -q。
9. 输出 completion report。

禁止：
- 不要新增功能。
- 不要修改交易逻辑。

完成后停止。
```

---

## 15. 什么时候可以合并到 main

### 15.1 可以第一次合并 main 的最低程度

建议不要等所有 Batch 完成才合并。最安全、最合理的第一次合并点是：

```text
FR-00 到 FR-05 完成
```

也就是：

```text
有 factor contract
有 registry schema
有 Factor Engine shadow mode
有 Factor Store
有 Dashboard 只读展示
但 Rule Engine 仍未真正消费 factor conditions
交易行为完全不变
```

这个阶段合并 main 的条件：

```text
1. 容器 pytest -q 全绿
2. Dashboard scheduler 仍 preview-only
3. live_submit 仍 false
4. submit_mode 仍 guarded
5. protected paths 未修改
6. 无新增 broker submit path
7. Factor Engine mode=shadow
8. allow_actionable_consumption=false
9. 现有 BUY/HOLD/EXIT fixture 输出不变
10. Backtest 原有核心指标不变，最多新增 factor 字段
11. Dashboard 只有只读展示，无写 endpoint
12. artifacts/factors/latest.json 等运行产物未提交
```

这是推荐的 **MVP 因子化基础设施合并点**。

### 15.2 FR-06 是否可以和第一次合并一起进入 main

谨慎。FR-06 接触 rule_engine 逻辑，建议单独 PR / 单独合并。

FR-06 可以合并 main 的条件：

```text
1. 旧 rules.json 行为等价测试通过
2. factor-based condition 只在测试 fixture 或显式配置中启用
3. 默认 factors/registry.json 不让因子进入 actionable path
4. context_only / extended-hours factor 不能触发 BUY
5. Signal metadata 增加 used_factors，但 signal action 不变
6. 容器 pytest 全绿
```

### 15.3 FR-08 factor-researcher 是否可以合并 main

可以，但必须满足：

```text
1. factor-researcher 是 subagent，不是第二主 agent
2. cron 只是 desired state，不自动同步 live
3. write scope 不包含 execution/broker/risk/live paths
4. taskFile 明确 no submit / no apply / no secrets
5. 容器 pytest 全绿
```

### 15.4 FR-09 governance 是否可以合并 main

可以，但必须满足：

```text
1. factor_config hot apply 只改 factors/registry.json
2. factor_rule_link hot apply 必须双 schema validation
3. factor_code cold/manual，不自动改 source
4. invalid apply 必须写 failure record
5. deployment record 包含 changed_factors / registry_hash / validation_summary
6. 容器 pytest 全绿
```

### 15.5 绝对不能合并 main 的情况

出现任一情况不得合并：

```text
pytest 在容器中不全绿
Dashboard scheduler 可 submit
live_submit=true 出现在默认配置
submit_mode=live 出现在默认配置
factor_engine.allow_actionable_consumption=true 出现在默认配置
extended-hours factor 可以直接触发 BUY
factor-researcher 可以写 broker/execution/risk/live paths
factor_code 可以被 applier 自动应用
protected paths 被修改或提交
运行 artifacts 被提交
现有规则默认行为被改变但没有明确审批
没有 rollback 文档
没有 completion report
```

---

## 16. 推荐的 PR / merge 结构

不要把整个分支一次性糊进 main。推荐拆成：

```text
PR 1: FR-00 ~ FR-02
  docs + registry schema，无 runtime 接入

PR 2: FR-03 ~ FR-05
  Factor Engine shadow + store + Dashboard read-only

PR 3: FR-06
  Rule Engine factor condition compatibility，默认不启用

PR 4: FR-07
  Factor attribution / IC in backtest

PR 5: FR-08
  factor-researcher subagent / cron / taskFile

PR 6: FR-09 ~ FR-10
  Factor proposal/applier integration + merge/rollback docs
```

如果你只想先把因子化基础设施合入 main，优先合并：

```text
PR 1 + PR 2
```

后面的 PR 可以继续留在 `factor-researcher` 分支迭代。

---

## 17. 主 agent / OpenClaw 操作建议

在 `factor-researcher` 分支开发期间：

```text
不要把 factor-research-afterhours cron 同步到 live
不要让 factor-researcher 修改主交易配置
不要让它调用 dashboard control API 切 mode
不要让它 approve/apply 自己的 proposal
```

如果后续要启用 factor-researcher cron，建议先在 paper 环境中只读运行 5 个交易日，确认：

```text
artifacts/factor_research/latest.json 正常生成
没有修改 rules/factors
没有修改 runtime/control
没有调用 execution submit
没有产生噪音通知
```

---

## 18. 最终验收总表

| 项目 | 合格标准 |
|---|---|
| 安全 | live_submit=false，submit_mode=guarded，scheduler preview-only |
| 容器测试 | `docker compose run --rm dashboard ... pytest -q` 全绿 |
| 保护路径 | `.env / properties / runtime / logs/latest / artifacts/broker` 未修改 |
| 因子模式 | `factor_engine.mode=shadow` |
| 行为变化 | 默认 BUY/HOLD/EXIT 不变 |
| extended-hours | 默认 context_only，不触发 actionable BUY |
| Dashboard | 只读 factor health，无编辑 endpoint |
| Rule Engine | factor condition 兼容但默认不启用 |
| Research Agent | subagent，无交易/发布权限 |
| Applier | factor_config hot，factor_code cold/manual |
| Artifacts | 运行产物不提交 git |
| 回滚 | 有 `docs/factor-system-rollback.md` |

---

## 19. 给 Codex 的通用前缀

每次交给 Codex 时，建议都用这个前缀：

```text
你正在 agent-trading 项目的 factor-researcher 分支上工作。
请先读取 docs/tasks/CODEX_FACTOR_RESEARCHER_MIGRATION_PLAN.md。
本次只执行 Batch FR-XX，不要提前执行后续 Batch。

全局禁止：
- 不要修改 .env、properties、runtime、logs/latest、artifacts/broker。
- 不要打开 live_submit。
- 不要把 submit_mode 设为 live。
- 不要新增真实 broker submit 路径。
- 不要让 Dashboard scheduler 恢复 submit 权限。
- 不要扩大 watchlist。
- 不要新增真实交易策略。
- 不要提交运行生成 artifacts。

测试必须在容器中执行：

docker compose build dashboard

docker compose run --rm dashboard sh -lc '
  cd /app &&
  PYTHONPATH=/app:/app/system/engine/src python -m pytest -q
'

完成后输出：
1. 修改文件列表
2. 新增文件列表
3. 新增/修改测试列表
4. 容器测试结果
5. 是否触碰 protected paths
6. 是否改变交易行为
7. 是否影响 live gate / scheduler submit
8. Batch completion report

完成后停止。
```

---

## 20. 最终原则

这条分支的核心不是“让 AI 找到赚钱因子后马上交易”，而是建立一套可验证、可审计、可回滚的因子研究基础设施。

正确顺序是：

```text
Factor Contract
  -> Factor Registry
  -> Factor Engine Shadow
  -> Factor Store
  -> Factor Attribution
  -> Factor Researcher
  -> Factor Proposal
  -> Approval / Applier
  -> Paper Shadow
  -> 再考虑 actionability
```

不要跳过前面的验证层，直接让 LLM 生成因子并影响 BUY。那不是因子化，是自动过拟合。杂鱼项目已经有安全治理骨架了，别把它拆掉重来。
