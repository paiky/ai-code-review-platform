# AI Review Command Center Information Architecture Optimization Plan

## 0. 文档状态

- 文档日期：`2026-08-04`
- 当前状态：`I3 COMPLETE — WAITING FOR USER DECISION`
- 文档用途：集中记录 AI Review 指挥中心首页的信息取舍、指标语义、待确认问题和后续实施边界。
- 当前授权：I3 已完成；只允许维护本文档和报告验收结果，不得继续修改产品代码或自动进入新的优化阶段。
- 当前边界：不得修改 Runtime / Governance 后端口径、数据库、Review / Scheduler / Agent / Provider 状态机，不得创建提交、推送或部署。
- 停止点：等待用户决定创建本地提交、部署或继续优化。

本文档是首页完成后的独立信息架构优化决策稿，不续写历史 Phase，也不改变以下文档的完成状态：

- `AI Review Command Center Current Flow Audit.md`
- `AI Review Command Center Homepage vNext Implementation Plan.md`
- `AI Review Command Center Evolution Plan v2.md`
- `AI Review Command Center Implementation Plan.md`

---

## 1. 本轮已确认问题

### D1：快照覆盖范围不属于首页关注数据

当前顶部 HUD 将“快照覆盖范围”作为常驻指标，展示“未截断 / 部分截断”和“有界快照”。该信息用于解释 Runtime 投影是否受接口上限影响，属于数据可信度诊断，不是用户进入指挥中心时需要持续关注的业务结果。

确认方向：

- 从常驻指标卡移除“快照覆盖范围”；
- 正常且未截断时不占用页面空间；
- 仅在快照截断、聚合不一致或数据不可用时，通过临时提示条表达；
- 不删除 Runtime v2 中的 `coverage` 字段，它仍用于前端可信展示和诊断。

### D2：底部容量卡与双 Review 执行轨重复

底部“Agent 容量”和“Standard Provider 槽位”分别重复了 Agent Review、Standard Review 模块中已经展示的运行数、在线容量或 Provider 容量。

确认方向：

- 从底部摘要区移除“Agent 容量”；
- 从底部摘要区移除“Standard Provider 槽位”；
- 当前队列、运行数、容量和执行器状态继续由中部双 Review 执行轨负责；
- 底部摘要区不再重复表达队列或执行槽位。

### D3：Runtime 告警不作为首页核心指标

顶部与底部均展示 Runtime 告警，既重复，也将技术运行告警提升成首页核心业务指标。用户当前不关注该数据。

确认方向：

- 移除顶部 Runtime 告警指标卡；
- 移除底部 Runtime 告警指标卡；
- 普通告警不再以常驻数量卡展示；
- 只有会影响页面数据可信度或 Review 主链路可用性的错误，才通过异常提示条表达；
- Runtime v2 的 `alerts` 字段暂不删除，任务详情跳转或后续独立诊断视图仍可复用。

---

## 2. 信息架构原则

首页后续调整遵守以下原则：

1. 顶部只回答“现在是否正常、正在排队多少、正在运行多少、由谁执行”。
2. 中部只回答“任务从哪里进入、选择哪条 Review 执行轨、当前运行到哪里”。
3. 底部只回答“最近一个统计窗口产生了什么业务和质量结果”。
4. 同一事实只保留一个主要展示位置，其他区域不得换名重复。
5. 数据诊断信息默认隐藏，仅在异常或有界截断影响理解时出现。
6. 不为了保持固定卡片数量引入弱口径、推断值或用户不关注的技术指标。
7. 页面展示必须区分“当前状态”和“时间窗口统计”，不得混用口径。

---

## 3. 推荐目标结构

### 3.1 顶部：当前调度状态

推荐保留或调整为以下信息：

