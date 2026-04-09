# Tiger Newswire 输出 Schema v1

## 概述

newswire 每次运行产出 `latest.json`，追加到 `history.jsonl`。
消费方：Strategist agent、Dashboard 新闻面板。

## latest.json 结构

```json
{
  "generated_at": "ISO-8601 时间戳",
  "shift": "premarket | intraday | afterhours",
  "items": [ ... ],
  "meta": {
    "sources_used": ["web_search", "yahoo_finance", "market_overview"],
    "symbol_count": 6,
    "total_items": 12,
    "duration_ms": 45000
  }
}
```

## Item 结构

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 去重用：`{source}:{symbol}:{headline_hash}` |
| `symbol` | string | ❌ | 标的代码，宏观新闻为 null |
| `category` | enum | ✅ | `stock` / `macro` / `sector` |
| `headline` | string | ✅ | 新闻标题 |
| `summary` | string | ❌ | 一句话摘要（可选） |
| `source` | string | ✅ | 信息来源标识（reuters / bloomberg / yahoo 等） |
| `url` | string | ❌ | 原文链接 |
| `importance` | enum | ✅ | `high` / `medium` / `low` |
| `sentiment` | enum | ✅ | `positive` / `negative` / `neutral` |
| `published_at` | string | ❌ | 发布时间 ISO-8601 |
| `tags` | string[] | ❌ | 标签：`earnings` `product` `regulation` `executive` `macro` `market` `sector` 等 |

## importance 定义

| 级别 | 标准 | 示例 |
|------|------|------|
| `high` | 财报发布、重大产品、监管诉讼、异常波动(>3%)、关税/Fed 决议 | AAPL 财报超预期、NVDA 被调查 |
| `medium` | 分析师升降级、行业趋势、高管交易、大盘走势 | MSFT 目标价上调、AI 板块走强 |
| `low` | 一般评论、分析文章、回顾性报道 | 苹果50周年回顾 |

## 去重规则

- 同一 `id` 在 `dedupe_window_hours`（默认 24h）内不重复出现
- `id` 生成：`md5("{source}:{symbol}:{headline}")[:12]`
- 不同源报道同一事件：保留信息最丰富的版本（有 summary > 无 summary，有 url > 无 url）

## history.jsonl

每行一个完整 latest.json 快照，用于：
- 历史回溯
- Strategist 分析趋势
- Dashboard 历史新闻浏览

## 文件路径

```
runtime/engine/newswire/
├── latest.json       # 最新一次运行结果
├── history.jsonl     # 历史追加（每行一个快照）
└── dedupe.json       # 24h 内已发新闻 ID 池
```
