# AI Review Command Center Evolution Plan v2

## 当前执行状态

- 当前阶段：`Evolution Phase 2：Visual & Motion Specification`
- 当前状态：`EVOLUTION PHASE 2 VISUAL & MOTION SPEC READY — WAITING FOR VISUAL AUTHORIZATION`
- 实施基线 Commit：`dfe20a9`
- 参考图：`docs/AI Review Center Design/assets/ai-review-command-center-reference.png`
- 计划创建时间：2026-08-03
- 当前授权：用户已于 2026-08-03 明确授权执行 Evolution Phase 1；仅允许修改 Command Center 前端投影、页面、静态 Renderer、样式、相关测试及本文档。
- 当前授权：用户已确认 Evolution Phase 1 空间架构并授权 Evolution Phase 2；本阶段只允许设计 Visual & Motion Specification，不允许编码。
- 当前停止点：Visual & Motion Specification 已完成并提交；等待用户确认，未经确认不得进入 Evolution Phase 3。

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

### 5.1 Evolution Phase 2：Visual & Motion Specification

Phase 2 是纯设计阶段，不编码。用户已确认 Evolution Phase 1 的五节点空间架构；本阶段在不改变 Runtime 数据和业务语义的前提下，将其升级为可直接指导 Phase 3 实施的视觉与动效规格。

#### 5.1.1 目标与非目标

目标：

- 保持 `Queue Gate → AI Review Core → Standard/Agent Lane → Result Beacon` 拓扑不变，将“白色信息卡片拼装”转化为“一张地图上的道路、基地、处理站和汇聚信标”。
- AI Review Core 成为页面第一视觉重心；道路连续性成为第二视觉重心；真实 Review、Worker 和容量站点成为第三视觉重心。
- Standard 使用金色稳定处理路线，Agent 使用紫色智能推理路线；两条路线必须仅表达执行模式差异，不暗示质量高低或成功率。
- 即使 `queuedCount=0`、`runningCount=0`，地图仍有明确的在线待机生命感，但不出现任何可被误认成任务的流动标记。
- 所有事件型动效必须由 Runtime 快照或相邻两次快照的可证明差异驱动。

非目标：

- 不新增或修改接口、字段、轮询频率、业务状态机和任务跳转。
- 不展示参考图中的健康度、完成量、通过率、平均处理时长、吞吐趋势、资源利用率或未建模处理阶段。
- 不创建名为 Planner、Retriever、Model、校验站、汇总站等虚构业务节点。
- 不把运行项消失推断为完成、成功、失败或已进入 Result Beacon。
- 不追求 3D 引擎、自由缩放、拖拽、碰撞、地图编辑或模块级钻取。

#### 5.1.2 当前页面、参考图与目标方案并排差距

Phase 3 验收必须将 1440×900 实现截图与 `assets/ai-review-command-center-reference.png` 并排查看，只比较空间语言，不比较参考图中的虚构数据：

| 维度 | Phase 1 当前页 | 参考图可借鉴点 | Evolution 目标 |
| --- | --- | --- | --- |
| Core | 小型白色矩形节点 | 中央大型多层能量核心 | Core 至少形成 200～240px 视觉直径，具备底座、内核、双环和状态光，不再是普通卡片 |
| Lane | 两块大型白色容器 | 道路串联建筑站点 | 去除整块白底；路线本体、容量基座和真实运行站共同形成 Lane |
| 道路 | Canvas 线被 DOM 面板覆盖 | 从入口经核心到双路再汇聚的完整道路 | 道路走廊始终可见，节点坐落在道路上或道路旁，不能用不透明面板截断线路 |
| Standard | 青色边框卡片 | 暖金稳定路线 | 改为金色稳定处理轨道与容量站，语义仍是 Standard |
| Agent | 紫色边框卡片 | 紫色智能基地与塔 | 改为紫色推理轨道、真实 Worker 塔和运行 Review 绑定标记 |
| Beacon | 独立白色信息卡 | 道路共同终点 | 改为嵌入地形的圆形汇聚台，不承担结果统计 |
| 空状态 | 大面积白色空框 | 地形、道路与核心仍有生命感 | 保留静态建筑和低频待机呼吸；无任务流粒子 |
| 信息真实性 | 已符合 Runtime | 参考图包含不可证明指标 | 继续只显示 Runtime v2 可证明信息和固定结构说明 |