| 指标 | 主要值 | 辅助信息 | 时间口径 |
| --- | --- | --- | --- |
| Runtime 更新时间 | 快照生成时间 | 实时、过期或不可用 | 当前快照 |
| 排队执行数 | Scheduler 排队 Job 数 | 最长排队等待时间 | 当前状态 |
| 运行执行数 | Scheduler 运行 Job 数 | Agent / Standard 分布 | 当前状态 |
| 进行中审查任务 | 运行或审查中的 ReviewTask 数 | 与 Job 数采用不同业务实体口径 | 当前状态 |
| 当前 Provider / Model | 当前或最近可观测 Provider / Model | 最近窗口成功 / 失败次数或状态 | 当前状态 + 时间窗口辅助信息 |

说明：

- 顶部不再展示“快照覆盖范围”和“Runtime 告警”；
- 顶部固定为 5 张卡片，不为维持原有 6 张卡片补充弱指标；
- 使用“排队执行数 / 运行执行数”表达 Scheduler Job，使用“进行中审查任务”表达 ReviewTask，避免三个“任务数”混淆；
- “最长排队等待”从底部独立卡片并入“排队任务总数”辅助说明，减少垂直重复。

### 3.2 中部：当前执行拓扑

中部职责保持不变：

- 审查入口；
- 引擎选择；
- Agent Review 当前排队、运行、在线容量和执行器状态；
- Standard Review 当前排队、运行、Provider 槽位和 Provider / Model；
- Agent 到 Standard 的结构性降级关系；
- 结果持久化入口。

中部已有的队列、运行和容量信息不再在顶部或底部重新展开。

### 3.3 底部：近 24 小时质量产出

底部从“当前容量摘要”改为“时间窗口质量产出摘要”，推荐展示：

| 指标 | 推荐展示 | 价值 |
| --- | --- | --- |
| 审查任务数 | 近 24 小时创建的 ReviewTask 数 | 表达平台实际审查量 |
| Provider 执行结果 | 成功数 / 失败数，成功率作为辅助信息 | 表达模型执行可靠性 |
| 发现问题数 | 时间窗口内 Finding 总数 | 表达审查产出 |
| 受影响任务 | 受影响任务数与最高风险合并为一张卡 | 表达问题覆盖面和风险强度 |

底部不再展示 Agent 容量、Standard Provider 槽位、最长排队等待或 Runtime 告警。

---

## 4. 真实字段来源与口径

### 4.1 Runtime v2 已有字段

| 页面语义 | 字段 | 口径 |
| --- | --- | --- |
| Runtime 更新时间 | `generatedAt` | 当前快照生成时间 |
| 排队执行数 | `scheduler.queuedJobCount` | 当前 `QUEUED` Scheduler Job 数 |
| 运行执行数 | `scheduler.runningJobCount` | 当前 `RUNNING` Scheduler Job 数 |
| 进行中审查任务 | `intake.activeTaskCount` | 当前 `ReviewTask.status=RUNNING` 或 `review_status=REVIEWING` 的任务数 |
| 近 24 小时审查任务数 | `intake.taskCount` | `window.from` 之后创建的 ReviewTask 数；默认窗口为 24 小时 |
| 最长 Agent 排队等待 | `agent.queueMetrics.oldestQueuedSeconds` | 当前 Agent 队列最早排队 Job 的等待秒数 |
| Provider 执行结果 | `providersObserved[].recentSuccessCount` / `recentFailureCount` | 当前窗口内各 Provider 的成功 / 失败 Result 数 |
| Provider 最近观测时间 | `providersObserved[].lastObservedAt` | 当前窗口内最近 Result 更新时间 |

对应实现：

- Schema：`backend-python/app/command_center/schemas.py`
- 统计查询：`backend-python/app/command_center/repository.py::_load_runtime_counts`
- Provider 统计：`backend-python/app/command_center/repository.py::_load_provider_observations`
- Runtime 投影：`backend-python/app/command_center/service.py::get_runtime_snapshot`

### 4.2 Governance v1 已有字段

