# TIGER_SUBAGENTS.md

`Operator` 当前可调用的 Tiger subagents：

共享股票清单：`./data/watchlist.json`
- 这是 Operator 与 Tiger subagents 的统一股票来源
- 默认优先使用这份清单，而不是各自维护独立列表

Newswire v1 信息源：`./news/newswire_sources.json`
- 主源 1：Brave Search
- 主源 2：web_fetch
- 辅助：Yahoo Finance / 其他可读页面


- `tiger-watcher`
  - 高频监控共享清单中的标的、市场状态、候选变化与异常节奏

- `tiger-newswire`
  - 收集标的/行业/宏观相关新闻、事件时间线与催化

- `tiger-strategist`
  - 负责交易思路、风险收益评估、仓位与计划建议

- `tiger-executor`
  - 把计划转成执行步骤、参数检查、preview/dispatch 校验

- `tiger-scout`
  - 扫描候选标的、异常波动、机会与待验证清单

- `tiger-closer`
  - 负责每个市场收盘后的行情/新闻/执行状态总结，以及明日关注点与收尾建议

## 使用原则

- 这些 agent 是给 `Operator` 的内部 subagent，不直接面向老师
- 默认优先输出给 `Operator`，由 `Operator` 决定如何汇总
- 默认优先读取共享股票清单：`./data/watchlist.json`
- 涉及 Python、脚本执行、真实提交、支付或其他高风险动作时，默认转交 `arona` 代执行
