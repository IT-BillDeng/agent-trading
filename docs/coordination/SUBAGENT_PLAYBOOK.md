# Subagent Playbook

给 `Operator` 的 subagent 实战手册。

## 可调用对象

- `watcher`：运行健康 / 权限 / 日志 / 队列 / 周期输出监控
- `newswire`：新闻、事件、催化与时间线整理
- `strategist`：策略、风险收益、仓位与计划建议
- `executor`：执行步骤、参数检查、preview / dispatch 校验
- `scout`：扫描候选标的、异常波动与待验证机会
- `closer`：退出、止盈止损、减仓平仓与收尾条件建议

## 什么时候调用谁

### 1. 先看盘面和候选有没有变化
调用：`watcher`
适合：
- 盯 `agent-trading/data/watchlist.json` 中 `enabled=true` 的本地用户清单标的
- 看 BUY / EXIT 候选是否变化
- 看市场状态、quote / bars 是否异常
- 看节奏是否突变

### 2. 先找有什么值得看
调用：`scout`
适合：
- 让它筛候选标的
- 让它从一堆波动里挑值得继续验证的

### 3. 想知道最近发生了什么
调用：`newswire`
适合：
- 收集单个标的的新闻时间线
- 总结某行业/宏观事件的潜在影响

### 4. 想把想法变成计划
调用：`strategist`
适合：
- 让它写入场 / 失效 / 风险收益 / 仓位逻辑
- 输出结构化交易计划草案

### 5. 想把计划变成可执行检查单
调用：`executor`
适合：
- 检查配置
- 写 preview_order 校验清单
- 写 guarded 验证步骤

### 6. 想在收盘后做总结与收尾
调用：`closer`
适合：
- 每个市场收盘后的行情总结
- 当日新闻/催化回顾
- 执行与风控状态总结
- 次日关注点整理
- 止盈止损 / 减仓平仓 / 收尾复盘

## 推荐调用方式

优先把任务描述写成这四部分：
1. **目标**：你要它解决什么
2. **输入**：它该看哪些文件/结果
3. **边界**：不允许做什么
4. **输出格式**：你希望它怎么回

## 示例模板

### 调 `watcher`
目标：检查本地清单中的标的最近一轮候选与市场状态是否有变化。
输入：
- `./data/watchlist.json`
- `./runtime/engine/.last_execution_cycle.json`
- `./runtime/engine/logs/dispatch_queue.jsonl`
边界：只读，不运行 Python，不对外发消息。
输出：
- 一句话结论
- 3 个关键观察
- 1 个下一步建议

### 调 `strategist`
目标：基于本地股票清单给当前优先标的做保守版计划。
输入：
- `./data/watchlist.json`
- 最新周期结果
- 风控约束
边界：不下单，不假设已执行。
输出：入场条件 / 失效条件 / 风险收益 / 仓位建议。

### 调 `executor`
目标：把计划转成 guarded 模式的执行检查单，并核对本地清单与执行链是否一致。
输入：
- `./data/watchlist.json`
- 策略草案
- app_config
- 上次执行结果
边界：不直接执行 Python，不提交真实订单。
输出：检查步骤、命令建议、验证点、最短错误点。

## 重要规则

- 这些 subagent 默认只对你汇报，不直接对老师说话
- 如果任务涉及 **Python、脚本执行、真实提交、支付或其他高风险动作**：
  - 你可以让 subagent 帮你整理命令和检查点
  - 但真正执行默认还是转交 `arona`

## 推荐工作流

1. `scout` / `newswire` 先收集
2. `strategist` 形成计划
3. `executor` 拆执行步骤
4. `watcher` 做运行与结果复核
5. `closer` 负责退出与收尾
