# AI Review Command Center Evolution Plan v2

## 当前执行状态

- 当前阶段：`Evolution Plan v2 文档落地`
- 当前状态：`EVOLUTION PLAN V2 READY — WAITING FOR SPATIAL MODEL AUTHORIZATION`
- 实施基线 Commit：`dfe20a9`
- 参考图：`docs/AI Review Center Design/assets/ai-review-command-center-reference.png`
- 计划创建时间：2026-08-03
- 当前授权：仅允许新增本文档，不允许修改代码、旧计划或 README。
- 当前停止点：计划文档落地后停止；未经用户明确确认，不得执行 Evolution Phase 1。

本文档是 Phase 5A～5C 完成后的新视觉架构总控。`AI Review Platform Runtime Map Implementation Plan.md` 继续作为 Phase 5 历史实施记录，不再追加 Evolution v2 的阶段状态。

## 一、演进结论

### 1.1 目标

将当前 `Review Runtime Dashboard` 升级为 `AI Review Operation Map`。首页仍然回答平台负载、双路线运行、前方队列和下一候选等运行问题，但空间表达从三个并列区域改为一张具备入口、调度核心、分流路线和汇聚终点的完整作战地图。

Evolution v2 固定采用以下空间拓扑：

```text
Queue Gate → AI Review Core ┬→ Standard Lane ┬→ Result Beacon
                            └→ Agent Lane ────┘
```

第一阶段只重置空间模型，不延续或增加当前页面动画。后续动效必须在新空间结构确认后重新设计，不能直接迁移 Phase 5B 的动画方案。

### 1.2 可行性

可行性高，且 Evolution Phase 1 不需要后端变更：

- `command-center-runtime-v2` 已提供 Standard/Agent Lane 的容量、运行数、等待数、运行项、下一候选、顺序语义和截断信息。
- Agent Worker Pool 已提供在线、忙碌、排空、容量和运行 Job 绑定，可直接投影到 Agent Lane。
- 当前前端已具备 Runtime v1/v2 兼容、5 秒轮询、旧快照保留、运行 Review 跳转、溢出 Modal 和完整 DOM fallback。
- 当前单 Canvas、ResizeObserver 和失败回退边界可以继续作为静态地形与道路基础，但 Phase 5B 动画绘制逻辑不进入新架构。

### 1.3 参考图使用原则

参考图只用于确认空间关系、视觉重心和路线汇聚方式，不作为数据契约：

- 采用左侧 Queue Gate、中央 AI Review Core、上下双 Lane、右侧 Result Beacon 的整体关系。
- 不复制参考图中的今日完成、通过率、调度健康度、平均处理时长、吞吐趋势或资源利用率等当前 Runtime 无法精确证明的数据。
- 不虚构 Provider 调度站、Planner、Retriever、结果校验站、模型推理站等处理节点及其容量。
- 不将参考图作为页面背景图，也不依赖其像素尺寸实现布局。

## 二、当前实现与目标差距

### 2.1 当前实现基础

当前 Phase 5C 页面已经实现：

- 顶部平台级 Runtime HUD，无 Task/Flow 选择器和重复 Queue/Failure 按钮。
- 左侧共享候场区，右侧 Standard Review 工坊与 Agent Review 基地。
- 两条路线的真实运行 Review、容量、等待数、下一候选和 Fallback 标识。
- 运行 Review 直接进入任务详情，超出可见数量后通过 Modal 查看有界完整列表。
- 桌面/平板单 Canvas，小屏和 Canvas 失败时使用完整 DOM fallback。

### 2.2 核心差距

1. **空间仍是 Dashboard 分区**：DOM 是“左侧候场卡 + 右侧两个大型基地卡”，三个区域彼此独立，缺少一张地图的连续空间感。
2. **缺少调度核心**：Canvas 中存在分流交点，但 DOM 和 Presentation 没有稳定的 `AI Review Core` 节点，用户无法感知队列如何进入统一调度再分流。
3. **缺少汇聚终点**：两条路线在地图右侧终止，没有共同的 Result Beacon，生命周期空间表达不闭合。
4. **道路与节点未对齐**：Canvas 使用容器百分比计算道路，DOM 使用 CSS Grid 布局；尺寸变化时道路并非由真实节点位置驱动。
5. **运行项仍像卡片列表**：Review Marker 被放在完整 Lane 面板内，强化了卡片 Dashboard 观感，而非沿作战路线分布的运行站。
6. **旧动效绑定旧空间**：候场脉冲、路线能量、移动 Review 和 Worker 心跳围绕旧分流几何实现，不能作为新 Operation Map 的动效基础。
7. **小屏只是模块堆叠**：当前 390px fallback 能保留信息，但尚未明确表达 Gate、Core、双 Lane 和 Beacon 的单图顺序。

