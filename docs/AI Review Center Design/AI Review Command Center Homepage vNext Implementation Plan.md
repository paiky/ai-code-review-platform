# AI Review Command Center Homepage vNext Implementation Plan

## 0. 当前执行状态

- 计划版本：`vNext / Homepage Frozen Topology`
- 基线提交：`3fc3fb9 Document current AI review flow audit`
- 当前阶段：`H3 既有 Runtime 交互接线`
- 当前状态：`H3 COMPLETED — WAITING FOR H4 CONFIRMATION`
- 当前允许结果：H3 已完成并停止；未经新授权不得进入视觉强化、响应式调整或悬浮/Drawer 专项。
- 下一授权口令：H3 验收完成后，等待用户明确回复“继续 H4”。
- 停止点：H3 本地提交后立即停止，等待用户确认。

本文档是审计完成后的独立首页实施总控。它不修改、覆盖或续写以下历史计划的执行状态：

- `AI Review Command Center Evolution Plan v2.md`
- `AI Review Command Center Implementation Plan.md`
- `AI Review Platform Runtime Map Implementation Plan.md`

历史计划中的 `Phase` 编号已经承载既有实施记录。本计划统一使用 `H0～H5`，避免把本次首页重构误解为继续旧 Phase 4 或 Phase 5。

### 0.1 冻结视觉参考

首页冻结参考图：

![AI Review Command Center 首页冻结参考图](assets/01.png)

仓库文件：`docs/AI Review Center Design/assets/01.png`

参考图用于固定亮色主题、五主体布局、双 Review 核心层级、紫/橙/青视觉 token 和首页信息密度，不是业务数据或接口契约。实现时的事实优先级为：

1. 当前代码、数据库字段和 Runtime v2 Schema；
2. `AI Review Command Center Current Flow Audit.md`；
3. 本计划冻结的产品与展示契约；
4. `assets/01.png` 的视觉表现。

参考图中仍可能存在生成式图片文字瑕疵，禁止照图复制：

- `STANDADD` 等错误拼写必须使用真实枚举 `STANDARD`；
- Result Persistence 的操作使用“查看 Review 任务”并进入 `/tasks`，不照抄“查看全部结果”；
- 图中数字仅是演示快照，必须绑定 Runtime，不得写死；
- 图中任何乱码、伪文字、不可识别图标和没有真实行为的入口都不得进入实现。

---

## 1. 是否具备推进条件

结论：**具备。**

推进所需的五类输入已经明确：

1. 真实流程已由 `AI Review Command Center Current Flow Audit.md` 核实。
2. 首页主拓扑已冻结为 `Review Intake → Engine Selection → Agent/Standard → Result Persistence`。
3. Agent→Standard 只显示静态结构关系，不声称 Runtime 已能无歧义追踪父子 Job。
4. V1 首页只使用 Runtime v2 当前可证明的字段，不展示历史 KPI、通过率、命中率或完整终态流。
5. 首页采用亮色平台外壳、平面科技 HUD、DOM 语义节点与 SVG/Canvas 装饰层；不采用真实 3D。

当前不存在需要阻塞计划编写的产品选择。悬浮流程和模块详情 Drawer 尚未冻结，但它们已被明确排除在 H1～H5 首页主线之外，因此不构成阻塞。

---

# 一、冻结的首页产品契约

## 1.1 主拓扑

```mermaid
flowchart LR
    I["Review Intake<br/>Manual / MR / Push / Retry"]
    E["Engine Selection<br/>策略路由 / 可用性检查 / 安全门禁"]
    A["Agent Review<br/>Queued / Running / Capacity / Worker"]
    S["Standard Review<br/>Queued / Running / Provider Slots"]
    R["Result Persistence<br/>Task Detail / Notification"]

    I --> E
    E -->|AGENT| A
    E -->|STANDARD| S
    A --> R
    S --> R
    A -. "Fallback · 结构性关系" .-> S
```

### 固定解释

- `Review Intake` 是触发入口，不是统一持久化队列。
- Engine Selection 发生在两类 Job 入队前；不得显示“负载均衡”或统一智能调度中枢。
- Agent 和 Standard 是两个一级执行模块，Standard 不是纯 fallback 支路。
- Agent fallback 连线只表达代码结构；不播放任务级转移动画。
- Result Persistence 只表达结果落库后进入任务详情与既有通知链；不显示完成抵达动画。

