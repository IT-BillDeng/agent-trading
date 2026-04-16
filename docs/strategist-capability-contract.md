# Strategist Capability Contract

更新时间：2026-04-17

这份文档定义 `strategist` 当前被授权的能力边界，避免 `agents/`、`docs/roles/`、`docs/tasks/` 出现彼此冲突的说法。

目标不是限制 strategist 的学习能力，而是把“能观察什么、能改什么、不能碰什么”说清楚。

如需规划从 `L2` 升级到 `L3`，参见：`docs/strategist-l3-evolution-plan.md`

---

## 当前等级

当前 `strategist` 的正式能力等级为：`L2`

`L2` 的含义是：

- 可以读取长期记忆与历史产物
- 可以分析信号质量并总结经验
- 可以调整现有规则参数
- 可以启用、停用、暂停、恢复现有规则
- 可以调用回测 API 验证候选方案
- 可以在满足约束时写入规则层变更

`L2` 不等于“自由修改整个系统”。它仍然受下列硬边界约束：

- 不直接下单
- 不扩张股票池
- 不修改 Engine 策略代码
- 不新增未治理的新执行链路

---

## 三档能力模型

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

### L3：策略研发与代码演化

允许：

- 做 L2 的全部事情
- 新增或删除策略定义
- 修改策略代码或因子计算逻辑
- 提交受治理的代码变更

额外要求：

- 必须有更严格的评审、测试、回滚和发布流程
- 不能与常规盘中 cron 混用

当前状态：

- `L3` 尚未授权

---

## 当前正式授权清单

### 允许做的事

- 读取 `./artifacts/strategist/memory/latest.json`
- 读取 `./artifacts/strategist/strategy_plan_history.jsonl`
- 读取 `./rules/rules.json`
- 盘前 / 盘后做参数候选方案回测
- 盘前做日内规则准备
- 盘中只做异常监控与暂停 / 恢复
- 盘后记录长期经验、提案与拒绝原因

### 明确不允许的事

- 直接下单
- 扩张 `watchlist`
- 绕过风控
- 修改 Engine Python 策略实现
- 自行创造新的执行入口

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