## 三、Evolution v2 空间与投影设计

### 3.1 Runtime 接口边界

Evolution Phase 1 不修改任何公开接口：

- 继续请求 `GET /api/command-center/runtime`。
- 继续接受 `schemaVersion = command-center-runtime-v2`，保留 Runtime v1 降级语义。
- 不新增、删除或重命名后端字段。
- 不修改 Standard 队列顺序、Agent Claim 顺序、容量来源、Fallback 归属或 Worker 状态语义。
- Result Beacon 不增加完成结果查询，也不从 `activeFlows`、告警或更新时间推导完成统计。

### 3.2 前端 Presentation 目标结构

Runtime Model 保持不变，仅调整 Command Center 内部 Presentation：

```text
map
├── zoneKey: ai-review-operation-map
├── queueGate
│   └── zoneKey: queue-gate
├── core
│   └── zoneKey: ai-review-core
├── lanes
│   ├── zoneKey: standard
│   └── zoneKey: agent
├── resultBeacon
│   └── zoneKey: result-beacon
├── connections
└── scene
```

固定连接关系：

```text
queue-gate    → ai-review-core
ai-review-core → standard
ai-review-core → agent
standard       → result-beacon
agent          → result-beacon
```

投影规则：

- `queueGate` 使用两条 Runtime Lane 的 `queuedCount` 和 `nextQueued`，不得从聚合 Flow 推断队头。
- `core` 使用 Standard/Agent 的运行数、容量和利用率，以及 Runtime 新鲜度；不设置健康评分。
- `standard` 与 `agent` 继续使用现有稳定 Lane Key，确保溢出 Modal 和 Review 跳转不需要改变业务参数。
- `resultBeacon` 只包含固定标题、说明和 `STRUCTURAL_ONLY` 展示语义，不包含业务统计。
- `connections` 是稳定的 Presentation 拓扑，不受当前是否有运行任务影响。

### 3.3 五个地图节点

#### Queue Gate

- 展示等待总数、Standard/Agent 分队等待数。
- 展示两条真实下一候选的项目名、Review 名称和 Provider/Model。
- 下一候选保持非交互；队列详情继续由全局右上角入口承载。
- 空队列显示“当前无等待 Review”，Runtime v1 有等待但无队头时继续明确说明顺序不可用。

#### AI Review Core

- 作为 Queue Gate 与双 Lane 之间唯一分流核心。
- 展示平台运行数/总容量、平台利用率和 Runtime 新鲜度。
- 不展示 Task ID，不提供点击或配置入口。
- 容量为零时显示真实 `0` 或不可用语义，不使用虚构默认容量。

#### Standard Lane

- 展示真实 Standard Capacity、利用率、等待数和运行 Review。
- Review 主文本为项目名，副文本为 Review 名称、Provider/Model 和阶段。
- Agent 降级后的 Standard Job 继续归入本 Lane，并使用 Fallback 琥珀标识。
- 使用紧凑容量轨道与运行站，不创建 Provider 子站或阶段计数。

#### Agent Lane

- 展示真实在线 Worker Capacity、利用率、等待数和运行 Review。
- Worker 以静态状态塔或状态槽表达 `IDLE/BUSY/DRAINING/OFFLINE`，不添加心跳动画。
- 运行项继续通过真实 `workerId/activeJobId` 绑定；缺失绑定时不虚构 Worker。
- 不因 Worker 全忙把排队项画入 Standard Lane。

#### Result Beacon

- 作为 Standard 与 Agent 路线的共同空间终点。
- 固定显示“结果回流至任务详情与既有通知链路”。
- 第一阶段不展示完成数、失败数、Finding 数、通过率或通知状态。
- 保持非交互，不承担任务详情或通知入口职责。

### 3.4 桌面和平板空间模型

桌面与 1024px 平板保持同一语义网格：

```text
"gate core standard beacon"
"gate core agent    beacon"
```