## 1.2 首页允许显示的数据

### 顶部 Runtime HUD

| UI 指标 | Runtime v2 来源 | 显示规则 |
| --- | --- | --- |
| Runtime 更新时间 | `generatedAt` | 前端计算距今时间 |
| Total Queued Jobs | `scheduler.queuedJobCount` | 明确为 Job，不称唯一任务数 |
| Agent / Standard queued | 两 Lane `queuedCount` | 两者合计应与 Scheduler 对账 |
| Total Running Jobs | `scheduler.runningJobCount` | 明确为 Job |
| Agent / Standard running | 两 Lane `runningCount` | 两者合计应与 Scheduler 对账 |
| Snapshot Coverage | `coverage.truncated/sections` | 显示“未截断/部分截断”与“有界快照”，不得称完整覆盖 |
| Observed Provider / Model | `providersObserved` | 无观测时显示真实空状态 |
| Runtime Alerts | `alerts` | 明确是当前有界告警列表 |

### Agent Review 模块

- `queuedCount`
- `runningCount`
- `agent.queueMetrics.onlineCapacity`，只显示在线容量，不拼接不存在的配置总容量
- `agent.workerPool` 的 IDLE/BUSY/DRAINING/OFFLINE 观察状态
- `reviewLanes.agent.nextQueued`
- `runningItems.length / runningCount`，显示“展示 N / 共 M”

### Standard Review 模块

- `queuedCount`
- `runningCount`
- `runningCount / capacity`；当前 Provider Scheduler capacity 为 10
- `providersObserved` 或活动 Flow 已返回的 Provider/Model
- `reviewLanes.standard.nextQueued`
- `runningItems.length / runningCount`，显示“展示 N / 共 M”

### 底部当前态

- Agent `runningCount / onlineCapacity`
- Standard `runningCount / capacity`
- `agent.queueMetrics.oldestQueuedSeconds`
- 当前 `alerts` 摘要

## 1.3 首页禁止显示的数据

H1～H5 不得新增或从前端推算：

- 较昨日变化、历史折线和任何前端临时累计趋势；
- 今日完成、完整结果抵达数量；
- Overall Pass Rate；
- Platform Health 百分比；
- Agent Hit Rate；
- Fallback Rate；
- Agent 与 Standard 混合后的全局 Resource Utilization；
- 平均处理时长或吞吐趋势；
- 成功、失败、取消抵达 Result Persistence 的动画；
- fallback Standard Job 与 Agent Job 的实时父子转移动画；
- Context Planner、Retriever 或 Provider 子阶段的首页实时状态。

## 1.4 固定空态和降级态

| 状态 | 首页行为 |
| --- | --- |
| `FRESH` | 正常显示当前 Runtime 快照 |
| `STALE` | 明确显示“Runtime 已过期”，停止非必要动画 |
| `EMPTY` | 不生成模拟 Job、Worker、Provider 或任务编号 |
| Runtime 请求失败 | 保留最后一次成功快照并显示错误；没有旧快照时显示空态 |
| `coverage.truncated=true` | 显示“部分截断”，运行项和告警入口标注有界 |
| `nextQueued=null` | 显示“当前无等待 Review” |
| Agent capacity 为 0 | 显示不可用状态，不计算除零百分比 |
| 无 Provider 观测 | 显示“暂无活跃 Provider”，不默认填充 OpenAI |

## 1.5 固定导航

- 运行 Review 标记：进入 `/tasks/:taskId?reviewKey=...`。
- “查看全部运行项”：使用当前有界列表 Modal 或现有等价能力，不声称是历史全量。
- Result Persistence 的入口使用“查看 Review 任务”，进入 `/tasks`。
- 未实现独立 `/review-results` 路由前，不使用“查看全部结果”。
- Runtime Alert 有 `navigationTarget` 时使用该目标；没有时仅打开当前告警摘要。

---

# 二、视觉与技术路线

## 2.1 默认视觉

- 使用现有平台亮色主题，不切换整页 Dark Mode。
- 页面背景为白色/浅灰蓝；Agent 使用紫色，Standard 使用橙色，Result 使用青色。
- 使用平面科技 HUD、轻量 2.5D 图标、SVG 轨道和克制光效。
- 正文文字不发光；颜色不是唯一状态信息。
- 不使用生成图片作为整页背景，不把文字烘焙到图片素材中。

