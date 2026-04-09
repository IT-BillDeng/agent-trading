#!/bin/bash
# Agent Trading Subagents 停止脚本
# 停止所有 6 个 tiger agent

echo "=== Agent Trading Subagents 停止开始 ==="

# 停止 watcher
echo "停止 watcher..."
subagents action=kill target=watcher

# 停止 newswire
echo "停止 newswire..."
subagents action=kill target=newswire

# 停止 strategist
echo "停止 strategist..."
subagents action=kill target=strategist

# 停止 executor
echo "停止 executor..."
subagents action=kill target=executor

# 停止 scout
echo "停止 scout..."
subagents action=kill target=scout

# 停止 closer
echo "停止 closer..."
subagents action=kill target=closer

echo "=== Agent Trading Subagents 停止完成 ==="
echo "检查停止状态..."
subagents action=list