- Queue Gate、AI Review Core 和 Result Beacon 跨两行居中。
- Standard Lane 位于上路，Agent Lane 位于下路。
- 整个地图只有一个连续地形底板；各节点使用紧凑站点外观，不恢复大型独立卡片面板。
- DOM Overlay 决定节点真实位置。Canvas 在绘制前读取五个 `data-zone-key` 节点相对地图容器的边界，以中心点或指定接入点作为道路锚点。
- 道路不使用固定百分比终点；ResizeObserver、Snapshot 更新或节点尺寸变化后重新测量并静态重绘。
- Review Marker 沿 Lane 内部轨道排布，1440/1024 的可见数量继续遵守现有 6/4 限制，超出后保留 `+N` Modal。

### 3.5 390px 纵向单图

小屏固定采用以下 DOM 顺序：

```text
Queue Gate
    ↓
AI Review Core
    ↓
Standard Lane
    ↓
Agent Lane
    ↓
Result Beacon
```

- 不挂载 Canvas，不产生横向滚动。
- Standard/Agent 仍是从 Core 分流后汇聚至 Beacon 的两条语义路线；纵向顺序仅是小屏可读性降级，不改变业务先后关系。
- 每条 Lane 最多显示 2 个运行 Review，超出后继续使用 Modal。
- DOM 必须保留等待总数、两条下一候选、双 Lane 负载、运行项和 Result Beacon。

### 3.6 DOM、Canvas 与交互边界

- DOM Overlay 独占全部文字、按钮、键盘焦点、Review 跳转和 Modal。
- Canvas 保持 `aria-hidden`，只绘制静态地形、道路、分流与汇聚结构，可绘制不带动画的装饰性节点底座。
- Canvas 初始化失败、绘制失败或小屏时，DOM 不依赖 Canvas 仍可完整理解地图。
- 运行 Review 保持原生 Button，跳转路径继续为 `/tasks/{taskId}?reviewKey={reviewKey}`。
- Queue Gate、AI Review Core、下一候选、Lane 本体、Worker 状态和 Result Beacon 均不设置 Button role。
- Modal 继续使用稳定 Lane Key 从最新 Runtime Presentation 派生列表，并在关闭后返回触发塔或刷新按钮。

## 四、Evolution Phase 1：静态空间架构重置

### 4.1 授权范围

仅在用户明确确认执行 Evolution Phase 1 后允许修改：

- `frontend/src/command-center/` 内的页面、Presentation、地图 DOM、静态 Renderer 和样式。
- Command Center 相关前端测试。
- 本文档的阶段状态、实施记录和验证证据。

不允许修改：

- `backend-python/` Runtime Schema、Repository、Service 或 API。
- Review、Scheduler、Agent、Provider、Fallback、Notification 等业务状态机。
- 共享 Canvas Runtime，除非现有公开能力无法实现静态重绘；发生该情况必须先停止并说明原因。
- 全局 Queue/Failure Drawer、AppFrame、任务详情、设置页和 legacy Java 后端。

### 4.2 实施顺序

1. 将本文档状态更新为 `EVOLUTION PHASE 1 IN PROGRESS`。
2. 先调整 Presentation 拓扑和测试，建立五个节点与五条连接的稳定内部契约。
3. 重构 DOM Overlay 为单地图网格，保留 Review 跳转和溢出 Modal。
4. 将 Renderer 改为读取 DOM 锚点的静态道路绘制。
5. 移除候场脉冲、路线能量、移动 Review、Worker 心跳及相关动画 helper。
6. 确认 Canvas 仅在初始化、Resize 和 Snapshot 更新时绘制，活动 RAF 恒为 0。
7. 完成专项测试、全量前端测试、构建、三视口浏览器验收和差异检查。
8. 回写实施结果和证据，将状态更新为停止点，提交并停止。

### 4.3 第一阶段验收标准

- 页面一眼可识别 Queue Gate、AI Review Core、Standard Lane、Agent Lane 和 Result Beacon。
- 桌面/平板两条路线从 Core 分流并在 Beacon 汇聚，不再表现为三个独立大面板。
- Result Beacon 不出现任何 Runtime v2 无法证明的统计。
- Runtime API 请求、字段、轮询频率、v1 fallback、Review 跳转和 Modal 行为保持不变。
- 页面不存在 Phase 5B 候场脉冲、流光、移动 Review 或 Worker 心跳；活动 RAF 为 0。
- Canvas 道路端点来自真实 DOM 锚点，Resize 后仍对齐。
- Empty、单 Lane、混合、积压、Worker 离线、Fallback、Stale、Runtime 错误和溢出均有完整静态表达。
- 1440×900、1024×800、390×844 无横向溢出，五个地图节点均可见或可在正常纵向滚动中到达。

