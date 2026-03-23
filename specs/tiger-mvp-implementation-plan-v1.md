# Tiger MVP Implementation Plan v1

> 范围：watcher / newswire 第一批结构化输出落地。
> 目标：在不先推倒现有 cron 的前提下，为后续 strategist / decision / executor 铺设结构化输入层。

---

## 1. 当前阶段目标

第一批只做两件事：

1. 让 watcher 输出结构化观察对象
2. 让 newswire 输出结构化情报对象

当前阶段暂不做：
- strategist 信号落地
- decision 事件链落地
- executor 触发重构
- old execution cron 退役

---

## 2. 运行目录骨架

建议立即建立：

```text
runtime/tiger_engine/
  watcher/
    latest.json
    history.jsonl
  newswire/
    latest.json
    history.jsonl
```

---

## 3. watcher MVP

### 输入保持不变
- shared watchlist
- .last_execution_cycle.json
- execution.jsonl
- dispatch_queue.jsonl
- control_state.json

### 新增输出
- `runtime/tiger_engine/watcher/latest.json`
- `runtime/tiger_engine/watcher/history.jsonl`

### 最小必填字段
- `watch_id`
- `generated_at`
- `market_session`
- `window`
- `symbols`
- `summary`

### 当前自然语言输出继续保留
用于：
- 人类阅读
- 临时过渡

---

## 4. newswire MVP

### 输入保持不变
- shared watchlist
- newswire source config
- brief / template

### 新增输出
- `runtime/tiger_engine/newswire/latest.json`
- `runtime/tiger_engine/newswire/history.jsonl`

### 最小必填字段
- `news_batch_id`
- `generated_at`
- `window`
- `items`
- `summary`

### 每条 item 最小字段
- `news_id`
- `symbol`
- `headline`
- `source`
- `published_at`
- `priority`
- `dedupe_key`

### 当前自然语言输出继续保留
用于：
- 人类阅读
- 临时过渡

---

## 5. 实施顺序

### Phase 1
- 更新 watcher / newswire brief 与 task template
- 明确结构化落盘要求

### Phase 2
- 建立 runtime 目录骨架
- 放置空的 latest/history 文件或由首轮任务自动创建

### Phase 3
- 调整 watcher / newswire 执行提示词，使其在每轮输出后写文件

### Phase 4
- 验证结构化输出是否稳定
- 再继续进入 strategist 接线

---

## 6. 成功标准

当以下条件同时满足时，视为第一批落地成功：

1. watcher 每轮能稳定写 `latest.json`
2. watcher 每轮能稳定追加 `history.jsonl`
3. newswire 每轮能稳定写 `latest.json`
4. newswire 每轮能稳定追加 `history.jsonl`
5. 即使无结果，也会写结构化空对象
6. 原有自然语言输出仍然保留

---

## 7. 一句话总结

**Tiger MVP 第一批的本质，不是重写 watcher/newswire 的逻辑，而是先让它们从“只会说话的岗位”升级成“会产结构化对象的岗位”。**
