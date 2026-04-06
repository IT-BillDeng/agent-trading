#!/bin/bash
# Tiger Trading Subagents 部署脚本
# 一次性启动所有 6 个 tiger agent
# 注意：此脚本需在 yuuka 主会话中执行，不能在 shell 中直接运行

echo "=== Tiger Trading Subagents 部署脚本 ==="
echo ""
echo "此脚本需在 yuuka 主会话中执行，使用以下命令："
echo ""
echo "1. 启动 tiger-watcher:"
echo "   sessions_spawn task=\"tiger-watcher: 系统健康监控\" label=\"tiger-watcher\" runtime=\"subagent\" agentId=\"tiger-watcher\" model=\"xiaomi-tp/mimo-v2-omni\" mode=\"session\" thread=true cwd=\"/workspace/tiger-trading\""
echo ""
echo "2. 启动 tiger-newswire:"
echo "   sessions_spawn task=\"tiger-newswire: 新闻/催化扫描\" label=\"tiger-newswire\" runtime=\"subagent\" agentId=\"tiger-newswire\" model=\"xiaomi-tp/mimo-v2-omni\" mode=\"session\" thread=true cwd=\"/workspace/tiger-trading\""
echo ""
echo "3. 启动 tiger-strategist:"
echo "   sessions_spawn task=\"tiger-strategist: 交易计划草案\" label=\"tiger-strategist\" runtime=\"subagent\" agentId=\"tiger-strategist\" model=\"xiaomi-tp/mimo-v2-pro\" mode=\"session\" thread=true cwd=\"/workspace/tiger-trading\""
echo ""
echo "4. 启动 tiger-executor:"
echo "   sessions_spawn task=\"tiger-executor: 执行检查单/参数校验\" label=\"tiger-executor\" runtime=\"subagent\" agentId=\"tiger-executor\" model=\"xiaomi-tp/mimo-v2-omni\" mode=\"session\" thread=true cwd=\"/workspace/tiger-trading\""
echo ""
echo "5. 启动 tiger-scout:"
echo "   sessions_spawn task=\"tiger-scout: 候选标的/异常波动扫描\" label=\"tiger-scout\" runtime=\"subagent\" agentId=\"tiger-scout\" model=\"xiaomi-tp/mimo-v2-omni\" mode=\"session\" thread=true cwd=\"/workspace/tiger-trading\""
echo ""
echo "6. 启动 tiger-closer:"
echo "   sessions_spawn task=\"tiger-closer: 收盘总结/复盘/明日关注\" label=\"tiger-closer\" runtime=\"subagent\" agentId=\"tiger-closer\" model=\"xiaomi-tp/mimo-v2-omni\" mode=\"session\" thread=true cwd=\"/workspace/tiger-trading\""
echo ""
echo "=== 部署完成 ==="