并排验收通过标准：在隐藏所有文字后，观察者仍能仅凭形状和路线识别入口、中央核心、上方金色路线、下方紫色路线和右侧汇聚点；同时页面不能被误认为五张 Dashboard 卡片。

#### 5.1.3 视觉层级与构图

1440 桌面视觉权重固定为：

1. **AI Review Core**：全图唯一高对比、大体积、持续待机呼吸的对象。
2. **连续道路**：Queue→Core 主干、Core→Standard/Agent 分流、双 Lane→Beacon 汇聚全程可读。
3. **真实运行节点**：运行 Review、Worker 塔、容量站；仅在数据存在时增强亮度。
4. **Queue Gate 与 Result Beacon**：分别承担入口和结构终点，不与 Core 争夺视觉重心。
5. **地形与 HUD**：提供上下文但保持低对比，不新增底部统计 Dashboard。

建议桌面占比：Queue Gate 16%～18%、Core 22%～25%、双 Lane 42%～46%、Beacon 12%～14%；Core 的可见面积和光强均不得小于任一单独 Lane 站点。

地图采用以下单表面层级，后续实现不得用五个不透明容器重新切割：

```text
L0 地形底板
L1 地形纹理 / 区域轮廓 / 建筑阴影
L2 道路沟槽 / 道路表面 / 分流与汇聚节点
L3 建筑底座 / Core / Queue Gate / 容量站 / Worker 塔 / Beacon
L4 真实 Review 标记 / Worker 状态灯 / 容量占用
L5 文本与交互 DOM
L6 有界光效与状态反馈
```

Canvas 负责 L0～L2、Core 环与 L6；DOM/CSS 负责具备语义和交互的 L3～L5。单 Canvas 位于 DOM 下方，路线走廊必须避开文字和点击目标，而不是被 DOM 白底遮住。

#### 5.1.4 地形、道路与建筑视觉词汇

**地形**

- 底色采用浅冰蓝灰 `#EAF2F7` 附近色阶，保留日光地图而非深色赛博屏。
- 使用低对比等距网格、道路压痕、平台分区轮廓和少量非任务型环境点；不得使用复杂图片背景遮盖信息。
- 地形对比度低于道路，地形纹理透明度建议不超过 10%；Stale 时整体饱和度降低，不改变布局。

**道路**

- 每条道路由“阴影沟槽 → 浅色路床 → 模式色内轨 → 节点接驳环”四层组成，保证浅色背景上仍连续可读。
- Queue→Core 主干使用中性冰蓝路床并带少量琥珀入口识别，不归属 Standard 或 Agent。
- Standard 内轨固定为金色/琥珀色族，建议核心色 `#C88A16`、高亮 `#F4C451`、浅底 `#FFF1C7`。
- Agent 内轨固定为紫色族，建议核心色 `#7056D8`、高亮 `#A892FF`、浅底 `#EEE9FF`。
- 两路进入 Beacon 前保持各自颜色，在汇聚环处转换为青白结构光；不得用颜色混合暗示成功或失败。
- 道路最小可见宽度：1440 为 14px 路床/5px 内轨，1024 为 11px/4px；390 不绘 Canvas 道路，使用 DOM/CSS 纵向静态轨道。

**建筑底座**

- 所有节点使用“贴地底座 + 小体积建筑/塔 + 独立标签”的组合，不使用覆盖整个 Lane 的矩形白面板。
- 白色仅用于小面积标签、交互标记和可读性衬底；单个白色衬底不得占 Lane 区域超过 35%。
- 容量槽是容量的视觉投影，不代表业务阶段；不得给容量槽命名为 Provider、Planner、Model 等业务站。

#### 5.1.5 AI Review Core 规格

Core 由四层组成：

1. **地面基座**：六边形或圆角八边形底台，连接入口、Standard、Agent 三个接驳口。
2. **外层能量环**：表达平台在线和总利用率；环形进度仅使用真实 `totalRunning/totalCapacity`，容量为零时显示中性断环。
3. **内层调度环**：分为金色 Standard 扇区和紫色 Agent 扇区，扇区强度分别由两条 Lane 的真实利用率驱动。
4. **核心晶体/光核**：显示 `AI Review Core` 标识与真实运行数/总容量；不显示健康度或调度分。

Core 状态：

