# agent-trading

agent-trading 自动化交易项目工作区。当前核心引擎已统一命名为 **engine**，用于承载 paper trading 执行链、观察岗位、总结岗位与后续更高频/多周期扩展。

---

## 1. 项目目标

当前项目目标：

- 建立一个可持续演进的自动化交易工程骨架
- 支持 paper trading 的策略执行、风控、状态记录、通知与汇报
- 通过 cron + 岗位化 agent 协作，完成盯盘、情报、总结、播报等任务
- 避免工程命名被单一频率绑定，为未来 `5m / 15m / 30m / multi-timeframe` 预留空间

当前默认仍以 **paper + guarded** 模式运行，不直接进入 live。

---

## 2. 当前目录结构

```text
agent-trading/
  README.md
  .gitignore
  data/
  config/
    app.defaults.json
    app_config.docker.json
    user.settings.example.json
  .env.example
  docs/
    roles/
    tasks/
    coordination/
  news/
    newswire_sources.json
  properties/
  specs/
    agent-trading-spec-v1-30min.md
  system/
    engine/
      README.md
      run_strategy_cycle.py
      run_dry_run_cycle.py
      run_readonly_cycle.py
      run_execution_cycle.py
      src/
        engine/
      logs/
      state/
  runtime/
    engine/
```

说明：

- `docs/`：岗位说明、任务模板、协作说明
- `docs/git-version-management.md`：仓库提交、忽略策略、tag 与分支约定
- `data/`：本地用户状态、种子配置与少量实验产物
- `config/`：项目默认配置、Docker 覆盖与本地用户设置示例
- `.env`：本地运行变量，不进 git
- `news/`：新闻源配置
- `specs/`：规格文档与设计草案
- `system/engine/`：核心执行引擎代码
- `runtime/engine/`：运行时产物、状态、日志

说明：

- `config/` 是当前推荐的配置分层入口
- 根目录 `.env` 是本地覆盖；`.env.example` 是可提交样板
- `system/engine/app_config.paper.json` 与 `system/engine/config.example.json` 仅保留兼容用途，不建议新流程继续引用

---

## 3. 岗位分工

当前协作模式不是“常驻多 agent 实时互聊”，而是：

> **Operator 定规则与调度，cron 定时触发岗位，岗位通过共享文件和运行产物完成交接。**

### Operator

职责：
- 总协调 / 改配置 / 调 cron / 风险把关 / 对用户汇报
- 负责整理工程结构、统一命名、决定演进方向
- 也承担部分执行链与汇报类任务

### watcher

职责：
- 高频只读监控行情与信号变化
- 读取最近执行结果与状态文件
- 产出观察结论与下一步建议

### newswire

职责：
- 在 HK / US 开盘前与 US 盘中做新闻与催化扫描
- 主源：Brave Search + web_fetch
- 辅助：Yahoo Finance / 其他可读页面

### closer

职责：
- HK / US 收盘后生成收盘总结
- 汇总行情、新闻、执行与风控摘要

### Operator 的 execution / portfolio-report 任务

职责：
- 定时运行 `engine` 执行周期
- 生成盘中/盘后持仓与盈亏播报

---

## 4. 数据如何交接

当前数据交接主要靠 4 类文件：

### 4.1 共享输入

- `data/watchlist.json`
  - 共享股票池
  - 各岗位优先读取

- `config/app.defaults.json`
  - 项目默认策略/风控/通知配置

- `config/app_config.docker.json`
  - Docker/容器环境覆盖入口

- `config/user.settings.json`
  - 本地用户设置
  - 不进 git，由运行时或用户本地生成

- `runtime/engine/market_context.json`
  - 共享市场上下文

- `news/newswire_sources.json`
  - newswire 的信息源配置

### 4.2 岗位说明 / SOP

- `docs/roles/*.md`
- `docs/tasks/*.md`
- `docs/coordination/*.md`

作用：
- 定义每个岗位的职责、输入、边界、输出格式

