# Strategist Capability Contract

更新时间：2026-04-17

这份文档定义 `strategist` 当前被授权的能力边界，避免 `agents/`、`docs/roles/`、`docs/tasks/` 出现彼此冲突的说法。

目标不是限制 strategist 的学习能力，而是把“能观察什么、能改什么、不能碰什么”说清楚。

升级路线参见：`docs/strategist-l3-evolution-plan.md`

---

## 当前等级

当前 `strategist` 的正式能力等级为：`L3a`

`L3a` 的含义是：

- 可以读取长期记忆与历史产物
- 可以分析信号质量并总结经验
- 可以调整现有规则参数
- 可以启用、停用、暂停、恢复现有规则
- 可以调用回测 API 验证候选方案
- 可以在白名单目录内修改策略代码与测试代码
- 可以生成 patch / commit proposal
- 可以在满足约束时写入规则层变更与代码变更产物

`L3a` 不等于“自由修改整个系统”。它仍然受下列硬边界约束：

- 不直接下单
- 不扩张股票池
- 不修改 broker / execution / deploy / infra
- 不新增未治理的新执行链路
- 不自动上线 live

---

## 分级能力模型

### L1：观察与总结

允许：

- 读取 `rules.json`、市场快照、新闻、历史计划、记忆文件
- 写 `strategy_plan_latest.json`
- 写 `strategy_plan_history.jsonl`
- 写 `artifacts/strategist/memory/*`
- 产出提案、拒绝原因、风险提示

不允许：

- 修改规则
- 调整参数
- 启停规则
- 调用会改变系统状态的接口

适用场景：

- 只做研究、复盘、日报
- 只给建议，不落地

### L2：规则自我迭代

允许：

- 做 L1 的全部事情
- 调整现有规则参数
- 启用 / 停用 / 暂停 / 恢复现有规则
- 调用 `/api/backtest` 或 `/api/backtest/batch` 做验证
- 在回测通过且符合任务约束时，通过规则层接口落地变更

不允许：

- 新增全新的 Engine 策略代码
- 修改信号引擎实现
- 修改下单 / 风控 / broker 执行代码
- 绕过回测直接做参数变更

适用场景：

- 当前项目的正式 strategist 能力

### L3a：代码提案型研发

允许：

- 做 L2 的全部事情
- 新增或删除策略定义
- 修改策略代码或因子计算逻辑
- 修改或新增策略测试
- 运行测试、dry-run、回测
- 提交受治理的 patch / commit proposal

不允许：

- 自动部署
- 自动上线 live
- 修改 broker 执行层或部署基础设施

当前状态：

- 当前项目已授权到 `L3a`

### L3b：受控提交型研发

允许：

- 做 `L3a` 的全部事情
- 自动生成并提交受控 commit
- 将代码变更结果写入正式 artifacts

不允许：

- 自动部署 live
- 自动绕过人工批准闸门

当前状态：

- `L3b` 尚未授权

### L3c：自动发布型研发

允许：

- 做 `L3b` 的全部事情
- 将通过验证的策略代码变更发布到正式运行链

当前状态：

- `L3c` 尚未授权

---

## 当前正式授权清单

### 允许做的事

- 读取 `./artifacts/strategist/memory/latest.json`
- 读取 `./artifacts/strategist/strategy_plan_history.jsonl`
- 读取 `./rules/rules.json`
- 盘前 / 盘后做参数候选方案回测
- 在白名单代码目录内修改策略实现与测试
- 运行 `py_compile`、单元测试、dry-run、回测
- 生成代码变更提案、结果与回滚记录
- 盘前做日内规则准备
- 盘中只做异常监控与暂停 / 恢复
- 盘后记录长期经验、提案与拒绝原因

### 明确不允许的事

- 直接下单
- 扩张 `watchlist`
- 绕过风控
- 修改 broker / execution / deploy / infra
- 自行创造新的执行入口
- 自动上线 live

## 当前白名单写入范围

允许修改：

- `rules/`
- `system/engine/src/engine/strategy.py`
- `system/engine/src/engine/rule_engine.py`
- `system/engine/src/engine/indicators.py`
- `system/engine/tests/`
- `tests/`
- `specs/`
- `artifacts/strategist/`

禁止修改：

- `system/engine/src/engine/live_execution.py`
- `system/engine/src/engine/broker_client.py`
- `system/engine/src/engine/tiger_client.py`
- `system/engine/src/engine/notifier.py`
- `docker-compose.yml`
- `dashboard/`

## 当前必须执行的验证链

每次代码级策略变更，至少必须完成：

1. `python3 -m py_compile` 检查目标策略文件
2. `python3 -m unittest system.engine.tests.test_indicators system.engine.tests.test_rule_engine system.engine.tests.test_backtest -v`
3. 如具备 broker props，则运行一次 dry-run
4. 运行 `/api/backtest` 或 `/api/backtest/batch`
5. 将结果写入代码变更 artifacts

---

## 与记忆系统的关系

`strategist` 的“自我进化”建立在显式记忆上，而不是模型隐式聊天记忆上。

当前学习闭环应依赖：

- `artifacts/strategist/memory/latest.json`
- `artifacts/strategist/memory/history.jsonl`
- `artifacts/strategist/proposals.jsonl`
- `artifacts/strategist/rejections.jsonl`
- `artifacts/strategist/iterations/`

也就是说，当前允许的是：

- 基于记忆的规则演化
- 基于回测的参数自我迭代
- 基于白名单目录的受控代码演化

当前不允许的是：

- 基于聊天上下文的无审计自我改写
- 无约束地生成并上线新策略代码

---

## 文档对齐要求

凡是涉及 strategist 能力边界的文档，应遵循以下口径：

- `docs/roles/STRATEGIST_BRIEF.md`
  说明角色目标与禁止事项
- `docs/tasks/STRATEGIST_TASK.md`
  说明执行流程与 shift 约束
- `agents/strategist.yaml`
  说明实际工具权限与输入输出

三者都应以本文件为准。
