# Tiger Trading 项目任务清单

> 更新时间：2026-04-07 02:05
> 更新内容：Phase 4 重写（热路径+冷路径架构），调度器集成完成
> 架构原则：Engine 做机械的，Agent 做判断的。决策权永远在 Agent 层。

## 架构概览

```
单进程 Dashboard（Docker 常驻）
  ├── Web UI (:8088)
  ├── 行情轮询 (30s, yfinance)
  └── 信号调度器 (60s)
       └── yfinance → Engine 信号生成 → 写入 runtime

热路径（代码，每次周期）：
  Engine → 信号 → 风控 → 订单 → Executor 提交
  （全自动化，无 Agent 介入）

冷路径（Agent，定期）：
  Strategist (15min cron) → 监控 + 调参 + 干预
  Newswire → 新闻扫描 → 写入 market_context

Agent 层 (yuuka 中枢 + subagents)
  ↕ 读写共享文件 / 配置变更
Engine 层 (Dashboard 内置调度器)
  ↕ yfinance / Tiger API
Tiger Open Platform (Paper → Live)
```

## 市场范围

| 市场 | 状态 | 说明 |
|------|------|------|
| **美股 (US)** | ✅ 当前实现 | Phase 1-4 全部聚焦美股 |
| **港股 (HK)** | ⏸️ 预留接口 | Dashboard 保留开关，代码预留市场参数，暂不实现 |

> 设计原则：所有市场相关代码使用 `markets` 配置驱动，通过开关控制启用哪些市场。
> HK 封装完成后再打开开关即可复用同一套逻辑。

---

## Phase 1：Engine 可运行验证（最高优先级）

目标：让 engine 在 Docker 内跑通一个完整的美股 only readonly 周期

| # | 任务 | 说明 | 阻塞点 | 状态 |
|---|------|------|---|---|
| 1.1 | Dockerfile + docker-compose.yml | 创建引擎和 Dashboard 的 Docker 镜像 | 无 | ✅ 已完成 |
| 1.2 | 配置文件分离 | app_config.paper.json / tiger_openapi_config.properties | 无 | ✅ 已完成 |
| 1.3 | 只读周期入口 | run_readonly_cycle.py 可执行 | 无 | ✅ 已完成 |
| 1.4 | 策略周期入口 | run_strategy_cycle.py 可执行 | 无 | ✅ 已完成 |
| 1.5 | Dry-run 周期入口 | run_dry_run_cycle.py 可执行 | 无 | ✅ 已完成 |
| 1.6 | 执行周期入口 | run_execution_cycle.py 可执行 | 无 | ✅ 已完成 |
| 1.7 | Dashboard 可运行 | dashboard/main.py 可启动 | 无 | ✅ 已完成 |
| 1.8 | Dashboard 健康检查 | /health endpoint 可访问 | 无 | ✅ 已完成 |
| 1.9 | Docker 镜像构建验证 | docker-compose up 可启动 | 无 | ✅ 已完成 |
| 1.10 | 只读周期跑通 | 读取账户/行情/持仓，不提交订单 | 无 | ✅ 已完成 |
| 1.11 | 策略周期跑通 | 生成信号，不提交订单 | 无 | ✅ 已完成 |
| 1.12 | Dry-run 周期跑通 | 生成信号+风控+预览+通知，不提交订单 | 无 | ✅ 已完成 |
| 1.13 | 执行周期跑通 | 生成信号+风控+预览+意图+提交适配，不真实下单 | 无 | ✅ 已完成 |
| 1.14 | Dashboard 行情显示 | 美股行情显示（延迟行情） | 无 | ✅ 已完成 |
| 1.15 | Dashboard 开盘状态 | 行情显示增加开盘状态 | 无 | ✅ 已完成 |
| 1.16 | 内置信号调度器 | Dashboard 内嵌 Engine 后台调度，单进程架构 | 无 | ✅ 已完成 |

---

## Phase 2：Dashboard 增强（次高优先级）

目标：完善 Dashboard 功能，支持行情监控、信号查看、执行预览

| # | 任务 | 说明 | 阻塞点 | 状态 |
|---|------|------|---|---|
| 2.1 | 行情页面 | 显示共享清单标的行情（延迟行情） | 无 | ✅ 已完成 |
| 2.2 | 信号页面 | 显示最新周期信号（BUY/EXIT 候选） | 无 | ✅ 已完成 |
| 2.3 | 执行预览页面 | 显示 dry-run 预览结果 | 无 | ✅ 已完成 |
| 2.4 | 持仓页面 | 显示当前持仓、订单、成交 | 无 | ✅ 已完成 |
| 2.5 | 风控页面 | 显示风控状态、preview_blockers | 无 | ✅ 已完成 |
| 2.6 | 控制页面 | 支持 lock/unlock、模式切换 | 无 | ✅ 已完成 |
| 2.7 | 日志页面 | 显示执行日志、审计日志 | 无 | ✅ 已完成（复用现有 audit API） |
| 2.8 | 通知页面 | 显示通知预览、dispatch queue | 无 | ✅ 已完成 |
| 2.9 | 配置页面 | 显示配置参数、股票清单 | 无 | ✅ 已完成 |
| 2.10 | 行情显示增加开盘状态 | 在行情显示中增加是否开盘的状态显示（美股/港股开盘时间判断） | 无 | ✅ 已完成 |
| 2.11 | 同步 watchlist/config | 解决 watchlist.json 与 app_config.paper.json 标的列表不一致（02097 蜜雪集团） | 无 | ✅ 已完成 |

