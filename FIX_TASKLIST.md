# Agent Trading 修复任务清单

更新时间：2026-04-16

## 目标

对 `agent-trading` 项目进行分阶段修复与改进，优先解决数据口径、关键功能 bug、目录漂移与可维护性问题。

## 当前状态

- `Phase 1` 已完成
- `Phase 2` 进行中
  - `2.1` 已修复 `/api/backtest/batch` 参数覆盖 `enabled` 开关失效问题
  - `2.2` 已完成 Tiger 首页口径切换、ET 当日边界修正、缓存刷新阻塞修复
- `Phase 3-5` 尚未正式展开

---

## Phase 1，数据口径与可观测性

### 1.1 统一盈亏口径
- [x] 梳理 Tiger API 各字段真实语义
  - `account.realized_pnl`
  - `account.unrealized_pnl`
  - `position.today_pnl`
  - `position.unrealized_pnl`
  - `filled_order.realized_pnl`
- [x] 输出一份项目内统一口径表
- [x] 明确 Dashboard 中以下概念：
  - 今日盈亏
  - 今日已实现盈亏
  - 今日未实现盈亏
  - 累计已实现盈亏
  - 当前未实现盈亏

### 1.2 修正 Dashboard 盈亏相关显示
- [x] 修正 `/api/pnl` 字段定义与返回结构
- [x] 修正“今日盈亏”顶部卡片显示逻辑
- [x] 修正“盈亏明细”block，明确展示：
  - symbol
  - status(open/closed)
  - unrealized_pnl
  - realized_pnl
  - today_pnl
- [x] 移除或重命名容易混淆的文案（如“总浮动”）
- [x] 确认前端显示与 API 字段一一对应

### 1.3 增强可观测性
- [x] 为 `/api/pnl` 增加调试字段开关或调试端点
- [x] 为关键 API 增加原始来源说明
- [x] 增加 PnL 计算链路的最小测试样例

---

## Phase 2，关键功能 bug 修复

### 2.1 回测批量 API 异常
- [x] 排查 `/api/backtest/batch` 参数变化结果相同问题
- [x] 验证参数覆盖是否真正写入临时规则文件
- [x] 验证回测引擎是否实际读取临时规则文件
- [x] 为 batch backtest 增加最小可复现测试
- [ ] 修复 Strategist 被阻塞的问题

### 2.2 Dashboard 数据链稳定性
- [x] 检查 `data_cache.py` 中业务逻辑是否正确
- [x] 检查 `tiger_client.py` 各接口字段提取是否完整
- [x] 检查 filled orders / orders / positions 的时间窗口是否一致
- [x] 检查缓存刷新与页面渲染之间的数据一致性

### 2.3 cron / agent 运行一致性
- [x] 排查所有 cron 配置中的旧路径残留
- [ ] 排查 agent 文档与真实工作目录是否一致
- [ ] 确认 watcher / strategist / closer / newswire 读取的是统一 runtime 路径

---

## Phase 3，目录与运行产物整理

### 3.1 统一 runtime 目录
- [ ] 梳理以下目录的职责边界：
  - `runtime/engine/`
  - `runtime/state/`
  - `runtime/outbox/`
  - `system/engine/`
- [ ] 明确根目录 `logs/` 作为统一观测入口，并迁移可巡检日志/历史产物
- [ ] 消除重复运行产物路径
- [ ] 确认 `.last_execution_cycle.json` 单一来源
- [ ] 确认状态文件、日志文件、outbox 文件的统一落点

### 3.2 清理命名漂移
- [ ] 全量排查 `tiger-trading` 残留引用
- [ ] 全量排查旧 engine/tiger_engine 命名残留
- [ ] 更新 docs / cron / agents / memory 中的过期路径说明

---

## Phase 4，代码结构优化

### 4.1 Dashboard 后端拆分
- [ ] 拆分 `dashboard/main.py`
  - account / pnl API
  - rules API
  - backtest API
  - control API
  - logs API
  - news API
- [ ] 抽离 PnL 聚合逻辑到独立模块
- [ ] 抽离 Tiger 数据适配逻辑到更清晰的 service 层

### 4.2 Dashboard 前端拆分
- [ ] 拆分 `dashboard/static/index.html`
- [ ] 抽离：
  - API 调用层
  - 状态管理层
  - 渲染层
- [ ] 为关键 block 建立独立渲染函数和字段约定

### 4.3 Engine 结构整理
- [ ] 检查 `runtime.py` 职责是否过重
- [ ] 梳理 strategy / rule_engine / execution / risk 的边界
- [ ] 为关键执行路径补最小测试

---

## Phase 5，文档同步

### 5.1 项目文档修正
- [ ] 更新 `README.md` 使其与真实目录一致
- [ ] 更新 `dashboard/README.md`
- [ ] 更新 `system/engine/README.md`
- [ ] 增加一份“当前真实运行架构图”文档

### 5.2 运维与协作文档
- [ ] 更新 cron 配置文档
- [ ] 更新岗位职责文档
- [ ] 增加“调试入口索引”文档

---

## 建议优先级

### P0，立即处理
1. 盈亏口径统一
2. Dashboard 盈亏显示修复
3. `/api/backtest/batch` 参数失效问题

### P1，短期处理
4. runtime 目录统一
5. cron 路径与产物路径统一
6. Dashboard 数据链稳定性修复

### P2，中期处理
7. `main.py` / `index.html` 拆分
8. 文档与目录结构同步
9. 测试补齐

---

## 当前建议执行顺序

1. 已完成 **Phase 1**
2. 当前优先处理 **Phase 2.1 backtest batch**
3. 然后做 **Phase 2.3 / Phase 3 目录与运行产物统一**
4. 最后推进 **Phase 4-5 结构优化与文档同步**

---

## 备注

这份清单先作为总控文档。后续可以继续拆成：
- `docs/fixes/pnl-fix-plan.md`
- `docs/fixes/backtest-batch-fix-plan.md`
- `docs/fixes/runtime-layout-fix-plan.md`

便于逐项执行与验收。