| 状态 | 可证明条件 | 视觉 | 动效 |
| --- | --- | --- | --- |
| Connecting/Empty | 尚无成功快照 | 中性灰蓝断环 | 无呼吸，仅状态点 |
| Fresh Idle | `FRESH` 且总运行/等待均为 0 | 完整低亮核心、道路待机灯 | 6 秒一次、2%～4% 幅度的低频呼吸 |
| Fresh Queued | `FRESH`、总运行为 0 且等待数大于 0 | 入口接驳口增强 | Gate 低频请求波，不向 Lane 发出虚假任务 |
| Fresh Low Load | `FRESH`、总运行大于 0 且平台利用率低于 25% | 少量泊位点亮，Core 保持中低亮度 | 4.8～6 秒呼吸；不因低负载放大任务数量 |
| Fresh Running | `FRESH`、平台利用率不低于 25% 且两条 Lane 均未饱和 | 内核亮度提升，双扇区按真实利用率显示 | 3.6～4.8 秒呼吸；真实快照变化可触发一次调度反馈 |
| Saturated | 任一 Lane 容量大于 0 且利用率达到 100% | 对应扇区外缘增强，不使用错误红 | 低频边缘警示，不闪烁 |
| Stale | `STALE` | 降饱和、环停驻、显示 Stale 标签 | 全部非必要动效停止 |
| Runtime Error | 请求失败且保留旧快照 | 保留旧值，外环出现固定断点 | 停止事件动效，不清空地图 |

Core 必须是唯一持续呼吸对象；其他建筑不得以相同频率和光强持续呼吸，防止地图处处抢焦点。

#### 5.1.6 Queue Gate、Standard Lane、Agent Lane 与 Beacon

**Queue Gate**

- 采用入口闸门和左右两个小型队列泊位，显示总等待数、Standard/Agent 分队数量和真实下一候选。
- 下一候选以两块紧凑铭牌显示，不绘制成已进入道路的任务。
- `queuedCount>0` 时只允许闸门边缘有低频请求光；不得让光点穿过 Core，除非相邻快照确认新的运行项出现。

**Standard Lane：金色稳定处理路线**

- 上路为金色连续轨道，视觉关键词为稳定、规则、可预期；不再使用青色大面板。
- `capacity` 投影为沿轨道排列的容量泊位，最多直接显示 10 个；更多容量使用末端 `+N` 容量基座，不虚构更多业务站。
- `runningItems` 占据真实容量泊位，表现为可点击的金色处理站标记；Fallback 使用琥珀外圈和固定 `Fallback` 标识，但仍位于 Standard Lane。
- Provider/Model、Review 名称和阶段放在站点附近的小标签中；主文本仍是项目名，不显示 Task ID。
- 无运行项时保留空泊位轮廓和低亮轨道，不展示大面积“空闲卡片”。

**Agent Lane：紫色智能推理路线**

- 下路为紫色连续轨道，视觉关键词为智能、推理、Worker 协同；不得使用比 Core 更强的持续光效。
- 每个真实 Worker 映射为一个塔：`IDLE` 青紫常亮、`BUSY` 紫色实心、`DRAINING` 琥珀环、`OFFLINE` 灰色低亮。
- 当运行项的 `workerId/activeJobId` 可绑定时，Review 标记附着在对应 Worker 塔的轨道插槽；缺失绑定时放入 Lane 的“未绑定运行位”，不得虚构 Worker。
- Worker 多于视口上限时使用 `+N Worker` 静态聚合塔；该塔第一阶段不点击。
- 阶段变化只更新该 Review 标记的环形状态和一次短反馈，不在道路上创建额外处理站。

**Result Beacon**

- 采用嵌入地形的圆形汇聚台，Standard 和 Agent 道路从上下两侧进入同一个基座。
- 只显示固定文案“结果回流至任务详情与既有通知链路”，不使用白色信息卡边界。
- 因 Runtime v2 没有完成事件，Beacon 只允许与平台 Fresh 状态绑定的低亮待机光；不得根据运行项消失播放抵达、成功或失败动效。
- Runtime Error/Stale 时 Beacon 保持静态结构可见，不显示完成数量或红色失败状态。

#### 5.1.7 Review、Worker 与容量的地图化规则

