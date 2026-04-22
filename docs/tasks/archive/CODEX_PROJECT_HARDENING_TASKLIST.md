# CODEX_PROJECT_HARDENING_TASKLIST.md

建议放置路径：`docs/tasks/CODEX_PROJECT_HARDENING_TASKLIST.md`  
适用项目：`agent-trading`  
版本日期：2026-04-20  
执行者：Codex / 人类工程师  
目标：把当前半自治 paper/guarded 交易系统，改造成**安全闸门可信、数据链路可诊断、策略逻辑可验证、agent 治理可落地**的系统。

---

## 0. 给 Codex 的总指令

你正在修改一个 agent-driven trading 项目。当前项目的核心原则是：

- Engine 负责机械执行。
- Agent / strategist 负责策略治理和提案。
- 当前默认状态应保持 `paper + guarded`。
- 不允许因为 Dashboard、scheduler 或 agent 的运行态字段而绕过 live 安全闸门。
- 在没有明确完成 P0 安全修复前，不要做任何提高自动交易能力的改动。

执行本任务清单时，必须遵守：

1. **每次只做一个任务编号**，不要把安全、策略、Dashboard、L3b 混在一个大提交里。
2. **先写或补测试，再改代码**。如果某任务无法单元测试，要写最小集成测试或明确的手动验证步骤。
3. **不要修改、读取或输出任何真实密钥**，包括 `.env`、`properties/*`、broker token、private key、Telegram token。
4. **不要提交 runtime 状态和历史执行记录**，包括 `runtime/`、`logs/latest/execution_state.json`、`artifacts/broker/*`。
5. **不要默认启用 live**。任何新增配置默认值必须是 off / signal-only / guarded / paper。
6. **不要扩大 watchlist，不要新增 broker，不要提高仓位上限**。这份任务清单先修安全和可信度，不追求收益。
7. 所有修改完成后，至少运行：

```bash
python -m unittest discover -s system/engine/tests -p 'test_*.py'
python -m compileall system/engine/src dashboard
```

如果环境里安装了 pytest，可以额外运行：

```bash
python -m pytest system/engine/tests -q
```

---

## 1. 当前已知事实与风险摘要

当前项目交接文档说明，系统已经具备规则引擎、风控、订单预览、Dashboard、岗位化 agent、strategist L3a 代码提案能力，以及 L3b 最小审批/应用治理骨架；但当前仍应被视为 paper + guarded 的半自治系统，而不是自动 live 发布系统。

当前代码审计发现的最高风险：

1. `dashboard/scheduler.py` 在 `trading_mode == "trade"` 时会直接把：

```python
app.raw["execution"]["live_submit"] = True
app.raw["execution"]["submit_mode"] = "live"
```

这会绕过配置层的 guarded 默认值。

2. 控制状态分裂：

```text
Dashboard 使用 trading_mode: off / signals / trade
Engine ControlPlane 使用 global.trade_mode: paper_live
```

这导致 UI、scheduler、Engine 对“能不能交易”的理解不一致。

3. `ControlPlane.can_trade()` 只检查 `enabled`，没有检查 symbol 级别的 `suspended: true`。

4. `risk.daily_loss_limit_pct` 被读取，但没有形成真正的 daily loss 硬阻断。

5. `rsi_reversal` 当前规则同时要求 `RSI < 30` 和 `RSI cross_above 30`，而 `cross_above` 当前实现只是 `value > threshold`，所以该规则基本等价于同一根 bar 上 `RSI < 30 AND RSI > 30`。

6. `cross_above / cross_below` 当前不是“穿越”，只是当前值的大于/小于。

7. `logs/latest/engine_cycle.json` 曾出现大量 `insufficient_bars` 和 `bars: 0`，说明 quote/API 表面正常不等于策略数据可用。

8. `dashboard/main.py` 中 execution-state reset 相关代码疑似被放进 `api_control()` 返回语句之后，实际不可达，需要拆成独立 endpoint。

---

## 2. 分阶段执行顺序

必须按以下顺序执行。不要跳过 P0。

| 阶段 | 目标 | 是否可并行 |
|---|---|---|
| P0 | 执行闸门与控制状态安全封锁 | 不可并行，必须最先做 |
| P1 | 风控硬限制补齐 | P0 完成后 |
| P2 | 策略规则正确性修复 | P0 完成后，可与 P1 部分并行 |
| P3 | 数据链路诊断 | P0 完成后 |
| P4 | 回测可信度修复 | P2 之后优先 |
| P5 | L3b 审批与应用产品化 | P0-P4 基本完成后 |
| P6 | Dashboard / runner 架构拆分 | P0-P3 完成后 |
| P7 | live 前置验收清单 | 最后，只做文档和 gate，不启用 live |

---

# P0：执行闸门与控制状态安全封锁

P0 的验收标准：

- Dashboard scheduler 不再能修改 `execution.live_submit` 或 `execution.submit_mode`。
- `LiveExecutionAdapter` 自身拥有最后一道 live gate。
- `suspended: true` 的 symbol 必须被阻断。
- 控制状态只有一个 canonical schema。
- 旧字段可以兼容读取，但不能作为越权依据。
- 所有默认状态都不能触发 broker live submit。