## 2.2 渲染边界

- DOM 负责所有文字、数值、按钮、焦点、Tooltip 和可访问语义。
- SVG 或现有 Canvas 装饰层只负责背景网格、轨道、静态连接和非语义光效。
- Canvas 必须 `aria-hidden` 且不接收 pointer event。
- 不引入 Three.js、PixiJS、React Flow 或新的动画依赖，除非后续单独证明现有 DOM/SVG/Canvas 无法满足并获得授权。
- 当前 `canvasRuntime` 的单 RAF、ResizeObserver、visibility、reduced-motion 和 dispose 治理不得退化。

## 2.3 响应式

- `≥ 1200px`：显示五主体双轨地图。
- `701～1199px`：压缩 Intake、Engine Selection 和 Result，保留 Agent/Standard 两个核心模块。
- `≤ 700px`：不挂载 Canvas；使用 Agent、Standard 两张纵向 DOM 卡片和紧凑入口说明。
- 任一宽度不得依赖横向滚动才能访问核心状态和操作。

---

# 三、实施文件边界

## 3.1 默认允许修改

- `frontend/src/command-center/CommandCenterPage.jsx`
- `frontend/src/command-center/CommandCenterCanvas.jsx`
- `frontend/src/command-center/commandCenterPresentation.js`
- `frontend/src/command-center/commandCenterModel.js`，仅当现有 Runtime 字段归一化确有缺口
- `frontend/src/command-center/platformRuntimeMapRenderer.js`，仅用于静态装饰/现有资源治理适配
- `frontend/src/command-center/commandCenter.css`
- `frontend/tests/commandCenter*.test.mjs`
- 本计划文档中的阶段状态、实施结果和验证证据

如需新增前端文件，应位于 `frontend/src/command-center/`，且只承载可复用的首页展示组件或纯函数。

## 3.2 默认禁止修改

- `backend-python/app/command_center/` Runtime v2 Schema、查询、Service 和 API；
- Review、Scheduler、Agent、Provider、Notification 状态机；
- 数据库模型、索引、迁移和业务数据；
- `frontend/src/App.jsx` 的全局路由和业务页面，除非已有 Command Center 路由无法使用；
- README；
- 三份历史 Evolution/Implementation Plan 的状态；
- 用户已有未跟踪文档和 `docs/AI Review Center Design/assets/`；
- 悬浮流程、模块详情 Drawer、历史 KPI 和新的结果列表页。

如果任一阶段发现必须修改上述禁止范围，立即停止，记录阻塞点并请求独立授权，不用视觉占位绕过真实数据缺口。

---

# 四、阶段总控

## 4.1 总控 Prompt

后续每次继续首页实施时使用以下总控约束：

```text
继续 AI Review Command Center Homepage vNext。

开始前读取：
1. 项目根目录 AGENTS.md
2. docs/AI Review Center Design/AI Review Command Center Current Flow Audit.md
3. docs/AI Review Center Design/AI Review Command Center Homepage vNext Implementation Plan.md
4. docs/AI Review Center Design/assets/01.png（仅作为视觉参考，事实语义服从前述文档和当前代码）

只执行用户本次明确授权的 H 阶段。先将本计划当前状态更新为该阶段 IN PROGRESS，再按允许文件和验收门禁实施。

不得修改 Runtime v2、数据库、Review/Scheduler/Agent/Provider 状态机、历史 Evolution/Implementation Plan 或 README；不得实现悬浮流程、模块详情 Drawer、历史 KPI、结果统计或任务级 fallback 转移动画。

完成当前阶段的专项测试、必要构建、浏览器验收和 git diff 检查后，回写实际修改、验证结果和剩余风险。只有验收通过才按本阶段约定创建本地提交；不得推送、部署或自动进入下一阶段。

当前阶段完成后必须立即停止，等待用户验证并明确回复“继续下一阶段”。
```

## 4.2 Agent 自主推进授权边界

### 可自主执行

- 读取 Runtime v2 现有 Schema、Service 和前端 Model 以核对字段；
- 修改当前 H 阶段明确列出的前端 Command Center 文件和测试；
- 运行 Command Center 专项 Node 测试、前端全量 Node 测试和生产构建；
- 复用已 ready 的前后端服务进行只读浏览器验收；
- 为本阶段验收创建工作区 `.local/` 临时日志或隔离 mock，验收后精确清理；
- 回写本计划的阶段结果。