- Review Marker 由“模式色底座 + 项目名 + Review 名称 + Provider/Model + 阶段微标签”组成，点击区域保持原生 Button 和既有跳转。
- 1440 每条 Lane 最多显示 6 个运行 Review，1024 最多 4 个，390 最多 2 个；其余继续使用 `+N` 聚合塔与既有 Modal。
- Marker 面积应显著小于当前卡片，推荐 88～118px 宽、56～72px 高；标签可悬浮在轨道旁，但不得挡住主道路超过其宽度的 40%。
- Standard 容量由泊位数量表达，Agent 容量由在线 Worker Capacity 与塔表达；两者不得在前端设置默认值。
- `capacity=0` 时保留关闭的基座轮廓并显示“Capacity 0/不可用”，不能画出可用空槽。
- 所有状态颜色必须同时具备形状或文字差异，不能仅靠颜色区分 Fallback、Worker 状态或 Stale。

#### 5.1.8 Runtime 事件—动效矩阵

动效只允许由下列证据触发：

| Runtime 证据 | 允许的反馈 | 禁止推断 |
| --- | --- | --- |
| `freshness` 变为 `FRESH` | Core 恢复待机呼吸，道路恢复模式色 | 系统健康优秀 |
| `freshness` 变为 `STALE` | 全图降饱和并冻结事件动效 | 任务失败 |
| 首次获得成功快照 | 地图从中性结构淡入真实状态，600ms 内完成 | 平台刚启动 |
| `queuedCount` 从 0 变为正数 | Gate 请求灯一次亮起；队列泊位更新 | 某个具体任务已开始 |
| `nextQueued` 身份变化 | 对应下一候选铭牌 300ms 交叉淡入 | 旧候选已成功执行 |
| 新 `runningItems` 身份出现在某 Lane | Core 对应扇区一次调度反馈，沿目标道路发送一个与该 Review 绑定的光标至其站点 | 精确调度耗时、队列出队原因 |
| 已有运行项 `stage` 变化 | 对应 Marker 外环一次 450ms 状态确认 | 阶段百分比或剩余时间 |
| Worker `state` 变化 | 对应 Worker 塔状态灯一次切换反馈 | Worker 性能、健康分 |
| 利用率变化 | Core 扇区和 Lane 容量占用平滑过渡 300～500ms | 趋势或预测 |
| 运行项从快照消失 | 仅移除 Marker | 完成、失败、取消或抵达 Beacon |
| Runtime 请求失败并保留旧快照 | 外环固定断点、错误说明保持 DOM | 旧快照仍实时 |

新运行项调度反馈必须按 `jobId/taskId/reviewKey` 去重；同一快照最多播放 2 条，更多变化以 Core 单次扇区反馈和静态站点更新合并表达。

#### 5.1.9 动效优先级、节奏与资源预算

优先级从高到低：

1. `P0` Stale/Error/隐藏页：立即冻结或降级。
2. `P1` 新运行项确认：Core→目标 Lane 一次性调度反馈。
3. `P2` Stage/Worker 状态变化：局部一次性反馈。
4. `P3` Queue 请求和利用率变化：低强度反馈。
5. `P4` Fresh Idle 环境生命感：Core 呼吸、极低密度环境微光。

节奏与上限：

- 只允许一个 Canvas、一个 Controller、一个 ResizeObserver、一个 RAF 所有者；不得使用第二 Canvas、`setInterval`、独立粒子循环或第三方动画库。
- Fresh Idle 采用最高 12fps 绘制节奏；出现 P1/P2 事件时可临时提升至最高 30fps，事件结束后回落。
- 同屏事件型道路光标最多 2 个；Core 环最多 2 个动态层；环境粒子最多 24 个且不得沿道路移动或使用 Review 形状。
- Core 呼吸周期 3.6～6 秒，亮度变化不超过 14%；事件反馈 300～900ms；禁止频闪、爆炸、抖动和无限旋转。
- 平均 Canvas 绘制不超过 4ms，超 8ms 帧低于 1%；连续 3 秒超过预算时先关闭环境粒子，再降低至 12fps，最后只保留静态地图。
- 页面隐藏时 RAF 为 0；重新可见后根据最新快照恢复，不补播隐藏期间事件。

环境生命感不属于任务数据：只允许核心呼吸、地形微光和建筑待机灯；环境粒子必须远离道路中心线，不能带项目名、任务形状或方向箭头。

#### 5.1.10 状态与降级矩阵

