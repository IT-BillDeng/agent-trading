# Strategist L3 Evolution Plan

更新时间：2026-04-17

这份文档说明 `strategist` 如何从早期的 `L2` 规则自我迭代能力，演进到 `L3` 策略研发与代码演化能力。

相关文档：

- `docs/strategist-capability-contract.md`
- `docs/strategist-memory-contract.md`
- `docs/tasks/STRATEGIST_TASK.md`

---

## 一、当前状态

当前 `strategist` 已被正式定义为 `L3a`。

它目前可以：

- 读取长期记忆与历史产物
- 调整现有规则参数
- 启用 / 停用 / 暂停 / 恢复现有规则
- 调用回测 API 验证方案
- 将通过验证的规则层变更落地
- 在白名单目录内修改策略代码与测试代码
- 生成代码变更 proposal、结果与回滚记录
- 运行测试、dry-run、回测

它目前不可以：

- 直接下单
- 扩张股票池
- 自动上线 live
- 修改 broker / execution / deploy / infra

因此，当前 strategist 更像：

- `代码提案型策略研究员`

而不是：

- `自动发布型策略工程师`

---

## 二、L3 的目标定义

`L3` 指 strategist 被授权执行“策略研发与代码演化”。

它应该具备以下新增能力：

1. 新增或删除策略定义
2. 修改策略代码或因子计算逻辑
3. 为新策略补测试与说明
4. 运行代码级验证链
5. 产出受治理的代码变更提案

但 `L3` 也不意味着无限权限。

`L3` 仍然不应直接获得：

- 直接下单权限
- 绕过风控的能力
- 修改 broker 执行层的自由
- 修改 deploy / infra 的自由

---

## 三、推荐的三级演进路线

### L3a：代码提案型研发

这是最推荐的第一阶段。

允许：

- 修改策略代码
- 修改或新增策略测试
- 运行测试、dry-run、回测
- 生成 patch / commit proposal

不允许：

- 自动部署
- 自动上线 live
- 自动修改 broker 执行链

目标：

- 让 strategist 先具备“会写代码并自证”的能力
- 保留人工批准上线

### L3b：受控提交型研发

在 `L3a` 通过一段时间稳定运行后，再考虑进入 `L3b`。

允许：

- 做 `L3a` 的全部事情
- 自动生成并提交受控 commit
- 将变更结果写入正式 artifacts

仍不允许：

- 自动部署 live
- 自动开启高风险执行

目标：

- 让 strategist 成为真正的“自动研究工程师”
- 但仍由人工或上层 agent 决定是否上线

### L3c：自动发布型研发

不建议作为近期目标。

它意味着 strategist 可以：

- 直接将策略代码变更发布到生产运行链

只有在以下条件全部满足后才可考虑：

- 策略测试充分
- 回滚链已自动化
- 观察期机制成熟
- 风险闸门独立可靠

当前项目不建议直接跳到 `L3c`。

---

## 四、从 L3a 升到更高阶 L3 的核心缺口

### 1. 缺少正式授权

当前已经允许 strategist 在白名单目录内修改策略代码。

接下来真正缺的不是基础写权限，而是更高阶治理：

- 更新 `docs/strategist-capability-contract.md`
- 更新 `docs/roles/STRATEGIST_BRIEF.md`
- 更新 `docs/tasks/STRATEGIST_TASK.md`
- 更新 `agents/strategist.yaml`

### 2. 缺少文件级边界

如果 strategist 升到 `L3`，必须限制它“能改哪些代码”。

建议允许修改：

- `rules/`
- `system/engine/src/engine/` 中的策略相关模块
- `tests/`
- `specs/`
- `artifacts/strategist/`

建议禁止修改：

- broker 适配器
- live execution 提交链
- 底层风险总闸
- Docker / deploy / infra
- Dashboard 核心展示逻辑

### 3. 缺少代码级验证链

`L3a` 已经具备回测、测试、dry-run 的基本要求。

继续向 `L3b / L3c` 提升时，仍需完善代码级验证的稳定性：

- 语法检查
- 单元测试
- 策略 smoke test
- dry-run
- 与当前基线策略的回测对比

### 4. 缺少代码变更审计

目前 strategist 的 artifacts 已经能记录：

- memory
- proposals
- rejections
- iterations

但 `L3` 还需要记录：

- 哪些代码文件被改了
- 为什么改
- 用什么假设驱动这次改动
- 测试是否通过
- 回测是否优于基线
- 如何回滚

### 5. 缺少上线闸门

即使 strategist 能写代码，也不应默认能自动上线。

