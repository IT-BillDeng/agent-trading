# Dashboard Adapter / Normalizer 设计说明

更新时间：2026-04-15

## 目的

说明 `agent-trading` 当前 Dashboard 数据链路中，`raw client / normalizer / aggregator / API / frontend` 的职责边界，明确哪些逻辑现在放错层，作为后续 Phase 1 与后续结构优化的依据。

相关契约见：[broker-adapter-contract.md](./broker-adapter-contract.md)

---

## 一、当前数据链路

当前 Dashboard 的数据路径可概括为：

```text
Broker API / SDK
    ↓
dashboard/tiger_client.py
    ↓
dashboard/data_cache.py
    ↓
dashboard/normalize/tiger.py
    ↓
dashboard/main.py (/api/*)
    ↓
dashboard/static/index.html
```

其中，真正参与“口径定义”的模块主要有四层：

1. `tiger_client.py`
2. `data_cache.py`
3. `normalize/tiger.py`
4. `static/index.html`

---

## 二、理想职责边界

### 1. Raw Client（原始数据层）

对应：
- `dashboard/tiger_client.py`

应负责：
- 直接调用当前默认 API 的 SDK / API
- 提取原始对象字段
- 做最小必要的 Python 对象 → dict 转换
- 不承担复杂业务口径计算

应避免：
- 在这里定义“今日盈亏”这类业务语义
- 在这里拼接多个来源的数据
- 在这里做前端导向的展示字段设计

**原则：**
> raw client 尽量保持“接近原始返回”，但把 Python 对象整理成项目可读 dict。

---

### 2. Normalizer / Adapter（字段统一层）

对应：
- `dashboard/normalize/tiger.py`

应负责：
- 把当前默认 API 字段统一映射到 Dashboard 通用字段名
- 统一基础类型（float/int/str）
- 处理字段别名与兼容字段

应避免：
- 计算跨接口聚合值
- 推导复杂业务语义
- 引入与展示强绑定的文案逻辑

**原则：**
> normalizer 负责“字段统一”，不是“业务计算引擎”。

---

### 3. Aggregator / Service（业务聚合层）

当前对应：
- `dashboard/data_cache.py`

未来建议拆分为：
- `dashboard/services/pnl_service.py`
- `dashboard/services/portfolio_service.py`

应负责：
- 组合多个上游数据源
- 定义 Dashboard 业务口径
- 计算如：
  - 今日盈亏
  - 今日已实现
  - 今日未实现（日内浮动）
  - 盈亏明细
- 把 raw + normalized 数据整理成可供 API 直接输出的稳定结构

**原则：**
> 业务语义只在这一层定义一次，下游全部消费稳定结果。

---

### 4. API Layer（接口层）

对应：
- `dashboard/main.py`

应负责：
- 暴露稳定 API
- 不重复定义业务口径
- 不在 endpoint 内临时做复杂计算

**原则：**
> API 只是把 service 的结果交给前端，不应成为第二套业务逻辑。

---

### 5. Frontend（展示层）

对应：
- `dashboard/static/index.html`

应负责：
- 渲染固定字段
- 展示状态和文案
- 不重新计算业务含义

应避免：
- 自己推导 PnL 结构
- 猜字段语义
- 使用与后端定义不同的文案

**原则：**
> 前端只消费已经定好口径的数据，不再自行解释。

---

## 三、当前实现里的主要问题

### 问题 1：`tiger_client.py` 不够“raw”

当前 `tiger_client.py` 已经不只是原始提取，还在承担：
- 字段清洗
- 特定字段拼装
- 某些接近语义化的选择

风险：
- 上层会误以为它输出的是“稳定语义字段”
- 实际上上游字段一旦变化，影响会直接扩散

---

### 问题 2：`normalize/tiger.py` 目前只是 rename，不是真正 adapter

当前 normalizer 更多是在做：
- 字段重命名
- 简单类型转换

但没有明确承担：
- 口径声明
- 语义校验
- 兼容策略说明

风险：
- 字段名虽然统一了，但语义并未真正统一

---

### 问题 3：`data_cache.py` 同时做 cache 和业务聚合

当前 `data_cache.py` 既负责：
- 轮询
- 缓存
- 错误记录
- PnL 聚合
- details 拼接

风险：
- 缓存逻辑和业务逻辑耦合过深
- 一旦 PnL 继续复杂化，这个文件会越来越难维护

---

### 问题 4：前端曾经反向定义了口径

此前前端出现过：
- “总浮动”与“今日盈亏”并列但语义不清
- 明细只显示 `unrealized_pnl`
- 不同位置使用不同口径词汇

风险：
- 用户看到的是 UI 定义出来的语义，而不是后端稳定定义的语义

---

## 四、Phase 1 修复应遵循的落点

### A. 与当前默认 API 字段直接相关的问题
放在：
- `dashboard/tiger_client.py`
- `dashboard/normalize/tiger.py`

例如：
- 某字段没提取
- 字段别名未兼容
- 原始对象转换不完整

### B. 与“今日盈亏”这类业务口径相关的问题
放在：
- `dashboard/data_cache.py`
- 后续建议拆到 `pnl_service.py`

例如：
- 今日盈亏 = 今日已实现 + 今日未实现
- 已平仓标的如何保留在明细中
- filled orders 如何按 symbol 聚合

### C. 与展示方式相关的问题
放在：
- `dashboard/static/index.html`

例如：
- 用“累计已实现”而不是“总已实现”
- 明细展示三项
- 已平仓标的标签

**注意：**
展示层只能改文案和排版，不能重新定义口径。

---

## 五、当前推荐的稳定设计

建议后续逐步收敛到：

```text
Broker API / SDK
    ↓
Raw Client (current client)
    ↓
Normalizer (current normalizer)
    ↓
Service / Aggregator (PnLService / PortfolioService)
    ↓
FastAPI endpoints
    ↓
Frontend renderer
```

其中：
- Raw Client：只做原始抽取
- Normalizer：只做统一字段名
- Service：只做业务语义
- Frontend：只做展示

---

## 六、Phase 1 的验收口径

### 后端
`/api/pnl` 应明确返回：
- `total_today`
- `today_realized`
- `today_unrealized`
- `total_unrealized`
- `total_realized`
- `details[]`，其中每项至少包含：
  - `symbol`
  - `name`
  - `status`
  - `unrealized_pnl`
  - `realized_pnl`
  - `today_pnl`

### 前端
- 顶部“今日盈亏”只显示最终定义值
- 盈亏明细保留已平仓标的
- 明细每项显示三项：
  - 今日
  - 未实现
  - 已实现
- “累计已实现”明确标注为账户级累计语义，不再用模糊文案

---

## 七、后续建议

### 短期
- 完成 Phase 1 收口
- 用这份文档约束接下来的修复位置

### 中期
- 从 `data_cache.py` 拆出 `pnl_service.py`
- 给 `/api/pnl` 增加最小测试
- 给 adapter 层增加字段来源说明

### 长期
- 拆 `main.py`
- 拆 `index.html`
- 把 dashboard 从“单文件堆叠”演进为可维护结构