---

## T00 — 建立安全基线与测试入口

优先级：P0  
目标：在修改前建立可回归的安全测试入口。

### 需要新增/修改的文件

- `system/engine/tests/test_control_plane.py`
- `system/engine/tests/test_live_execution_gates.py`
- `system/engine/tests/test_dashboard_scheduler_safety.py`
- 可选：`system/engine/tests/helpers.py`

### 实施步骤

1. 新增 fake broker client，至少实现：
   - `create_order_no()`
   - `preview_order(payload)`
   - `place_order(payload)`
   - `cancel_order(...)`

2. fake client 必须记录：
   - `place_order_called`
   - `cancel_order_called`
   - `preview_order_called`

3. 写测试确认默认配置下：
   - `mode = paper`
   - `execution.submit_mode = guarded`
   - `execution.live_submit = false`
   - 调用 `LiveExecutionAdapter.submit_intent()` 不会调用 `place_order()`。

4. 写测试确认 control locked 时：
   - `submit_intent()` 返回 `submitted = False`
   - reason 包含 lock/gate 类信息。

### 验收标准

- 测试在当前实现上至少应暴露部分失败，证明测试能抓到风险。
- 后续 P0 任务完成后，这些测试必须全部通过。

---

## T01 — 统一 ControlPlane canonical schema

优先级：P0  
目标：消除 `trading_mode` 与 `global.trade_mode` 分裂。

### 需要修改的文件

- `system/engine/src/engine/control.py`
- `dashboard/main.py`
- `dashboard/scheduler.py`
- `system/engine/tests/test_control_plane.py`

### 推荐 canonical schema

在 `runtime/state/control_state.json` 中统一使用：

```json
{
  "locked": false,
  "reason": null,
  "updated_at": "...",
  "updated_by": "system",
  "global": {
    "enabled": true,
    "mode": "off"
  },
  "markets": {
    "US": true
  },
  "symbols": {},
  "risk": {
    "reduce_only": false,
    "emergency_flatten": false,
    "daily_loss_locked": false
  },
  "history": []
}
```

允许的 `global.mode`：

```text
off
signal_only
paper_trade
live_trade
```

含义：

| mode | 生成信号 | 生成订单意图/preview | broker place_order |
|---|---:|---:|---:|
| `off` | 否 | 否 | 否 |
| `signal_only` | 是 | 否 | 否 |
| `paper_trade` | 是 | 是 | 否 |
| `live_trade` | 是 | 是 | 仅在配置也显式 live 时允许 |

### 兼容要求

旧状态可能含有：

```json
{"trading_mode": "off|signals|trade"}
```

或者：

```json
{"global": {"trade_mode": "paper_live"}}
```

必须增加 normalization 逻辑：

```text
trading_mode=off     -> global.mode=off
trading_mode=signals -> global.mode=signal_only
trading_mode=trade   -> global.mode=paper_trade，不能直接映射 live_trade
trade_mode=paper_live 且没有 canonical mode -> global.mode=paper_trade
```

注意：**旧字段永远不能自动升级成 `live_trade`**。

### 推荐 API

在 `ControlPlane` 内新增：

```python
def mode(self) -> str: ...
def signals_enabled(self) -> bool: ...
def paper_execution_enabled(self) -> bool: ...
def live_execution_enabled(self) -> bool: ...
def can_generate_signals(self, market=None, symbol=None) -> tuple[bool, str | None]: ...
def can_build_order_intents(self, market=None, symbol=None) -> tuple[bool, str | None]: ...
def can_live_submit(self, market=None, symbol=None) -> tuple[bool, str | None]: ...
```

保留 `can_trade()` 作为兼容 wrapper，但它必须调用 canonical gate，不能继续依赖 `paper_live`。

### Dashboard API 改造

`/api/trading/mode` 仍可接受旧 UI 值：

```text
off
signals
trade
```

但写入时映射为 canonical：

```text
off     -> global.mode=off
signals -> global.mode=signal_only
trade   -> global.mode=paper_trade
```

新增可选字段 `live_trade` 时必须要求 body 显式：

```json
{"mode": "live_trade", "confirm_live": true}
```

即使 API 允许写 `live_trade`，最终能不能下单仍由 `LiveExecutionAdapter` 同时检查 app config。

### 测试要求

覆盖：

- 新状态默认 mode 是 `off` 或最保守状态。
- 旧 `trading_mode=trade` normalize 后是 `paper_trade`，不是 `live_trade`。
- 旧 `global.trade_mode=paper_live` normalize 后是 `paper_trade`。
- locked 状态下所有 gate 都返回 False。
- `signal_only` 允许信号，不允许订单意图和 live submit。
- `paper_trade` 允许订单意图，不允许 live submit。
- `live_trade` 只表示 control 层允许 live；不代表配置层允许 live。

---

## T02 — 删除 scheduler 对 live 配置的运行时覆盖

优先级：P0  
目标：Dashboard scheduler 不能把 guarded/paper 改成 live。

### 需要修改的文件