### 必须停止并请求授权

- 需要新增或修改 Runtime 字段、查询或索引；
- 需要修改数据库、后端状态机或业务数据；
- 需要新增依赖；
- 需要新增历史聚合、结果统计或独立结果列表 API；
- 需要实现悬浮流程、详情 Drawer 或新的业务交互；
- 需要部署、推送或修改本阶段外文件；
- 发现现有未提交修改与目标文件重叠且无法安全隔离。

---

# 五、H1：Presentation 数据契约

## 5.1 目标

在不改变页面 DOM 和 Runtime v2 的前提下，先建立冻结首页所需的纯前端 Presentation View Model，消除旧“AI Review Core/统一候场门/全局利用率”等不准确展示语义。

## 5.2 允许修改

- `frontend/src/command-center/commandCenterPresentation.js`
- 必要时最小修改 `commandCenterModel.js`
- `frontend/tests/commandCenterPresentation.test.mjs`
- `frontend/tests/commandCenterModel.test.mjs`
- 本计划文档

## 5.3 必须形成的 View Model

- `hud`：freshness、generatedAt、totalQueuedJobs、totalRunningJobs、coverage、providersObserved、alerts。
- `intake`：四类固定入口展示信息，不包含队列数。
- `engineSelection`：AGENT/STANDARD 两条固定路由和自动 Agent 不可用的说明文本。
- `agentLane`：queued、running、onlineCapacity、workerSummary、nextQueued、visible/total running items。
- `standardLane`：queued、running、capacity、providers、nextQueued、visible/total running items。
- `fallback`：固定 `STRUCTURAL_ONLY`。
- `resultPersistence`：固定 `STRUCTURAL_ONLY`，导航目标 `/tasks`。
- `footer`：Agent capacity、Standard slots、oldest Agent queue、alerts。

## 5.4 验收

- v2 FRESH、STALE、EMPTY、请求失败保留旧快照、truncated、capacity=0、无 Provider、无 nextQueued 均有测试。
- queued/running 的 Scheduler 总数与 Lane 分布不一致时不静默伪造，应保留真实字段并提供 coverage/diagnostic 标识。
- 不再生成 pass rate、hit rate、fallback rate、platform health、历史趋势或混合利用率。
- 不修改 JSX、CSS、Canvas 或后端。

## 5.5 落地 Prompt

```text
执行 H1：Presentation 数据契约。

只修改 Command Center 的前端 Model/Presentation 纯函数及对应测试，建立已冻结首页的 HUD、Intake、Engine Selection、Agent Lane、Standard Lane、结构性 Fallback、Result Persistence 和 Footer View Model。

不得修改页面 JSX/CSS/Canvas、Runtime v2、后端、数据库或业务状态机；不得实现悬浮流程、Drawer、历史 KPI 或结果统计。

完成专项测试和 git diff 检查，回写 H1 实施结果。验收通过后状态更新为 H1 COMPLETED — WAITING FOR H2 CONFIRMATION，创建本地提交并立即停止。
```

## 5.6 停止点

H1 完成后不得自动进入 H2。

---

# 六、H2：静态首页结构

## 6.1 目标

使用 H1 View Model 实现亮色平面首页的一屏静态结构，不增加动态流光和模块详情交互。

## 6.2 允许修改

- `CommandCenterPage.jsx`
- `CommandCenterCanvas.jsx`
- 必要的首页展示子组件
- `commandCenter.css`
- Command Center 信息架构/Presentation 测试
- 本计划文档

## 6.3 实施范围

- 顶部六项 Runtime HUD；
- Review Intake；
- Engine Selection；
- Agent Review 核心模块；
- Standard Review 核心模块；
- 单条结构性 fallback 虚线；
- Result Persistence；
- 底部四项当前态；
- 真实空态、STALE、ERROR 和 truncated 文案。

本阶段所有连接使用静态 SVG/CSS。Canvas 可关闭或仅保留不影响语义的静态背景；不得播放业务粒子或状态转移动画。

## 6.4 验收

