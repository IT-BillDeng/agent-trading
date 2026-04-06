#!/bin/bash
# Tiger Trading Subagents 停止脚本
# 停止所有 6 个 tiger agent

echo "=== Tiger Trading Subagents 停止开始 ==="

# 停止 tiger-watcher
echo "停止 tiger-watcher..."
subagents action=kill target=tiger-watcher

# 停止 tiger-newswire
echo "停止 tiger-newswire..."
subagents action=kill target=tiger-newswire

# 停止 tiger-strategist
echo "停止 tiger-strategist..."
subagents action=kill target=tiger-strategist

# 停止 tiger-executor
echo "停止 tiger-executor..."
subagents action=kill target=tiger-executor

# 停止 tiger-scout
echo "停止 tiger-scout..."
subagents action=kill target=tiger-scout

# 停止 tiger-closer
echo "停止 tiger-closer..."
subagents action=kill target=tiger-closer

echo "=== Tiger Trading Subagents 停止完成 ==="
echo "检查停止状态..."
subagents action=list