### 4.4 Phase 1 停止点

完成后状态必须设置为：

`EVOLUTION PHASE 1 COMPLETED — WAITING FOR SPATIAL ARCHITECTURE CONFIRMATION`

提交实际修改与验证证据后立即停止。未经用户确认空间结构，不得设计或实现新动画。

## 五、后续阶段门禁

### 5.1 Evolution Phase 2：Motion Specification

Phase 2 是纯设计阶段，不编码。只有在用户确认 Evolution Phase 1 空间结构后才能开始。

Motion Specification 必须明确：

- 哪些动效由真实 `queuedCount/runningItems/stage/worker state/freshness` 变化驱动。
- Queue Gate、Core、Standard Lane、Agent Lane 和 Result Beacon 分别允许哪些动效。
- 静态、Fresh、Stale、Runtime Error、reduced-motion、小屏和 Canvas Failure 的行为矩阵。
- 同一时刻的动效优先级、数量上限、速度、持续时间和视觉强度。
- 单 Canvas、单 RAF、无模拟任务、无第二动画循环的资源边界。
- 性能预算、自动暂停条件和用户验收截图/录屏场景。

完成状态：

`EVOLUTION PHASE 2 MOTION SPEC READY — WAITING FOR MOTION AUTHORIZATION`

### 5.2 Evolution Phase 3：新地图动效与视觉增强

只有 Motion Specification 获用户确认后才能实施。Phase 3 必须以新空间模型和已批准的事件—动效矩阵为依据，不恢复或机械迁移旧 Phase 5B 动画。

完成状态：

`EVOLUTION PHASE 3 COMPLETED — WAITING FOR VISUAL EFFECT CONFIRMATION`

### 5.3 Evolution Phase 4：最终验收

完成纯键盘、reduced-motion、失败回退、长轮询、资源稳定性、真实数据密度、三视口和生产构建验收，只修复验收暴露的真实问题，不扩展结构或动效。

完成状态：

`EVOLUTION V2 COMPLETED — WAITING FOR DEPLOYMENT CONFIRMATION`

## 六、测试与验收矩阵

### 6.1 Presentation 与信息架构

- 五个稳定节点与五条固定连接。
- Core 聚合值与 Runtime Lane 数据一致。
- Result Beacon 只有结构语义，不包含虚构结果数据。
- Standard/Agent Lane Key、运行项、下一候选、Fallback 和截断语义保持。
- 页面不存在旧三分区信息架构、旧 Phase 标记和 Phase 5B 动画入口。

### 6.2 Renderer 与资源

- 道路锚点来自 DOM 节点，不来自硬编码路线终点。
- 初始化、Resize、Runtime Snapshot 更新可触发静态重绘。
- 活动 RAF、动画 Review 数和动画 Worker 数均为 0。
- 只有一个 Canvas、一个 Controller 和一个 ResizeObserver；多次快照更新后数量不增长。
- Canvas 失败后 Controller、Observer 和 Listener 正确清理，DOM 信息保持完整。

### 6.3 数据场景

- Empty。
- Standard-only。
- Agent-only。
- Standard/Agent 混合运行。
- 双路线队列积压。
- Standard 或 Agent 容量为零。
- Worker IDLE、BUSY、DRAINING、OFFLINE。
- Agent Fallback 进入 Standard Lane。
- Stale。
- Runtime 请求失败保留最后成功快照。
- 运行项超过 1440/1024/390 可见上限。
- Runtime v1 有聚合等待但无法提供下一候选。

### 6.4 交互与响应式

- 运行 Review 可通过鼠标与键盘进入现有任务详情。
- `+N` Modal 始终展示最新快照并正确返回焦点。
- Queue Gate、Core、下一候选、Lane、Worker 状态和 Beacon 保持非交互。
- 1440×900、1024×800、390×844 无横向溢出。
- 390px 使用纵向单图且不挂载 Canvas。

### 6.5 验证命令与停止条件

每个实现阶段按影响范围执行：

- Command Center Presentation、信息架构和 Renderer 专项 Node 测试。
- 前端全量 Node 测试。
- `scripts/run-frontend.cmd build`。
- 三视口浏览器验收、控制台检查和必要的静态截图。
- `git diff --check`。