- 1440×900 初始视口可看到五主体、双 Lane、结果终点和底部当前态。
- 不出现统一 Task Queue、AI Review Core、负载均衡、历史 KPI 或结果统计。
- 所有文字由 DOM 渲染，Canvas 失败不影响信息读取。
- 主文字和次级文字达到 WCAG AA；键盘焦点可见。
- 本阶段的“悬浮查看流程/点击查看详情”如果尚无交互，必须隐藏或显示为非交互说明，不放置无行为按钮。

## 6.5 落地 Prompt

```text
执行 H2：静态首页结构。

基于 H1 Presentation 实现冻结的亮色五主体双轨首页。使用 DOM 负责全部语义、SVG/CSS 负责静态连接；不实现悬浮流程、Drawer、动态流光、任务转移或结果抵达动画。

完成 Command Center 专项测试、前端生产构建、1440×900 静态浏览器检查和 git diff 检查，回写结果。验收通过后状态更新为 H2 COMPLETED — WAITING FOR H3 CONFIRMATION，创建本地提交并立即停止。
```

## 6.6 停止点

H2 完成后等待用户确认页面结构、信息密度和亮色主题，不自动进入 H3。

---

# 七、H3：既有 Runtime 交互接线

## 7.1 目标

只接通冻结首页已经定义且有现有路由/数据支持的操作，不设计悬浮流程或模块 Drawer。

## 7.2 允许交互

- 手动刷新 Runtime；
- 运行 Review 标记进入 `/tasks/:taskId?reviewKey=...`；
- 运行项溢出列表复用现有 Modal；
- Result Persistence 的“查看 Review 任务”进入 `/tasks`；
- 告警存在 `navigationTarget` 时跳转；
- 键盘 Enter/Space 与点击行为一致；
- Modal 关闭后恢复触发器焦点。

## 7.3 明确不做

- 悬浮执行链；
- 模块详情 Drawer；
- nextQueued 的修改优先级/取消/重试；
- fallback 连线点击与任务级追踪；
- 新结果列表页；
- 后端写操作。

## 7.4 验收

- 所有可见按钮都有真实行为；无空按钮和假入口。
- bounded/truncated 提示在溢出列表可见。
- 页面离开后请求、Timer、Observer 和 Listener 正确清理。
- 不新增重复 Runtime 轮询。

## 7.5 落地 Prompt

```text
执行 H3：既有 Runtime 交互接线。

只实现刷新、运行 Review 跳转、现有溢出 Modal、告警导航和 Result Persistence 到 /tasks 的既有路由。不得实现悬浮流程、模块 Drawer、新结果列表、写操作或 fallback 任务追踪。

完成专项测试、前端全量 Node 测试、生产构建、键盘/焦点浏览器验收和 git diff 检查，回写结果。验收通过后状态更新为 H3 COMPLETED — WAITING FOR H4 CONFIRMATION，创建本地提交并立即停止。
```

## 7.6 停止点

H3 完成后等待用户确认基础交互，不自动进入 H4。

---

# 八、H4：视觉强化与响应式

## 8.1 目标

在结构和交互已确认后增加生产级视觉完成度，但不扩展业务语义。

## 8.2 允许增强

- 亮色科技网格和轻量 2.5D 图标；
- Agent 紫、Standard 橙、Result 青的静态双层描边；
- SVG 轨道的低速装饰流光；
- 当前运行模块的克制呼吸效果；
- 告警状态短周期视觉强调；
- 三档响应式布局；
- reduced-motion、Canvas 失败和小屏 DOM fallback。

## 8.3 禁止增强

- 任务级 fallback 转移动画；
- Result 成功抵达动画；
- 本地定时器模拟业务阶段；
- 根据 active item 消失推断成功；
- 真 3D、WebGL 场景、粒子爆炸或持续高耗动画；
- 悬浮流程和模块 Drawer。

## 8.4 性能门禁

- 页面只允许一个受控 RAF owner；无动效时 RAF 停止。
- hidden、STALE、reduced-motion、小屏和 Canvas 失败时停止动画。
- 1440×900、1024×800、390×844 无横向溢出。
- 连续刷新不累积 Canvas、RAF、Observer 或 Listener。

## 8.5 落地 Prompt

```text
执行 H4：视觉强化与响应式。

保持 H2/H3 结构和交互不变，只增加亮色科技 HUD、紫/橙/青轨道、克制装饰流光、响应式和 reduced-motion。不得新增业务状态、悬浮流程、Drawer、fallback 转移动画或 Result 抵达动画。

完成三档视口、reduced-motion、STALE/ERROR/Canvas fallback、资源治理、前端测试和生产构建验收，回写结果。验收通过后状态更新为 H4 COMPLETED — WAITING FOR H5 CONFIRMATION，创建本地提交并立即停止。
```