所以还需要一个明确的发布决策点：

- `proposed`
- `validated`
- `approved_for_merge`
- `deployed`

---

## 五、L3 所需的新能力

### 必要能力

- 可读策略代码与测试代码
- 可写策略代码与测试代码
- 可运行测试命令
- 可运行 dry-run
- 可运行回测 API
- 可生成结构化代码变更报告

### 建议能力

- 可生成 patch
- 可生成非交互 commit
- 可输出 rollback notes
- 可比较新旧策略表现差异

### 不建议直接授予

- 直接 live deploy
- 直接下单
- 修改 broker 认证 / 凭据
- 修改 Telegram / 外部通知密钥

---

## 六、L3 所需的新权限

### 推荐新增写权限范围

- `system/engine/src/engine/strategy*.py`
- `system/engine/src/engine/rule_engine*.py`
- `system/engine/src/engine/signals*.py`
- `tests/`
- `specs/`
- `artifacts/strategist/`

说明：

- 这里的路径应该再按真实模块细化一次
- 核心原则是“允许改策略，不允许改基础设施”

### 推荐 exec 权限用途

- `python -m unittest ...`
- `python -m py_compile ...`
- 本地 dry-run 命令
- `/api/backtest`
- `/api/backtest/batch`

### 建议保留的 read 权限

- 现有 memory
- 历史 plan / proposals / rejections
- 回测结果
- 最新 market context
- 最近 execution cycle

---

## 七、L3 所需的新 artifacts

建议新增：

- `artifacts/strategist/code_change_proposals.jsonl`
- `artifacts/strategist/code_change_results.jsonl`
- `artifacts/strategist/rollback_notes.jsonl`
- `artifacts/strategist/experiments/`

### `code_change_proposals.jsonl`

记录：

- `proposal_id`
- `generated_at`
- `hypothesis`
- `target_files`
- `change_summary`
- `expected_benefit`
- `risk_notes`

### `code_change_results.jsonl`

记录：

- `proposal_id`
- `tests_passed`
- `dry_run_passed`
- `backtest_delta`
- `approved`
- `approver`
- `commit_sha`

### `rollback_notes.jsonl`

记录：

- `proposal_id`
- `rollback_trigger`
- `rollback_steps`
- `follow_up`

---

## 八、L3 所需的新验证链

每次代码级策略变更至少应经过：

1. 语法检查
2. 相关单元测试
3. 最小 smoke test
4. dry-run
5. 回测对比
6. 结构化结果写入 artifacts

推荐输出统一状态：

- `draft`
- `tested`
- `dry_run_passed`
- `backtest_passed`
- `awaiting_approval`
- `rejected`
- `approved`

---

## 九、推荐的治理原则

### 1. 策略代码与执行代码分层治理

允许 strategist 改：

- 策略逻辑
- 信号逻辑
- 规则判定逻辑

不允许 strategist 改：

- broker 提交逻辑
- 风控总闸门
- 账户同步逻辑

### 2. 盘中不做代码演化

即使升到 `L3`，盘中 cron 仍应保持：

- 监控
- 暂停 / 恢复

不应在盘中直接改代码。

### 3. 代码变更必须与假设绑定

每次变更都应能回答：

- 为了解决什么问题？
- 证据是什么？
- 如果失败如何回滚？

### 4. 自动研究不等于自动上线

`L3` 最好先停在：

- 自动研究
- 自动验证
- 自动产出变更

而不是直接：

- 自动发布 live

---

## 十、建议的近期实施顺序

### 第一步：落地 L3a 设计（已完成）

- 增加 `L3a / L3b / L3c` 说明
- 明确 strategist 可修改的代码目录
- 增加代码变更 artifacts
- 增加测试 / dry-run / backtest 的统一结果格式

### 第二步：实现更稳定的受控代码变更

- 让 strategist 能在受限目录内生成 patch
- 让 strategist 能补测试并自测
- 让 strategist 能输出 commit proposal

### 第三步：引入人工批准闸门

- 只有通过批准的变更才能进入主分支或正式运行链

---

## 十一、结论

如果你希望 strategist 真正“会成长”，那么 `L3` 是合理方向。

但 `L3` 的本质不是：

- 再多给一点写权限

而是：

- 正式允许策略代码演化
- 限定代码可写边界
- 补上测试链、dry-run、回测链
- 增加审计与回滚 artifacts
- 保留人工批准闸门

推荐目标顺序：

- `L3a` 已落地
- 下一步考虑 `L3b`
- 暂不考虑 `L3c`
