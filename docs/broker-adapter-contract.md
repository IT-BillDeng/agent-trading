# Broker Adapter Contract

> 目标：把当前依赖单一实现的交易执行层，逐步收束成可替换 broker adapter。
> 原则：先定接口，再逐步迁移调用方；不一次性重命名所有现有实现。

## 1. 当前判断

项目现在已经做到：
- 行情层可以通过 provider 切换
- 展示层和调度说明已经 broker-neutral
- 运行时仍然直接依赖默认 broker 实现做账户、持仓、订单与交易执行

也就是说：
- **可替换已部分成立**
- **执行层还没真正抽象**

## 2. 最小 BrokerClient 接口

下面这组能力，是后续任何 broker 适配器都应提供的最小集合：

```text
account
positions
orders
filled_orders
transactions
market_state
quote_permission
delay_quotes
briefs
bars
contracts
create_order_no
preview_order
place_order
cancel_order
```

## 3. 语义分层

### 3.1 只读查询

应包含：
- `get_accounts`
- `get_assets`
- `get_positions`
- `get_active_orders`
- `get_filled_orders`
- `get_transactions`
- `get_market_state`
- `get_quote_permission`
- `get_delay_quotes`
- `get_briefs`
- `get_bars`
- `get_contract`

特点：
- 可被 dashboard、engine、watcher、closer 复用
- 默认不产生副作用

### 3.2 执行类操作

应包含：
- `create_order_no`
- `preview_order`
- `place_order`
- `cancel_order`

特点：
- 只能进入 execution / live execution 路径
- 不能被展示层或纯只读任务误用

## 4. 当前实现与目标接口的关系

### 4.1 现在的默认 broker 实现

现在默认 broker 实现已经同时承担：
- 原始 API 调用
- 账户/持仓/订单查询
- 下单 / 预检 / 撤单
- 部分适配与字段整理

因此它更像：
- `BrokerClient` 的默认实现
- 而不是抽象接口本身

### 4.2 后续建议

建议后面拆成两层：

```text
BrokerClient (protocol / interface)
    ↓
DefaultBrokerClient (default implementation)
    ↓
当前 broker SDK / Open API
```

这样以后切换 broker 时，只需要新增：
- `FutuBrokerClient`
- `IBBrokerClient`
- 或其他实现

而不用先改 dashboard / engine 的调用方。

## 5. 建议迁移顺序

1. 先冻结当前默认 broker 实现的对外方法集合，不再随意扩展
2. 新增 `BrokerClient` 协议或抽象基类
3. 把当前 broker 实现标记为默认实现
4. 逐步让 `dashboard/main.py`、`system/engine/src/engine/runtime.py`、`live_execution.py` 依赖接口而不是具体类
5. 最后再考虑是否重命名文件

## 6. 结论

**当前项目已经 broker-neutral 到“文档和部分数据层”，但执行层还需要一个真正的 BrokerClient 接口才能算完成抽象。**
