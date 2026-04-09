#!/bin/bash
# Agent Trading Subagents 部署脚本
# 一次性启动所有 6 个 tiger agent
# 注意：此脚本需在 yuuka 主会话中执行，不能在 shell 中直接运行

echo "=== Agent Trading Subagents 部署脚本 ==="
echo ""
echo "此脚本需在 yuuka 主会话中执行，使用以下命令："
echo ""
echo "1. 启动 watcher:"
echo "   sessions_spawn task=\"watcher: 系统健康监控\" label=\"watcher\" runtime=\"subagent\" agentId=\"watcher\" model=\"xiaomi-tp/mimo-v2-omni\" mode=\"session\" thread=true cwd=\"/workspace/agent-trading\""
echo ""
echo "2. 启动 newswire:"
echo "   sessions_spawn task=\"newswire: 新闻/催化扫描\" label=\"newswire\" runtime=\"subagent\" agentId=\"newswire\" model=\"xiaomi-tp/mimo-v2-omni\" mode=\"session\" thread=true cwd=\"/workspace/agent-trading\""
echo ""
echo "3. 启动 strategist:"
echo "   sessions_spawn task=\"strategist: 交易计划草案\" label=\"strategist\" runtime=\"subagent\" agentId=\"strategist\" model=\"xiaomi-tp/mimo-v2-pro\" mode=\"session\" thread=true cwd=\"/workspace/agent-trading\""
echo ""
echo "4. 启动 executor:"
echo "   sessions_spawn task=\"executor: 执行检查单/参数校验\" label=\"executor\" runtime=\"subagent\" agentId=\"executor\" model=\"xiaomi-tp/mimo-v2-omni\" mode=\"session\" thread=true cwd=\"/workspace/agent-trading\""
echo ""
echo "5. 启动 scout:"
echo "   sessions_spawn task=\"scout: 候选标的/异常波动扫描\" label=\"scout\" runtime=\"subagent\" agentId=\"scout\" model=\"xiaomi-tp/mimo-v2-omni\" mode=\"session\" thread=true cwd=\"/workspace/agent-trading\""
echo ""
echo "6. 启动 closer:"
echo "   sessions_spawn task=\"closer: 收盘总结/复盘/明日关注\" label=\"closer\" runtime=\"subagent\" agentId=\"closer\" model=\"xiaomi-tp/mimo-v2-omni\" mode=\"session\" thread=true cwd=\"/workspace/agent-trading\""
echo ""
echo "=== 部署完成 ==="
