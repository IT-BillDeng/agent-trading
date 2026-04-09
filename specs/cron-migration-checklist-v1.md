# Tiger Cron Migration Checklist v1

> 目标：把 Tiger 相关 cron 从历史堆叠状态迁移到新岗位化调度体系。
> 前提：已完成 `engine-schema-v1.md` 与 `tiger-cron-redesign-v1.md`。
> 原则：先建新路，再退旧路；先 disable，再 remove；每一步都可回滚。

---

## 1. 当前迁移目标

本次迁移不只是“改频率”，而是要完成以下事情：

1. watcher / newswire 接入结构化输出层
2. strategist 从旧式隐含逻辑中独立出来，成为明确岗位
3. decision / executor 从固定 cron 模式中拆出，转向事件触发
4. 退役不再符合当前设计的历史 cron
5. 保留用户侧 portfolio-report，避免影响已有使用体验

---

## 2. 迁移分组

## 2.1 保留并改造

这些 job 暂不删除，但需要按新设计逐步改造。

### watcher
- `watcher-market-watch`
- jobId: `4d758bba-dcd3-4dff-ad14-7c2ff737a5d0`

动作：
- 保留
- 后续改成仅盘中运行
- 增加结构化输出：`runtime/engine/watcher/latest.json` / `history.jsonl`

### newswire preopen
- `newswire-us-preopen`
- jobId: `e3957315-a8ea-4f69-a7b2-ec395d48e285`

动作：
- 保留
- 接入结构化输出：`runtime/engine/newswire/latest.json` / `history.jsonl`

### closer
- `closer-us-close-summary`
- jobId: `75de7f51-fa69-4ea2-b43f-0e1585420f57`

动作：
- 暂时保留
- 后续逐步改成 closer schema 输出

### portfolio-report
- `tiger-portfolio-report-intraday-q15`
- jobId: `09054d50-42be-466a-847a-6d9b471921b3`

- `tiger-portfolio-report-afterhours-hourly`
- jobId: `965badbb-37ac-4ae7-9ad7-0f5f08d5e5c5`

动作：
- 暂时保留
- 作为用户侧输出层，不在第一轮迁移里删除

---

## 2.2 重建后替换

### newswire intraday
现有：
- `newswire-us-intraday`
- jobId: `4588d7a0-88b1-404a-9b8a-d9b6dee58bfd`

- `newswire-us-intraday-q15`
- jobId: `c551d084-d712-4eb6-9961-e8ba0de757bd`

问题：
- 历史叠加
- 频率与新目标不一致
- 存在重叠风险

动作：
- 新建统一的盘中 newswire job（q30）
- 新建统一的盘后 newswire job（q2h）
- 观察稳定后 disable 旧 intraday 类 job
- 最后 remove

### strategist
现状：
- 尚无明确新架构下的 strategist cron

动作：
- 新建 `strategist-intraday-q15`
- 后续补高优先级事件唤醒逻辑

---

## 2.3 过渡保留

### `tiger-paper-execution`
- jobId: `8aaf7c82-fb33-434c-8165-067f8c45b8ad`

现状：
- 代表旧架构里的固定 execution cron

问题：
- 不符合长期的 `decision -> executor` 模型
- 但短期内仍承担主执行链功能

动作：
- 第一轮迁移中 **保留**
- 标记为“过渡任务”
- 待 strategist / decision / executor 链打通后再 disable/remove

---

## 2.4 最终应改为事件触发，不建 cron

### decision
动作：
- 不创建固定 cron
- 由 strategist signal 触发

### executor
动作：
- 不创建固定 cron
- 由 decision approved 后的 task 触发

---

## 3. 推荐迁移顺序

## Phase 0：冻结目标

在正式迁移前确认：
- 以 `tiger-cron-redesign-v1.md` 为蓝图
- 不再在旧 cron 上继续做零散补丁

完成标准：
- 迁移方向拍板

---

## Phase 1：先落 watcher / newswire 结构化输出

### 目标
在不大动 cron 的前提下，让 watcher / newswire 先具备结构化产物。

### 动作
1. 创建目录：
   - `runtime/engine/watcher/`
   - `runtime/engine/newswire/`
