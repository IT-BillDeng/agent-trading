# 美股收盘后生成总结报告（16:00 ET）

- 来源 cron: `trading-closer-us.json`
- taskFile: `docs/tasks/cron/closer-us.md`
- 调度名: `trading-closer-us`

## 任务正文

执行美股收盘总结：

工作目录：`/workspace/agent-trading/`

1. 运行脚本：python3 ./system/engine/src/engine/closer.py US
2. 解析输出的 JSON：
   - 如果 status 是 'skipped' 且 reason 是 '非交易日'，直接回复 HEARTBEAT_OK
   - 否则提取 report 字段
3. 将报告内容通过 message 工具发送到 Telegram（channel: telegram, target: ${ENGINE_TELEGRAM_TARGET}）
4. 如果有异常或风险，在报告末尾添加 ⚠️ 标记
5. 运行结果会同步落到 `./artifacts/closer/summary_latest.json` 和 `./artifacts/closer/summary_history.jsonl`

注意：API 地址 http://host.docker.internal:8088

## 说明

cron 只应引用这个文件；任务正文改动时，无需再修改 cron JSON。