| 页面语义 | 字段 | 口径 |
| --- | --- | --- |
| 发现问题数 | `findingRisk.findingCount` | Governance 时间窗口内 Finding 总数 |
| 受影响任务数 | `findingRisk.affectedTaskCount` | 时间窗口内至少产生一个 Finding 的任务数 |
| 最高风险 | `findingRisk.highestRisk` | 时间窗口内最高风险等级 |
| 风险分布 | `findingRisk.severityCounts` | 时间窗口内各风险等级数量 |

Governance 接口已经存在，推荐方案不要求新增后端统计口径，但前端首页需要同时读取 Runtime 和 Governance 快照，并明确两者的加载、过期和错误边界。

### 4.3 明确不使用的数据

- `coverage.truncated`：只作为异常提示条件，不作为业务指标；
- `alerts.length`：不作为首页核心指标；
- `agent.queueMetrics.onlineCapacity`：由 Agent Review 模块展示，不在底部重复；
- `reviewLanes.standard.capacity`：由 Standard Review 模块展示，不在底部重复；
- `standard.findingCount` / `agent.findingCount`：当前是活动 Flow 的 Finding 汇总，不得误标为“近 24 小时发现问题数”。

---

## 5. I0 已冻结决策

以下 11 项决策已经用户确认。后续实施必须按本节执行；需要改变其中任一结论时，应先回到 I0 更新本文档并重新确认。

### 5.1 顶部 HUD 固定为 5 张卡片

按以下顺序展示：

1. Runtime 更新时间；
2. 排队执行数；
3. 运行执行数；
4. 进行中审查任务；
5. 当前 Provider / Model。

不保留第 6 张占位卡，不以弱指标填充固定数量。

### 5.2 保留进行中审查任务并区分实体口径

- `scheduler.queuedJobCount` 展示为“排队执行数”；
- `scheduler.runningJobCount` 展示为“运行执行数”；
- `intake.activeTaskCount` 展示为“进行中审查任务”；
- 页面文案必须明确前两项是 Scheduler Job，后一项是 ReviewTask，不再统称为“任务数”。

### 5.3 统计窗口固定为近 24 小时

- 当前版本不增加时间筛选器；
- 所有窗口统计直接显示“近 24 小时”，不得使用口径不明确的“当前窗口”；
- 未来真实增加页面时间筛选器时，再单独调整 Runtime 与 Governance 的窗口联动契约。

### 5.4 Provider 执行结果以成功 / 失败为主

- 主信息展示“成功 N / 失败 N”；
- 有执行记录时，成功率可作为辅助信息；
- 无执行记录时显示“暂无执行记录”，不得显示容易被理解为执行失败的 `0%`；
- 当前或最近可观测 Provider / Model 继续放在顶部，近 24 小时执行结果放在底部，二者不属于重复口径。

### 5.5 受影响任务与最高风险合并

底部使用一张组合卡同时展示：

- 受影响任务数；
- 最高风险等级。

该卡共同回答问题覆盖范围与风险强度，不拆分为两张卡。

### 5.6 只为存在真实落点的指标提供跳转

| 指标 | 推荐落点 | 约束 |
| --- | --- | --- |
| 近 24 小时审查任务数 | 携带近 24 小时条件的任务列表 | 必须保持统计口径一致 |
| 发现问题数 | 质量治理页或 Finding 列表 | 必须存在对应页面和可复现过滤条件 |
| 受影响任务 | 携带风险条件的任务列表 | 必须保留近 24 小时窗口 |
| Provider 执行结果 | Provider 执行记录页 | 没有真实落点前保持不可点击 |

不得为了表现可交互而加入无对应页面、无过滤条件或无法保持统计口径的链接。

### 5.7 Runtime 告警暂不建设独立入口

