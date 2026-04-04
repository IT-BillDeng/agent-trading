# Tiger Trading 项目任务清单

> 更新时间：2026-04-05
> 架构原则：Engine 做机械的，Agent 做判断的。决策权永远在 Agent 层。

## 架构概览

```
Agent 层 (yuuka 中枢 + subagents)
  ↕ 读写共享文件
Engine 层 (Docker 自动化: 数据→信号→风控→执行)
  ↕ Tiger API
Tiger Open Platform (Paper → Live)
```

---

## Phase 1：Engine 可运行验证（最高优先级）

目标：让 engine 在 Docker 内跑通一个完整 readonly 周期

| # | 任务 | 说明 | 阻塞点 | 状态 |
|---|------|------|--------|------|
| 1.1 | 验证 engine Docker 容器能启动 | `docker compose up tiger-engine`，确认容器存活 | 需宿主机 Docker | ⬜ 未开始 |
| 1.2 | 运行 `run_readonly_cycle.py` | 在容器内跑一次只读周期，输出账户/持仓/市场状态 | 需 Tiger API 连通 | ⬜ 未开始 |
| 1.3 | 验证 kline 数据拉取 | 确认 30min K 线数据能正确获取并解析 | Tiger kline 权限已确认 | ⬜ 未开始 |
| 1.4 | 运行 `run_strategy_cycle.py` | 验证 SMA 信号生成正常输出 | 依赖 1.3 | ⬜ 未开始 |
| 1.5 | 运行 `run_dry_run_cycle.py` | 验证风控→意图→通知预览全链路 | 依赖 1.4 | ⬜ 未开始 |
| 1.6 | 修复发现的 bug | 完整周期运行后必然会发现的问题 | — | ⬜ 未开始 |
| 1.7 | Engine 接入 yfinance 行情源 | 与 dashboard 共用 QuoteProvider 抽象，kline 数据用 yfinance 做 fallback | — | ⬜ 未开始 |

## Phase 2：Dashboard 增强

目标：Dashboard 成为完整的监控+控制面板

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 2.1 | 展示 Engine 运行结果 | /api/engine 端点：最近信号、风控决策、执行状态 | ⬜ 未开始 |
| 2.2 | 风控参数在线调整 | 暴露上限、止损比例等参数可从 web UI 修改 | ⬜ 未开始 |
| 2.3 | 系统开关控制 | /api/control/lock, /api/control/unlock | ⬜ 未开始 |
| 2.4 | 行情刷新频率调整 | 前端可修改 DataCache 的 refresh_interval | ⬜ 未开始 |
| 2.5 | 审计日志查看 | /api/audit 端点，展示最近 N 条审计记录 | ⬜ 未开始 |
| 2.6 | Engine 状态健康检查 | engine 的 last_heartbeat, consecutive_failures 等 | ⬜ 未开始 |
| 2.7 | Tiger 配置文件上传入口 | 支持 paper/live 配置切换 | ⬜ 未开始 |
| 2.8 | Paper/Live 模式自动检测 | 从配置文件读取 env 字段，自动适配 API 端点差异 | ⬜ 未开始 |

## Phase 3：Agent 体系搭建

目标：建立完整的 Agent 协作体系

| # | Agent | 模型 | 任务 | 调度方式 | 状态 |
|---|-------|------|------|----------|------|
| 3.1 | tiger-watcher | mimo-v2-pro | 系统健康监控：engine 心跳、Docker 状态、API 权限 | 每 15min 定时 | ⬜ 未开始 |
| 3.2 | tiger-newswire | 中等模型 | 新闻/催化扫描，输出结构化情报 | HK/US 盘前 + 盘中 15min | ⬜ 未开始 |
| 3.3 | tiger-strategist | 较强模型 | 基于信号+新闻+宏观产生交易建议 | 信号触发或定时 | ⬜ 未开始 |
| 3.4 | tiger-executor | mimo-v2-pro | 执行检查单：参数校验、preview 确认 | 策略完成后触发 | ⬜ 未开始 |
| 3.5 | tiger-scout | 中等模型 | 候选标的扫描、异常波动检测 | 按需或定时 | ⬜ 未开始 |
| 3.6 | tiger-closer | 中等模型 | 收盘总结：行情+新闻+执行+次日关注 | 每市场收盘后 | ⬜ 未开始 |

## Phase 4：自动化调度

目标：Engine + Agent 全自动运转

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 4.1 | Engine cron 调度 | 每 30min 自动跑 `run_dry_run_cycle` → 输出信号文件 | ⬜ 未开始 |
| 4.2 | Agent 定时任务 | OpenClaw cron 配置各 agent 的触发时间 | ⬜ 未开始 |
| 4.3 | 信号触发链 | Engine 输出信号 → yuuka 读取 → 决定是否激活 strategist | ⬜ 未开始 |
| 4.4 | A2A 通知链 | 交易发生 → yuuka → Telegram 通知 | ⬜ 未开始 |
| 4.5 | 异常恢复 | Engine 异常 → watcher 检测 → yuuka 处理 | ⬜ 未开始 |
| 4.6 | Dashboard 记录 | 所有事件写入 dashboard 日志 | ⬜ 未开始 |

## Phase 5：Live 交易过渡

| # | 任务 | 说明 | 状态 |
|---|------|------|------|
| 5.1 | Paper/Live 配置差异适配 | API 端点、下单参数、权限差异处理 | ⬜ 未开始 |
| 5.2 | Live 安全机制 | 更严格的 preview、人工确认、限速 | ⬜ 未开始 |
| 5.3 | Dashboard live 模式切换 | UI 明确区分 paper/live 状态 | ⬜ 未开始 |

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
