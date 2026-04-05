# Tiger Trading 项目任务清单

> 更新时间：2026-04-06 04:13
> 更新内容：整理结构，将设计说明和规则移至附录 A
> 架构原则：Engine 做机械的，Agent 做判断的。决策权永远在 Agent 层。

## 架构概览

```
Agent 层 (yuuka 中枢 + subagents)
  ↕ 读写共享文件
Engine 层 (Docker 自动化: 数据→信号→风控→执行)
  ↕ Tiger API
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
|---|------|------|--------|------|
| 1.1 | 配置仅启用美股 | 修改 `app_config` 中 markets 为 `["US"]`，watchlist 仅保留美股标的 | — | ✅ 完成 |
| 1.2 | 验证 engine Docker 容器能启动 | `docker compose up tiger-engine`，确认容器存活 | — | ✅ 完成 |
| 1.3 | 运行 `run_readonly_cycle.py` | 在容器内跑一次只读周期，输出美股账户/持仓/市场状态 | — | ✅ 完成 |
| 1.4 | 验证美股 kline 数据拉取 | 确认 30min K 线数据能正确获取并解析 | — | ✅ 完成 |
| 1.5 | 运行 `run_strategy_cycle.py` | 验证美股 SMA 信号生成正常输出 | — | ✅ 完成 |
| 1.6 | 运行 `run_dry_run_cycle.py` | 验证美股风控→意图→通知预览全链路 | — | ✅ 完成 |
| 1.7 | 修复发现的 bug | 完整周期运行后必然会发现的问题 | — | ✅ 完成（无重大 bug） |
| 1.8 | Engine 接入 yfinance 行情源 | kline 数据用 yfinance 做 fallback，保留 Tiger 接口 | — | ✅ 完成（待 Docker 测试） |

## Phase 2：Dashboard 增强

目标：Dashboard 成为美股交易的完整监控+控制面板

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 2.1 | 市场开关 UI | Dashboard 增加 US/HK 启用开关（当前仅 US 生效） | ✅ 完成（/api/config PATCH） |
| 2.2 | 展示 Engine 运行结果 | /api/engine 端点：最近信号、风控决策、执行状态 | ✅ 完成 |
| 2.3 | 风控参数在线调整 | 暴露上限、止损比例等参数可从 web UI 修改 | ✅ 完成（/api/config PATCH） |
| 2.4 | 系统开关控制 | /api/control/lock, /api/control/unlock | ✅ 完成 |
| 2.5 | 行情刷新频率调整 | 前端可修改 DataCache 的 refresh_interval | ✅ 完成（/api/refresh） |
| 2.6 | 审计日志查看 | /api/audit 端点，展示最近 N 条审计记录 | ✅ 完成 |
| 2.7 | Engine 状态健康检查 | engine 的 last_heartbeat, consecutive_failures 等 | ✅ 完成（/api/health/engine） |
| 2.8 | Tiger 配置文件上传入口 | 支持 paper/live 配置切换 | ✅ 完成 |
| 2.9 | Paper/Live 模式自动检测 | 从配置文件读取 env 字段，自动适配 | ✅ 完成 |

## Phase 3：Agent 体系搭建

目标：建立完整的美股 Agent 协作体系

| # | Agent | 模型 | 任务 | 调度方式 | 状态 |
|---|-------|------|------|----------|------|
| 3.1 | tiger-watcher | mimo-v2-omni | 系统健康监控：engine 心跳、Docker 状态、API 权限 | 每 15min 定时 | ⬜ 未开始 |
| 3.2 | tiger-newswire | mimo-v2-omni | 美股新闻/催化扫描，输出结构化情报 | US 盘前 + 盘中 15min | ⬜ 未开始 |
| 3.3 | tiger-strategist | mimo-v2-pro | 基于美股信号+新闻+宏观产生交易建议（复杂推理） | 信号触发或定时 | ⬜ 未开始 |
| 3.4 | tiger-executor | mimo-v2-omni | 美股执行检查单：参数校验、preview 确认 | 策略完成后触发 | ⬜ 未开始 |
| 3.5 | tiger-scout | mimo-v2-omni | 美股候选标的扫描、异常波动检测 | 按需或定时 | ⬜ 未开始 |
| 3.6 | tiger-closer | mimo-v2-omni | 美股收盘总结：行情+新闻+执行+次日关注 | US 收盘后 | ⬜ 未开始 |

## Phase 4：美股自动化调度

目标：Engine + Agent 全自动运转（美股）

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 4.1 | Engine cron 调度 | 每 30min 自动跑 `run_dry_run_cycle`（美股盘中） | ⬜ 未开始 |
| 4.2 | Agent 定时任务 | OpenClaw cron 配置各 agent 的美股时段触发 | ⬜ 未开始 |
| 4.3 | 信号触发链 | Engine 输出信号 → yuuka 读取 → 决定是否激活 strategist | ⬜ 未开始 |
| 4.4 | A2A 通知链 | 美股交易发生 → yuuka → Telegram 通知 | ⬜ 未开始 |
| 4.5 | 异常恢复 | Engine 异常 → watcher 检测 → yuuka 处理 | ⬜ 未开始 |
| 4.6 | Dashboard 记录 | 所有事件写入 dashboard 日志 | ⬜ 未开始 |

## Phase 5：港股扩展 + Live 过渡

美股稳定运行后再推进

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 5.1 | 启用港股开关 | 打开 HK market toggle，watchlist 加入港股标的 | ⬜ 未开始 |
| 5.2 | 港股行情接入 | kline + quote 数据源适配港股 | ⬜ 未开始 |
| 5.3 | 港股交易时段适配 | entry_window、lunch_break 等时段逻辑 | ⬜ 未开始 |
| 5.4 | 港股 Agent 调度 | newswire/closer 适配港股盘前盘后时段 | ⬜ 未开始 |
| 5.5 | Paper/Live 配置差异适配 | API 端点、下单参数、权限差异处理 | ⬜ 未开始 |
| 5.6 | Live 安全机制 | 更严格的 preview、人工确认、限速 | ⬜ 未开始 |
| 5.7 | Dashboard live 模式切换 | UI 明确区分 paper/live 状态 | ⬜ 未开始 |

---

## 附录 A：设计说明

### A.1 newswire_sources 设计说明

**核心定位：** tiger-newswire 扫描市场新闻/催化事件时的数据源配置清单。

**技术栈：** Brave Search + web_fetch + Yahoo Finance

**三层数据源架构：**

| 层级 | 来源 | 用途 |
|------|------|------|
| **搜索引擎层** | Brave Search API | 关键词搜索（如 "小米财报"、"NVDA earnings"），获取最新动态 |
| **网页抓取层** | web_fetch | 定向抓取指定财经网站（如 Seeking Alpha、Yahoo Finance 特定页面） |
| **结构化数据层** | Yahoo Finance API | 直接拉取财报日历、分析师评级、重大新闻等结构化数据 |

**设计优势：**

1. **冗余保障** — 三层互为备份，单源故障不阻塞
2. **去重机制** — 不同源可能报道同一事件，需要合并/去重
3. **调度适配** — HK 盘前/US 盘前/US 盘中各 15min 频率，信息源可能根据市场切换权重

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
| `xiaomi-tp/mimo-v2-pro` | pro | 高性能（4x成本） | 复杂推理、策略分析、多步规划、代码审查 |
| `xiaomi-tp/mimo-v2-omni` | omni | 多模态（低成本） | 截图分析、图像理解、浏览器交互、通用任务 |

**选择原则：**

- **默认用 omni**（成本更低，覆盖面广）
- 涉及深度推理、复杂逻辑、关键决策 → 用 **pro**（4 倍成本，非必要不用）
- 图像/浏览器/多模态 → **omni**

**Agent 模型分配：**

| Agent | 模型 | 说明 |
|-------|------|------|
| tiger-watcher | mimo-v2-omni | 系统健康监控（通用任务） |
| tiger-newswire | mimo-v2-omni | 新闻扫描（通用任务） |
| tiger-strategist | mimo-v2-pro | 交易建议（复杂推理） |
| tiger-executor | mimo-v2-omni | 执行检查（通用任务） |
| tiger-scout | mimo-v2-omni | 标的扫描（通用任务） |
| tiger-closer | mimo-v2-omni | 收盘总结（通用任务） |

---

## 关键决策记录

| 日期 | 决策 |
|------|------|
| 2026-04-05 | 架构定为双层：Engine(机械) + Agent(判断)，决策权在 Agent |
| 2026-04-05 | tiger-watcher 重新定位为系统健康监控（非行情监控） |
| 2026-04-05 | 行情源设计为可切换，当前以 yfinance 验证，后续切 Tiger |
| 2026-04-05 | Tiger API 待购买纳斯达克 basic 权限 |
| 2026-04-05 | Engine 做代码级信号，Agent 做判断级信号，灵活组合 |
| 2026-04-05 | Dashboard 合并进 Engine 服务，作为前端展示+控制面板 |
| 2026-04-05 | **Phase 1-4 仅实现美股，港股通过 market toggle 预留接口** |
| 2026-04-06 | **newswire_sources 预留选项机制**：新闻数据源可配置、可切换、可降级 |
| 2026-04-06 | **Agent 模型选择规则**：tiger-watcher/tiger-executor 用 omni，tiger-strategist 用 pro（复杂推理） |

---

## 状态标记

- ⬜ 未开始
- 🔨 进行中
- ✅ 完成
- ❌ 阻塞/失败
- ⏸️ 暂缓