- `dashboard/scheduler.py`
- `system/engine/tests/test_dashboard_scheduler_safety.py`

### 必须删除的行为

删除或禁止以下逻辑：

```python
app.raw.setdefault("execution", {})
app.raw["execution"]["live_submit"] = True
app.raw["execution"]["submit_mode"] = "live"
```

### 新行为

scheduler 应根据 ControlPlane canonical mode 分支：

```text
off:
  skip cycle

signal_only:
  build_strategy_summary only

paper_trade:
  build_execution_summary
  persist order_intents / execution_preview
  do not call _submit_orders

live_trade:
  build_execution_summary
  call _submit_orders only if explicit app config live gate passes
```

### 验收标准

- 任何 scheduler cycle 都不能修改 `app.raw["execution"]` 中的 `submit_mode` 和 `live_submit`。
- `paper_trade` 下 summary 里可以有 `order_intents`，但不能出现 broker `submitted=True`。
- `live_trade` 下如果 app config 仍是 `mode=paper` 或 `submit_mode=guarded`，也不能 submit。
- 日志里应清楚写出：`preview_only_due_to_guarded_config` 或类似 reason。

---

## T03 — LiveExecutionAdapter 增加最后一道 hard live gate

优先级：P0  
目标：无论上游如何误传，submit 层自己必须阻止非显式 live。

### 需要修改的文件

- `system/engine/src/engine/live_execution.py`
- `system/engine/tests/test_live_execution_gates.py`

### 必须满足的 live submit 条件

`place_order()` 只有在以下条件全部满足时才能被调用：

```text
app_config.mode == "live"
execution.submit_mode == "live"
execution.live_submit is True
ControlPlane.global.mode == "live_trade"
ControlPlane.global.enabled is True
ControlPlane.locked is False
market enabled
symbol enabled and not suspended
risk.reduce_only is not True for BUY
risk.emergency_flatten is not True for BUY
```

任何一个条件不满足，都返回：

```python
SubmitResult(
    submitted=False,
    reason="具体 gate reason",
    mode=current_submit_mode,
)
```

### 推荐实现

在 `LiveExecutionAdapter` 中新增私有方法：

```python
def _can_live_submit(self, intent: dict[str, Any]) -> tuple[bool, str]:
    ...
```

`submit_intent()` 必须在调用 `client.place_order()` 前执行该方法。

### cancel gate

`cancel_order()` 也必须检查：

```text
app_config.mode == "live"
execution.live_cancel is True
ControlPlane.global.mode == "live_trade"
not locked
```

如果不是 live，返回 `guarded_cancel_mode` 或更具体 reason。

### 测试要求

使用 fake broker client 覆盖：

- 默认 paper/guarded 下不会调用 `place_order()`。
- `mode=live` 但 `submit_mode=guarded` 不会调用。
- `mode=live` + `submit_mode=live` + `live_submit=true` 但 control `paper_trade` 不会调用。
- 所有条件满足时才会调用一次 `place_order()`。
- `cancel_order()` 在 `live_cancel=false` 时不会调用 broker cancel。

---

## T04 — `suspended: true` 必须阻断 symbol 交易

优先级：P0  
目标：symbol 暂停状态必须真实生效。

### 需要修改的文件

- `system/engine/src/engine/control.py`
- `system/engine/tests/test_control_plane.py`

### 期望行为

对于：

```json
{
  "symbols": {
    "SMCI": {
      "suspended": true,
      "reason": "manual_suspend"
    }
  }
}
```

以下调用必须返回 False：

```python
control.can_build_order_intents("US", "SMCI")
control.can_live_submit("US", "SMCI")
```

如果是：

```json
{
  "symbols": {
    "SMCI": {
      "enabled": false
    }
  }
}
```

也必须返回 False。

如果是：

```json
{
  "symbols": {
    "SMCI": {
      "enabled": true,
      "suspended": false
    }
  }
}
```

则不因 symbol gate 阻断。

### 验收标准

- reason 要区分：`symbol_suspended:SMCI` 与 `symbol_disabled:SMCI`。
- 旧格式 `"SMCI": false` 仍兼容为 disabled。

---

## T05 — 修复 Dashboard execution-state reset 不可达代码

优先级：P0  
目标：将 `dashboard/main.py` 中疑似位于 `api_control()` 返回语句之后的 reset execution state 代码拆成独立 endpoint。

### 需要修改的文件

- `dashboard/main.py`
- 可选：`dashboard/static/index.html`
- 可选测试：`system/engine/tests/test_dashboard_api_structure.py`

### 期望 endpoint

新增：

```python
@app.post("/api/execution-state/reset")
async def api_execution_state_reset():
    ...
```

行为：

1. 读取 `runtime/state/execution_state.json`。
2. 备份为 `execution_state.bak.<timestamp>.json`。
3. 清空：
   - `submitted`
   - `previews`
   - `sync`
   - `history`
4. 同时锁定 control state：
   - `locked = true`
   - `reason = "execution_state_reset"`
   - `updated_by = "dashboard"`
5. 返回清理数量和备份文件名。

### 验收标准

