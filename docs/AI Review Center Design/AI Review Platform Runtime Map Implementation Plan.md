# AI Review 平台运行地图后续推进计划

基线文档：[AI Review Command Center Implementation Plan.md](/D:/projects/ai-code-review-platform/docs/AI%20Review%20Center%20Design/AI%20Review%20Command%20Center%20Implementation%20Plan.md)

## 当前执行状态

- 当前阶段：`Phase 5A`
- 阶段状态：`PHASE 5A COMPLETED — WAITING FOR STRUCTURE AND INFORMATION DENSITY CONFIRMATION`
- Phase 4 基线 Commit：`d63fccf`
- Phase 5A 授权时间：2026-08-03
- 计划创建时间：2026-08-03
- 当前目标：等待用户验证静态双路线地图的结构与信息密度。
- 当前停止点：Phase 5A 已完成；未经用户确认“继续下一阶段”不得进入 Phase 5B。

本文档是 Phase 5 的独立实施总控。Phase 4 及更早阶段继续以原 Implementation Plan 为历史记录，不再向原文档追加 Phase 5 内容。

## 一、可行性与产品结论

### 1.1 可行性

- 现有 `/api/command-center/runtime` 已聚合活跃 Task、Flow、Scheduler、Agent Worker、Provider 和告警，新增双路线投影无需修改 Review、Scheduler、Agent 或 Provider 状态机。
- `code_quality_scheduler_jobs` 已有 `status, priority, queued_at` 等队列索引，可支持 Review Lane 计数、运行项和队头候选查询；Phase 5A 必须以真实 MySQL EXPLAIN 最终确认。
- 现有 Command Center 已具备单 Canvas、单 RAF、ResizeObserver、visibility/focus 去重、静态 DOM fallback 和 5 秒 Runtime 轮询，可复用其生命周期边界。
- 现有任务详情支持 `/tasks/{taskId}?reviewKey={reviewKey}`，运行 Review 可以直接钻取，无需新增中间业务页面。

### 1.2 固定产品方向

- 首页从“单 Task 生命周期聚焦”改为“全平台 Review 运行态总览”。
- 移除 Task/Flow 选择器、GitLab/Manual、Rule Analysis、五阶段生命周期节点、Flow Dock、页面内 Queue/Failure 按钮和结果区。
- 保留全局右上角 Queue/Failure 能力；首页地图通过 Runtime 快照展示队列，不复制 Drawer 状态或请求。
- 主结构采用双路线基地：共享候场区分流到 Standard Review 工坊与 Agent Review 基地，路线在右侧淡出，不展示完成、失败、Finding 或风险卡片。
- 地图采用明亮日光配色，桌面/平板为上帝视角地图，390 宽度使用完整静态 DOM 双路线布局。

## 二、Runtime v2 接口设计

### 2.1 版本与兼容

- `GET /api/command-center/runtime` 返回 `schemaVersion = command-center-runtime-v2`。
- 保留 v1 的原字段，新增顶层 `reviewLanes`，避免影响其他读取方。
- 前端同时接受 v1 和 v2。v1 降级模式只展示可证明的聚合数，不展示运行项且不得推断 `nextQueued`。
- Runtime 仍使用一个请求、5 秒轮询、AbortController 和 visibility/focus 恢复去重；不恢复 Governance 请求。

### 2.2 Review Lane 契约

```json
{
  "reviewLanes": {
    "standard": {
      "zoneKey": "standard",
      "engine": "STANDARD",
      "capacity": 10,
      "runningCount": 2,
      "queuedCount": 3,
      "utilizationPercent": 20,
      "runningItems": [],
      "nextQueued": null,
      "runningItemsTruncated": false,
      "queueOrder": "PROVIDER_PRIORITY_FIFO"
    },
    "agent": {
      "zoneKey": "agent",
      "engine": "AGENT",
      "capacity": 4,
      "runningCount": 1,
      "queuedCount": 2,
      "utilizationPercent": 25,
      "runningItems": [],
      "nextQueued": null,
      "runningItemsTruncated": false,
      "queueOrder": "AGENT_PRIORITY_FIFO"
    }
  }
}
```

每个 `runningItems` / `nextQueued` 元素固定包含：

