# Tiger 模拟盘全自动交易系统需求规格 v1（30min）

## 1. 目标

构建一套基于 **Tiger Open Platform 模拟盘** 的美股自动交易系统 v1。

设计原则：
- 低频优先：按 `30min` 级别运行
- 风控优先：先限制风险，再考虑收益
- 可审计：每次评估、下单、异常都留痕
- 可回滚：异常即停机，不做隐式恢复
- 先模拟盘验证，不直接面向实盘

---

## 2. 已确认边界

### 2.1 账户与市场
- 环境：Tiger 模拟盘
- 市场：美股
- 账户：PAPER account
- 数据面：Tiger 延迟行情 + Tiger 交易接口
- 执行面：Tiger Open API
- 当前已确认：
  - US `quote_delay` 可用

### 2.2 允许与禁止
- 允许：自动下单
- 禁止：做空
- 禁止：杠杆
- 禁止：期权
- 禁止：盘前/盘后交易

### 2.3 订单类型白名单
- 市价单 `MKT`
- 限价单 `LMT`
- 止损单 `STP`
- 止损限价单 `STP_LMT`

### 2.4 风控硬约束
- 单笔最大金额：`10,000 USD`
- 单日最大亏损阈值：`5%`
- 最大持仓上限：`10,000 USD`
- 异常处理：触发异常即停止交易

### 2.5 标的白名单
#### 美股
- AAPL
- MSFT
- NVDA
- AMZN
- SMCI（Super Micro Computer）
- GOOGL（Alphabet Class A / Google）

---

## 3. v1 频率与运行方式

### 3.1 运行频率
- 主评估周期：每 `30min` 执行一次
- 建议评估时点按**各市场常规时段**对齐

#### 美股（America/New_York）
- 10:00
- 10:30
- 11:00
- 11:30
- 12:00
- 12:30
- 13:00
- 13:30
- 14:00
- 14:30
- 15:00
- 15:30

### 3.2 不在以下时间执行新开仓
- 美股 09:30–10:00
- 常规时段结束前最后 15 分钟
- 非常规时段

### 3.3 运行模式
- 常驻进程 + 定时调度
- 每个周期执行：
  1. 拉账户状态
  2. 拉持仓/订单
  3. 拉白名单标的行情
  4. 计算信号
  5. 做风控校验
  6. 生成订单
  7. 提交下单
  8. 发送通知
  9. 记录审计日志

---

## 4. 策略方案（v1 保守版）

## 4.1 定位
采用 **30min 趋势跟随/强弱筛选** 的保守方案。

目标：
- 利用大盘中较平滑的方向信号
- 避免依赖逐笔和高频盘口
- 适配延迟行情

## 4.2 v1 候选策略骨架
对每个白名单标的，在每个 30min 周期计算：
- 近若干根 30min bar 的价格趋势
- 短中期均线关系
- 当日相对强度
- 波动率过滤

> v1 实现建议：以 `KLINE 30min` 历史数据作为主输入；可附加 `quote_delay` 作为诊断。

### 入场参考条件（示意）
满足以下多数条件才允许开仓：
- 当前价格高于短期均线
- 短期均线高于中期均线
- 最近若干根 30min bar 未出现明显转弱
- 当日涨跌幅未过度扩张
- 当前无持仓、无冲突订单

### 出场参考条件（示意）
出现以下任一条件可触发平仓：
- 趋势转弱
- 触发止损
- 触发止盈
- 收盘前强制平仓（可配置）
- 风控熔断触发

> 注：v1 先采用规则型策略，不引入复杂机器学习决策。

---

## 5. 仓位与风险管理

## 5.1 仓位规则
- 单笔下单金额不得超过 `10,000 USD` 等值
- 不允许超过账户可用资金与购买力约束
- 单标的默认同时仅允许一个方向持仓
- 若已有持仓，默认不重复加仓
- 美股下单以股为单位（无 lot size 约束）

## 5.2 单日亏损控制
- 基准：账户当日净值变化
- 当日亏损达到 `5%` 时：
  - 立即停止新开仓
  - 取消待成交开仓单
  - 发送熔断通知
  - 系统进入 `STOPPED` 状态

## 5.3 异常停止条件
以下任一情况触发停机：
- API 返回异常或持续超时
- 账户读取失败
- 行情读取失败达到阈值
- 下单返回不一致
- 订单状态异常
- 配置缺失或关键字段非法
- 风控模块校验失败

## 5.4 异常恢复策略
- v1 默认 **不自动恢复**
- 异常停机后需人工确认再恢复

---

## 6. 订单执行规则

## 6.1 下单前校验
每次提交订单前必须校验：
- 标的在白名单内
- 当前时段允许交易
- 订单类型在白名单内
- 单笔金额不超过 10,000 USD
- 未触发单日亏损熔断
- 无同标的冲突订单
- 无重复提交风险

## 6.2 幂等与去重
- 每笔意图生成 `idempotency_key`
- key 可由以下字段组成：
  - trade_date
  - symbol
  - side
  - strategy_signal_id
  - cycle_timestamp
- 同一 key 不允许重复下单

## 6.3 v1 默认执行建议
- 入场默认优先：`LMT`
- 快速确认成交场景可选：`MKT`
- 风控离场：`STP` 或 `STP_LMT`

