# engine

Tiger 模拟盘 30min 自动交易系统 v1 的实现骨架。

## 当前状态
- 已接入 Tiger Open API 的最小请求封装
- 已支持读取：账户、资产、持仓、订单、市场状态、quote 权限、延迟行情、30min K 线
- 已支持 US 白名单配置
- 已补上：
  - **30min 策略骨架**
  - **风控骨架**
  - **dry-run 执行预览**
  - **订单意图层**
  - **Telegram 通知预览骨架**
  - **JSONL 审计日志骨架**
  - **真实执行适配层（guarded/live）**
  - **状态持久化骨架**
  - **preview_order 预检查骨架**
  - **订单状态同步骨架**
  - **成交回报（order_transactions）同步骨架**
  - **preview 阻塞原因映射**
  - **成交回报字段归一化**
  - **Telegram 真发送开关（dispatch plan）**
  - **人工锁定 / 解锁控制平面**
  - **dispatch queue 落盘**
- 当前入口包括：
  - **只读运行周期**
  - **策略运行周期（仅生成信号，不下单）**
  - **dry-run 周期（生成信号 + 风控决策 + 订单预览 + 意图 + 通知预览 + 日志，不下单）**
  - **execution 周期（生成信号 + 风控 + preview_check + 意图 + guarded/live 提交适配 + 同步）**
  - **control_state.py（手动 lock/unlock/status）**

## 已确认的行情事实
- **US**：`quote_delay` 可用，`brief` 当前无权限

v1 的 30min 策略以 **K 线历史** 为主输入。

## 目录
- `config.example.json`：配置模板
- `app_config.paper.json`：当前 paper 配置
- `../watchlist.json`：Operator + Tiger subagents 共用本地股票清单
- `src/engine/config.py`：配置加载
- `src/engine/tiger_client.py`：Tiger API 请求封装
- `src/engine/indicators.py`：指标函数
- `src/engine/strategy.py`：30min 策略骨架
- `src/engine/risk.py`：风控骨架
- `src/engine/execution.py`：dry-run 执行预览
- `src/engine/intent.py`：订单意图层
- `src/engine/notifier.py`：通知预览与 dispatch plan
- `src/engine/audit.py`：JSONL 审计日志
- `src/engine/state.py`：执行状态持久化
- `src/engine/control.py`：人工锁定/解锁控制平面
- `src/engine/live_execution.py`：真实执行适配层（含 preview / submit / sync / transactions）
- `src/engine/sync.py`：订单/成交回报字段归一化
- `src/engine/runtime.py`：只读/策略/dry-run/execution 周期逻辑
- `run_readonly_cycle.py`：只读入口
- `run_strategy_cycle.py`：策略入口
- `run_dry_run_cycle.py`：dry-run 入口
- `run_execution_cycle.py`：真实执行适配入口
- `control_state.py`：锁定/解锁/status 控制入口
- `logs/*.jsonl`：本地审计日志
- `logs/dispatch_queue.jsonl`：待发通知队列
- `state/execution_state.json`：提交状态、预检查、同步状态与重复单防护状态
- `state/control_state.json`：锁定/解锁控制状态

## 运行方式
```bash
python3 run_readonly_cycle.py /path/to/app_config.json /path/to/tiger_openapi_config.properties
python3 run_strategy_cycle.py /path/to/app_config.json /path/to/tiger_openapi_config.properties
python3 run_dry_run_cycle.py /path/to/app_config.json /path/to/tiger_openapi_config.properties
python3 run_execution_cycle.py /path/to/app_config.json /path/to/tiger_openapi_config.properties
python3 control_state.py /path/to/app_config.json status
python3 control_state.py /path/to/app_config.json lock "manual review"
python3 control_state.py /path/to/app_config.json unlock "resume after review"
```

## 执行模式
- `preview_check=true`：提交前先调用 `preview_order`
- `submit_mode=guarded`：构造真实提交链，但不真正下单
- `submit_mode=live` 且 `live_submit=true`：允许真实提交
- `live_cancel=true`：允许真实撤单

## Telegram 开关
- `telegram_preview_only=true`：只生成通知预览
- `telegram_send_enabled=true`：生成可直接投递的 dispatch plan
- `telegram_target=REDACTED`：默认目标

说明：当前代码层生成的是 **dispatch plan / dispatch queue**，后续可由 OpenClaw `message` 工具实际投递。

## 恢复机制
- `stop_on_exception=true`：执行异常时触发系统锁定
- `resume_requires_manual_unlock=true`：异常后必须手动 `unlock`
- 锁定后：
  - 允许继续只读 / preview / 信号观察
  - **禁止提交订单**

默认配置仍是：
- `preview_check=true`
- `submit_mode=guarded`
- `live_submit=false`
- `live_cancel=false`
- `telegram_preview_only=true`
- `telegram_send_enabled=false`
- `resume_requires_manual_unlock=true`

## 本地股票清单
- 默认本地清单：`./data/watchlist.json`
- watcher / strategist / executor / scout / newswire 建议都以这份文件为股票来源
- 当前运行配置中已显式写入 `strategy.watchlist_file`
- **执行代码现在会优先读取这份本地清单；`strategy.symbols` 仅作为回退配置**

## 目前 execution 层已覆盖的项目
- 市场是否处于常规交易时段（heuristic）
- 单笔最大名义金额（USD 等值）
- 最大总暴露（当前 paper 配置：`10,000 USD`）
- 单笔下单约束
- 已有持仓/活动订单冲突检查
- 订单意图生成（含 idempotency key）
- Telegram 文案预览（默认 preview-only）
- Telegram dispatch plan 生成（默认 disabled）
- dispatch queue 落盘
- 本地 JSONL 审计日志输出
- 提交状态落盘与重复单防护状态文件
- Tiger `order_no` / `preview_order` / `place_order` / `cancel_order` 适配
- 已提交订单的详情同步骨架
- 已提交订单的成交回报同步骨架
- preview warning → 风控阻塞原因摘要
- 成交数量/均价/手续费/剩余数量归一化
- 手动 lock/unlock 与异常自动锁定

## 下一步
1. 用 OpenClaw `message` 工具把 dispatch plan / queue 接成真发送
2. 增加 cron/调度接入
3. 增加实盘前的多重确认与总开关
4. 增加更精细的恢复策略（只恢复读取，不恢复提交）