## 8.6 停止点

H4 完成后等待用户确认视觉强度，不自动进入 H5。

---

# 九、H5：生产验收与收口

## 9.1 目标

不再增加功能，只验证冻结首页能在真实数据、异常数据和常用视口下稳定工作。

## 9.2 验收矩阵

### 数据

- Agent/Standard 均为空；
- 仅 Standard 排队/运行；
- Agent Worker 在线、忙碌、DRAINING、OFFLINE；
- nextQueued 为空；
- Provider 无观测/多 Provider；
- runningItems 截断；
- coverage truncated；
- Runtime FRESH/STALE/EMPTY/ERROR；
- Agent capacity=0；
- 当前告警存在/不存在。

### 交互与可访问性

- 全键盘访问和焦点返回；
- 任务路由与 reviewKey 编码；
- 运行项 Modal；
- 告警导航；
- 屏幕阅读器名称；
- reduced-motion。

### 性能与生命周期

- 60 秒以上刷新观察；
- 单 RAF/Observer/Listener；
- 页面 hidden/visible 自动化覆盖；
- 卸载后无请求回写；
- 控制台无错误；
- 主页面无横向溢出。

## 9.3 验证命令

按影响范围至少执行：

```text
node --test frontend/tests/commandCenterApi.test.mjs frontend/tests/commandCenterModel.test.mjs frontend/tests/commandCenterPresentation.test.mjs frontend/tests/commandCenterInformationArchitecture.test.mjs
scripts/run-frontend.cmd build
git diff --check
```

若阶段新增了 Command Center 专项测试文件，应纳入同一 Node test 命令。只有脚本缺少能力或失败时才进入 `frontend/` 执行底层命令，并记录原因。

## 9.4 落地 Prompt

```text
执行 H5：生产验收与收口。

不得增加新功能。只针对真实数据矩阵、三档视口、键盘、reduced-motion、Runtime 异常、资源生命周期和构建结果进行验收；只修复验收发现的 H1～H4 范围内缺陷。

完成专项/全量前端测试、生产构建、浏览器验收和 git diff 检查后，回写完整证据与剩余风险。全部通过时状态更新为 HOMEPAGE VNEXT COMPLETED — WAITING FOR DEPLOYMENT CONFIRMATION，创建本地提交并立即停止。不得部署或推送。
```

## 9.5 停止点

H5 完成后不自动部署、不推送、不开始悬浮流程或后续数据投影。

---

# 十、后续独立专项（当前不排期）

以下能力不属于 H1～H5。每项都必须先补独立设计、数据来源、交互参考和用户授权：

1. Agent/Standard 悬浮流程预览；
2. 模块详情 Drawer 或移动端 Bottom Sheet；
3. 今日成功结果、执行成功率、P50/P95 时长、小时吞吐等历史只读聚合；
4. 独立 Review Results 列表页；
5. Runtime P0 fallback Lane 投影修复和 Agent→Standard 父子 Job 关联；
6. 具备完整终态 feed 后的 Result Persistence 动态；
7. 暗色运营大屏或全局主题切换。

后续专项不得通过前端当前快照推算历史数据，也不得为匹配愿景图修改业务状态机语义。

---

# 十一、阶段实施记录

## 11.1 H0 完成结论

- 首页主拓扑：已冻结。
- V1 数据范围：已冻结。
- 空态、过期、截断和错误边界：已冻结。
- 技术路线：DOM + SVG/现有 Canvas 装饰层，已冻结。
- 悬浮流程与 Drawer：明确延期，不阻塞首页。
- 下一阶段：`H1 Presentation 数据契约`。

H0 完成时状态：

```text
H0 COMPLETED — WAITING FOR H1 CONFIRMATION
```

## 11.2 H1 实施结果

H1 已完成以下纯前端 Presentation 数据契约：