| 场景 | 1440/1024 Canvas | DOM | 动效 |
| --- | --- | --- | --- |
| Fresh Idle | 完整地形、道路、建筑底座 | 五节点和真实 0 值完整 | Core 低频呼吸；无任务光标 |
| Fresh Running | 完整地图与真实状态 | Review/Worker/容量可读可操作 | 单 RAF，有界事件反馈 |
| Stale | 保留最后地图并降饱和 | Stale 文案和旧值完整 | RAF 0 |
| Runtime Error | 保留最后成功快照 | Error 提示，不清空节点 | RAF 0 |
| reduced-motion | 完整静态 Canvas 或一次静态绘制 | 信息与交互完整 | RAF 0、过渡时长 0 |
| Canvas Failure | 不挂载/清理 Canvas | CSS 静态地形、轨道、五节点完整 | 0 |
| 页面隐藏 | 保留资源所有权 | 无变化 | RAF 0 |
| 390×844 | 不挂载 Canvas | 纵向 Gate→Core→Standard→Agent→Beacon；轨道由 CSS 静态表达 | 0 |

三视口细化：

- **1440×900**：完整等距地形；Core 建议视觉直径 200～240px；每 Lane 最多 6 个 Review、最多 8 个 Worker 塔、环境粒子最多 24 个；五节点在首屏形成完整闭环。
- **1024×800**：保持相同左右拓扑，不改成 Dashboard 堆叠；Core 缩至 160～190px；每 Lane 最多 4 个 Review、最多 4 个 Worker 塔加 `+N`；隐藏非关键描述而不隐藏容量、等待、下一候选和阶段；环境粒子最多 12 个。
- **390×844**：不尝试缩小桌面塔防地图，也不挂载 Canvas；Core 使用紧凑双环徽记；Standard/Agent 各自保持金色/紫色纵向轨道；Worker 和 Review 使用两列站点；Beacon 作为纵向终点。所有节点正常滚动可达，无横向滚动。

所有视口的正文、数字和交互标签继续以 `#17324D` 附近深蓝为主，并在实际衬底上满足 WCAG AA；光晕、颜色和粒子不得成为唯一状态载体。

#### 5.1.11 Phase 3 实施切片与停止条件

Phase 3 获授权后按以下顺序编码，不得一次混合重写数据层：

1. 先建立 Visual Token、地图层级和无大白卡的静态道路/建筑底座。
2. 将 Core、Standard 容量泊位、Agent Worker 塔、Review Marker 和 Beacon 地图化，保持交互不变。
3. 完成三视口静态截图并与参考图并排确认空间语言；若仍像 Dashboard，停止动效实现并修正静态层。
4. 再实现 Runtime 差异检测与事件—动效矩阵，确保运行项消失不触发结果动画。
5. 加入 reduced-motion、Stale/Error、Canvas Failure 和性能自动降级。
6. 完成专项/全量测试、生产构建、浏览器验收和资源稳定性检查后提交并停止。

#### 5.1.12 用户要求追踪

| 用户要求 | 规格落点 |
| --- | --- |
| 去除 Standard/Agent 大型白卡 | 5.1.2、5.1.4、5.1.6、6.6 |
| Core 成为第一视觉重心 | 5.1.3、5.1.5 |
| 连续道路且不被面板遮挡 | 5.1.3、5.1.4 |
| 低负载和零任务生命感 | 5.1.5、5.1.8～5.1.10 |
| 金色 Standard、紫色 Agent | 5.1.4、5.1.6 |
| Worker/Review/容量地图化 | 5.1.6、5.1.7 |
| Beacon 融入地图 | 5.1.6 |
| 地形、道路、底座、光效、粒子、状态、层级和三视口 | 5.1.3～5.1.10 |
| 参考图并排且不虚构数据 | 5.1.1、5.1.2、6.6 |
| Phase 2 完成后停止 | 5.1.11、7.3、当前执行状态 |

Phase 2 完成状态：

`EVOLUTION PHASE 2 VISUAL & MOTION SPEC READY — WAITING FOR VISUAL AUTHORIZATION`

### 5.2 Evolution Phase 3：新地图动效与视觉增强

只有 Visual & Motion Specification 获用户确认后才能实施。Phase 3 必须以新空间模型、视觉层级和已批准的事件—动效矩阵为依据，不恢复或机械迁移旧 Phase 5B 动画。

完成状态：

`EVOLUTION PHASE 3 COMPLETED — WAITING FOR VISUAL EFFECT CONFIRMATION`

### 5.3 Evolution Phase 4：最终验收

