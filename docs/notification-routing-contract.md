# Notification Routing Contract

更新时间：2026-04-17

## 目的

定义 `agent-trading` 中通知的默认路由规则，避免每个 subagent 自行决定并直接外发 Telegram。

目标：

- 统一通知标准
- 避免重复和噪音
- 收口外发权限
- 让主 agent 成为默认通知决策层

## 默认原则

### 1. subagent 不直接发 Telegram

subagent 默认只做三件事：

- 写业务产物到 `artifacts/`
- 写运行信息到 `logs/`
- 在需要时通过 `sessions_send sessionKey=agent:yuuka:main` 汇报主 agent

不默认具备：

- 直接决定是否打扰用户
- 直接将结果外发到 Telegram

### 2. 主 agent 负责二次判断

主 agent 负责：

- 汇总多个 subagent 的结果
- 对相似事件做去重
- 判断优先级与紧急程度
- 决定：
  - 仅记录
  - 汇总后回复到主会话
  - 外发 Telegram

### 3. 通知提案与通知发送分离

推荐分层：

- `subagent`：产生通知提案
- `main agent`：决定是否发送
- `engine notifier`：如需统一发送，可作为执行层，不作为决策层

## 当前推荐架构

### 默认链路

`subagent -> agent:yuuka:main -> Telegram(可选)`

### 不推荐链路

`subagent -> Telegram`

原因：

- 规则容易漂移
- 难以去重
- 难以汇总
- 配置和外发权限分散

## 是否需要单独的 notifier subagent

当前结论：**默认不需要。**

原因：

- 当前项目规模下，主 agent 足以承担通知汇总与二次判断
- 额外引入 notifier subagent 会增加一层协作复杂度
- 在没有多通道、重试队列、严格 SLA 之前，notifier subagent 的收益不高

### 什么时候再考虑 notifier subagent

只有在出现以下情况时，才建议单独引入：

- 渠道明显增多（Telegram / Email / Push / Slack）
- 通知量明显增大，需要统一队列和重试
- 需要独立的通知优先级、静默时间和速率限制
- 主 agent 已经承担过多职责，通知决策成为明显瓶颈

## 例外

如果未来确实存在系统级紧急告警，需要允许直发，也应满足：

- 明确限定在极少数 `critical/emergency` 场景
- 在文档中单独声明为例外
- 不扩展成普通 subagent 的常规能力

## 当前仓库约定

- `cron/*.json` 中不再为 subagent 保留 Telegram 外发配置
- `agents/*.yaml` 默认只汇报到 `agent:yuuka:main`
- `docs/tasks/cron/*.md` 中凡提到“通知先生”，默认指“先汇报主 agent”
- 由主 agent 再决定是否发送 Telegram
