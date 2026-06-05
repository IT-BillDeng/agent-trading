# Artifacts

更新时间：2026-04-17

`artifacts/` 用来放 agent 产出的业务结果、学习成果和可复用历史，不放运行审计日志，也不放内部控制状态。

## 目录职责

- `artifacts/strategist/`：策略计划、学习记录、提案、回测与迭代结果
- `artifacts/newswire/`：新闻批次、历史新闻结果、对比快照
- `artifacts/watcher/`：健康检查结果、历史巡检结果
- `artifacts/executor/`：执行检查单与核验结果
- `artifacts/scout/`：候选扫描结果与历史
- `artifacts/closer/`：收盘总结与复盘产物
- `artifacts/broker/`：broker 真实费用校准、费用模型偏差记录

## 约定

- 这里放“有业务语义的输出”
- 这里不放纯 debug 日志
- 这里不放控制状态、锁定状态、冷却状态
- 这里不放待发送 outbox

## 读取建议

- Dashboard / Operator 如果要看“系统产出了什么”，优先读 `artifacts/`
- 若是要看“系统运行得怎么样”，请看 `logs/`
