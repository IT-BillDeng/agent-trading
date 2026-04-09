# Agent Trading 项目任务清单

> 更新时间：2026-04-09 02:38 CST
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

## 当前部署架构

```
┌─────────────────────────────────────────────┐
│  agent-dashboard（单一容器）                  │
│  ┌───────────┐ ┌───────────┐ ┌────────────┐ │
│  │ FastAPI   │ │ Scheduler │ │ RuleEngine │ │
│  │ REST API  │ │ 引擎调度   │ │ 规则评估    │ │
│  └───────────┘ └───────────┘ └────────────┘ │
│  ┌───────────┐ ┌───────────┐ ┌────────────┐ │
│  │ Backtest  │ │ Config    │ │ YFinance   │ │
│  │ 回测框架   │ │ 管理      │ │ 数据源      │ │
│  └───────────┘ └───────────┘ └────────────┘ │
└─────────────────────────────────────────────┘
  Docker: 8088 → host
  Cron (sandbox): newswire / strategist / watcher / closer
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
| 策略周期 | 30min（固定），未来支持多周期 |
| 数据源 | yfinance（免费，盘前/盘后/非交易日均可） |
| 策略热更新 | rules.json 每周期重新读取，零重启 |
| 回测 | 内置回测框架，Strategist 改规则前先回测验证 |

---

## ✅ Phase 1：基础平台（已完成）

Dashboard + 内置调度器 + 完整执行链路 + 仓位管理基座

## ✅ Phase 2：Subagent 体系（已完成）

6 个 Subagent cron 配置就绪并运行中。

---

## ✅ Phase 3：规则引擎

策略逻辑参数化，Strategist 改配置 = 改策略，零重启

### 3.1 指标库

| 指标 | 状态 |
|------|------|
| SMA | ✅ |
| EMA | ✅ |
| RSI | ✅ |
| Bollinger | ✅ |
| MACD | ✅ |
| ATR | ✅ |
| Momentum | ✅ |
| Volume | ✅ |

### 3.2 规则引擎

| # | 任务 | 状态 |
|---|------|------|
| 3.2.1 | 规则配置 schema（JSON） | ✅ |
| 3.2.2 | 条件评估器 | ✅ |
| 3.2.3 | 多 timeframe 支持 | ✅ |
| 3.2.4 | 规则配置 API（/api/rules） | ✅ |
| 3.2.5 | 规则 symbols 覆盖全部 watchlist | ✅ 2026-04-08 |

---

## ✅ Phase 4：回测框架

| # | 任务 | 状态 |
|---|------|------|
| 4.1 | 历史数据获取（yfinance） | ✅ |
| 4.2 | 逐 Bar 模拟引擎 | ✅ |
| 4.3 | 订单撮合模拟 | ✅ |
| 4.4 | 绩效指标 | ✅ |
| 4.5 | 回测 API（/api/backtest） | ✅ |
| 4.6 | 批量回测 API（/api/backtest/batch） | ✅ |
| 4.7 | Dashboard 回测报告 | ✅ |

---

## ✅ Phase 5：Agent 调度与运行

### 5.0 Newswire（新闻采集） ✅

- 数据源：web_search（Perplexity）
- 输出：POST /api/news → Dashboard 面板
- Cron：盘前/盘中(q30)/盘后(q2h)
- 每条含 importance/sentiment/category/tags
- **当前状态：已 disable（待调试）**

### 5.1 Watcher（系统健康） ✅ 运行中

| 级别 | 处理 |
|------|------|
| info | 仅记录 |
| warning | 日志 + 状态 |
| critical | 通知先生 |
| emergency | 通知 + 自动锁定 |

- 频率：每 15 分钟
- 7 项健康检查全部通过

### 5.2 Strategist（策略管理） ✅ 运行中

| 时段 | 职责 | 频率 |
|------|------|------|
| 盘前 | 复盘 + 设定今日参数 | 09:05 ET |
| 盘中 | 监控异常 → 暂停/恢复 | q15min |
| 盘后 | 分析信号质量 → 调整明日策略 | 16:30 ET |

- 模型：pro（深度推理）
- 硬约束：盘中不改参数，参数变更必须回测通过

### 5.3 Closer（收盘总结） ✅ 运行中

- 美股收盘后生成总结报告
- 推送到 Telegram

### 5.4 其他 Agent

| Agent | 状态 |
|-------|------|
| Executor | 🔧 待实现 |
| Scout | 🔧 待实现 |

---

## Phase 6：策略优化与迭代

### 6.1 min_bars 优化 ✅ 2026-04-08

| 项目 | 修复前 | 修复后 |
|------|--------|--------|
| 默认 max_period | 30 | 0 |
| buffer | +10 | +5 |
| RSI 实际 min_bars | 35 | 19 |
| BB 实际 min_bars | 35 | 25 |

根因：max_period 默认 30，所有指标周期 < 30，导致 min_bars = 35 与指标周期无关。

### 6.2 Volume Ratio 调整 ✅ 2026-04-08

- bollinger_breakout volume_ratio: 1.5 → 1.2

### 6.3 待验证方案

| 方案 | 状态 | 说明 |
|------|------|------|
| RSI 阈值 30/70 → 35/65 | ❌ 回测拒绝 | 胜率更低 |
| 止损调整 | ❌ 回测无显著改善 | RSI exit 优先于止损 |
| 日线 SMA-50 趋势过滤 | ⏳ 待实现 | Level 1 多周期组合 |

### 6.4 批量回测 API ✅

- 支持多 param_sets 并行对比
- 止损止盈参数映射已修复
- RSI/BB 参数均正确区分

---

## ✅ Dashboard 功能清单

| 功能 | 状态 | 说明 |
|------|------|------|
| 账户概览 | ✅ | 总资产/今日盈亏(含%)/可用资金/持仓市值 |
| 持仓列表 | ✅ | 含 watchlist 统一名称 |
| 自选行情 | ✅ | yfinance 数据源，盘前/盘后价格优先 |
| 最近订单 | ✅ | 紧凑格式，限 10 条 |
| 盈亏明细 | ✅ | 含 watchlist 名称 |
| 新闻面板 | ✅ | importance 筛选，时间显示 |
| 信号面板 | ✅ | 含 watchlist 名称 |
| 风控面板 | ✅ | 含 watchlist 名称 |
| 回测报告 | ✅ | 单次 + 批量 |
| 自选管理 | ✅ | 添加/删除/优先级，新增时自动获取名称 |
| 控制面板 | ✅ | 锁定/解锁/刷新间隔/风控参数 |
| 风控参数 | ✅ | max_exposure: $100K |

---

## 待办清单

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | 恢复 newswire cron | 当前已 disable，待调试 |
| P1 | 日线 SMA-50 趋势过滤 | 多周期组合 Level 1 |
| P1 | Executor 实现 | 信号触发后自动执行 |
| P2 | Scout 实现 | 候选标的/异常波动扫描 |
| P2 | 多周期支持 | 规则引擎支持多 timeframe |
| P3 | 过拟合保护 | 多标的验证、交叉验证 |

---

## 当前活跃规则

| 规则 | 指标 | 标的 | 参数 |
|------|------|------|------|
| rsi_reversal | RSI 14 | * (全部) | 买入<30, 卖出>70, 止损2% |
| bollinger_breakout | BB 20,2 | * (全部) | 突破上轨买入, volume>1.2x, 止损2.5% |
| trend_follow_30m | SMA 5/10/20 + Momentum | * (全部) | ⚠️ 已禁用 |

---

## Watchlist

| 符号 | 名称 | 市场 | 优先级 |
|------|------|------|--------|
| AAPL | Apple | US | normal |
| MSFT | Microsoft | US | high |
| NVDA | NVIDIA | US | high |
| AMZN | Amazon | US | normal |
| SMCI | Super Micro | US | normal |
| GOOGL | Alphabet | US | normal |

---

## Cron 任务一览

| 任务 | 频率 | 模型 | 状态 |
|------|------|------|------|
| watcher | q15min | omni | ✅ 运行 |
| newswire-premarket | 盘前 | omni | ❌ disabled |
| newswire-intraday | q30min | omni | ❌ disabled |
| newswire-afterhours | q2h | omni | ❌ disabled |
| strategist-premarket | 盘前 | pro | ✅ 运行 |
| strategist-intraday | q15min | pro | ✅ 运行 |
| strategist-afterhours | 盘后 | pro | ✅ 运行 |
| closer-us | 收盘后 | omni | ✅ 运行 |

---

## 已知问题与修复

| 日期 | 问题 | 修复 |
|------|------|------|
| 2026-04-07 | 订单时间戳显示 Invalid Date | Number() 转换字符串毫秒 |
| 2026-04-08 | 全部信号 insufficient_bars (30/35) | max_period 默认 30→0，buffer +10→+5 |
| 2026-04-08 | 仅 5 个信号而非 12 个 | 规则 symbols 从特定列表改为 ['*'] |
| 2026-04-08 | sandbox cron 写入的新闻 dashboard 读不到 | 新增 POST /api/news，改为 curl 写入 |
| 2026-04-08 | newswire items=0 | 文件写入改为 inline JSON curl |
| 2026-04-08 | watchlistMap 时序 bug | fetchWatchlist 改为 Promise.all 并行 |
| 2026-04-08 | 股票名称不统一 | watchlistMap 为唯一名称来源 |

---

## 变更日志

| 日期 | 变更内容 |
|------|----------|
| 2026-04-03 | 初始化，Docker 化 |
| 2026-04-06 | Phase 1-2 完成 |
| 2026-04-07 | Phase 3 规则引擎 + Phase 4 回测框架 |
| 2026-04-07 | Phase 5 Agent 调度体系（watcher/newswire/strategist/closer） |
| 2026-04-08 | min_bars 修复 + 规则 symbols 修复 + 新闻 API 通道修复 |
| 2026-04-08 | Dashboard UI 大量优化：今日盈亏/千分点/名称统一/百分比 |
| 2026-04-08 | 移除冗余 engine 服务 |
| 2026-04-08 | volume_ratio 1.5→1.2，总暴露 $10K→$100K |
| 2026-04-08 | Strategist 周期优化分析：维持 30min，建议日线 SMA-50 过滤 |