- `/api/control/{action}` 只负责 lock/unlock。
- reset endpoint 独立可调用。
- reset 后 engine 必须处于 locked 状态。

---

## T06 — 安全 handoff / 打包脚本

优先级：P0  
目标：避免再次把 `.env`、broker properties、runtime state 打包给外部模型。

### 需要新增/修改的文件

- `scripts/make_safe_handoff.sh`
- `.gitignore`
- `docs/project-handoff-for-gpt-pro.md` 可追加一小节

### 脚本要求

生成一个安全 zip，排除：

```text
.env
.env.*
properties/*
runtime/*
logs/latest/execution_state.json
logs/latest/control_state.json
artifacts/broker/*
*.pem
*.key
*token*
*secret*
__pycache__/
*.pyc
```

保留：

```text
docs/
rules/
config/app.defaults.json
config/app_config.docker.json
config/*.example.json
agents/
cron/
system/engine/src/
system/engine/tests/
dashboard/
```

### 验收标准

- 执行脚本后 zip 内不包含真实 `.env`、properties、runtime state。
- 在脚本中打印 zip 路径和排除规则摘要。

---

# P1：风控硬限制补齐

P1 的目标是把“看起来有配置”变成“实际能阻断”。

---

## T10 — 实现 daily loss hard stop

优先级：P1  
目标：`daily_loss_limit_pct` 必须真正阻断新增 BUY，并触发全局锁定或 reduce-only。

### 需要修改的文件

- `system/engine/src/engine/risk.py`
- `system/engine/src/engine/control.py`
- `system/engine/src/engine/state.py` 或新增 `risk_state.py`
- `system/engine/tests/test_risk_daily_loss.py`

### 推荐状态结构

在 `control_state.json` 或单独 `risk_state.json` 中记录：

```json
{
  "risk": {
    "trading_day": "2026-04-20",
    "day_start_equity_usd": 100000.0,
    "last_equity_usd": 95000.0,
    "daily_loss_pct": 5.0,
    "daily_loss_locked": true,
    "reduce_only": true
  }
}
```

### 行为要求

1. 每个交易日首次看到有效 `netLiquidation` 时，初始化 `day_start_equity_usd`。
2. 当：

```text
(day_start_equity_usd - current_equity_usd) / day_start_equity_usd * 100 >= daily_loss_limit_pct
```

触发：

```text
daily_loss_locked = true
reduce_only = true
```

3. 触发后：
   - 新增 BUY 必须被阻断。
   - EXIT / flatten 类减仓动作允许继续。
   - 只有人工 unlock 或新交易日 reset 才能解除。

### 验收标准

- 测试覆盖低于阈值不阻断。
- 等于或超过阈值阻断 BUY。
- daily loss locked 后 EXIT 仍允许。
- reason 包含 `daily_loss_limit_exceeded`。

---

## T11 — max trades per day 与 symbol cooldown

优先级：P1  
目标：防止 agent / strategy bug 导致高频反复下单。

### 需要修改的文件

- `config/app.defaults.json`
- `system/engine/src/engine/risk.py`
- `system/engine/src/engine/state.py`
- `system/engine/tests/test_risk_trade_limits.py`

### 新增配置默认值

```json
"risk": {
  "max_trades_per_day": 10,
  "max_trades_per_symbol_per_day": 3,
  "symbol_cooldown_minutes_after_order": 30,
  "symbol_cooldown_minutes_after_loss": 120
}
```

默认值必须保守。

### 行为要求

- 每次成功 submit 或 paper intent 生成后记录 symbol/day 计数。
- 超过全局 daily trades 阈值，阻断新增 BUY。
- 超过 symbol daily trades 阈值，阻断该 symbol 的 BUY。
- symbol cooldown 内，阻断该 symbol 的 BUY。
- EXIT 不应被 cooldown 阻断。

### 验收标准

- 测试覆盖全局计数、symbol 计数、cooldown、EXIT 例外。

---

## T12 — reduce-only 与 emergency flatten 模式

优先级：P1  
目标：让系统具备“只减仓”和“紧急平仓”语义。

### 需要修改的文件

- `system/engine/src/engine/control.py`
- `system/engine/src/engine/risk.py`
- `dashboard/main.py`
- 可选：`dashboard/static/index.html`
- `system/engine/tests/test_reduce_only.py`

### 行为要求

`risk.reduce_only = true`：

- BUY 一律阻断。
- EXIT 允许。

`risk.emergency_flatten = true`：

- 不允许新增 BUY。
- 允许或主动生成 flatten intents，具体实现可拆二期。
- Dashboard 必须显示 emergency 状态。

### 验收标准

- reduce-only 不影响 EXIT。
- emergency flatten 不会 submit 新 BUY。

---

# P2：策略规则正确性修复

P2 的目标是让规则引擎说人话：穿越就是真穿越，冲突就有仲裁，策略不能自相矛盾。

---

## T20 — 修复 `cross_above / cross_below` 为真实穿越

优先级：P2  
目标：`cross_above` 和 `cross_below` 必须比较上一根 bar 和当前 bar。

### 需要修改的文件