Evolution Phase 1 不修改后端、查询或 Schema，因此不执行数据库迁移、MySQL EXPLAIN 或 Python 测试。若实施中发现必须修改 Runtime 接口或数据库，立即停止并单独申请授权。

## 七、总控与分阶段落地 Prompt

### 7.1 总控 Prompt

```text
以 docs/AI Review Center Design/AI Review Command Center Evolution Plan v2.md 为唯一总控。只执行用户明确授权的 Evolution Phase；先更新文档状态，再开展该阶段工作。不得修改 Runtime v2、Review、Scheduler、Agent、Provider、Fallback、通知业务状态机，不得虚构运行数据。每阶段完成后回写验证证据、提交并立即停止，不得推送、部署或自动进入下一阶段。
```

### 7.2 Evolution Phase 1 Prompt

```text
执行 Evolution Phase 1。保持 Runtime v2 和所有 Review 业务语义不变，将 Command Center 重构为 Queue Gate → AI Review Core → Standard/Agent Lane → Result Beacon 的静态单地图。Result Beacon 仅为结构节点；冻结并移除旧 Phase 5B 动画，Canvas 不保有活动 RAF。保留真实运行 Review 跳转、溢出 Modal、Runtime v1 fallback 和完整 DOM fallback。完成三视口、场景、专项/全量前端测试、生产构建、浏览器和 git diff 验证后，将状态设为 EVOLUTION PHASE 1 COMPLETED — WAITING FOR SPATIAL ARCHITECTURE CONFIRMATION，提交并立即停止。
```

### 7.3 Evolution Phase 2 Prompt

```text
在 Evolution Phase 1 空间架构获用户确认后，仅规划新的 Motion Specification。为每种动效绑定可证明的 Runtime 事件，明确静态、动态、Stale、Runtime Error、reduced-motion、小屏和 Canvas 失败行为，以及动效优先级、数量上限和性能预算。不得编码或复用旧 Phase 5B 动画方案。状态设为 EVOLUTION PHASE 2 MOTION SPEC READY — WAITING FOR MOTION AUTHORIZATION 后停止。
```

### 7.4 Evolution Phase 3 Prompt

```text
仅在 Evolution Phase 2 Motion Specification 获用户确认后执行 Evolution Phase 3。严格按已批准的事件—动效矩阵在新 Operation Map 上实现动效和视觉增强；不得创建模拟 Review、第二 Canvas、第二 RAF 循环或未授权指标。完成性能、reduced-motion、失败回退、三视口和真实场景验收后，将状态设为 EVOLUTION PHASE 3 COMPLETED — WAITING FOR VISUAL EFFECT CONFIRMATION，提交并立即停止。
```

### 7.5 Evolution Phase 4 Prompt

```text
仅在用户确认 Evolution Phase 3 视觉效果后执行 Evolution Phase 4。完成纯键盘、焦点返回、长时间轮询、资源稳定性、Canvas 失败、Stale、真实数据密度、三视口、前端全量测试和生产构建验收。只修复验收暴露的问题，不扩展已确认结构和动效。状态设为 EVOLUTION V2 COMPLETED — WAITING FOR DEPLOYMENT CONFIRMATION，提交并立即停止，不得部署或推送。
```

## 八、Agent 自主推进边界

允许：

- 在用户授权后修改 `frontend/src/command-center/` 和直接相关前端测试。
- 回写本文档阶段状态、实施结果、验证证据和剩余风险。
- 执行只读 Runtime 请求、前端测试、构建和浏览器验收。

禁止：

- 修改 `command-center-runtime-v2` 或任何后端 Review 业务逻辑。
- 新增表、迁移、缓存、WebSocket/SSE 或第三方动画依赖。
- 虚构任务、Worker、完成数、通过率、健康度或处理站。
- 修改全局 Queue/Failure 入口、通知状态机、任务详情和设置行为。
- 更新 README、历史 Phase 5 计划或冻结的路线文档。
- 自动推送、部署或进入下一阶段。

## 九、当前计划落地记录

- 已确认参考图与当前 Phase 5C 页面之间的空间架构差距。
- 已锁定 Result Beacon 第一阶段仅为结构节点，不新增完成统计。
- 已锁定 Evolution Phase 1 冻结并移除旧 Phase 5B 动画。
- 已锁定 390px 使用无横向滚动的纵向单图。
- 本次只创建本文档；前后端代码、旧计划和 README 均不修改。

计划落地到此停止。等待用户明确授权执行 Evolution Phase 1。
