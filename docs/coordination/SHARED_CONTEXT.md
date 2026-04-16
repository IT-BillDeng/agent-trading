# Shared Context

统一共享上下文文件：`market_context.json`

## 用途

给以下岗位共享同一份市场上下文：
- watcher
- newswire
- strategist
- closer

## 字段约定

### market_snapshot
- 按市场记录当前 session / tradeable / summary

### watcher_observation
- watcher 本轮观察摘要
- focus_symbols 填本轮重点盯盘标的

### newswire_summary
- newswire 新闻摘要
- sentiment 可填: bullish / neutral / bearish
- focus_symbols 填新闻影响较大的标的

### strategy_inputs
- 给 strategist 的统一附加输入
- bias 可填: risk_on / neutral / risk_off
- allowed_markets 与统一 gate 保持一致
- notes 放补充说明

## 读写原则

1. watcher 写 watcher_observation + 可更新 market_snapshot
2. newswire 写 newswire_summary
3. strategist 读取全部字段，不覆盖 newswire/watcher 内容
4. closer 只读并汇总，不回写策略结论
5. 不在这个文件里放订单、成交、资产快照；这些继续走 `logs/`、`artifacts/`、`runtime/state/` 与 `runtime/outbox/`

## 更新时间

每次更新都应同时写：
- updated_at
- updated_by
