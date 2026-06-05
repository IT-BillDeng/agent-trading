# Broker Fee Model

更新时间：2026-04-17

## 目标

让回测、strategist 评估、broker preview 预估和 adapter-reported execution 复盘使用同一套手续费语义：

- 回测：使用 broker-specific 静态费率模型
- Broker preview：使用 `preview_order`
- Adapter-reported execution review：使用 `get_order(show_charges=true)` 或成交同步结果

当前项目的最小落地优先级是：

1. 回测先从“毛收益”改成“净收益”
2. strategist 优先比较净收益、净 Sharpe 和 fee drag
3. 再逐步用本地 adapter 返回的费用数据校准模型

## 当前实现

当前最小费率模型文件：

- `config/broker_fee.tiger.json`

当前已接入：

- 回测中的 `OrderSimulator`
- Backtest 结果中的：
  - `commission_total`
  - `slippage_total`
  - `transaction_cost_total`
  - `fee_drag_pct`

## 为什么不能只用固定百分比

原来的占位模型：

- `commission_rate = 0.001`
- `slippage_rate = 0.001`

问题在于 broker 费用结构并不是简单的统一百分比，而是：

- 有 per-share 收费
- 有 per-order 最低收费
- 有卖出侧才收的监管费用
- 有平台费、结算费、第三方费用
- 不同市场规则不同

所以对：

- 高频策略
- 低价股
- 小额交易
- 卖出频繁策略

如果不纳入真实得多的费用模型，会系统性高估策略效果。

## Tiger 当前最小模型（US Stocks & ETFs）

当前最小模型只覆盖：

- `broker = tiger`
- `market = US`
- `product = stocks_etf`

字段包括：

- `commission_per_share`
- `commission_min`
- `platform_per_share`
- `platform_min`
- `platform_max_pct_trade_value`
- `settlement_per_share`
- `settlement_max_pct_trade_value`
- `sec_sell_rate`
- `sec_sell_min`
- `taf_sell_per_share`
- `taf_sell_min`
- `taf_sell_max`

说明：

- `BUY`：佣金 + 平台费 + 结算费
- `SELL`：在上面基础上再加 SEC / TAF

这还是一个“最小可用模型”，不是完整全球费率引擎。

## 与运行时 API 的关系

### 回测 / strategist

使用静态文件：

- `config/broker_fee.tiger.json`

优点：

- 稳定
- 可复现
- 适合大规模历史回测

### Broker preview

优先用 broker API：

- `preview_order`

目的：

- 获取订单级预估费用
- 判断候选订单在当前 broker 下的大致净成本

### Adapter-reported execution review

优先用 broker API：

- `get_order(show_charges=true)`

或：

- 成交同步时的实际费用字段

目的：

- 获取真实费用
- 用于校准回测模型
- 统计 `estimated vs actual`

## strategist 应该看哪些指标

不应只看：

- `return_pct`
- `sharpe`

应优先看：

- `total_return_pct`（净收益）
- `sharpe_ratio`
- `max_drawdown_pct`
- `win_rate`
- `commission_total`
- `transaction_cost_total`
- `fee_drag_pct`

## 迭代路线

### Phase A

- 已完成 Tiger US minimal model
- strategist 文档改成净收益优先

### Phase B

- 把 batch backtest 返回里稳定暴露 cost fields
- dashboard / strategy 页面显示 `fee_drag_pct`

### Phase C

- 增加更多市场：
  - HK
  - SG
  - AU
- 增加不同产品：
  - options
  - fractional shares

### Phase D

- 用本地 adapter 返回的费用数据校准静态模型
- 输出 `estimated_cost_error`
- 把“费用偏差”也纳入 strategist 记忆

## 校准产物

当前本地费用校准记录会写到：

- `artifacts/broker/fee_calibration.jsonl`
- `artifacts/broker/fee_calibration_summary.json`

每条记录至少包含：

- `broker_platform`
- `market`
- `symbol`
- `side`
- `price`
- `quantity`
- `estimated_total`
- `actual_total`
- `delta`

这份文件的作用是：

- 对比静态 fee model 与 broker 实际 charges
- 识别哪些市场 / 产品 / 价格带偏差最大
- 后续更新 `config/broker_fee.*.json` 时提供依据

其中 `fee_calibration_summary.json` 适合：

- strategist 盘后快速读取
- dashboard / strategy 页面直接展示
- 主 agent 判断当前净收益模型是否仍可信

## Fee Confidence Gate

当 `artifacts/broker/fee_calibration_summary.json` 存在时，审批与应用链应读取其中的 `trust`，
并归一化为：

- `high`
- `medium`（来自 `observe`）
- `low`
- `missing`

建议 gate：

- `high`：允许正常 hot / cold apply
- `medium`：允许低换手策略调参；不允许新增高换手 BUY 规则
- `low / missing`：不允许启用新 BUY 规则；只允许 `paper_shadow`、禁用规则、降低频率、降低仓位、收紧过滤器等降风险变更

deployment record 应写入当时的 `fee_confidence_snapshot`，便于事后审计：

- `confidence`
- `label`
- `reason`
- `count`
- `avg_delta`
- `max_abs_delta`