### 4.3 运行产物

主要在：
- `runtime/engine/`

关键文件包括：

- `.last_execution_cycle.json`
  - 最近一轮执行摘要
- `logs/cycles.jsonl`
  - 周期级汇总
- `logs/execution.jsonl`
  - 执行链、订单、同步日志
- `logs/dispatch_queue.jsonl`
  - 待发送通知队列
- `logs/notifications.jsonl`
  - 通知相关日志
- `state/control_state.json`
  - 锁定/解锁状态
- `state/execution_state.json`
  - 执行状态与相关结构化数据

### 4.4 核心代码层

- `system/engine/run_*_cycle.py`
- `system/engine/src/engine/*`

作用：
- 负责读取配置、生成信号、执行风控、维护状态、输出日志

---

## 5. 当前触发方式

### 5.1 手动触发

由用户直接在对话中要求 Operator：
- 改规则
- 调 cron
- 整理项目
- 解释结果
- 推进下一阶段架构

### 5.2 cron 定时触发

当前主要依赖 OpenClaw cron 触发各岗位：

- `paper-execution`
- `watcher-market-watch`
- `newswire-*`
- `closer-*`
- `portfolio-report-*`

本质是：

> **到点触发 → 读取固定输入 → 完成本轮任务 → 输出到文件或直接发消息。**

---

## 6. 当前运行链路

可以简化理解为：

```text
data/*.json + docs/*.md
        ↓
Engine 执行周期 / watcher / newswire / closer
        ↓
runtime/engine/*.json / *.jsonl
        ↓
Operator / closer / portfolio-report 消费结果
        ↓
给用户汇报 / 留下下一轮可读状态
```

更具体一点：

```text
watchlist / market_context / sources
        ↓
run_strategy_cycle / run_dry_run_cycle / run_execution_cycle
        ↓
.last_execution_cycle.json + execution.jsonl + state/*.json
        ↓
watcher / closer / portfolio-report / Operator
        ↓
Telegram 汇报 / 下一轮继续读取
```

---

## 7. 当前设计特点

### 优点

- 可追踪：JSON / JSONL 日志天然可审计
- 低耦合：岗位之间不要求实时内存通信
- 易回滚：工程改动可通过 Git 和 cron patch 回退
- 易扩展：已经解除 `30m` 命名绑定，适合后续提频

### 限制

- 目前不是实时事件总线
- 岗位之间以“文件中转”为主，存在轮次延迟
- 若未来频率进一步提升，可能需要引入更明确的事件队列 / outbox / inbox 机制

---

## 8. 后续建议演进方向

### Phase A：稳态优化

- 持续清理与统一文档
- 补更清晰的配置说明
- 强化验收脚本与只读健康检查

### Phase B：频率解绑后的结构升级

从“单周期工程”过渡到“多周期工程”，例如：

```text
system/engine/
  strategies/
    m5/
    m15/
    m30/
    multi_timeframe/
  execution/
  risk/
  data/
  adapters/
```

### Phase C：事件化

如果未来频率更高，可逐步引入：
- outbox / inbox 机制
- 更清晰的 task/result schema
- 更标准化的 state model

---

## 9. 当前命名约定

- 仓库名：`agent-trading`
- 核心引擎：`engine`
- 运行产物：`runtime/engine`
- Python 包：`src/engine`

说明：
- 项目已移除 `30m` 作为主命名
- 这样后续提高频率或扩展到多周期时，不需要再次做大规模重命名

---

## 10. 操作原则

当前工程默认遵循以下原则：

- 先观测，再最小改动
- 先 paper / guarded，再考虑 live
- 变更尽量可回滚
- 外发与高风险动作前明确边界
- 优先使用简短、可审批、可复核的命令与流程

---

## 11. 一句话总结

**这是一个以 `engine` 为核心、用 cron 触发岗位协作、通过本地状态文件与运行日志交接数据的自动化交易工程。**