- `system/engine/src/engine/rule_engine.py`
- `system/engine/tests/test_rule_engine.py`
- 可选：`system/engine/tests/test_rule_engine_cross.py`

### 正确定义

```text
cross_above(threshold): prev_value <= threshold and current_value > threshold
cross_below(threshold): prev_value >= threshold and current_value < threshold
```

如果 compare 对象是另一个 indicator，则：

```text
cross_above(indicator_b): prev_a <= prev_b and current_a > current_b
cross_below(indicator_b): prev_a >= prev_b and current_a < current_b
```

### 实现提示

当前 `_eval_indicator()` 只计算 current value。需要让 evaluator 能计算 previous value。可选方案：

1. 在 cross operator 时，对 `bars[:-1]` 再计算一次当前 indicator 和 compare indicator。
2. 或新增 `IndicatorCalculator.calculate_series_tail(...)`。

优先选择简单、可测试、侵入小的实现。

### 测试要求

- RSI 从 29 -> 31，`cross_above 30` 为 True。
- RSI 从 31 -> 32，`cross_above 30` 为 False。
- RSI 从 31 -> 29，`cross_below 30` 为 True。
- 数据不足时返回 False，diagnostics reason 为 `insufficient_data_for_cross`。

---

## T21 — 修复 `rsi_reversal` 自相矛盾规则

优先级：P2  
目标：让 RSI 反转策略不再要求同一根 bar 同时低于和穿越 30。

### 需要修改的文件

- `rules/rules.json`
- `system/engine/tests/test_rule_engine.py`

### 推荐修改

把 entry 条件从：

```text
RSI below 30 AND RSI cross_above 30
```

改成：

```text
RSI cross_above 30
```

或者：

```text
previous RSI below/equal 30 AND current RSI above 30
```

如果 T20 已经实现真实 cross，则只保留 `cross_above 30` 即可。

### 验收标准

- 人造 bars 能触发一次 RSI reversal BUY。
- 不穿越时不会触发。
- rule diagnostics 中能看到 cross 的 prev/current 值。

---

## T22 — 增加 SignalArbiter，统一每个 symbol 的最终动作

优先级：P2  
目标：多个规则同时对同一 symbol 输出 BUY/EXIT/HOLD 时，Engine 只能产出一个最终 intent。

### 需要新增/修改的文件

- `system/engine/src/engine/signal_arbiter.py`
- `system/engine/src/engine/rule_engine.py` 或 `runtime.py`
- `system/engine/tests/test_signal_arbiter.py`

### 行为要求

输入：多个 rule signals。输出：每个 symbol 一个 final signal。

推荐优先级：

1. EXIT 高于 BUY。
2. 非 HOLD 高于 HOLD。
3. `priority` 数字越小优先级越高。
4. 同优先级时，score/confidence 高者优先。
5. 仍冲突时，选择更保守动作：EXIT > HOLD > BUY。

### 输出 diagnostics

final signal 中应包含：

```json
{
  "arbiter": {
    "selected_rule_id": "...",
    "suppressed": ["rule_a", "rule_b"],
    "resolution": "exit_over_buy|priority|score|conservative"
  }
}
```

### 验收标准

- 同一 symbol 同时 BUY 和 EXIT，最终 EXIT。
- 多个 BUY，按 priority 选择。
- 没有有效信号时输出 HOLD 或空列表，行为要稳定。

---

## T23 — 增加 rule schema validation

优先级：P2  
目标：避免 malformed rules 进入运行路径。

### 需要新增/修改的文件

- `specs/rule-schema-v1.json` 或 `system/engine/src/engine/rule_schema.py`
- `system/engine/src/engine/rule_engine.py`
- `dashboard/main.py` 中 `/api/rules/validate`
- `system/engine/tests/test_rule_schema.py`

### 必须校验

- `rule_id` 唯一。
- `enabled` 是 bool。
- `priority` 是 int。
- `entry.action` 只能是 `BUY`。
- `exit.action` 只能是 `EXIT`。
- indicator 名称必须在已支持列表中。
- operator 必须在已支持列表中。
- cross operator 必须有足够 params/value/compare 对象。
- search_space path 必须能解析到真实字段。

### 验收标准

- `/api/rules/validate` 返回 errors/warnings。
- invalid rule 不应被 hot apply。

---

# P3：数据链路诊断

P3 的目标是解决“quote API 看似 ok，但策略 bars=0”的盲区。

---

## T30 — 增加 DataHealthReport

优先级：P3  
目标：每次 cycle 输出每个 symbol 的数据链路诊断。

### 需要修改的文件

- `system/engine/src/engine/runtime.py`
- `dashboard/main.py`
- `dashboard/static/logs.html` 或 `dashboard/static/strategy.html`
- `system/engine/tests/test_data_health.py`

### 输出结构建议

在 summary 中新增：

```json
"data_health": {
  "AAPL": {
    "market": "US",
    "provider": "yfinance|tiger",
    "quote_status": "ok|failed|delayed|unknown",
    "contract_status": "ok|failed|missing",
    "raw_bars_count": 123,
    "normalized_bars_count": 123,
    "required_bars": 25,
    "latest_bar_time": "...",
    "timeframe": "30min",
    "strategy_ready": true,
    "reason": null
  }
}
```

