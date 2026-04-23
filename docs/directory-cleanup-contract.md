# Directory Cleanup Contract

更新时间：2026-04-23

## 目的

这份文档定义 `factor-researcher` 分支在 factor-first rewrite 之前的目录清理契约。

FF-01 的目标不是立刻删除旧实现，而是：

- 先建立新的 canonical 目录骨架
- 给后续迁移预留稳定入口
- 保证旧导入与旧运行路径暂时不破

## FF-01 的总体原则

### 1. 先立新，不立刻删旧

- 可以新增 `engine/adapters/`、`engine/strategy/`、`experiments/rule_batches/`
- 不在 FF-01 删除 `engine/strategy.py`、旧 broker/data provider 实现、旧 runtime/rule path
- 所有新目录先以 skeleton / compatibility layer 形式落地

### 2. 兼容优先

- 旧导入必须继续可用
- `engine.strategy` 仍然保持 legacy entrypoint 语义
- 新目录通过 import shim / compatibility shim 暴露，不强行要求现有调用方立即改完

### 3. 不改变行为

FF-01 不得改变以下行为：

- `execution.submit_mode=guarded`
- `execution.live_submit=false`
- `factor_engine.mode=shadow`
- `factor_engine.allow_actionable_consumption=false`
- Dashboard scheduler preview-only

### 4. 实验与 canonical 分离

- `rules/rules.json` 继续是 canonical rules 配置入口
- `_batch_*.json` 属于实验规则批次，不再放在 `rules/`
- 实验批次统一收口到 `experiments/rule_batches/`

## FF-01 新目录契约

### Engine adapters

新增：

```text
system/engine/src/engine/adapters/
  broker/
  market_data/
```

职责：

- `adapters/broker/`：作为 broker adapter 的新入口层
- `adapters/market_data/`：作为 market data adapter 的新入口层

FF-01 限制：

- 只允许 re-export / compatibility-style 骨架
- 不在本批把 dashboard / engine 的所有 provider 实现一次性搬空

### Engine strategy skeleton

新增：

```text
system/engine/src/engine/strategy/
  bindings.py
  evaluator.py
  compatibility.py
```

职责：

- `bindings.py`：放 rule <-> factor 的绑定抽象
- `evaluator.py`：放未来 factor-first evaluator 的入口骨架
- `compatibility.py`：放 legacy strategy 到新结构的兼容桥

FF-01 限制：

- `engine/strategy.py` 不删除
- `runtime.py` 等旧调用暂时继续走 `engine.strategy`
- 新目录只提供后续迁移入口，不在本批强行替换热路径

## Legacy Import Compatibility

为了同时满足“旧导入不破”和“新目录可渐进使用”，FF-01 采用以下兼容策略：

1. `engine.strategy` 仍然保留 legacy module
2. `engine.strategy` 增加 package-like shim，使新代码可使用：
   - `engine.strategy.bindings`
   - `engine.strategy.evaluator`
   - `engine.strategy.compatibility`
3. `compatibility.py` 只桥接旧实现，不引入新的交易行为

## Rule Batch 文件迁移契约

FF-01 迁移范围：

- `rules/_batch_*.json` -> `experiments/rule_batches/`

迁移后的约束：

- `rules/` 不再承载实验 batch 配置
- Dashboard backtest batch 的临时规则文件默认写入 `experiments/rule_batches/`
- 这些 batch 文件属于实验输入/输出，不改变 `rules/rules.json` 的 canonical 身份

## 本批不做的事

- 不删除旧 broker client / data provider 实现
- 不把 `engine/strategy.py` 直接拆掉
- 不重写 `rule_engine` 为 factor-first evaluator
- 不改 execution / risk / control / live gate
- 不恢复 Dashboard scheduler submit 权限

## 后续 batch 的依赖关系

- FF-02 / FF-03 可以开始把 factor-first evaluator 和 legacy compatibility 分流挂到 `engine/strategy/`
- FF-07 才是删除明显重复实现的批次

在 FF-07 之前，任何目录清理都应遵守：

- 先加兼容层
- 再迁调用方
- 最后删旧实现