- Runtime `alerts` 字段继续保留；
- 普通技术告警不在首页展示，也不在本专项中新建诊断页；
- 只有数据不可用、数据过期、快照截断或 Review 主链路不可用时，首页才显示临时异常提示条；
- 独立诊断入口留待出现明确运维使用场景后另行规划。

### 5.8 Runtime 与 Governance 独立加载、局部降级

| 状态 | 页面行为 |
| --- | --- |
| Runtime 失败、Governance 成功 | 顶部与执行拓扑局部不可用，底部质量结果继续展示 |
| Runtime 成功、Governance 失败 | 顶部与执行拓扑继续展示，底部质量结果局部不可用 |
| 单资源存在 retained snapshot | 保留上次数据并标注“上次数据 · HH:mm”与过期状态 |
| Runtime 与 Governance 均失败且无 retained snapshot | 显示页面级异常与重试入口 |

单个资源失败不得清空另一个正常资源的数据。

### 5.9 移动端按关注优先级折叠

顶部优先级：

1. 运行执行数；
2. 排队执行数；
3. 进行中审查任务；
4. 当前 Provider / Model；
5. Runtime 更新时间。

底部优先保留：

1. 近 24 小时审查任务数；
2. 发现问题数；
3. 受影响任务数与最高风险；
4. Provider 执行结果。

Runtime 更新时间在空间不足时降级为页头辅助文字，不必保持独立卡片形态。

### 5.10 零值、无记录与异常文案

| 场景 | 冻结文案或规则 |
| --- | --- |
| 真实数量为零 | 显示 `0` |
| 近 24 小时无记录 | `近 24 小时暂无记录` |
| Provider 无执行记录 | `暂无执行记录` |
| Provider 不可观测 | `暂无可观测 Provider` |
| 使用 retained snapshot | `当前数据可能已过期，上次更新于 HH:mm` |
| Governance 局部失败 | `质量统计暂时无法获取` |
| Runtime 快照截断 | `部分运行数据已截断，当前指标可能不完整` |

零值、无记录、不可观测、过期和加载失败必须使用不同语义，不得统一显示为 `--`。

### 5.11 100% 缩放下宽屏密度基线

用户提供的 100% 缩放截图约为 `1915×909`。当前页面在该视口下进入 `min-width: 1200px` 的桌面布局，并同时受到以下规则影响：

- 页面使用 `min-height: calc(100dvh - 56px)` 填满导航栏以下首屏；
- Runtime Map 使用 `flex: 1 1 438px` 吸收剩余高度；
- 双 Review 行使用 `minmax(178px, 1fr)`，会继续平分并吸收 Runtime Map 的额外高度；
- 多数辅助文字仍为固定 `8px / 9px / 10px`；
- 当前只有宽度断点 `1200 / 1199 / 900 / 700px`，没有针对“宽屏但高度有限”的密度规则。

因此，当前实现不是以某个浏览器缩放百分比作为设计基准，而是按 CSS viewport 和固定像素字号排版。约 1920×900、100% 缩放时，可用 CSS 区域较大，双 Review 卡片被纵向拉伸而文字保持固定小字号，形成“卡片松散、文字偏小”的观感。浏览器切到 125% 后，有效 CSS viewport 约缩小为原来的 80%，同时固定像素文字在物理屏幕上放大，视觉上自然更接近紧凑版本。

冻结方向：

- 以约 `1920×900`、浏览器 100% 缩放作为首要桌面验收基线；
- 不使用整页 `transform: scale()` 或要求用户调整浏览器缩放；
- 增加“宽屏、低至中等高度桌面”的密度策略，例如同时基于 `min-width` 与 `max-height` 判断，而不是只看宽度；
- 双 Review 卡片采用有限高度并允许小幅增长，不继续平分并吸收所有 Runtime Map 剩余高度；
- Runtime Map 背景继续填满首屏，剩余空间优先留在拓扑画布中，不转移为页面底部空白；
- 指挥中心普通辅助文字目标不低于 `11px`，核心标签以 `12px` 为主；实际值可在 I2 视觉验收中微调，但不得回退到当前大面积 `8px / 9px` 的可读性；
- 125% 缩放只要求结构完整、信息层级正确且无溢出，不要求与 100% 保持完全相同的信息密度；
- 50% 缩放继续保证页面背景与导航宽度一致并铺满可视区域，但不以 50% 下的正文可读性作为设计目标；
- 移动端、125%、50% 和系统字体缩放必须分别回归，禁止针对单一屏幕硬编码整体缩放比例。

