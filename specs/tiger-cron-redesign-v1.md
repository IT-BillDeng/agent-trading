# Tiger Cron Redesign v1

> 目标：清理 Tiger 历史遗留 cron，按新的岗位化流水线重建调度体系。
> 范围：watcher / newswire / strategist / decision / executor / closer / portfolio-report。
> 原则：先定义蓝图，再平滑替换；不在旧 cron 上继续打补丁。

---

## 1. 重构目标

当前 Tiger cron 存在以下问题：

- 历史叠加，部分任务职责重叠
- 有些 cron 代表的是旧架构思路，不再符合当前岗位设计
- watcher / newswire 尚未接入结构化输出层
- execution 仍使用固定班次，和新的“decision -> executor”链路不完全匹配
- newswire 班次存在历史频率残留，不完全符合新讨论结果

本次 redesign 的目标是：

1. 用岗位职责重新定义 cron
2. 把“固定 cron”与“事件触发”区分开
3. 降低历史冗余任务数量
4. 为 watcher / newswire / strategist / decision / executor 的新链路预留调度入口

---

## 2. 新设计总览

### 最终目标链路

```text
watcher + newswire
        ↓
strategist
        ↓
decision
        ↓
executor
        ↓
closer
        ↓
Operator 汇总给用户
```

### 调度原则

- **watcher**：cron 固定频率，仅盘中运行
- **newswire**：cron 固定频率，盘中 / 盘后分开
- **strategist**：低频 cron + 高优先级事件唤醒
- **decision**：由 strategist signal 触发，不单独常驻 cron
- **executor**：仅接收 decision approved 之后的任务，不做固定 cron
- **closer**：收盘后固定 cron
- **portfolio-report**：保留为用户侧播报层，但后续可重构

---

## 3. 岗位级设计

## 3.1 watcher

### 定位
高频只读盯盘，结构化产出市场观察对象。

### 触发方式
- cron 固定频率
- 仅在盘中运行

### 推荐频率
- 初版：`5m`
- 后续是否提频，取决于 API 权限与稳定性

### 输入
- `shared/tiger_shared_watchlist.json`
- `runtime/tiger_engine/.last_execution_cycle.json`
- `runtime/tiger_engine/logs/dispatch_queue.jsonl`
- `runtime/tiger_engine/logs/execution.jsonl`
- `runtime/tiger_engine/state/control_state.json`

### 输出
- `runtime/tiger_engine/watcher/latest.json`
- `runtime/tiger_engine/watcher/history.jsonl`

### 备注
- watcher 不直接产出执行任务
- watcher 可在高优先级变化时额外产出事件对象，供 strategist 被唤醒

---

## 3.2 newswire

### 定位
新闻猎手，定时扫描并结构化产出情报对象。

### 触发方式
- cron 固定频率
- 盘前 / 盘中 / 盘后分开

### 推荐频率
- 盘中：每 `30m`
- 盘后：每 `2h`
- 盘前：保留 HK / US 各一班

### 输入
- `shared/tiger_shared_watchlist.json`
- `shared/tiger_newswire_sources_v1.json`
- role brief / task template

### 输出
- `runtime/tiger_engine/newswire/latest.json`
- `runtime/tiger_engine/newswire/history.jsonl`

### 备注
- newswire 不直接产出交易信号
- newswire 可在重大事件时附带高优先级事件对象
- 未来可接付费情报源，统一映射到 newswire schema

---

## 3.3 strategist

### 定位
读取 watcher + newswire 的结构化结果，结合策略规则与历史，产出 signal object。

### 触发方式
- 低频 cron
- 高优先级事件唤醒

### 推荐频率
- 基础频率：盘中每 `15m`
- 额外：当 watcher/newswire 产生高优先级变化时唤醒一次

### 输入
- `runtime/tiger_engine/watcher/latest.json`
- `runtime/tiger_engine/newswire/latest.json`
- 历史/上下文数据（后续扩展）

### 输出
- `runtime/tiger_engine/strategist/latest_signal.json`
- `runtime/tiger_engine/strategist/signals.jsonl`
- 可选：`strategist_signal_ready` 事件对象

### 备注
- strategist 使用较强模型
- strategist 只产出候选 signal，不直接调用 executor

---

## 3.4 decision

### 定位
对 strategist signal 做二次裁决，决定是否进入执行。

### 触发方式
- 不做固定 cron
- 由 `strategist_signal_ready` 事件触发
- 或由 Operator 读取 signal 后主动执行 decision

### 输入
- `runtime/tiger_engine/strategist/latest_signal.json`

### 输出
- `runtime/tiger_engine/decision/latest_decision.json`
- `runtime/tiger_engine/decision/decisions.jsonl`

### 备注
- `decision=approved` 才允许进入 executor
- 这是系统风控闸门，不建议再拆成独立低频 cron

---

## 3.5 executor

### 定位
纯执行者，接收明确任务后执行交易或预检查。

### 触发方式
- 不做固定 cron
- 由 `decision=approved` 之后的任务派发触发

### 输入
- decision object
- executor task object