- `jobId`、`taskId`、`reviewKey`、`projectId`、`projectName`、`displayName`。
- `requestedEngine`、`effectiveEngine`、`fallback`、`status`、`stage`。
- `provider`、`model`、`workerId`。
- `queuedAt`、`startedAt`、`durationSeconds`。

规则：

- Standard 路线包含 `AI_REVIEW` Job，包括 Agent 降级后进入 Provider Scheduler 的 Standard Job。
- Agent 路线包含 `AGENT_REVIEW` Job。
- Standard 队头按 Provider Scheduler 的真实顺序：`priority ASC, queuedAt ASC, id ASC`。
- Agent 队头按 Worker Claim 的真实顺序：`priority DESC, queuedAt ASC, id ASC`。
- `nextQueued` 是快照时刻的下一可调度候选，不承诺在并发竞争中一定成为下一实际执行项。
- Standard Capacity 由 Provider Scheduler 的共享容量常量提供；Agent Capacity 使用在线 Worker Capacity。
- Running Item 上限为 100；超过时 `runningItemsTruncated=true`，总数仍由 `runningCount` 精确表达。
- 所有 Lane 查询遵守 `projectId/groupId` 过滤；Coverage 记录 Lane 上限与实际返回数。

### 2.3 查询与索引门禁

- Review Lane 计数复用 Runtime base counts，Standard 由总 Review Job 计数减 Agent Job 计数得到。
- Running Item 与 Next Queue 使用独立有界查询，避免从按更新时间选择的 `activeFlows` 推断执行顺序。
- Provider/Model 来自 Review Result，Agent Worker 通过 Worker `active_job_id` 对账；缺失时返回 `null`，不虚构关联。
- Phase 5A 必须执行真实 MySQL EXPLAIN。若出现需要新增索引、迁移、缓存或物化表的查询计划，立即停止并申请单独授权。

## 三、静态双路线地图设计

### 3.1 信息架构

- 顶部 HUD：页面标题、Runtime 新鲜度、更新时间、总运行/总容量、总等待、Standard 占用、Agent 占用和刷新。
- 候场区：分别展示 Standard/Agent 等待总数、下一条 Review 的项目、Review 名称和 Provider/Model；下一条保持非交互。
- Standard 工坊：容量槽与运行 Review 标记，展示普通 Provider Review 的占用情况。
- Agent 基地：Worker 塔与运行 Review 标记，展示 Worker、Agent 阶段和占用情况。
- 右侧只有淡出道路，不显示结果、失败、风险或通知模块。

### 3.2 Review 标记与交互

- 标记主文本为 `projectName`，副文本为 `displayName/reviewKey`、Provider/Model 和 Stage；不显示 Task ID。
- 运行标记使用原生 `button`，点击或 Enter/Space 进入 `/tasks/{taskId}?reviewKey={reviewKey}`。
- 每路线可见上限：1440 为 6、1024 为 4、390 为 2。
- 超出可见上限时显示 `+N` 聚合塔；点击后打开轻量 Ant Design Modal，列出该路线全部运行 Review，每行可进入同一任务详情路由。
- Modal 关闭后焦点返回聚合塔；运行项不足时不创建 Modal 入口。
- 候场、Standard 基地、Agent 基地只保留稳定 `zoneKey`，本阶段不设置 button role 或模块级点击。

### 3.3 视觉与 Canvas 边界

- 页面背景 `#F4F8FB`，地图底板 `#EAF2F7`，基地 `#FFFFFF`，道路 `#BFD4DF`。
- 主文字 `#17324D`，次文字 `#587187`，Standard `#0F8FA3`，Agent `#7056D8`，Queue `#B87500`，Fallback `#B66A00`。
- Phase 5A 只实现静态浅色地形、基地、道路和高对比状态，不实现移动粒子、道路能量流或 Worker 心跳。
- DOM Overlay 独占文本、焦点和跳转；Canvas 保持 `aria-hidden`，失败、小屏或 reduced-motion 时完整 DOM 信息不丢失。
- 移除旧 Task/Flow focus、五阶段 Topology、Flow Dock 和 `controller.setFocus` 产品依赖；资源治理能力继续保留。

## 四、分阶段总控

### 4.1 总控 Prompt

