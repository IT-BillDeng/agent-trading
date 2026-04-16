# Engine Cron Instructions

用于 OpenClaw cron systemEvent 的执行约定。

## 每次触发时执行
0. 若 cron payload 包含 `taskFile`，优先读取该 markdown 文件作为任务正文；`message` 仅作为兼容兜底或简短提示。
1. 运行：
   ```bash
   cd <项目根目录>/agent-trading && \
   python3 ./system/engine/run_execution_cycle.py \
     ./system/engine/app_config.paper.json \
     <broker API 配置文件路径>
   ```
   > 注意：cron 执行时需将 `<项目根目录>` 和 `<broker API 配置文件路径>` 替换为实际绝对路径。
2. 读取输出中的：
   - `notification_dispatch.items`
   - `control.locked`
   - `risk.preview_blockers`
   - `execution_submit`
   - `order_sync`
3. 若 `notification_dispatch.items` 非空：逐条用 `message` 工具发送到 Telegram 目标。
4. 若 `control.locked = true`：允许继续观测与发送锁定告警，但不要尝试提交订单。
5. 若无可发送内容：保持静默。

## 备注
- 当前配置为 `submit_mode=guarded`，不会真实下单。
- 当前目标是：先稳定 30min paper-trading 观察链路，再考虑 live。
