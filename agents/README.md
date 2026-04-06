# Tiger Trading Subagents

本目录包含 Tiger Trading 项目的 6 个 subagent 配置文件。

## Agent 列表

| Agent | 职责 | 频率 | 模型 |
|-------|------|------|------|
| tiger-watcher | 系统健康监控 | 每 15 分钟 | mimo-v2-omni |
| tiger-newswire | 新闻/催化扫描 | US 盘前 + 盘中 15min | mimo-v2-omni |
| tiger-strategist | 交易计划草案 | 信号触发或定时 | mimo-v2-pro |
| tiger-executor | 执行检查单/参数校验 | 策略完成后触发 | mimo-v2-omni |
| tiger-scout | 候选标的/异常波动扫描 | 按需或定时 | mimo-v2-omni |
| tiger-closer | 收盘总结/复盘/明日关注 | 每市场收盘后 | mimo-v2-omni |

## 部署方式

### 一键部署所有 agent（yuuka 主会话执行）

在 yuuka 主会话中执行以下命令：

```bash
cd /workspace/tiger-trading/agents
./deploy_tiger_agents_yuuka.sh
```

### 停止所有 agent

```bash
cd /workspace/tiger-trading/agents
./stop_tiger_agents.sh
```

### 查看 agent 状态

```bash
subagents action=list
```

### 部署到 host（arona 执行）

如果需要在 host 上部署，arona 需要执行：

```bash
cd /Users/openclaw/.openclaw/workspace-yuuka/tiger-trading/agents
./deploy_tiger_agents.sh
```

注意：host 上的部署脚本仅显示命令说明，实际部署需在 yuuka 主会话中执行。

## 配置文件说明

- `tiger-watcher.yaml`：tiger-watcher 配置
- `tiger-newswire.yaml`：tiger-newswire 配置
- `tiger-strategist.yaml`：tiger-strategist 配置
- `tiger-executor.yaml`：tiger-executor 配置
- `tiger-scout.yaml`：tiger-scout 配置
- `tiger-closer.yaml`：tiger-closer 配置

## Tool 权限说明

| Agent | Tool 权限 |
|-------|-----------|
| tiger-watcher | read, write, exec, sessions_send |
| tiger-newswire | read, write, browser, web_search, web_fetch, sessions_send |
| tiger-strategist | read, write, sessions_send |
| tiger-executor | read, write, exec, sessions_send |
| tiger-scout | read, write, browser, web_search, web_fetch, sessions_send |
| tiger-closer | read, write, sessions_send |

## 汇报目标

所有 agent 默认汇报给 `agent:yuuka:main`（yuuka 中枢）。
