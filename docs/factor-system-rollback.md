# Factor System Rollback

更新时间：2026-04-22

## 目标

这份文档说明在 `factor-researcher` 分支及其后续合并中，如何：

- 关闭 Factor Engine shadow mode
- 回滚 `factors/registry.json` 的 hot apply
- 保持 live / broker / risk 边界不被突破

它只描述回滚和止血步骤，不授予新的 apply、submit 或 live 权限。

## 回滚原则

执行任何回滚前，都要先满足这些原则：

- 不把 `submit_mode` 改成 `live`
- 不把 `live_submit` 改成 `true`
- 不把 `factor_engine.allow_actionable_consumption` 改成 `true`
- 不让 `factor-researcher` 直接执行 rollback apply
- 不修改 broker / execution / risk hard gates
- 所有回滚动作都必须能在文档、deployment record 或 git 记录中追溯

## 场景 A：关闭 Factor Engine Shadow Mode

这是最小止血动作，适用于：

- 因子快照持续报错
- 因子 artifacts 写入异常
- Dashboard factor health 噪音过高
- 暂时不希望 runtime 再运行 shadow 计算

标准步骤：

1. 在当前部署实际使用的配置覆盖层中，把 `factor_engine.enabled` 设为 `false`。
2. 不要把 `factor_engine.mode` 改成其他值；保持或恢复为 `shadow`。
3. 保持 `factor_engine.allow_actionable_consumption=false`。
4. 保持 `execution.submit_mode=guarded`、`execution.live_submit=false`。
5. 重启相关 runtime / dashboard 进程。
6. 检查 latest cycle / strategy overview，确认 Factor Engine 已停用或不再输出新的 shadow 摘要。
7. 记录 rollback note，注明关闭原因、执行时间、执行人和受影响环境。

预期结果：

- Factor Engine 不再运行 shadow 计算
- 交易逻辑保持原有路径
- 不新增任何 live/execution/broker 行为

## 场景 B：回滚 `factors/registry.json` hot apply

### B.1 自动回滚何时发生

对于 `factor_config` hot apply：

- applier 会先为目标文件创建备份
- 如果 schema validation 失败或写入过程报错，会自动恢复原始内容
- 同时写入 failure record，记录失败原因

因此：

- 失败的 hot apply 一般不需要额外手动回滚
- 需要手动回滚的，通常是“已经成功 apply，但后来确认应该撤回”的场景

### B.2 手动回滚成功 apply 的标准步骤

1. 暂停新的 factor proposal apply，避免并发覆盖。
2. 打开 `artifacts/strategist/deployment_records.jsonl`，定位目标 proposal：
   - `proposal_type = factor_config`
   - `apply_action = apply_factor_registry_only`
   - `success = true`
3. 读取该条记录里的：
   - `proposal_id`
   - `registry_hash`
   - `changed_factors`
   - `targets[].backup_path`
4. 用 `targets[].backup_path` 指向的备份文件恢复 `factors/registry.json`。
5. 如果备份文件不可用，则从最近一次已知安全提交恢复 `factors/registry.json`，只恢复这个文件，不扩大到其他路径。
6. 重新执行 registry 校验和容器测试。
7. 在 `artifacts/strategist/rollback_notes.jsonl` 记录这次回滚：
   - `proposal_id`
   - 回滚原因
   - 恢复来源（backup path 或 git commit）
   - 操作人
   - 时间戳
8. 检查 runtime / strategy overview 中的 `registry_hash` 是否已回到预期值。

### B.3 建议的核对点

完成 registry 回滚后，至少核对：

- `factors/registry.json` 内容与预期恢复版本一致
- `factor_engine.mode` 仍是 `shadow`
- `allow_actionable_consumption` 仍是 `false`
- `changed_factors` 对应的因子定义已经恢复
- 没有误改 `rules/rules.json`
- 没有误改 live / broker / execution / risk 文件

## 场景 C：`factor_rule_link` hot apply 撤回

虽然这份文档重点是 registry 回滚，但若要撤回 `factor_rule_link`：

1. 查 `artifacts/strategist/deployment_records.jsonl`
2. 定位 `proposal_type = factor_rule_link` 的成功 apply 记录
3. 使用对应 `targets[].backup_path` 恢复 `rules/rules.json`
4. 重新跑 rule schema 和 factor registry schema 相关验证
5. 写入 rollback note

注意：

- `factor_rule_link` 的撤回只应回滚 `rules/rules.json`
- 不应顺手改动 `factors/registry.json`

## `factor_code` 的处理原则

`factor_code` 从设计上就是 cold/manual：

- applier 只会记录 `manual_code_apply_required`
- 不会自动修改 engine source

因此：

- 不存在“自动 apply 了 factor_code 然后再回滚”的正常路径
- 如果有人手动改了 factor source，就必须按普通代码回滚流程处理，并经过代码审查

## 回滚时禁止做的事

回滚过程中，禁止以下动作：

- 借回滚之名打开 `live_submit`
- 借回滚之名把 `submit_mode` 设为 `live`
- 借回滚之名修改 broker / execution / risk gate
- 让 `factor-researcher` 自己执行热路径回滚
- 一次性回滚 `rules/`、`factors/`、`runtime/`、`broker/` 多个不相关区域
- 提交运行生成的 artifacts

## 建议测试命令

完成关闭或回滚后，至少执行：

```bash
docker compose build dashboard

docker compose run --rm dashboard sh -lc '
  cd /app &&
  PYTHONPATH=/app:/app/system/engine/src python -m pytest -q
'
```

如果需要补充验证当前测试镜像：

```bash
docker compose --profile test build test-runner
docker compose --profile test run --rm test-runner
```

## 与 `factor-researcher` 的关系

`factor-researcher` 不应同步到 live，除非主 agent 单独审批。

所以在 rollback 语境下：

- 它可以提供研究结论
- 可以帮助定位受影响的 factor proposal
- 但不能自己 approve / apply / rollback 热路径配置

最终的回滚决定和执行，仍然应由主 agent 或人工运维方负责。