## 6.4 订单状态处理
系统应跟踪：
- Submitted
- PartiallyFilled
- Filled
- Cancelled
- Rejected
- Inactive

若订单长时间未成交：
- 可按配置撤单
- 不做无限重试

---

## 7. 系统模块划分

## 7.1 MarketData 模块
职责：
- 拉取延迟行情
- 标准化白名单标的数据
- 生成 30min 周期输入

输入：
- 白名单 symbol 列表

输出：
- 标准化行情快照
- 周期特征数据

## 7.2 Strategy 模块
职责：
- 基于 30min 数据计算入场/出场信号
- 输出结构化交易意图

输出示例：
- symbol
- action
- score
- reason
- suggested_order_type
- stop_loss
- take_profit

## 7.3 RiskManager 模块
职责：
- 校验交易意图是否合法
- 执行账户级与策略级风控
- 判断是否允许下单

## 7.4 Execution 模块
职责：
- 生成标准订单参数
- 提交 Tiger API
- 跟踪订单状态
- 处理撤单与异常

## 7.5 Portfolio 模块
职责：
- 维护账户、持仓、订单快照
- 提供风险计算依据

## 7.6 Notifier 模块
职责：
- 通过 Telegram 发送状态消息

通知事件：
- 系统启动
- 系统停止
- 下单成功
- 下单失败
- 风控拦截
- 异常熔断
- 每日总结

## 7.7 AuditLogger 模块
职责：
- 落盘所有关键操作日志
- 供复盘与排障使用

---

## 8. Telegram 通知规范

每条通知建议包含：
- 时间
- 账户环境（PAPER）
- 标的
- 动作
- 原因
- 金额/数量
- 结果

### 示例事件
#### 下单成功
- `[PAPER] BUY AAPL`
- 周期：2026-03-11 10:30 ET
- 订单：LMT
- 数量：xx
- 价格：xx
- 原因：trend_follow_30m

#### 风控拦截
- `[BLOCKED] NVDA`
- 原因：daily_loss_limit_reached

#### 异常熔断
- `[STOPPED] Tiger trading halted`
- 原因：api_response_inconsistent

---

## 9. 日志与审计要求

至少记录以下字段：
- timestamp
- cycle_time
- symbol
- signal_id
- signal_reason
- account_snapshot
- position_snapshot
- order_payload
- api_response
- risk_check_result
- final_action
- error_message

日志建议拆分：
- `runtime.log`
- `signals.log`
- `orders.log`
- `risk.log`
- `exceptions.log`

---

## 10. 状态机

系统状态：
- `IDLE`
- `RUNNING`
- `BLOCKED`
- `STOPPED`
- `ERROR`

状态流转：
- 启动后进入 `RUNNING`
- 风控拦截保留 `RUNNING`，但跳过本次下单
- 遇到异常进入 `STOPPED` 或 `ERROR`
- 人工确认后恢复为 `RUNNING`

---

## 11. 配置项建议

```yaml
mode: paper
markets: [US]
strategy:
  timeframe: 30min
  symbols:
    - { symbol: AAPL, market: US }
    - { symbol: MSFT, market: US }
    - { symbol: NVDA, market: US }
    - { symbol: AMZN, market: US }
  sessions:
    US: { entry_window_start: "10:00", entry_window_end: "15:15" }
  force_flat_before_close: true
risk:
  max_order_notional_usd: 10000
  daily_loss_limit_pct: 5
  max_total_exposure_usd: 1000000
  allow_short: false
  allow_margin: false
  allow_options: false
execution:
  allowed_order_types: [MKT, LMT, STP, STP_LMT]
  tif: DAY
  allow_prepost: false
  dedupe: true
notify:
  telegram: true
  ntfy: false
system:
  stop_on_exception: true
  auto_resume: false
```

---

## 12. v1 暂不包含

以下内容明确不进入 v1：
- 5min / 1min 高频策略
- 盘前/盘后交易
- 做空
- 杠杆
- 期权
- 复杂算法单
- 自动恢复机制
- 多市场扩展
- 自适应参数优化

---

## 13. 上线前检查清单

### 技术检查
- Tiger API 连通性通过
- 账户读取通过
- 资产/持仓/订单读取通过
- 延迟行情读取通过
- Telegram 通知通过
- 日志写入通过
- 熔断逻辑通过

### 交易检查
- 白名单配置正确
- 风控参数正确
- 模拟盘下单测试通过
- 撤单测试通过
- 重复下单防护通过

### 安全检查
- API 密钥不出现在日志
- 敏感配置仅本机可读
- 异常默认停机

---

## 14. 实施优先级

### Phase 1
- 完成配置加载
- 完成账户/持仓/订单读取
- 完成 30min 调度框架
- 完成 Telegram 通知

### Phase 2
- 完成策略模块
- 完成风险管理模块
- 完成订单执行模块
- 完成审计日志

### Phase 3
- 进行模拟盘连续观察
- 调整参数
- 评估是否升级到实时行情版本

---

## 15. 当前结论

Tiger 模拟盘自动交易系统 v1 应定位为：

> **基于延迟行情、30min 级别、风控优先的低频自动交易系统。**

在未获得 Tiger API 实时行情权限前，不应将 v1 扩展为 5min 级盘中实时策略系统。