### 输出
- `runtime/tiger_engine/executor/latest_task.json`
- `runtime/tiger_engine/executor/tasks.jsonl`
- `runtime/tiger_engine/executor/latest_result.json`
- `runtime/tiger_engine/executor/results.jsonl`

### 备注
- executor 不负责策略判断
- executor 不应自发运行
- 固定班次 execution cron 只是旧架构遗留，长期应退役

---

## 3.6 closer

### 定位
收盘总结者，汇总市场、新闻、执行与风险摘要。

### 触发方式
- cron 固定班次

### 推荐频率
- HK 收盘后 1 次
- US 收盘后 1 次

### 输入
- watcher / newswire / execution / state 全链路结果

### 输出
- `runtime/tiger_engine/closer/hk_latest.json`
- `runtime/tiger_engine/closer/us_latest.json`
- `runtime/tiger_engine/closer/history.jsonl`

### 备注
- closer 负责沉淀结构化收盘总结
- 最终给用户的文本可由 Operator 再加工

---

## 3.7 portfolio-report

### 定位
用户侧持仓与盈亏播报层。

### 触发方式
- cron 固定班次（当前保留）

### 当前建议
- 暂时保留：
  - 盘中每 15m
  - 盘后每 1h
- 后续再决定是否并入更统一的汇报系统

### 输入
- `runtime/tiger_engine/logs/cycles.jsonl`
- `runtime/tiger_engine/logs/execution.jsonl`
- `runtime/tiger_engine/state/execution_state.json`

### 输出
- 直接向用户播报

---

## 4. 新 cron 蓝图

## 4.1 保留为 cron 的岗位

### watcher
- `tiger-watcher-market-watch`
- 建议：仅盘中运行，频率 `5m`

### newswire
- `tiger-newswire-hk-preopen`
- `tiger-newswire-us-preopen`
- `tiger-newswire-intraday-q30`
- `tiger-newswire-afterhours-q2h`

### strategist
- `tiger-strategist-intraday-q15`
- 另配事件唤醒

### closer
- `tiger-closer-hk-close-summary`
- `tiger-closer-us-close-summary`

### portfolio-report
- `tiger-portfolio-report-intraday-q15`
- `tiger-portfolio-report-afterhours-hourly`

---

## 4.2 不保留为固定 cron 的岗位

### decision
- 改为事件触发
- 不设独立固定 cron

### executor
- 改为任务派发触发
- 不设独立固定 cron

---

## 5. 现有 cron → 新 cron 映射建议

## 5.1 建议保留并改造

### `tiger-watcher-market-watch`
- 保留
- 但改成：仅盘中运行 + 写结构化 watcher 输出

### `tiger-newswire-hk-preopen`
- 保留
- 输出接入 newswire schema

### `tiger-newswire-us-preopen`
- 保留
- 输出接入 newswire schema

### `tiger-closer-hk-close-summary`
- 保留
- 后续输出接入 closer schema

### `tiger-closer-us-close-summary`
- 保留
- 后续输出接入 closer schema

### `tiger-portfolio-report-intraday-q15`
- 暂时保留

### `tiger-portfolio-report-afterhours-hourly`
- 暂时保留

---

## 5.2 建议删除或重建

### `tiger-paper-execution`
- **建议退役**
- 原因：旧架构下的固定执行班次，不符合新的 decision -> executor 模型
- 短期可保留为过渡任务，长期应删除

### `tiger-newswire-us-intraday`
- **建议删除**
- 原因：与 `...-q15` 历史重叠；新架构应统一成更明确的盘中频率方案

### `tiger-newswire-us-intraday-q15`
- **建议重建为 `q30`**
- 原因：你最新确认的目标是盘中每 30m，而不是 15m

---

## 6. 建议的重建顺序

### Phase 1：蓝图确认
- 确认这份 cron redesign v1

### Phase 2：先落结构化输出
- watcher 写 `latest.json/history.jsonl`
- newswire 写 `latest.json/history.jsonl`

### Phase 3：新 cron 表重建
- 创建新 strategist cron
- 重建 newswire 盘中 / 盘后 cron
- 视情况保留过渡 execution cron

### Phase 4：旧 cron 退役
- disable 旧 job
- 观察 1~2 个周期
- 再 remove

---

## 7. 风险控制建议

### 不建议直接裸删所有旧 cron
原因：
- 可能导致主链短暂失能
- 难以快速判断是调度问题还是岗位实现问题

### 建议策略
- 先创建新 job
- 再 disable 旧 job
- 确认稳定后 remove

---

## 8. 当前最建议立即执行的动作

按优先级排序：

1. watcher / newswire 结构化输出先落地
2. 重建 newswire 频率（盘中 q30，盘后 q2h）
3. 新增 strategist 基础 cron（盘中 q15）
4. 将 decision / executor 明确为事件触发，不建固定 cron
5. 评估并退役 `tiger-paper-execution`

---

## 9. 一句话总结

**Tiger 新 cron 体系应该从“历史堆叠的固定班次”升级成“watcher/newswire 定时采集，strategist 混合触发，decision/executor 事件驱动，closer/portfolio-report 定时汇总”的混合调度系统。**
