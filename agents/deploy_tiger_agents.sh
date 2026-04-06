#!/bin/bash
# Tiger Trading Subagents 部署脚本
# 一次性启动所有 6 个 tiger agent

echo "=== Tiger Trading Subagents 部署开始 ==="

# 1. 启动 tiger-watcher
echo "启动 tiger-watcher..."
sessions_spawn \
  task="tiger-watcher: 系统健康监控（engine 心跳、Docker 状态、API 权限）" \
  label="tiger-watcher" \
  runtime="subagent" \
  agentId="tiger-watcher" \
  model="xiaomi-tp/mimo-v2-omni" \
  mode="session" \
  thread=true \
  cwd="/workspace/tiger-trading"

# 2. 启动 tiger-newswire
echo "启动 tiger-newswire..."
sessions_spawn \
  task="tiger-newswire: 新闻/催化扫描（美股新闻、事件时间线整理）" \
  label="tiger-newswire" \
  runtime="subagent" \
  agentId="tiger-newswire" \
  model="xiaomi-tp/mimo-v2-omni" \
  mode="session" \
  thread=true \
  cwd="/workspace/tiger-trading"

# 3. 启动 tiger-strategist
echo "启动 tiger-strategist..."
sessions_spawn \
  task="tiger-strategist: 交易计划草案（基于信号+新闻+宏观产生交易建议）" \
  label="tiger-strategist" \
  runtime="subagent" \
  agentId="tiger-strategist" \
  model="xiaomi-tp/mimo-v2-pro" \
  mode="session" \
  thread=true \
  cwd="/workspace/tiger-trading"

# 4. 启动 tiger-executor
echo "启动 tiger-executor..."
sessions_spawn \
  task="tiger-executor: 执行检查单/参数校验（把计划转成可执行检查单）" \
  label="tiger-executor" \
  runtime="subagent" \
  agentId="tiger-executor" \
  model="xiaomi-tp/mimo-v2-omni" \
  mode="session" \
  thread=true \
  cwd="/workspace/tiger-trading"

# 5. 启动 tiger-scout
echo "启动 tiger-scout..."
sessions_spawn \
  task="tiger-scout: 候选标的/异常波动扫描（扫描候选标的、异常波动检测）" \
  label="tiger-scout" \
  runtime="subagent" \
  agentId="tiger-scout" \
  model="xiaomi-tp/mimo-v2-omni" \
  mode="session" \
  thread=true \
  cwd="/workspace/tiger-trading"

# 6. 启动 tiger-closer
echo "启动 tiger-closer..."
sessions_spawn \
  task="tiger-closer: 收盘总结/复盘/明日关注（每个市场收盘后输出总结）" \
  label="tiger-closer" \
  runtime="subagent" \
  agentId="tiger-closer" \
  model="xiaomi-tp/mimo-v2-omni" \
  mode="session" \
  thread=true \
  cwd="/workspace/tiger-trading"

echo "=== Tiger Trading Subagents 部署完成 ==="
echo "等待所有 agent 启动完成..."
sleep 5
echo "检查启动状态..."
sessions_list