---

## Phase 3：Subagent 搭建（当前重点）

目标：搭建 6 个 subagent，配置 tool 权限，启动运行

| # | 任务 | 说明 | 阻塞点 | 状态 |
|---|------|------|---|---|
| 3.1 | tiger-watcher 搭建 | 创建独立 agent，配置 tool 权限，启动 subagent | 无 | ✅ 已完成 |
| 3.2 | tiger-newswire 搭建 | 创建独立 agent，配置 tool 权限，启动 subagent | 无 | ✅ 已完成 |
| 3.3 | tiger-strategist 搭建 | 创建独立 agent，配置 tool 权限，启动 subagent | 无 | ✅ 已完成 |
| 3.4 | tiger-executor 搭建 | 创建独立 agent，配置 tool 权限，启动 subagent | 无 | ✅ 已完成 |
| 3.5 | tiger-scout 搭建 | 创建独立 agent，配置 tool 权限，启动 subagent | 无 | ✅ 已完成 |
| 3.6 | tiger-closer 搭建 | 创建独立 agent，配置 tool 权限，启动 subagent | 无 | ✅ 已完成 |

> **说明**：Phase 3 的 6 个 agent 配置文件已准备完成，存放在 `/workspace/tiger-trading/agents/` 目录。
> 部署脚本：`deploy_tiger_agents.sh`（一键启动所有 agent）
> 停止脚本：`stop_tiger_agents.sh`（一键停止所有 agent）

---

## Phase 4：策略实现（当前阶段）

目标：实现 30min 趋势跟随策略，热路径自动化 + 冷路径 Agent 监控

> **架构决策**：
> - **热路径**（代码）：Engine 信号 → 风控 → 订单 → 执行，全自动化无 Agent 介入
> - **冷路径**（Agent）：Strategist 每 15min 监控信号质量、市场变化，调参或干预
> - **数据源**：多源可选，当前开发阶段使用 yfinance
> - **调度**：内置 SignalScheduler，60s 间隔检测 Bar 闭合并触发信号评估

### 4.1 热路径（代码层）

| # | 任务 | 说明 | 阻塞点 | 状态 |
|---|------|------|---|---|
| 4.1.1 | 信号调度器集成 | Dashboard 内嵌 Engine 后台调度，yfinance 数据源 | 无 | ✅ 已完成 |
| 4.1.2 | 信号生成（30min SMA 交叉） | Engine 代码生成 BUY/EXIT/HOLD 信号 | 无 | ✅ 已完成 |
| 4.1.3 | 风控逻辑 | 单笔 ≤$10,000 / 单日亏损 ≤5% / 最大暴露 ≤$10,000 | 无 | ✅ 已完成（已有代码） |
| 4.1.4 | 订单构建 | IntentBuilder 生成订单意图 | 无 | ✅ 已完成（已有代码） |
| 4.1.5 | 执行适配 | Executor 通过 Tiger API 提交订单 | 无 | ⬜ 待集成 |
| 4.1.6 | 调度器可调间隔 | 支持 5min / 15min / 30min 可配置 | 无 | ✅ 已完成 |
| 4.1.7 | 数据源多选 | 支持 yfinance / Tiger 可切换 | 无 | ✅ 已完成 |

### 4.2 冷路径（Agent 层）

| # | 任务 | 说明 | 阻塞点 | 状态 |
|---|------|------|---|---|
| 4.2.1 | Strategist 监控循环 | 15min cron，读取信号日志 + 市场上下文 | 4.1.1 | ⬜ 未开始 |
| 4.2.2 | 信号质量分析 | 分析最近信号的胜率、假信号率 | 4.2.1 | ⬜ 未开始 |
| 4.2.3 | 参数调参建议 | 根据信号质量建议调整 SMA/动量参数 | 4.2.2 | ⬜ 未开始 |
| 4.2.4 | 紧急干预 | 发现异常时 lock 控制台 | 4.2.1 | ⬜ 未开始 |
| 4.2.5 | Newswire 新闻接入 | 给 Strategist 提供新闻上下文 | 4.2.1 | ⬜ 未开始 |

### 4.3 执行层

| # | 任务 | 说明 | 阻塞点 | 状态 |
|---|------|------|---|---|
| 4.3.1 | Executor 提交适配 | Tiger API 订单提交（paper 模式） | 4.1.4 | ⬜ 未开始 |
| 4.3.2 | 订单状态同步 | 查询订单状态，更新 Dashboard | 4.3.1 | ⬜ 未开始 |
| 4.3.3 | 持仓同步 | 下单后同步持仓到 Dashboard | 4.3.1 | ⬜ 未开始 |

