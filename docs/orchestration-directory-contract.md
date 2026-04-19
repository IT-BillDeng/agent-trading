# Orchestration Directory Contract

更新时间：2026-04-16

## 目的

这份文档定义 `agent-trading` 中与调度、子 agent、任务正文、运行日志和运行态相关的目录职责。

目标很简单：

- 让主 agent / 管理 agent 知道该去哪里创建 cron
- 让 subagent 知道该去哪里读任务、写产物
- 让排障时能快速分清“调度”“角色”“任务”“日志”“状态”分别在哪里
- 避免把运行态、业务产物、日志混写到同一个目录

---

## 一、目录职责总览

### 1. `cron/`

职责：**调度声明**

放什么：

- 什么时候触发
- 触发哪个 agent
- 稳定任务名（`name`）
- 可选的 live 映射标识（`id`）
- 用什么模型
- 超时时间
- 是否启用
- 投递到哪里
- 任务正文的引用（`taskFile`，指向 `docs/tasks/cron/`）

不放什么：

- 任务正文
- 业务产物
- 运行日志

适用场景：

- 主 agent / 管理 agent 读取后，创建、更新、启停定时任务
- 人工查看当前系统有哪些定时任务
- 主 agent 按 [docs/main-agent-cron-playbook.md](./main-agent-cron-playbook.md) 将仓库 `cron/` 当作 desired state 并与 live 任务 reconcile

### 2. `agents/`

职责：**子 agent 配置与编排入口**

放什么：

- agent 角色定义
- 工具权限
- 输入文件
- 输出文件
- 启动/停止脚本
- subagent 部署参考

不放什么：

- 运行日志
- 业务历史产物
- 真正的系统状态

适用场景：

- 主 agent 决定 spawn 哪些 subagent
- subagent 读取自己的角色说明
- 运维脚本统一从这里启动或停止一组 agent

### 3. `docs/tasks/`

职责：**任务正文 / 执行模板**

放什么：

- 任务步骤
- 输入输出格式
- 约束条件
- 核心提示词
- 运行示例

对于 cron 类任务，正文建议单独放在 `docs/tasks/cron/`，并由 `cron/*.json` 通过 `taskFile` 引用。

不放什么：

- 运行结果
- 运行日志
- 最终状态文件

适用场景：

- cron 触发时，agent 读取这里的任务文本执行
- subagent 需要稳定、可版本控制的任务说明

### 4. `logs/`

职责：**运行状态与诊断**

放什么：

- 审计日志
- 组件运行日志
- 最新快照总览
- 可用于巡检和排障的结构化记录

不放什么：

- 核心业务历史产物
- 控制状态
- 待发送 outbox

适用场景：

- 人工巡检系统是否正常
- Dashboard 展示运行状态
- 排查某轮周期为什么没跑、为什么被阻断

### 5. `artifacts/`

职责：**agent 业务产物与学习成果**

放什么：

- 策略计划
- 新闻批次
- 健康检查结果
- 执行检查单
- 候选扫描结果
- 收盘总结
- 经验记录、提案、拒绝记录、回测结果

不放什么：

- 纯运行日志
- 控制状态
- 待发送 outbox

适用场景：

- Dashboard / Operator 读取 agent 产出的业务结果
- Strategist / Newswire / Watcher / Executor / Scout / Closer 继续在下一轮读取历史产物
- 人工回看某个 agent 的长期演进记录

### 6. `runtime/state/`

职责：**控制态 / 内部状态**

放什么：

- 锁定状态
- 去重状态
- 冷却状态
- 最近一次执行状态

不放什么：

- 面向人看的日志
- 面向业务消费的产物历史

适用场景：

- 引擎运行时读写内部状态
- 需要保留但不需要直接展示给用户的状态

### 7. `runtime/outbox/`

职责：**待发送消息 / 待消费产物**

放什么：

- 待发 Telegram / 其它通道的消息
- 待消费的收盘/执行输出

不放什么：

- 审计日志
- 状态快照
- 历史业务结果

适用场景：

- closer / executor 这类需要把结果交给下一步流程的 agent

---

## 二、推荐读写关系

### 主 agent / 管理 agent

优先读：

- `cron/`
- `agents/`
- `docs/tasks/`
- `docs/roles/`
- `runtime/outbox/`
- `artifacts/`

用来决定：

- 哪些任务要创建
- 哪些 subagent 要启用
- 哪些 task 文本要下发
- 哪些通知只记录、哪些需要汇总、哪些值得外发

边界：

- 不应把运行期审查结果写回 `docs/`、`cron/`、`agents/`
- 不应在项目根目录创建自由格式 markdown / json 作为运行记录
- 如需持久化运行决策，应优先使用 `artifacts/`、`runtime/state/`、`runtime/outbox/` 或 live 环境自身审计系统

### subagent

优先读：

- 自己的 `agents/*.yaml`
- 对应的 `docs/tasks/*`
- 必要时读取 `runtime/state/`

用来决定：

- 自己该做什么
- 允许写什么
- 结果该落到哪里
- 哪些结果需要汇报给主 agent

例如：

- `strategist`：研究、验证、提案
- `applier`：应用已批准的变更
- `executor`：交易执行检查与执行链审查

### Dashboard / Operator

优先读：

- `logs/`
- `runtime/state/`
- `runtime/outbox/`
- 业务产物的 latest/history 快照

用来决定：

- 系统是否正常
- 当前计划是什么
- 风控是否阻断
- 最近一次发生了什么

---

## 三、当前仓库里的现实情况

这份规范描述的是**目标语义**。当前仓库里仍然存在一些历史路径：

- `runtime/engine/logs/*`
- `artifacts/newswire/*`
- `artifacts/strategist/*`

这些路径里有些已经开始迁移到根目录 `logs/` / `artifacts/` / `runtime/state/`，有些仍然是兼容态，不应再作为新增产物入口。

当前建议是：

1. `logs/` 只承接“运行状态与诊断”
2. `artifacts/` 承接真正的 agent 业务产物
3. `runtime/state/` 保留控制态
4. `runtime/outbox/` 保留待发送消息

---

## 四、通知路由原则

- subagent 默认只写产物、日志与通知提案，不直接外发 Telegram
- 主 agent 负责聚合、去重、升级/降级通知，并决定是否发送 Telegram
- 如需系统级兜底告警，应作为明确例外单独设计，而不是每个 subagent 各自直发

---

## 四、关于 `agents/` 是否可信

`agents/` 目录仍然有用，但不能视为系统唯一真相来源。

如果 `agents/*.yaml` 与实际运行链路冲突，优先级建议为：

1. 真实运行链路
2. `cron/`
3. `docs/tasks/`
4. `agents/*.yaml`

也就是说，`agents/` 更像“可执行配置草案 + 编排参考”，而不是最终事实记录。

---

## 五、建议的落地顺序

1. 先把 `cron/` 收敛成“纯调度声明”
2. 再把 `docs/tasks/` 收敛成“纯任务正文”
3. 接着把 `logs/` 固定成“运行状态与诊断”
4. 然后把 `runtime/state/` 和 `runtime/outbox/` 的职责写清
5. 最后再回头校准 `agents/*.yaml`

---

## 六、一个简单记忆法

- `cron/` = 什么时候跑
- `agents/` = 谁来跑
- `docs/tasks/` = 跑什么
- `logs/` = 跑完看什么
- `artifacts/` = 跑完留下些什么
- `runtime/state/` = 当前记住什么
- `runtime/outbox/` = 接下来要发什么