- `hud`：保留 Runtime freshness、generatedAt、Scheduler queued/running Job 总数、coverage、Provider 观测、alerts 和请求错误状态；
- `intake`：固定 Manual、Merge Request、Push、Retry 四类入口，不混入队列统计；
- `engineSelection`：固定 AGENT、STANDARD 两条路由，并说明自动 Agent 不可用时可按策略直接进入 Standard；
- `agentLane`：queued、running、onlineCapacity、Worker 摘要、下一候选和有界 running items；
- `standardLane`：queued、running、Provider capacity、Provider/Model 观测、下一候选和有界 running items；
- `fallback` 与 `resultPersistence`：均固定为 `STRUCTURAL_ONLY`，Result 导航目标固定为 `/tasks`；
- `footer`：Agent capacity、Standard slots、Agent 最老排队时长和当前有界 alerts；
- Scheduler 总数与两条 Lane 合计不一致时保留两边真实数值，并输出 queued/running reconciliation diagnostics；
- FRESH、STALE、EMPTY、错误保留旧快照、truncated、capacity=0、无 Provider 和无 nextQueued 均已形成测试。

本阶段实际修改：

- `frontend/src/command-center/commandCenterPresentation.js`
- `frontend/tests/commandCenterPresentation.test.mjs`
- 本计划文档
- `docs/AI Review Center Design/assets/01.png` 作为本计划冻结视觉参考一并纳入版本控制

`commandCenterModel.js` 的现有 Runtime v2 归一化字段已足够，未做无必要修改。H1 按约束未修改 JSX、CSS、Canvas、Runtime v2、后端、数据库或业务状态机。为保证分阶段提交后现有页面不崩溃，Presentation 暂时保留带 `H1_LEGACY_RENDERER` 标记的旧 Canvas 兼容投影；新首页 DOM 不依赖该投影，H2 切换页面结构时处理兼容层退出。

验证结果：

```text
node --test tests/commandCenterPresentation.test.mjs tests/commandCenterModel.test.mjs tests/commandCenterInformationArchitecture.test.mjs
22 passed, 0 failed

git diff --check
passed（仅提示 Git 将按工作区配置转换 LF/CRLF）
```

H1 是纯 View Model 阶段，没有 DOM、样式或运行服务变更，因此未执行生产构建和浏览器验收；这些门禁从 H2 静态首页结构开始执行。

## 11.3 H2 实施结果

H2 已基于 H1 View Model 完成冻结首页的亮色静态结构：

- 顶部六项 Runtime HUD：更新时间、queued Jobs、running Jobs、coverage、Provider/Model 观测和 alerts；
- 桌面五主体双轨拓扑：Review Intake、Engine Selection、Agent Review、Standard Review、Result Persistence；
- Agent 与 Standard 作为两个一级核心模块，Standard 保留 Engine Selection 独立入口；
- Agent→Standard 仅保留一条 `STRUCTURAL_ONLY` fallback 虚线和说明，不表达任务级转移动画；
- Result Persistence 仅表达结果落库、任务详情和既有通知链，不展示完成量或终态抵达；
- 底部四项当前态：Agent capacity、Standard Provider slots、最老 Agent 排队时长和 Runtime alerts；
- FRESH、STALE、EMPTY、ERROR、truncated、无 Provider、无 nextQueued 和容量为零均使用真实文案；
- `≤700px` 静态降级为 Agent/Standard 两张纵向核心卡片，不挂载复杂地图。

H2 关闭旧业务动画 Canvas。所有语义、文字和数字均由 DOM 渲染；背景网格和连线仅由 `aria-hidden`、无 pointer event 的静态 SVG/CSS 承载。页面未放置刷新、Review 跳转、Modal、告警导航、Result 导航或悬浮/详情按钮，避免在 H3 接线前出现无行为入口。

本阶段实际修改：

- `frontend/src/command-center/CommandCenterPage.jsx`
- `frontend/src/command-center/CommandCenterCanvas.jsx`
- `frontend/src/command-center/commandCenter.css`
- `frontend/tests/commandCenterInformationArchitecture.test.mjs`
- 本计划文档

验证结果：

```text
node --test tests/commandCenterPresentation.test.mjs tests/commandCenterModel.test.mjs tests/commandCenterInformationArchitecture.test.mjs
22 passed, 0 failed

.\scripts\run-frontend.cmd build
passed；Vite 仅保留既有的大 chunk 提示

1440×900 应用内浏览器验收
- viewport：1440×900
- document：1440×900，无横向或纵向滚动溢出
- HUD、Review Intake、Engine Selection、Agent、Standard、Result 和 Footer 全部位于首屏
- Command Center 内：0 个 button、0 个 canvas、1 个静态 svg
- 浏览器 console：0 warnings / 0 errors
```

