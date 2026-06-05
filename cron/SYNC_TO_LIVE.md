# Cron Sync To Live

这份文件用于在每次 `cron/` 目录发生变更后，指导主 agent 将仓库中的 cron 定义同步到 live 环境。

## 适用范围

同步以下目录中的所有 cron 定义：

- `cron/*.json`

当前仓库内包含：

- `trading-watcher.json`
- `trading-newswire-premarket.json`
- `trading-newswire-intraday.json`
- `trading-newswire-afterhours.json`
- `trading-strategist-premarket.json`
- `trading-strategist-intraday.json`
- `trading-strategist-afterhours.json`
- `trading-closer-us.json`

## 核心原则

1. 仓库中的 `cron/*.json` 是 **desired state**
2. `docs/tasks/cron/*.md` 是任务正文唯一来源
3. `payload.taskFile` 必须按仓库当前值同步到 live
4. 不要依赖当前工作目录猜测 repo root
5. 仓库 cron 不再携带：
   - `id`
   - `enabled`
6. live 侧是否启用，由主 agent / live 环境自行管理

## 同步步骤

1. 读取所有 `cron/*.json`
2. 对每个 cron：
   - 核对 `name`
   - 核对 `description`
   - 核对 `schedule.kind`
   - 核对 `schedule.expr`
   - 核对 `schedule.tz`
   - 核对 `sessionTarget`
   - 核对 `wakeMode`（如存在）
   - 核对 `payload.kind`
   - 核对 `payload.model`
   - 核对 `payload.timeoutSeconds`
   - 核对 `payload.message`
   - 核对 `payload.taskFile`
   - 核对 `delivery`
3. 读取对应的 `payload.taskFile`
4. 确认 `taskFile` 路径可在 live 环境访问
5. 将 live cron 与仓库定义做最小变更对齐
6. 如发现旧任务：
   - 若已被新定义覆盖，停用或删除旧任务
   - 不保留重复任务

## 产物边界

这份文件是同步说明，不是运行记录落点。

禁止事项：

- 不得把同步结果写回 `cron/*.json`
- 不得把 live 差异写回 `docs/tasks/cron/*.md`
- 不得在项目根目录新建自由格式 markdown / json 同步笔记
- 不得把同步记录写到 `docs/`、`cron/`、`agents/` 目录
- 不得重新创建根目录 `memory/`

同步后的结果应：

- 直接在主会话中汇报
- 如 live 环境需要持久审计，写入 live 自身的任务/审计系统，而不是仓库正文

## 特别注意

### 1. taskFile 路径

必须使用仓库当前的绝对项目路径，例如：

- `/workspace/agent-trading/docs/tasks/cron/watcher.md`
- `/workspace/agent-trading/docs/tasks/cron/strategist-premarket.md`

不要错误读取成：

- `/workspace/docs/tasks/cron/...`

### 2. 主 agent 汇报

任务正文里如果写的是：

- `通过 sessions_send 汇报主 agent`

则主 agent 应按当前 live 环境中的主 agent session key 处理，不要依赖任务正文里出现具体名字。

### 3. Telegram

subagent 不应直发 Telegram。  
如需外发，由主 agent 在读取 subagent 结果后自行判断。

## 建议输出

同步完成后，请输出：

- 每个 cron 的 `name`
- live 是否存在
- 是否完成更新
- 当前 `schedule.expr`
- 当前 `schedule.tz`
- 当前 `payload.taskFile`
- 当前 `payload.model`
- 当前 `delivery`
- 是否发现旧任务
- 是否停用/删除旧任务
- 不要把这份输出回写到仓库文件

## 参考文档

- `docs/main-agent-cron-playbook.md`
- `docs/tasks/cron/README.md`
- `docs/orchestration-directory-contract.md`
- `docs/notification-routing-contract.md`