2. 补 `latest.json` / `history.jsonl` 约定
3. 更新 watcher / newswire 岗位说明，使其输出结构化文件

### 风险
- 低
- 不动主要调度，只是在岗位侧加输出

### 回滚
- 移除新增输出逻辑
- 删除新增运行目录即可

---

## Phase 2：重建 newswire 班表

### 目标
让 newswire 频率符合新设计：
- 盘中 q30
- 盘后 q2h

### 动作
1. 新建盘中 q30 newswire job
2. 新建盘后 q2h newswire job
3. 保留 preopen 两条不动
4. 观察 1~2 个周期
5. disable：
   - `newswire-us-intraday`
   - `newswire-us-intraday-q15`
6. 验证无缺口后 remove 旧 job

### 风险
- 中
- 若新班次表达式写错，可能出现扫描空窗

### 回滚
- 重新启用旧 intraday job
- 暂不 remove 直到新 job 稳定

---

## Phase 3：新增 strategist cron

### 目标
让 strategist 成为明确岗位，而不是隐含逻辑。

### 动作
1. 新建 `strategist-intraday-q15`
2. 输入先读取：
   - `runtime/engine/watcher/latest.json`
   - `runtime/engine/newswire/latest.json`
3. 输出：
   - `runtime/engine/strategist/latest_signal.json`
   - `signals.jsonl`

### 风险
- 中
- strategist 使用强模型，成本和稳定性要一起评估

### 回滚
- disable strategist 新 job
- 保持 watcher/newswire 继续运行

---

## Phase 4：接 decision / executor 事件链

### 目标
摆脱固定 execution cron 的长期依赖。

### 动作
1. 先定义 signal -> decision -> task -> result 的触发链
2. 不创建固定 decision/executor cron
3. 先用文件 / 事件对象方式打通流程
4. 等链路稳定后，重新评估 `tiger-paper-execution`

### 风险
- 中偏高
- 因为会真正触及执行模型变化

### 回滚
- 保持 `tiger-paper-execution` 继续作为主执行链

---

## Phase 5：退役旧 execution cron

### 目标
最终移除旧式固定 execution cron。

### 动作
1. 先 disable `tiger-paper-execution`
2. 观察至少 1~2 个交易日
3. 若 signal -> decision -> executor 链稳定，则 remove

### 风险
- 高于前几阶段
- 因为这一步涉及主执行链切换

### 回滚
- 重新启用 `tiger-paper-execution`

---

## 4. 立即可执行的最小动作清单

这是当前最推荐的顺序：

### 第一优先级
- [ ] 落 watcher 结构化输出
- [ ] 落 newswire 结构化输出

### 第二优先级
- [ ] 新建 newswire 盘中 q30 job
- [ ] 新建 newswire 盘后 q2h job
- [ ] disable 旧 intraday newswire job

### 第三优先级
- [ ] 新建 strategist q15 job
- [ ] strategist 读取 watcher/newswire 结构化输出

### 第四优先级
- [ ] 定义 decision / executor 事件触发链
- [ ] 保留旧 execution cron 作为过渡

### 第五优先级
- [ ] 退役 `tiger-paper-execution`

---

## 5. 当前不建议先做的事

以下动作当前不建议先做：

- 直接 remove 所有旧 Tiger cron
- 在没有 watcher/newswire 结构化输出前就上 strategist
- 在 decision/executor 链没打通前就移除 `tiger-paper-execution`
- 一次性同时修改所有 cron + 所有岗位逻辑

原因：
- 风险过高
- 难定位故障来源
- 会让回滚变复杂

---

## 6. 回滚原则

每个阶段都遵循：

1. 新 job 先 add
2. 旧 job 先 disable，不立即 remove
3. 验证稳定后再 remove
4. 任一阶段出问题，优先回滚到“上一个已稳定阶段”

---

## 7. 一句话总结

**Tiger cron 迁移的正确顺序不是“先删旧 cron”，而是：先让 watcher/newswire 产出结构化数据，再重建 newswire 与 strategist，再接 decision/executor 事件链，最后退役旧 execution cron。**
