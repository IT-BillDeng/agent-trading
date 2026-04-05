# TIGER Strategist Task Template

给 `tiger-strategist` 派工时，优先使用这份模板。

---

目标：基于共享股票清单与当前 Tiger Engine paper 状态，输出保守版交易计划草案。

输入：
- `./data/watchlist.json`
- `./specs/tiger-trading-spec-v1-30min.md`
- `./system/tiger_engine/app_config.paper.json`
- `./runtime/tiger_engine/.last_execution_cycle.json`

要求：
- 优先只看共享清单中 `enabled=true` 的标的
- 对 `priority=high` 的标的优先分析
- 必须遵守当前风控边界：
  - 30min
  - paper
  - guarded
  - max_total_exposure_usd = 10000
  - daily_loss_limit_pct = 5
  - 不做空 / 不杠杆 / 不期权 / 不盘前盘后

边界：
- 不直接下单
- 不运行 Python
- 不假设已经真实执行
- 不修改股票池

输出格式：
1. 一句话结论
2. 当前最值得关注的 1~2 个标的
3. 对每个标的给出：
   - 入场前提
   - 失效条件
   - 风险点
   - 仓位建议
4. 1 个下一交易时段前最该确认的事项

---

可选附加要求：
- 若共享清单中新增标的（如 SMCI / GOOGL），请单独说明是否已进入“值得重点盯”的范围
- 若当前信号过多，请明确给出“单标的优先”还是“允许分仓”建议