### 必须区分的 reason

```text
provider_error
contract_missing
bars_empty
bars_normalization_failed
insufficient_bars
market_closed
unsupported_timeframe
symbol_disabled
unknown
```

### 验收标准

- 当 bars=0 时，Dashboard 能显示具体 reason。
- `strategy_overview.json` 或 `/api/strategy-overview` 能暴露 data_health。
- 策略 HOLD reason 不再是唯一诊断来源。

---

## T31 — bars provider fallback 与显式失败

优先级：P3  
目标：不要静默把无数据当作正常 HOLD。

### 需要修改的文件

- `system/engine/src/engine/data_provider.py`
- `dashboard/quote_provider.py`
- `dashboard/yfinance_provider.py`
- `dashboard/tiger_quote_provider.py`
- `system/engine/tests/test_data_provider_health.py`

### 行为要求

- provider 返回 bars 时，同时返回 status metadata。
- 如果 primary provider bars=0，可以按配置 fallback 到 secondary provider。
- fallback 发生时必须记录到 `data_health`。
- 如果 fallback 也失败，summary 中明确显示失败，不要伪装成正常 HOLD。

### 新增配置建议

```json
"strategy": {
  "data_provider": {
    "primary": "yfinance",
    "fallback": "tiger",
    "fail_on_empty_bars": false
  }
}
```

默认仍保守：不因数据失败自动交易。

---

# P4：回测可信度修复

P4 的目标是让 strategist 的判断有可信输入。否则 agent 越聪明，越容易聪明地犯错。

---

## T40 — 修复 backtest win_rate 计算

优先级：P4  
目标：win rate 应基于已闭合交易，而不是全部 BUY+SELL trade 数。

### 需要修改的文件

- `system/engine/src/engine/backtest.py`
- `system/engine/tests/test_backtest_metrics.py`

### 当前问题

当前逻辑类似：

```python
win_rate = winning_trades / total_trades
```

但 `total_trades` 包含 BUY 和 SELL。正确口径应是：

```python
closed_trades = winning_trades + losing_trades
win_rate = winning_trades / closed_trades if closed_trades > 0 else 0.0
```

### 验收标准

- 一买一卖盈利，win_rate 应为 1.0，而不是 0.5。
- 一买一卖亏损，win_rate 应为 0.0。
- 只有 BUY 未平仓，closed_trades=0，win_rate=0.0 或 None，但要文档化。

---

## T41 — 多 symbol 回测按 timestamp 对齐

优先级：P4  
目标：避免不同 symbol bars 长度不一致导致 equity timestamp 错位。

### 需要修改的文件

- `system/engine/src/engine/backtest.py`
- `system/engine/tests/test_backtest_multisymbol_alignment.py`

### 当前风险

当前回测用最大 bars 长度循环，并用第一个 symbol 的 timestamp 记录 equity。若第一个 symbol bars 较短，可能错位或 index 出错。

### 推荐实现

把回测循环改为事件驱动：

```text
1. 收集所有 symbol 的所有 timestamp。
2. 排序后逐 timestamp 处理。
3. 每个 symbol 只在该 timestamp 有 bar 时更新。
4. equity_curve 使用当前 timestamp。
```

### 验收标准

- AAPL 有 100 根 bars，MSFT 有 60 根 bars 时不报错。
- equity_curve timestamp 单调递增。
- positions 的 current_price 使用各 symbol 最新可用 bar。

---

## T42 — fee confidence 进入 strategist / approval gate

优先级：P4  
目标：低手续费可信度时，不允许 agent 启用高换手策略。

### 需要修改的文件

- `system/engine/src/engine/strategist_artifacts.py`
- `system/engine/src/engine/applier.py`
- `docs/broker-fee-model.md`
- `docs/strategist-l3b-approval-contract.md`
- `system/engine/tests/test_fee_confidence_gate.py`

### 行为建议

读取：

```text
artifacts/broker/fee_calibration_summary.json
```

根据 `fee_model_confidence` 分级：

| confidence | 允许行为 |
|---|---|
| high | 允许正常参数/规则 apply |
| medium | 允许低换手策略调参，不允许新增高换手策略 |
| low/missing | 不允许启用新策略，只允许 paper shadow 或禁用/降风险 |

### 验收标准

- low/missing confidence 下，hot apply 启用新 BUY 规则会被拒绝。
- 禁用策略、降低仓位、降低交易频率的变更仍可通过。
- deployment record 记录 fee confidence snapshot。

---

# P5：L3b 审批与应用产品化

P5 必须在 P0 完成后做。不要在安全闸门没修好时提高 agent 自动发布能力。

---

## T50 — Proposal Review API

优先级：P5  
目标：Dashboard 能读取 approval queue，显示提案、证据、风险和状态。

### 需要修改的文件

- `dashboard/main.py`
- `system/engine/src/engine/strategist_artifacts.py`
- `system/engine/tests/test_proposal_review_api.py`

### Endpoint 建议