```text
继续推进 AI Review 平台运行地图。

先读取：
1. AGENTS.md
2. docs/AI Review Center Design/AI Review Platform Runtime Map Implementation Plan.md 的当前执行状态、目标阶段、验收标准、授权边界和停止点

只执行当前已授权阶段。开始前回写阶段状态为 IN PROGRESS；先写数据结构与接口，再写业务逻辑。完成专项测试、全量测试、构建、浏览器验收和 git diff --check 后回写实际结果、提交并立即停止。未经用户明确确认“继续下一阶段”，不得进入下一阶段、部署、推送或额外优化。
```

### 4.2 Agent 自主推进授权边界

允许：

- `backend-python/app/command_center/` 的只读投影、Schema、查询与测试。
- Provider Scheduler Capacity 的无行为变化共享常量抽取。
- `frontend/src/command-center/`、必要的通用 Canvas Runtime兼容调整和相关测试。
- 新计划文档的状态、实施记录、验证证据与剩余风险。

禁止：

- 修改 Review、Scheduler、Agent、Provider、Notification、Feedback、Evaluation 或 Policy 状态机。
- 新增表、迁移、索引、缓存、物化视图、WebSocket、SSE 或第三方动画依赖。
- 修改全局 Queue/Failure Drawer 产品行为、重构整个 AppFrame 或维护 legacy Java 后端。
- 自动部署、推送、进入下一阶段或处理本阶段外的既有未跟踪文档。

## 五、Phase 5A：Runtime v2 与静态双路线地图

### 5.1 落地 Prompt

```text
执行 Phase 5A。先将计划状态更新为 PHASE 5A IN PROGRESS，然后实现 Runtime v2 Review Lane 契约、真实队头顺序、共享 Standard Capacity、前端 v1/v2 兼容、静态双路线地图、运行 Review 跳转和溢出 Modal。移除 Task/Flow 选择、GitLab/Manual、Rule Analysis、五阶段节点、Flow Dock 和页面内 Queue/Failure 按钮。完成后执行后端契约/单元测试、前端专项/全量测试、生产构建、真实 MySQL EXPLAIN、1440×900/1024×800/390×844 浏览器验收和 git diff --check。回写结果，状态设为 PHASE 5A COMPLETED — WAITING FOR STRUCTURE AND INFORMATION DENSITY CONFIRMATION，提交并立即停止。
```

### 5.2 验收标准

- Runtime v2 精确返回两条 Lane 的容量、运行数、等待数、运行项、队头、截断和顺序语义。
- v1 响应能降级展示且不虚构队头；未知字段/状态不导致首页崩溃。
- 首页不存在 Task/Flow Selector、GitLab/Manual、Rule Analysis、结果区、Flow Dock 或重复 Queue/Failure 按钮。
- Empty、Standard-only、Agent-only、混合、队列积压、容量为零、Worker 离线、Fallback、Stale、错误保留旧快照和运行项溢出均有确定 DOM 表达。
- 运行 Review 直接跳转；`+N` Modal 可键盘打开、逐项跳转、关闭并返回焦点；队头和基地不交互。
- 1440×900、1024×800、390×844 均无横向溢出，能看到两条路线的负载、运行项、队头和剩余队列。
- Phase 5A 专项、前端全量、受影响 Python 测试、生产构建、MySQL EXPLAIN、浏览器控制台和 `git diff --check` 全部通过。

### 5.3 停止点

Phase 5A 完成后状态更新为 `PHASE 5A COMPLETED — WAITING FOR STRUCTURE AND INFORMATION DENSITY CONFIRMATION`，提交实际修改、测试、构建、EXPLAIN、三视口截图和剩余风险后立即停止。未经确认不得进入 Phase 5B。

## 六、Phase 5B：塔防地图动态与视觉强化

### 6.1 落地 Prompt

```text
仅在用户确认 Phase 5A 结构与信息密度后执行 Phase 5B。保持 Runtime v2 和 DOM 交互不变，在同一 Canvas/RAF 帧管线内增加候场脉冲、分流道路、Standard 调用光流、Agent Worker 心跳和真实 Review 移动。不得创建模拟业务任务或第二条动画循环。完成效果、性能、reduced-motion、失败回退、三视口验收后，状态设为 PHASE 5B COMPLETED — WAITING FOR MAP EFFECT CONFIRMATION，提交并停止。
```

### 6.2 停止点

未经用户确认地图效果强度，不得进入 Phase 5C。

## 七、Phase 5C：性能、无障碍与真实环境收口

### 7.1 落地 Prompt