浏览器验收复用了已运行后端和仓库脚本启动的独立 Vite 5174 实例；验收完成后只停止本次记录的 5174 owner/launcher，未影响此前存在的 5173 服务。

当前状态：

```text
H2 COMPLETED — WAITING FOR H3 CONFIRMATION
```

本计划到此停止。未经用户明确回复“继续 H3”，不得接入刷新、任务跳转、Modal、告警导航或 Result 导航。

## 11.4 H3 实施结果

H3 已在冻结首页结构上接通现有 Runtime 支持的只读交互：

- 顶部“刷新 Runtime”复用 `useCommandCenterRuntimeSnapshot().reload`，请求进行中禁用按钮，不新增第二套轮询；
- 运行 Review 标记使用 Presentation 生成的安全内部地址 `/tasks/:taskId?reviewKey=...`，缺少正整数 taskId 时不渲染为可点击入口；
- Agent/Standard 运行项超出首页四项或 Runtime 标记截断时，可打开现有 Ant Design Modal；Modal 始终说明列表来自有界 Runtime 快照，并展示已载入/总数及 truncated 状态；
- Result Persistence 的“查看 Review 任务”进入既有 `/tasks` 路由；
- HUD 选择首个带 `navigationTarget` 的当前告警作为可点击告警入口，不带安全内部目标时保持只读卡片；
- 所有交互入口均使用原生 `button`，浏览器默认提供 Enter/Space 等价激活；没有新增手写键盘 Listener；
- Modal 关闭后优先恢复溢出触发器焦点；若轮询导致触发器消失，则回退到刷新按钮；
- 页面仍只使用原有 Runtime hook 的 AbortController、单 Timeout 和 visibility/focus lifecycle，未新增轮询、Observer 或全局 Listener。

本阶段实际修改：

- `frontend/src/command-center/CommandCenterPage.jsx`
- `frontend/src/command-center/CommandCenterCanvas.jsx`
- `frontend/src/command-center/commandCenterInteractions.js`
- `frontend/src/command-center/commandCenterPresentation.js`
- `frontend/src/command-center/commandCenter.css`
- `frontend/tests/commandCenterInformationArchitecture.test.mjs`
- `frontend/tests/commandCenterInteractions.test.mjs`
- `frontend/tests/commandCenterPresentation.test.mjs`
- 本计划文档

H3 未实现悬浮执行链、模块详情 Drawer、fallback 点击追踪、队列写操作、新结果页、Runtime/后端/数据库或业务状态机修改。

验证结果：

```text
node --test tests/commandCenterPresentation.test.mjs tests/commandCenterModel.test.mjs tests/commandCenterInformationArchitecture.test.mjs tests/commandCenterInteractions.test.mjs
26 passed, 0 failed

node --test
103 passed, 0 failed

.\scripts\run-frontend.cmd build
passed；Vite 仅保留既有的大 chunk 提示

1440×900 应用内浏览器验收
- 复用既有 5173 前端和 8090 Runtime API，两个 URL 均返回 HTTP 200；未启动或停止服务
- viewport/document：1440×900，无横向或纵向滚动溢出
- 手动刷新只将 started 从 7 增至 8，deduplicated 保持 0
- 运行 Review：进入 /tasks/1174?reviewKey=agent-claude-code-deepseek-v4-pro
- Runtime Alert：进入 /tasks/1165
- Result Persistence：进入 /tasks
- 键盘焦点落在刷新按钮，focus-visible outline 为 solid 3px
- 离开首页后 Command Center DOM 已卸载；轮询清理仍由既有 lifecycle 专项测试覆盖
- Command Center 独立新标签 console：0 warnings / 0 errors
```

浏览器验收时真实 Runtime 没有出现超过首页上限的运行项，因此未人为创建后台任务。Modal 的触发器恢复、触发器消失后的刷新按钮回退和无效目标保护由 3 项纯函数专项测试覆盖；有界/truncated 文案和 Modal 接线由信息架构测试覆盖。

当前状态：

```text
H3 COMPLETED — WAITING FOR H4 CONFIRMATION
```

本计划到此停止。未经用户明确回复“继续 H4”，不得进入视觉强化、响应式、reduced-motion、Canvas fallback 或资源治理工作。