```text
GET  /api/strategy/proposals
GET  /api/strategy/proposals/{proposal_id}
POST /api/strategy/proposals/{proposal_id}/approve
POST /api/strategy/proposals/{proposal_id}/reject
```

### 输出字段

```json
{
  "proposal_id": "...",
  "status": "awaiting_approval",
  "target_files": [],
  "recommended_update_mode": "hot|cold",
  "requires_restart": false,
  "diff_summary": "...",
  "validation": {
    "tests": [],
    "backtest": {},
    "risk": {},
    "fee_confidence": "low|medium|high|missing"
  }
}
```

### 验收标准

- API 只改变 approval artifacts，不直接改 live trading config。
- approve/reject 写入 `approval_decisions.jsonl`。
- 非法状态迁移返回 400。

---

## T51 — Applier 真正执行 hot rules apply

优先级：P5  
目标：`applier.py` 对 hot update 不能只标记 applied，必须应用规则文件变更。

### 需要修改的文件

- `system/engine/src/engine/applier.py`
- `system/engine/src/engine/strategist_artifacts.py`
- `system/engine/tests/test_applier_hot_apply.py`

### 要求

对于 `recommended_update_mode=hot` 且 `target_files` 仅限 `rules/` 的 proposal：

1. 从 proposal 中读取 patch 或完整目标内容。
2. 校验 target path 只能在 `rules/` 内。
3. 应用前备份原文件。
4. 应用后运行 rule schema validation。
5. 写入 deployment record：
   - target file
   - before checksum
   - after checksum
   - validation result
   - operator
   - timestamp
6. 失败时恢复备份。

### 验收标准

- hot apply 成功后 `rules/rules.json` checksum 变化。
- invalid rules 不会 applied。
- rollback 后文件恢复。

---

## T52 — Cold proposal 只记录，不自动改代码

优先级：P5  
目标：代码变更提案必须保持人工/主 agent 审批，不自动落地。

### 需要修改的文件

- `system/engine/src/engine/applier.py`
- `docs/strategist-l3b-approval-contract.md`
- `system/engine/tests/test_applier_cold_gate.py`

### 行为要求

对于 target 包含：

```text
system/engine/src/engine/strategy.py
system/engine/src/engine/rule_engine.py
system/engine/src/engine/indicators.py
```

applier 只允许：

- 校验 proposal 已批准。
- 生成 apply plan。
- 标记 `requires_restart=true`。
- 记录 `manual_code_apply_required`。

不能自动 patch 代码，除非之后另开明确任务并引入更强 sandbox、diff review、test runner、rollback。

---

## T53 — Dashboard proposal review 页面

优先级：P5  
目标：人类能在 `/strategy` 或新页面看见 proposal 并审批。

### 需要修改的文件

- `dashboard/static/strategy.html` 或新增 `dashboard/static/proposals.html`
- `dashboard/main.py`

### 页面至少展示

- proposal id
- status
- target files
- update mode
- requires restart
- diff summary
- validation summary
- fee confidence
- risk impact
- approve/reject 按钮

### 安全要求

- approve 按钮不能直接 submit broker orders。
- apply 按钮只调用 applier，且 applier 自己做 gate。

---

# P6：Dashboard 与 runner 架构收口

---

## T60 — 拆分 dashboard/main.py 路由

优先级：P6  
目标：降低 Dashboard 里 UI、控制、回测、配置、日志全部混在一起的风险。

### 建议新增结构

```text
dashboard/api/control.py
dashboard/api/config.py
dashboard/api/strategy.py
dashboard/api/backtest.py
dashboard/api/logs.py
dashboard/api/proposals.py
dashboard/services/control_service.py
dashboard/services/backtest_service.py
dashboard/services/artifact_service.py
```

### 执行要求

- 不要一次性大拆。
- 每次只迁移一类 routes。
- 保持原 URL 不变。
- 每迁移一类 route，运行 compileall 和最小 API smoke test。

---

## T61 — 将 scheduler 从 Dashboard 权限中降级

优先级：P6  
目标：Dashboard 不应拥有绕过 execution gate 的能力。

### 可分两步

第一步：保持 scheduler 在 Dashboard 进程内，但只调用 ControlPlane canonical gate，不接触 live config mutation。

第二步：拆成独立服务：

```text
dashboard: UI + API
engine-runner: 周期执行策略/preview
agent-runner: newswire/watcher/strategist/closer
applier: 只应用已批准变更
```

### 修改文件

- `docker-compose.yml`
- `dashboard/scheduler.py`
- 新增 `system/engine/src/engine/runner.py` 或 `scripts/engine_runner.py`

### 验收标准

- Dashboard 关闭不影响 engine-runner 的明确运行状态，或者至少不会因为 UI 操作直接改变 live submit。
- runner 的 logs/artifacts 路径符合目录契约。

---

# P7：live 前置验收清单，不启用 live

P7 只做 checklist 和 gate，不实际打开 live。

---

## T70 — 添加 live readiness checklist

优先级：P7  
目标：任何 live_trade 前必须满足显式 checklist。

### 需要新增/修改的文件