完成纯键盘、reduced-motion、失败回退、长轮询、资源稳定性、真实数据密度、三视口和生产构建验收，只修复验收暴露的真实问题，不扩展结构或动效。

完成状态：

`EVOLUTION V2 COMPLETED — WAITING FOR DEPLOYMENT CONFIRMATION`

## 六、测试与验收矩阵

6.1～6.5 记录 Phase 1 已建立的数据、交互和静态回退基线；Phase 3 实施视觉与动效时必须继续全部通过，并追加 6.6 的视觉与动效验收。

### 6.1 Presentation 与信息架构

- 五个稳定节点与五条固定连接。
- Core 聚合值与 Runtime Lane 数据一致。
- Result Beacon 只有结构语义，不包含虚构结果数据。
- Standard/Agent Lane Key、运行项、下一候选、Fallback 和截断语义保持。
- 页面不存在旧三分区信息架构、旧 Phase 标记和 Phase 5B 动画入口。

### 6.2 Renderer 与资源

- 道路锚点来自 DOM 节点，不来自硬编码路线终点。
- 初始化、Resize、Runtime Snapshot 更新可触发静态重绘。
- Phase 1 静态基线的活动 RAF、动画 Review 数和动画 Worker 数均为 0；Phase 3 只有符合 5.1.8 的真实事件或 Fresh Idle 待机生命感才允许启动单 RAF。
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

### 6.6 Phase 3 视觉与动效专项验收

- 1440 实现截图与参考图并排：仅比较 Core 权重、道路连续性、建筑底座、双路线区分和 Beacon 汇聚；不得补齐参考图中的虚构指标。
- 将页面截图转为灰度或临时隐藏文字后，仍能识别 Core 为第一视觉重心、Standard 为上方稳定路线、Agent 为下方智能路线。
- Lane 和 Beacon 不存在覆盖路线的大型白色卡片；任一 Lane 的白色标签衬底面积不超过该 Lane 可见区域的 35%。
- Fresh Idle 至少连续观察 20 秒：只有 Core、环境微光和建筑待机灯产生生命感，任务道路上不存在 Review 形状或方向性流动标记。
- 新运行项、Stage 变化、Worker 状态变化分别使用确定性快照夹具验收；每个反馈均可追溯至具体字段差异并按身份去重。
- 运行项从快照消失时不得触发 Beacon 抵达、成功、失败或完成反馈。
- Stale、Runtime Error、reduced-motion、页面隐藏、Canvas Failure 和 390px 的 RAF 均为 0，DOM 信息与交互完整。
- 1440/1024 的单 Canvas、单 Controller、单 Observer、单 RAF 所有者不随 12 次以上 Runtime 更新增长；390 不挂载 Canvas。
- Fresh Idle 平均绘制不超过 4ms，超 8ms 帧低于 1%；触发自动降级时顺序符合“环境粒子→帧率→静态地图”。

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
在 Evolution Phase 1 空间架构获用户确认后，仅规划新的 Visual & Motion Specification，不编码。重点解决大型白卡观感、Core 第一视觉重心、连续道路、零任务生命感、金色 Standard、紫色 Agent、Worker/Review/容量地图站点化和 Beacon 汇聚；明确地形、道路、建筑、光效、粒子、状态、视觉层级、Runtime 事件绑定、资源预算及 1440/1024/390 降级。使用参考图并排验收空间语言，但不得复制 Runtime 无法证明的指标或处理站。状态设为 EVOLUTION PHASE 2 VISUAL & MOTION SPEC READY — WAITING FOR VISUAL AUTHORIZATION 后提交并停止。
```

### 7.4 Evolution Phase 3 Prompt

```text
仅在 Evolution Phase 2 Visual & Motion Specification 获用户确认后执行 Evolution Phase 3。先实现无大型白卡的静态地图、Core、道路、容量泊位、Worker 塔、Review 站点和 Beacon，并完成参考图并排静态验收；静态空间语言通过后再严格按已批准的 Runtime 事件—动效矩阵实现单 Canvas/单 RAF 动效。不得创建模拟 Review、虚构结果、第二 Canvas、第二 RAF 循环或未授权指标。完成性能、reduced-motion、失败回退、三视口和真实场景验收后，将状态设为 EVOLUTION PHASE 3 COMPLETED — WAITING FOR VISUAL EFFECT CONFIRMATION，提交并立即停止。
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

### Evolution Phase 1 实施记录