### 5.12 I0 验收矩阵

| 验收维度 | 必须覆盖的状态 |
| --- | --- |
| Runtime | 正常、零值、失败、retained、过期、截断 |
| Governance | 正常、窗口无记录、失败、retained、过期 |
| Provider | 有成功与失败、只有成功、只有失败、无执行记录、不可观测 |
| 资源组合 | 双资源正常、Runtime 单独失败、Governance 单独失败、双资源失败 |
| 桌面视口 | 约 1920×900 的 100% 主基线、125%、50%、超宽屏 |
| 其他视口 | 平板、移动端、系统字体缩放 |
| 交互 | 有真实落点的指标跳转、无落点指标不可点击、局部重试、页面级重试 |

---

## 6. 后续实施阶段建议

### I0：问题确认与契约冻结（已完成）

- 逐项确认第 5 节问题；
- 冻结顶部、中部、底部的信息职责；
- 冻结字段映射、统计窗口、空态和错误态；
- 输出最终页面文案与验收矩阵。

完成结果：11 项信息架构、资源降级、空态文案和桌面密度决策已冻结，并形成验收矩阵。

阶段结果：用户已于 `2026-08-04` 确认全部 I0 决策并授权开始 I1。

### I1：前端投影与资源状态设计（已完成）

- 已新增统一 Snapshot Resource 状态契约，独立表达 `loading`、`freshness`、`ERROR_EMPTY`、`ERROR_RETAINED`、`retained`、错误信息与最后成功快照；
- 已将 Runtime 与 Governance 接入同一页面数据 Hook，但分别持有请求、AbortController、sequence、timer 和诊断计数；Runtime 每 5 秒刷新，Governance 每 60 秒刷新，共用一套页面可见性生命周期；
- 已扩展组合 Presentation：`resources` 保存两个资源的独立状态，`currentStatus` 只投影 Runtime 当前状态，`qualityOutput` 分别从 Runtime 与 Governance 投影近 24 小时质量产出；
- 当资源不可用且无 retained snapshot 时，对应组合指标返回 `null`，不伪造为真实零值；单资源失败不清空另一个资源；
- Provider 执行结果聚合 `recentSuccessCount / recentFailureCount`，无执行记录时成功率保持 `null`；
- Finding 数、受影响任务、最高风险与风险分布只读取 Governance `findingRisk`，不使用活动 Flow Finding 冒充近 24 小时数据；
- `CommandCenterPage.jsx` 仅接入 Governance 数据并传递给 Presentation，I1 未调整 HUD、底部摘要、拓扑 JSX 或 CSS 布局。

I1 主要实现文件：

- `frontend/src/command-center/commandCenterResourceState.js`；
- `frontend/src/command-center/useCommandCenterSnapshots.js`；
- `frontend/src/command-center/commandCenterPresentation.js`；
- `frontend/src/command-center/CommandCenterPage.jsx`。

I1 验证结果：

- 前端全部 Node 契约测试：`118 passed / 0 failed`；
- 新增资源状态测试覆盖首次失败、保留旧快照、过期重算与成功恢复；
- Presentation 测试覆盖双资源正常、Runtime 单独失败、Governance 单独失败和双资源 retained；
- `scripts/run-frontend.cmd build`：通过；
- 浏览器验收：复用已就绪的 `5173` 前端与 `8090` Python 后端，首页正常渲染且 Runtime 保持 `FRESH`；Runtime 与 Governance 均完成真实请求，分别持有轮询计时器，共用 2 个既有 visibility/focus 监听器；现有 H5 HUD、双 Review 拓扑和底部区域未发生布局变化；
- Vite 仍报告既有主 Chunk 超过 500 kB 的非阻塞警告，本阶段未扩大范围处理代码拆分。

