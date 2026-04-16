# Strategist Code Change Task

更新时间：2026-04-17

这份任务说明定义 strategist 在 `L3a` 阶段如何进行代码级策略提案。

相关文档：

- `docs/strategist-capability-contract.md`
- `docs/strategist-l3-evolution-plan.md`
- `docs/tasks/STRATEGIST_TASK.md`

---

## 适用场景

仅在以下条件满足时进入本流程：

- 已经形成明确的策略级假设
- 单纯调参数无法验证该假设
- 变更范围落在白名单目录内
- 当前不是盘中监控时段

---

## 白名单目录

- `./system/engine/src/engine/strategy.py`
- `./system/engine/src/engine/rule_engine.py`
- `./system/engine/src/engine/indicators.py`
- `./system/engine/tests/`
- `./tests/`
- `./specs/`
- `./artifacts/strategist/`

禁止触碰：

- broker 适配器
- live execution 提交链
- notifier
- deploy / infra
- dashboard 主逻辑

---

## 执行步骤

1. 读取：
   - `./artifacts/strategist/memory/latest.json`
   - `./artifacts/strategist/strategy_plan_history.jsonl`
   - `./rules/rules.json`
   - 最近一轮 `iterations/`
2. 明确本次代码变更假设：
   - 要解决什么问题
   - 证据是什么
   - 为什么参数调整不够
3. 在白名单目录内做最小代码改动
4. 如需要，补充最小测试
5. 执行验证链
6. 将 proposal / result / rollback 写入 `artifacts/strategist/`
7. 生成 patch 或 commit proposal
8. 等待人工或上层 agent 批准

---

## 必须执行的验证链

### 1. 语法检查

```bash
python3 -m py_compile \
  system/engine/src/engine/strategy.py \
  system/engine/src/engine/rule_engine.py \
  system/engine/src/engine/indicators.py
```

### 2. 策略相关单元测试

```bash
python3 -m unittest \
  system.engine.tests.test_indicators \
  system.engine.tests.test_rule_engine \
  system.engine.tests.test_backtest -v
```

### 3. dry-run

如具备 broker props，运行：

```bash
python3 system/engine/run_dry_run_cycle.py \
  config/app_config.docker.json \
  /path/to/broker_props.properties
```

### 4. 回测验证

至少运行一次：

- `/api/backtest`
- 或 `/api/backtest/batch`

---

## 必须写入的 artifacts

### `artifacts/strategist/code_change_proposals.jsonl`

至少包含：

- `proposal_id`
- `generated_at`
- `hypothesis`
- `target_files`
- `change_summary`
- `expected_benefit`
- `risk_notes`

### `artifacts/strategist/code_change_results.jsonl`

至少包含：

- `proposal_id`
- `tests_passed`
- `dry_run_passed`
- `backtest_delta`
- `approved`
- `commit_sha`

### `artifacts/strategist/rollback_notes.jsonl`

至少包含：

- `proposal_id`
- `rollback_trigger`
- `rollback_steps`
- `follow_up`

---

## 当前边界

允许：

- 修改策略代码
- 修改策略测试
- 生成 patch / commit proposal

不允许：

- 自动 merge
- 自动部署
- 自动 live submit
