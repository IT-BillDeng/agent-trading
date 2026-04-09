#!/bin/bash
# Agent Trading Subagents 部署脚本（yuuka 版本）
# 此脚本由 yuuka 在主会话中执行，使用 OpenClaw 工具

echo "=== Agent Trading Subagents 部署开始 ==="

# 1. 启动 watcher
echo "启动 watcher..."
sessions_spawn \
  task="watcher: 系统健康监控（engine 心跳、Docker 状态、API 权限）" \
  label="watcher" \
  runtime="subagent" \
  agentId="watcher" \
  model="xiaomi/mimo-v2-omni" \
  mode="session" \
  thread=true \
  cwd="/workspace/agent-trading"

# 2. 启动 newswire
echo "启动 newswire..."
sessions_spawn \
  task="newswire: 新闻/催化扫描（美股新闻、事件时间线整理）" \
  label="newswire" \
  runtime="subagent" \
  agentId="newswire" \
  model="xiaomi/mimo-v2-omni" \
  mode="session" \
  thread=true \
  cwd="/workspace/agent-trading"

# 3. 启动 strategist
echo "启动 strategist..."
sessions_spawn \
  task="strategist: 交易计划草案（基于信号+新闻+宏观产生交易建议）" \
  label="strategist" \
  runtime="subagent" \
  agentId="strategist" \
  model="xiaomi/mimo-v2-pro" \
  mode="session" \
  thread=true \
  cwd="/workspace/agent-trading"

# 4. 启动 executor
echo "启动 executor..."
sessions_spawn \
  task="executor: 执行检查单/参数校验（把计划转成可执行检查单）" \
  label="executor" \
  runtime="subagent" \
  agentId="executor" \
  model="xiaomi/mimo-v2-omni" \
  mode="session" \
  thread=true \
  cwd="/workspace/agent-trading"

# 5. 启动 scout
echo "启动 scout..."
sessions_spawn \
  task="scout: 候选标的/异常波动扫描（扫描候选标的、异常波动检测）" \
  label="scout" \
  runtime="subagent" \
  agentId="scout" \
  model="xiaomi/mimo-v2-omni" \
  mode="session" \
  thread=true \
  cwd="/workspace/agent-trading"

# 6. 启动 closer
echo "启动 closer..."
sessions_spawn \
  task="closer: 收盘总结/复盘/明日关注（每个市场收盘后输出总结）" \
  label="closer" \
  runtime="subagent" \
  agentId="closer" \
  model="xiaomi/mimo-v2-omni" \
  mode="session" \
  thread=true \
  cwd="/workspace/agent-trading"

echo "=== Agent Trading Subagents 部署完成 ==="
echo "等待所有 agent 启动完成..."
sleep 5
echo "检查启动状态..."
sessions_list