---

## Phase 5：模拟盘连续观察/调参（待开发）

目标：模拟盘连续运行，观察策略表现，调优参数

| # | 任务 | 说明 | 阻塞点 | 状态 |
|---|------|------|---|---|
| 5.1 | 模拟盘连续运行 | 30min 周期自动运行 | Phase 4 | ⬜ 未开始 |
| 5.2 | 策略表现观察 | 记录 PnL、胜率、最大回撤 | Phase 4 | ⬜ 未开始 |
| 5.3 | 参数调优 | 调整策略参数，优化表现 | Phase 4 | ⬜ 未开始 |
| 5.4 | 风控调优 | 调整风控参数，降低风险 | Phase 4 | ⬜ 未开始 |

---

## 附录 A：设计说明与规则

### A.1 newswire_sources 设计说明

**核心定位：** tiger-newswire 扫描市场新闻/催化事件时的数据源配置清单。

**信息源：**

1. **Brave Search**（主源 1）
   - 用途：发现最新事件
   - 配置：需要 BRAVE_API_KEY
   - 当前状态：❌ 未配置（API 密钥缺失）

2. **web_fetch**（主源 2）
   - 用途：提取文章摘要
   - 配置：无需 API 密钥
   - 当前状态：⚠️ 受限（页面提取受限）

3. **Yahoo Finance**（辅助）
   - 用途：补充新闻/催化
   - 配置：无需 API 密钥
   - 当前状态：⚠️ 受限（页面为 JavaScript 渲染，提取困难）

**去重机制** — 不同源可能报道同一事件，需要合并/去重

**调度适配** — HK 盘前/US 盘前/US 盘中各 15min 频率，信息源可能根据市场切换权重

**信息流：**

```
Brave Search ─┐
              ├─→ tiger-newswire ─→ 写入 tiger_shared_market_context.json
web_fetch ────┤         ↓
              │    催化事件/风险信号
Yahoo Finance─┘         ↓
                    tiger-strategist 读取 → 生成交易计划
```

**配置预留选项：**

- JSON 配置文件支持多组 source，按优先级顺序尝试
- 单源故障时自动降级到下一优先级源
- 支持动态切换（如盘前用 Yahoo Finance，盘中用 Brave Search）

### A.2 Agent 模型选择规则

| 模型 | 别名 | 定位 | 适用场景 |
|------|------|------|---------|
| `xiaomi/mimo-v2-pro` | pro | 高性能（4x成本） | 复杂推理、策略分析、多步规划、代码审查 |
| `xiaomi/mimo-v2-omni` | omni | 多模态（低成本） | 截图分析、图像理解、浏览器交互、通用任务 |

**Agent 模型分配：**

| Agent | 模型 | 说明 |
|-------|------|------|
| tiger-watcher | xiaomi/mimo-v2-omni | 系统健康监控（通用任务） |
| tiger-newswire | xiaomi/mimo-v2-omni | 新闻扫描（通用任务） |
| tiger-strategist | xiaomi/mimo-v2-pro | 交易建议（复杂推理） |
| tiger-executor | xiaomi/mimo-v2-omni | 执行检查（通用任务） |
| tiger-scout | xiaomi/mimo-v2-omni | 标的扫描（通用任务） |
| tiger-closer | xiaomi/mimo-v2-omni | 收盘总结（通用任务） |

**选择原则：**
- **默认用 omni**（成本更低，覆盖面广）
- 涉及深度推理、复杂逻辑、关键决策 → 用 **pro**（4 倍成本，非必要不用）
- 图像/浏览器/多模态 → **omni**
- 原则：能用 omni 解决的不升级 pro

---

## 变更日志

| 日期 | 变更内容 |
|------|----------|
| 2026-04-03 | 初始化任务清单 |
| 2026-04-03 | 完成 Phase 1 全部任务 |
| 2026-04-03 | tiger-watcher 重新定位为系统健康监控 |
| 2026-04-04 | 新增 Phase 2 Dashboard 增强任务 |
| 2026-04-05 | 新增 Phase 3 Subagent 搭建任务 |
| 2026-04-06 | 整理任务清单结构，将设计说明和规则移至附录 A |
| 2026-04-06 | 新增任务：行情显示增加开盘状态 |
| 2026-04-06 | 完成行情显示开盘状态功能 |
| 2026-04-06 | 完成 Phase 3 subagent 配置准备，交由 arona 部署 |
| 2026-04-07 | 同步 watchlist/config，添加 02097 蜜雪集团 |
| 2026-04-07 | Phase 2 全部完成（信号/风控/执行预览/通知页面） |
| 2026-04-07 | Docker 容器部署完成（dashboard + engine） |
| 2026-04-07 | Engine readonly cycle 验证通过 |
| 2026-04-07 | 架构重构：单进程 Dashboard + 内置信号调度器 |
| 2026-04-07 | Phase 4 重写：热路径（代码）+ 冷路径（Agent）架构 |
| 2026-04-07 | Phase 4.1 完成：信号调度器集成，信号生成正常 |