- 2026-08-03：用户明确授权执行 Evolution Phase 1，状态更新为 `EVOLUTION PHASE 1 IN PROGRESS`。
- 已将 Presentation 重置为 `ai-review-operation-map`、`queue-gate`、`ai-review-core`、`standard`、`agent`、`result-beacon` 稳定投影，并固定 Gate→Core、Core→双 Lane、双 Lane→Beacon 五条连接。
- 已将 DOM Overlay 重构为单一地图表面：桌面/平板使用 Gate、Core、上下双 Lane、Beacon 网格，小屏使用 Gate→Core→Standard→Agent→Beacon 纵向单图。
- 已保留 Runtime v2/v1 fallback、5 秒轮询、真实 Review 跳转、`+N` Modal、焦点返回、容量/队列/Fallback 和 Worker 状态语义；后端与业务状态机零修改。
- Result Beacon 仅展示“结果回流至任务详情与既有通知链路”，未新增完成数、失败数、通过率、Finding 或通知状态。
- Canvas 已改为读取五个真实 `data-zone-key` DOM 矩形并绘制静态道路；初始化、Resize 和 Runtime Snapshot 更新触发重绘，活动 RAF、动画 Review 和动画 Worker 恒为 `0`。
- 已移除 Phase 5B 候场脉冲、路线能量、移动 Review、Worker 心跳及对应动画 helper；390px 不挂载 Canvas，Canvas 失败时完整 DOM 保持可用。

### Evolution Phase 1 验证证据

- Command Center 专项 Node 测试：`13 passed`。
- 前端全量 Node 测试：`87 passed`。
- 生产构建：`scripts/run-frontend.cmd build` 成功；仅保留既有大 Chunk 提示，无构建错误。
- 1440×900：五节点均存在，五条 DOM 锚点道路，单 Canvas，`activeRaf=0`，无横向溢出。
- 1024×800：保持同一 Gate/Core/双 Lane/Beacon 拓扑，五条 DOM 锚点道路，单 Canvas，`activeRaf=0`，无横向溢出。
- 390×844：按 Gate→Core→Standard→Agent→Beacon 顺序完整可达，Canvas 数量 `0`，无横向溢出。
- 浏览器控制台：无 warning/error；`git diff --check` 通过。
- 未执行后端测试、迁移或 MySQL EXPLAIN：本阶段没有后端、接口、查询或 Schema 变更。

Evolution Phase 1 已由用户确认通过。

### Evolution Phase 2 设计记录

- 2026-08-03：用户授权进入 Evolution Phase 2，并将阶段范围从 Motion Specification 升级为 Visual & Motion Specification；本阶段仍只设计、不编码。
- 已以 Phase 1 Commit `887740a` 和本地参考图为依据完成并排差距分析；只采用参考图的空间语言，不采用其健康度、完成量、通过率、处理时长、趋势或虚构子站。
- 已固定视觉层级：Core 第一、连续道路第二、真实运行站点第三、Gate/Beacon 第四、地形/HUD 第五。
- 已固定金色 Standard 稳定路线、紫色 Agent 智能推理路线，以及容量泊位、Worker 塔、Review Marker 和结构性 Beacon 的地图化表达。
- 已定义 Fresh Idle、Running、Saturated、Stale、Runtime Error、reduced-motion、Canvas Failure、页面隐藏和 390px 的视觉/动效行为。
- 已建立 Runtime 事件—动效白名单、运行项消失禁止推断规则、单 Canvas/单 RAF 资源边界、自动降级顺序及 Phase 3 实施切片。

### Evolution Phase 2 验证证据

- 已按 5.1.12 逐项覆盖用户提出的 10 项视觉与动效要求。
- 已对照 Phase 1 页面与参考图完成空间语言审计；明确排除所有 Runtime v2 无法证明的业务数据和处理站。
- 已审计事件—动效矩阵：每个事件反馈均绑定 Runtime 字段或相邻快照的可证明身份变化，运行项消失只允许移除 Marker。
- 已审计三视口、reduced-motion、Stale、Runtime Error、页面隐藏和 Canvas Failure 降级边界。
- 本阶段仅修改本文档；未修改前端、后端、测试、README、旧计划或未跟踪资料。
- 文档差异通过 `git diff --check`；纯设计阶段不执行测试、构建或浏览器运行验收。

Evolution Phase 2 到此停止。等待用户确认 Visual & Motion Specification；不得自动进入 Phase 3 编码、推送或部署。
