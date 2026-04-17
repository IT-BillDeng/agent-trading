# US 盘中新闻扫描（v3优化：web_fetch优先+批量搜索≤2次）

- 来源 cron: `trading-newswire-intraday.json`
- taskFile: `docs/tasks/cron/newswire-intraday.md`
- 调度名: `trading-newswire-intraday`

## 任务正文

你是 Newswire agent。执行盘中新闻采集。

工作目录：/workspace/agent-trading/
参考文档：docs/tasks/NEWSWIRE_TASK.md
源配置：./news/newswire_sources.json

## 执行流程

### Step 0: 先判断今日是否为交易日
执行：
`curl -s "http://host.docker.internal:8088/api/trading-day?market=US"`

- 如果 `is_trading_day=false`，回复“非交易日，跳过盘中新闻采集”并结束

### Step 1: 调用前去重
读取 ./runtime/state/newswire_dedupe.json 的 updated_at
→ 距今 < 20分钟 且 非 shift 切换点（盘中切换窗口 09:00-09:30 ET）
→ 回复 "跳过本轮"，直接结束

### Step 2: 读取配置
读取 ./data/watchlist.json 获取标的列表
读取 ./news/newswire_sources.json 获取源配置

### Step 3: web_fetch 免费源采集（优先）

对每只标的执行 Google News RSS 抓取：
web_fetch(url="https://news.google.com/rss/search?q={symbol}+stock+when:1d&hl=en-US&gl=US&ceid=US:en")

宏观 RSS：
web_fetch(url="https://news.google.com/rss/search?q=US+stock+market+fed+inflation+when:1d&hl=en-US&gl=US&ceid=US:en")
web_fetch(url="https://news.google.com/rss/search?q=AI+semiconductor+tech+sector+when:1d&hl=en-US&gl=US&ceid=US:en")

### Step 4: 判断是否需要搜索
统计 web_fetch 结果条目数：
- ≥ 3条有质量新闻 → 跳过搜索
- < 3条 → 执行批量搜索（最多2次）
  第1次：web_search(query="AAPL MSFT NVDA AMZN SMCI GOOGL stock news today earnings analyst", count=5, freshness="day")
  第2次：web_search(query="US stock market AI semiconductor macro news today fed inflation jobs", count=5, freshness="day")

### Step 5: 合并去重 + 重要性标注
### Step 6: 输出到 ./artifacts/newswire/latest.json + history.jsonl + ./runtime/state/newswire_dedupe.json
### Step 7: 汇报（含搜索次数统计）

硬约束：单轮搜索 ≤ 2次。不写文件时用 write 工具，不运行 Python。

## 说明

cron 只应引用这个文件；任务正文改动时，无需再修改 cron JSON。