- `docs/live-readiness-checklist.md`
- `system/engine/src/engine/control.py`
- `dashboard/main.py`

### checklist 至少包含

```text
P0 所有 safety tests 通过
P1 daily loss / reduce-only / cooldown tests 通过
至少 20 个交易日 paper shadow 稳定
fee_model_confidence != low/missing
最近 N 次 data_health 无 bars_empty / normalization_failed
broker 后台无未知挂单
execution_state 已 reconciliation
operator 手动确认
```

### gate 行为

设置 `global.mode=live_trade` 时，API 必须要求：

```json
{
  "mode": "live_trade",
  "confirm_live": true,
  "readiness_checklist_id": "..."
}
```

但即使设置成功，`LiveExecutionAdapter` 仍必须检查 app config：

```text
mode=live
submit_mode=live
live_submit=true
```

### 验收标准

- 没有 checklist id 不能进入 live_trade。
- checklist 不通过不能进入 live_trade。
- 默认配置仍然 paper/guarded。

---

# 3. 推荐任务执行批次

给 Codex 的推荐执行方式：

## Batch A：只做 P0 安全

```text
T00 -> T01 -> T02 -> T03 -> T04 -> T05 -> T06
```

完成后必须运行：

```bash
python -m unittest discover -s system/engine/tests -p 'test_*.py'
python -m compileall system/engine/src dashboard
```

并人工检查：

```bash
grep -R "live_submit.*= True\|submit_mode.*= \"live\"" dashboard system/engine/src
```

除测试用例和显式 config 外，不应出现 scheduler 强制覆盖 live 的逻辑。

## Batch B：风控硬限制

```text
T10 -> T11 -> T12
```

完成后测试：

```bash
python -m unittest system.engine.tests.test_risk_daily_loss
python -m unittest system.engine.tests.test_risk_trade_limits
python -m unittest system.engine.tests.test_reduce_only
```

如果模块路径不支持上述命令，就使用 discover。

## Batch C：策略正确性

```text
T20 -> T21 -> T22 -> T23
```

完成后测试：

```bash
python -m unittest discover -s system/engine/tests -p 'test_rule*.py'
```

## Batch D：数据与回测可信度

```text
T30 -> T31 -> T40 -> T41 -> T42
```

## Batch E：L3b 产品化

```text
T50 -> T51 -> T52 -> T53
```

## Batch F：架构拆分与 live readiness

```text
T60 -> T61 -> T70
```

---

# 4. Codex 每个任务完成后必须输出的报告格式

每完成一个任务，输出以下内容：

```markdown
## Task <ID> completion report

### Files changed
- ...

### Behavior changed
- ...

### Tests added/updated
- ...

### Commands run
```bash
...
```

### Results
- pass/fail

### Remaining risks
- ...

### Next recommended task
- ...
```

如果测试失败，不要继续下一个任务。先修当前任务。

---

# 5. 明确禁止事项

在本任务清单完成前，Codex 不得：

- 把 `execution.live_submit` 默认值改成 true。
- 把 `execution.submit_mode` 默认值改成 live。
- 把 `Dashboard trading_mode=trade` 映射为 live submit。
- 自动扩大 watchlist。
- 修改 broker credentials。
- 发送 Telegram 实盘告警以外的自动交易指令。
- 让 strategist 直接下单。
- 自动应用 cold code proposal。
- 删除 execution history 而不备份。
- 在没有 explicit checklist 的情况下加入 live_trade 快捷按钮。

---

# 6. 最小验收总表

当所有高优先级任务完成后，必须满足：

| 验收项 | 期望 |
|---|---|
| 默认配置 | paper + guarded + live_submit=false |
| scheduler | 不修改 live_submit / submit_mode |
| control state | canonical `global.mode` |
| old trading_mode | 只兼容映射，不越权 live |
| symbol suspended | 阻断 BUY / live submit |
| daily loss | 超阈值后 reduce-only / locked |
| cross_above | 使用 prev/current 真穿越 |
| rsi_reversal | 不再自相矛盾 |
| data_health | 能解释 bars=0 |
| backtest win_rate | 基于 closed trades |
| applier hot | 真 apply rules 且可 rollback |
| applier cold | 不自动改代码 |
| live readiness | checklist gate 存在，默认不启用 |

---

# 7. 建议交给 Codex 的第一条 prompt

把下面这段直接交给 Codex：

```text
请读取 docs/tasks/CODEX_PROJECT_HARDENING_TASKLIST.md，并只执行 Batch A 的 T00。不要修改任何密钥、runtime、logs/latest 或 artifacts/broker。先添加安全测试，允许测试暴露当前失败。完成后输出 Task T00 completion report，并停止等待下一步。
```

T00 完成后再给：

```text
继续执行 T01。只修改 ControlPlane canonical schema 和相关兼容测试，不要触碰策略逻辑、broker credentials 或 Dashboard UI 大改。完成后运行 unittest discover 和 compileall，并输出 completion report。
```

之后按任务编号逐个推进。别让 Codex 一口气全干，杂鱼项目会被它炖成一锅不可回滚的乱汤。
