# TIGER Newswire Task Template

给 `tiger-newswire` 派工时，优先使用这份模板。

---

目标：为共享股票清单提供一轮新闻与催化扫描。

输入：
- `./data/watchlist.json`
- `./config/newswire_sources.json`
- （可选）最新 watcher / strategist 输出

信息源要求：
- 主源 1：Brave Search
- 主源 2：web_fetch
- 辅助：Yahoo Finance / 其他可读页面
- 先用搜索发现，再用抓取提炼，不要直接抄网页片段

要求：
- 优先只看共享清单中 `enabled=true` 的标的
- `priority=high` 标的优先扫描
- 信息不足时必须明确说明
- 不直接给出下单指令

边界：
- 不运行 Python
- 不对外发送消息
- 不修改股票池或配置

结构化落盘要求（MVP v1）：
- 额外写入 `./runtime/tiger_engine/newswire/latest.json`
- 额外追加 `./runtime/tiger_engine/newswire/history.jsonl`
- 若无有效新闻，也要写结构化空结果

输出格式：
1. 一句话结论
2. 1~3 条最相关新闻 / 催化
3. 最值得继续盯的 1 个标的
4. 1 个需要警惕的风险事件
5. 并写入结构化 newswire 输出

---

可选附加要求：
- 若当天有财报 / 指引 / 监管事件，优先写在第一条
- 若某标的是当前 BUY 候选，说明新闻是否支持该信号
- 若新闻数据不足，明确写“新闻信息不足，暂不下结论”
