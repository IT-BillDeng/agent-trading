# Git 版本管理约定

更新时间：2026-04-20

这份文档定义 `agent-trading` 仓库的 git 管理方式，目标是：

- 保持提交历史可读
- 避免运行时产物污染工作区
- 让主线版本、实验版本、部署版本容易回溯

---

## 1. 主原则

### 1.1 一次提交只做一类事

推荐按以下粒度拆分 commit：

- `feat:` 新功能
- `fix:` 缺陷修复
- `refactor:` 重构，不改变行为
- `docs:` 文档更新
- `test:` 测试补充/修正
- `chore:` 杂项维护

不建议把这些混在同一个 commit：

- dashboard 改动
- engine 逻辑改动
- cron 配置改动
- 文档改动
- 运行产物清理

### 1.2 仓库只跟踪“可复现的源码与配置”

应该进 git 的内容：

- 源码
- 测试
- 文档
- `cron/` desired state
- `docs/tasks/` / `docs/roles/`
- 配置模板
- schema / specs

不应进 git 的内容：

- 本地用户状态
- secrets
- 运行日志
- 临时快照
- 会话记忆
- 本地实验中间产物

---

## 2. 当前忽略策略

以下内容默认不进 git：

- `.env`
- `config/user.settings.json`
- `data/watchlist.json`
- `runtime/`
- `logs/` 下生成型日志
- `memory/`
- `logs/watcher-*.json`
- `rules/rules_backup/`

原则上：

- `logs/README.md`、`.gitkeep`、`manifests/log_index.json` 这种结构性文件可以跟踪
- 真实运行输出不跟踪

---

## 3. 分支策略

当前项目可以保持简单策略：

- `master`：当前主线

如果需要多人/多阶段协作，建议使用短生命周期分支：

- `feat/<topic>`
- `fix/<topic>`
- `refactor/<topic>`
- `docs/<topic>`

例如：

- `feat/strategist-fee-confidence`
- `fix/strategy-overview-api`
- `refactor/cron-model-selection`

原则：

- 小步分支
- 小步提交
- 快速合并
- 不长期堆积巨大未合并分支

---

## 4. 提交信息约定

推荐格式：

```text
type(scope): summary
```

例如：

- `feat(strategy): add broker fee calibration view`
- `fix(dashboard): restore overview API JSON loading`
- `refactor(models): switch watcher to gpt-5.4-mini`
- `docs(strategist): add code-change test runbook`

要求：

- `summary` 尽量短
- 用动词
- 能看出影响范围

---

## 5. Tag / 版本建议

如果后续要做明确版本点，建议使用：

- `v0.1.0`
- `v0.2.0`
- `v0.2.1`

当前项目仍在快速演进，建议：

- 稳定里程碑再打 tag
- tag 应该对应“可部署、可回退”的状态

适合打 tag 的场景：

- dashboard 结构大调整完成
- strategist L3a / L3b 关键节点完成
- cron / artifacts / logs 目录契约稳定
- broker fee model 闭环稳定

不建议因为一次普通小修就打 tag。

---

## 6. 提交前检查

每次提交前至少做：

```bash
git status
git diff --check
```

如果改的是 Python：

```bash
python3 -m py_compile <changed files>
```

如果改的是 dashboard：

- 必要时重建容器
- 至少确认关键页面和接口可打开

---

## 7. 运行产物处理

对于运行时生成的：

- `logs/`
- `artifacts/`
- `memory/`
- `runtime/`

处理原则是：

- 文档和目录骨架可跟踪
- 实际生成内容默认不跟踪

如果某类产物需要长期保留，应优先：

- 设计规范文件
- 保存到 canonical path
- 再决定是否应该版本化

不要直接把一次运行结果随手提交进仓库。

---

## 8. 特殊文件处理

### `rules/rules.json`

这是策略主配置，原则上：

- 修改要小步提交
- 变更原因最好能从 commit message 看出来

### `cron/*.json`

这是 live cron 的 desired state：

- 改动后应配合 `cron/SYNC_TO_LIVE.md`
- 不再写 `id`
- 不再写 `enabled`

### `docs/tasks/cron/*.md`

这是任务正文：

- 可以频繁迭代
- 但应与 `cron/*.json` 保持语义一致

---

## 9. 当前建议

当前仓库最推荐的工作方式：

1. 先改一类内容
2. 本地验证
3. 单独 commit
4. 保持工作区尽量干净
5. 再进入下一类改动

如果工作区已经混入多类改动，优先先分清：

- 哪些是源码
- 哪些是运行产物
- 哪些是临时笔记

再决定是否提交。

