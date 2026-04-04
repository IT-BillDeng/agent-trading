# TIGER Executor Task Template

给 `tiger-executor` 派工时，优先使用这份模板。

---

目标：审查当前 Tiger paper 执行链的准备度，并把计划转成最短执行检查单。

输入：
- `./shared/tiger_shared_watchlist.json`
- `./system/tiger_engine/README.md`
- `./system/tiger_engine/app_config.paper.json`
- `./runtime/tiger_engine/.last_execution_cycle.json`
- `./runtime/tiger_engine/logs/execution.jsonl`
- `./runtime/tiger_engine/logs/dispatch_queue.jsonl`
- `./runtime/tiger_engine/state/control_state.json`

要求：
- 优先只看共享清单中 `enabled=true` 的标的
- 检查当前执行链是否与共享清单一致
- 重点检查：
  - preview_check
  - guarded/live mode
  - control.locked
  - notification_dispatch
  - risk.preview_blockers
  - 最大总暴露与单笔上限是否一致

边界：
- 只读
- 不运行 Python
- 不对外发送消息
- 不真实提交订单
- 不修改股票池或配置

输出格式：
1. 一句话结论
2. 3 个已就绪项
3. 3 个剩余风险 / 缺口
4. 1 份最短执行检查单（5 条内）

---

可选附加要求：
- 如果共享清单与 `.last_execution_cycle.json` 中的标的不一致，必须明确指出
- 如果发现执行链已具备 paper guarded 观察条件，请明确说明“可以继续 guarded 观察”
- 如果发现任何会导致误下单或漏通知的点，请把它放在第一优先级