```text
仅在用户确认 Phase 5B 效果后执行 Phase 5C。完成纯键盘、Modal 焦点返回、hidden/visible、失败回退、60 秒以上资源观察、真实数据密度、三视口和控制台最终验收。只修复验收暴露的真实缺陷，不改变已确认结构与视觉。完成后状态设为 PHASE 5 COMPLETED — WAITING FOR DEPLOYMENT OR REAL ENVIRONMENT CONFIRMATION，提交并停止，不部署、不推送。
```

### 7.2 性能门禁

- 观察不少于 60 秒并覆盖至少 12 次 Runtime 刷新。
- Canvas、Controller、Timer、RAF、ResizeObserver、Listener 和 DOM 数量不增长。
- 平均绘制不超过 4ms，超过 8ms 帧比例低于 1%。

## 八、当前阶段记录

### 8.1 Phase 5A 实施结果

- Runtime 已升级为 `command-center-runtime-v2`，新增 Standard/Agent Lane 容量、运行数、等待数、运行项、队头、截断和固定顺序语义；原 v1 字段继续保留。
- Provider Scheduler 的容量 `10` 已抽取为只读共享常量，调度器与 Command Center 使用同一来源，未修改调度行为。
- Standard 队头使用 `priority ASC, queued_at ASC, id ASC`；Agent 队头使用 `priority DESC, queued_at ASC, id ASC`。Fallback Standard Job 归入 Standard Lane。
- Worker 绑定复用 Runtime 已加载的 Worker `active_job_id`，没有为地图新增 Agent Run/Worker join，也没有修改 Agent claim 或 Provider Scheduler 状态机。
- 首页已移除 Task/Flow Selector、GitLab/Manual、Rule Analysis、结果区、Flow Dock 和页面内 Queue/Failure 按钮，替换为共享候场区、Standard Review 工坊和 Agent Review 基地。
- DOM Overlay 负责全部文字、键盘与 Review 跳转；Canvas 仅绘制静态日光地形和双路线。旧五阶段 Topology、Focus helper 与旧 Renderer 已删除。
- 运行项按 1440/1024/390 分别显示 6/4/2 条，超出后通过 `+N` Ant Design Modal 展示完整有界列表；`zoneKey` 保持稳定，候选和基地保持非交互。

### 8.2 验证证据

- Python Ruff：受影响 Command Center、Scheduler Capacity 与测试文件全部通过。
- Python 受影响测试：`32 passed`，覆盖 Runtime v2 契约、空态、双路线队头顺序、Fallback、Worker 绑定、过滤、查询数量与共享容量。
- 前端专项：Command Center Model、Presentation、信息架构、静态 Renderer、Canvas Runtime 和轮询生命周期共 `25 passed`。
- 前端全量：`node --test` 共 `86 passed`、`0 failed`。
- 生产构建：`scripts/run-frontend.cmd build` 通过；仅保留仓库既有的大 Chunk 警告。
- 真实 MySQL EXPLAIN：Scheduler Job 使用 `idx_code_quality_scheduler_jobs_status_priority`，Project 使用主键，Review Result 使用 `uk_code_quality_result_task_review_key`；无全表扫描，无需新增迁移或索引。
- 浏览器：1440×900、1024×800、390×844 均无横向溢出；桌面/平板为单 Canvas，390 使用 `SMALL_SCREEN` 完整 DOM fallback；控制台无 Error/Warning。
- 稳定性：持续观察超过 60 秒且覆盖不少于 12 次 Runtime 刷新；Canvas/Map 始终各 1 个，Observer/Listener 各 1 个，活动 RAF 为 0，平均绘制约 `0.11ms`、最大约 `0.20ms`、超 8ms 帧为 0。
- `git diff --check` 通过。

### 8.3 剩余验证边界

- 当前真实环境快照为空队列；混合运行、Fallback、Worker 绑定、队头与溢出 Modal 已由契约/模型/组件边界测试覆盖，但仍建议用户在真实积压数据出现时重点确认信息密度。
- 额外执行整个 Code Quality 合约文件时出现 3 个与本次范围无关的既有顺序敏感失败；本次唯一受影响的 Scheduler Capacity 用例已单独通过，不在 Phase 5A 修改范围内扩展修复。

Phase 5A 到此停止。下一步只在用户明确确认“继续下一阶段”后执行 Phase 5B。
