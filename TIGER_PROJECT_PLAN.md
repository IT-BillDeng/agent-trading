# Tiger Trading 项目任务清单

> 更新时间：2026-04-07 03:53
> 架构原则：Engine 做机械的，Agent 做判断的。信号始终由代码规则产生，Agent 只管理规则。

## 架构概览

```
热路径（代码，每次调度周期）：
  DataHub 拉取行情 → 规则引擎评估 → 信号 → 风控 → 订单 → Tiger API 提交

冷路径（Agent，定时）：
  Strategist:
    盘前 (09:00 ET) → 复盘 + 设定今日参数
    盘中 (每 15min) → 监控异常 → 暂停/恢复（不改参数）
    盘后 (16:30 ET) → 分析信号质量 → 调整明日策略
```

## 核心设计决策

| 决策 | 结论 |
|------|------|
| 信号谁产生 | Engine 规则引擎（代码） |
| Strategist 做什么 | 管理规则（设计/调参/暂停），不直接产生信号 |
| 新闻如何影响交易 | Strategist 分析新闻 → 调整规则参数 → Engine 按新规则评估 |
| 仓位怎么算 | risk_based sizing（风险预算 / 每股风险） |
| 运行模式 | off / signals / trade |
| Paper vs Live | 账户类型（Tiger 配置决定），非运行模式 |
| 策略周期 | 每条规则独立 timeframe（5min/15min/30min/60min） |
| 策略热更新 | 配置参数热更新，代码变更需重启 |
| 回测 | 内置回测框架，Strategist 改规则前先回测验证 |

---

## ✅ Phase 1：基础平台（已完成）

单进程 Dashboard + 内置调度器 + 完整执行链路 + 仓位管理基座

## ✅ Phase 2：Subagent 体系（配置就绪）

6 个 Subagent 配置文件就绪。待调度机制实现后启动。

---

## ✅ Phase 3：规则引擎

目标：策略逻辑参数化，Strategist 改配置 = 改策略，零重启

### 3.1 指标库

| 指标 | 状态 |
|------|------|
| SMA | ✅ 已有 |
| EMA | ✅ 完成 |
| RSI | ✅ 完成 |
| Bollinger | ✅ 完成 |
| MACD | ✅ 完成 |
| ATR | ✅ 完成 |
| Momentum | ✅ 已有 |
| Volume | ✅ 完成 |

### 3.2 规则引擎

| # | 任务 | 状态 |
|---|------|------|
| 3.2.1 | 规则配置 schema（JSON） | ✅ 完成 |
| 3.2.2 | 条件评估器（解析条件 → 调用指标 → AND/OR 组合） | ✅ 完成 |
| 3.2.3 | 多 timeframe 支持（每规则独立周期） | ✅ 完成 |
| 3.2.4 | 替换当前硬编码 StrategyEngine | ✅ 完成 |
| 3.2.5 | 规则配置读写 API（/api/rules） | ✅ 完成 |

---

## ✅ Phase 4：回测框架

目标：Strategist 改规则前可回测验证，策略有据可依

| # | 任务 | 状态 |
|---|------|------|
| 4.1 | 历史数据获取（yfinance） | ✅ 完成 |
| 4.2 | 逐 Bar 模拟引擎 | ✅ 完成 |
| 4.3 | 订单撮合模拟（滑点/手续费） | ✅ 完成 |
| 4.4 | 绩效指标（Sharpe/胜率/回撤/PnL/盈亏比） | ✅ 完成 |
| 4.5 | 回测 API（/api/backtest） | ✅ 完成 |
| 4.6 | Dashboard 回测报告 | ✅ 完成 |

---

## ⏳ Phase 5：Agent 调度与运行

### 5.1 Watcher（系统健康监护人）✅ 设计完成

| 级别 | 条件 | 处理方式 |
|------|------|----------|
| Info | 正常 | 仅日志 |
| Warning | 单次异常 | 日志 + 状态记录 |
| Critical | 连续失败 ≥3 | 日志 + 通知先生 |
| Emergency | 连续失败 ≥5 / 账户异常 | 日志 + 通知先生 + 自动锁定 |

**监控维度：**
- 引擎健康（locked/unlocked、运行模式）
- 执行周期（最近周期、信号、风控）
- 数据源状态
- 账户状态（净值、异常检测）
- 风控状态（阻塞项）

**通知抑制：** 同一告警 30 分钟内不重复

### 5.2 其他 Agent（待实现）

| Agent | 时段 | 频率 | 模型 |
|-------|------|------|------|
| tiger-strategist | 盘前 | 09:00 ET | pro |
| tiger-strategist | 盘中 | 每 15min | pro |
| tiger-strategist | 盘后 | 16:30 ET | pro |
| tiger-closer | 盘后 | 收盘后 | omni |
| tiger-newswire | 盘前/盘中 | 按需 | omni |

---

## ⏳ Phase 6：模拟盘优化

| # | 任务 |
|---|------|
| 6.1 | 每日 PnL 跟踪 |
| 6.2 | 信号质量跟踪 |
| 6.3 | 组合相关性管理 |
| 6.4 | 波动率自适应止损（ATR） |
| 6.5 | 参数优化 |

---

## 附录

### 风控参数

**系统层（不可由规则覆盖）：**

| 参数 | 值 | 说明 |
|------|-----|------|
| max_order_notional_usd | $10,000 | 单笔订单金额上限 |
| max_total_exposure_usd | $10,000 | 全部持仓总暴露上限 |
| daily_loss_limit_pct | 5% | 当日亏损限制 |

**策略层（可在规则配置中设置）：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| stop_loss_pct | 0.03 | 止损比例 |
| take_profit_pct | 0.06 | 止盈比例 |
| risk_budget_pct | 0.01 | 风险预算（max_order 的 1%） |

**仓位公式：**
```
risk_per_share = 入场价 × stop_loss_pct
risk_budget = max_order × risk_budget_pct
risk_quantity = risk_budget / risk_per_share
final_quantity = min(max_limit_quantity, risk_quantity, suggested_quantity)
```

### Agent 模型

| 模型 | 适用场景 |
|------|---------|
| `xiaomi-tp/mimo-v2-pro` | Strategist |
| `xiaomi-tp/mimo-v2-omni` | 其他 Agent |

### 交易时段

| 市场 | 常规 | 盘前 | 盘后 |
|------|------|------|------|
| US | Mon-Fri 9:30-16:00 ET | 4:00-9:30 | 16:00-20:00 |
| HK | Mon-Fri 9:30-12:00, 13:00-16:00 HKT | — | — |

---

## 变更日志

| 日期 | 变更内容 |
|------|----------|
| 2026-04-03 | 初始化 |
| 2026-04-06 | Phase 1-2 完成 |
| 2026-04-07 | 架构重构 + 执行链路 + 仓位管理 |
| 2026-04-07 | 全面重写：固化架构决策，新增规则引擎/回测/Strategist 定位 |
| 2026-04-07 | Phase 3 规则引擎完成：指标库扩展 + 条件评估器 + 规则配置 API |
| 2026-04-07 | Phase 4 回测框架完成：历史数据获取 + 订单撮合模拟 + 绩效指标 + 回测 API |