停止点：契约测试通过后停止，等待用户确认“继续 I2”。

### I2：首页信息结构实施（已完成）

- 顶部 HUD 已固定为 Runtime 更新时间、排队执行数、运行执行数、进行中审查任务、当前 Provider / Model 共 5 项；
- 顶部已移除“快照覆盖范围”和“Runtime 告警”常驻卡片；快照截断只在异常提示条中表达；
- Agent 最长排队等待已并入“排队执行数”的辅助信息，不再单独占据底部卡片；
- 底部已替换为近 24 小时审查任务、Provider 执行结果、发现问题数、受影响任务与最高风险共 4 项质量产出；
- 底部已移除 Agent 容量、Standard Provider 槽位、最长排队等待和 Runtime 告警；
- 已实现 Runtime 与 Governance 的局部错误提示、retained snapshot 文案和独立重试；双资源同时失败且均无 retained snapshot 时显示页面级错误与统一重试；
- 当前任务列表和质量治理路由没有可保证“近 24 小时同口径过滤”的 URL 契约，因此底部指标保持不可点击，没有加入无法复现统计口径的虚假跳转；
- 中部审查入口、引擎选择、Agent Review、Standard Review、结构性降级关系和结果持久化拓扑未改变事实语义；
- 约 `1920×900`、100% 缩放的宽屏密度规则使用宽高联合断点，将双 Review 卡片限制为可小幅增长的紧凑高度，剩余空间保留在拓扑画布；
- 普通辅助文字提升到 `11px`，核心标签以 `12px` 为主；移动端按“运行、排队、进行中任务、Provider、Runtime 时间”和“任务、Finding、风险、Provider 结果”的优先级重排。

I2 验证结果：

- 前端全部 Node 测试：`118 passed / 0 failed`；
- `scripts/run-frontend.cmd build`：通过；
- 浏览器 `1920×900` CSS 视口：页面总高度为 900px，双 Review 卡片各 189px，地图网格和文档均无横向溢出，HUD / Review / 质量区辅助文字实测为 11px；
- 浏览器 125% 等效 `1536×727` CSS 视口：双 Review 卡片各 178px，无横向溢出，页面结构完整；
- 浏览器移动端 `390×843` CSS 视口：顶部与底部顺序符合冻结优先级，左右结构节点按既有规则折叠，无横向溢出；
- Runtime 与 Governance 真实数据均正常加载，浏览器控制台无 error / warning；
- Vite 仍报告既有主 Chunk 超过 500 kB 的非阻塞警告，本阶段未扩大范围处理代码拆分。

停止点：前端专项测试与构建通过后停止，等待用户确认“继续 I3”。

### I3：真实数据验收与收口

- 使用真实 Runtime / Governance 数据验收；
- 覆盖正常、零值、接口失败、单资源 retained、双资源失败和移动端状态；
- 回写验收结果；
- 只在用户授权时创建本地提交，不自动推送或部署。

I3 真实数据验收补充契约：

- 顶部“当前 Provider / Model”不得直接依赖 `providersObserved` 的数组顺序；
- 选择优先级固定为：存在活动 Flow 的 Provider、`lastObservedAt` 最新的 Provider、默认且启用的 Provider、其他启用 Provider；活动 Flow 或时间相同等同一优先级保持接口原有顺序；
- Provider 无活动 Flow 但存在近期执行结果时，必须展示最近被观测到的 Provider，不得展示 `NO_RECENT_DATA` 的首个配置项；
- 该修正仅属于前端投影收口，不改变 Runtime Schema、Provider 配置、默认 Provider 或调度状态机。

I3 实施与验收结果：

- 真实 `5173` 前端与 `8090` Python 后端接口验收通过，Runtime 与 Governance 均为 `FRESH`；近 24 小时真实数据为 ReviewTask `30`、Provider 成功 `17` / 失败 `0`、Finding `27`、受影响任务 `11`、最高风险 `CRITICAL`；
- 真实当前状态中的排队执行、运行执行和进行中 ReviewTask 均为 `0`，页面按真实零值展示，没有误用破折号或“暂无数据”；
- 真实数据首轮验收发现 `providersObserved` 数组首项 OpenAI 为 `NO_RECENT_DATA`，而 DeepSeek 存在最新成功记录；已按补充契约修正前端投影，顶部现展示 `DeepSeek / deepseek-v4-pro`；
- 已补 Provider 选择回归测试，覆盖活动 Flow 优先、最新 `lastObservedAt` 优先和无观测记录时启用默认 Provider 优先；
- 使用隔离的临时本地接口复现 Runtime 单资源 `ERROR_RETAINED`：Runtime 保留最后成功快照和 5 张顶部指标，Governance 继续为 `FRESH`，页面显示“重试 Runtime”；恢复接口后下一轮轮询自动回到 `FRESH`；
- 复现 Governance 单接口首次失败：Runtime 相关质量指标继续显示，Governance Finding 与风险指标显示 `—`，页面显示“重试质量统计”；
- 复现 Runtime 与 Governance 双资源首次失败：两资源均为 `ERROR_EMPTY`，顶部与底部全部不可用值显示 `—`，页面只显示统一错误和“重新加载”；
- 临时验收环境未连接真实数据库，完成后已精确停止本次 `18091` 与 `5174` 端口所有者并清理临时辅助文件，未影响既有 `5173` / `8090` 服务；
- 移动端 `390×842` CSS 视口下无横向溢出；顶部顺序为运行、排队、进行中任务、Provider、Runtime 时间，质量区顺序为任务、Finding、风险、Provider 结果；审查入口折叠为移动端摘要，Runtime 与 Governance 均保持 `FRESH`；
- 真实页面控制台无 warning / error；前端全部 Node 测试为 `119 passed / 0 failed`；`scripts/run-frontend.cmd build` 通过；
- Vite 仍报告既有主 Chunk 超过 500 kB 的非阻塞警告，本阶段未扩大范围处理代码拆分；
- 本阶段未创建提交、未推送、未部署。

停止点：验收结果回写后停止，等待用户决定部署或继续优化。

---

## 7. 后续总控 Prompt

```text
继续 AI Review Command Center 信息架构优化。

开始前只读取：
1. 根目录 AGENTS.md；
2. AI Review Command Center Current Flow Audit.md 中与本次问题相关的命中章节；
3. AI Review Command Center Information Architecture Optimization Plan.md。

只处理用户本次明确指定的问题点或 I 阶段。先回写本文档状态，再执行获授权范围。
不得修改 Runtime / Governance 后端口径、数据库、Review/Scheduler/Agent/Provider 状态机、历史计划或 README，除非用户独立明确授权。

每个阶段完成测试、构建、浏览器验收和文档回写后必须停止，不得自动进入下一阶段、推送或部署。
```

---

## 8. Agent 自主推进边界

### 讨论阶段可自主执行

- 只读核对现有 Runtime / Governance Schema、查询和前端投影；
- 将用户已确认的结论回写本文档；
- 补充备选方案、风险和待确认问题；
- 不修改任何产品代码。

### 必须等待用户明确授权

- 修改前端页面、Presentation、API Hook、样式或测试；
- 修改 Runtime / Governance 接口及其字段口径；
- 增加数据库统计、缓存、定时任务或新接口；
- 创建提交、推送、部署或发布；
- 自动进入下一个实施阶段。
