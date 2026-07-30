# Review 运行态沉浸式工作台改造计划

## 1. 状态与结论

- 文档状态：方案已由用户确认；阶段一“沉浸布局与状态切换”已实施、提交并通过用户人工验收；
  阶段二“原生 Canvas 粒子核心”已完成代码、自动化测试、构建和 1440 / 1024 / 390px 安全合成浏览器
  验收。Windows detached launcher 的 command-exit 复验继续按用户要求暂停，不影响本次人工准备环境下的
  浏览器结论。
- 前置基线：
  - `docs/38-review-lifecycle-and-frontend-entrypoints.md`：当前实际任务详情入口与 Review 生命周期。
  - `docs/48-review-task-detail-unified-progress-ui-plan.md`：ReviewJourney、六阶段、身份、时间轴、
    Drawer、Popover、结果布局和安全白名单。
  - `docs/49-review-progress-animation-style-extension-plan.md`：已暂停，ENERGY、Lottie、动画风格切换
    和偏好不属于本专项。
- 结论：queued / running Review 改造成路由级沉浸工作台可行，不需要修改 Backend、数据库或公开 API。
- 本专项不是简单放大现有 Hero。它只替换当前选中 Review 处于 queued / running 时的页面编排和主视觉；
  terminal 状态继续使用 `docs/48` 已完成的结果优先详情页。
- 参考视觉只用于确定深色沉浸氛围、中央主视觉和左右信息分区，不照搬其中的虚构百分比、置信度、
  Reasoning Stream 或模型思考文案。

## 2. 决策与专项关系

固定实施顺序：

```text
docs/48 已完成的 ReviewJourney 与任务详情基线
  -> docs/50 阶段一：沉浸布局、模式切换和安全信息编排
  -> 用户验证布局与信息密度
  -> docs/50 阶段二：原生 Canvas 粒子核心
  -> 用户验证视觉、性能和部署
```

专项边界：

- `docs/48` 的数据模型和交互契约继续生效；本专项不得建立第二套阶段判断。
- `docs/49` 当前暂停。不得在本专项中实现 ENERGY、Lottie、风格菜单、动画偏好或播放器。
- 原生 Canvas 粒子核心是沉浸工作台的固定 Agent 运行态视觉，不是可选动画风格。
- 本专项完成后不自动恢复 `docs/49`；是否仍需要多风格动画必须由用户重新确认。

## 3. 当前问题

当前 queued / running 首屏采用普通任务详情中的局部 Hero：

```text
全局导航
  -> 任务页头和操作
  -> 任务基础信息卡
  -> Review 白色内容卡
       -> 190 × 154 的 BRAIN / Provider 动画
       -> Hero 文案
       -> 横向完整时间轴
```

该布局能准确表达状态，但存在以下限制：

1. 运行态视觉只占局部卡片，无法形成“当前页面正在执行一次 Review”的主任务感。
2. 任务基础信息和普通后台导航占据首屏，当前阶段、时间轴和安全运行摘要的层级不够突出。
3. 放大 SVG 只能放大图形，不能解决页面编排、左右信息层次和响应式问题。
4. 参考图中的百分比、推理流和置信度没有可靠 Backend 数据，不能通过前端模拟补齐。
5. Agent 与 Standard 需要统一工作台结构，但二者不能错误地共用 Agent 大脑或取证语义。

## 4. 目标与非目标

### 4.1 目标

- 当前选中的 Review 为 `QUEUED` 或 `RUNNING` 时，自动进入占满应用主视口的沉浸工作台。
- 使用极简顶栏、六阶段导航、中央运行视觉和安全摘要，突出当前真实阶段。
- Agent 与 Standard 使用同一布局骨架，但使用不同的运行视觉和文案。
- 保留多模型选择、`reviewKey` URL 直达、轮询选择保持、Drawer、Popover、焦点恢复和中断能力。
- Review 进入 terminal 后自动恢复结果优先详情，Finding、Diff、Patch 和结果操作顺序不回归。
- 中央 Agent 视觉最终使用原生 Canvas 2D 实现，不增加动画依赖或远程资源。
- 支持 1440、1024 和 390px，支持键盘、屏幕阅读器和 `prefers-reduced-motion`。

### 4.2 非目标

- 不调用浏览器 Fullscreen API，不请求浏览器全屏权限。
- 不重做 terminal 的结果、Finding、Diff、Patch、反馈、评估样本或补证据 UI。
- 不修改 ReviewJourney 六阶段、七种阶段状态、Review 身份或事件隔离规则。
- 不显示完成百分比、预计剩余时间、置信度、token 进度或模型思考过程。
- 不实现三维 WebGL、Three.js、Lottie、图片包、视频背景、音频或远程动画。
- 不实现 ENERGY、动画风格切换、用户动画偏好或运营配置。
- 不修改 Backend、数据库、API、Review Card schema、Provider、Prompt、预算或工具白名单。
- 不改变 Standard Review、fallback、队列、租约、Worker、通知或 Review 结果行为。

## 5. 运行模式契约

### 5.1 模式来源

页面模式只由当前选中的 `ReviewJourney` 派生：

| 当前选中 Review | 页面模式 |
| --- | --- |
| `QUEUED` | `IMMERSIVE` |
| `RUNNING` | `IMMERSIVE` |
| `SUCCESS` | `RESULT` |
| `FAILED` | `RESULT` |
| `CANCELLED` | `RESULT` |
| `SKIPPED` | `RESULT` |
| fallback 已进入终态 | `RESULT` |
| 历史或状态缺失 | `RESULT` |
| Review 数据尚未加载 | `LOADING`，保持普通应用框架 |

固定规则：

- 多 Review 场景只以用户当前选择的 `reviewKey` 决定模式；其它结果正在运行时不得抢占页面。
- URL 中合法 `reviewKey` 继续优先直达；轮询、列表重排和状态变化不得重置选择。
- 当前选择从 queued / running 进入 terminal 时，无需刷新路由，页面自动切换到结果布局。
- 当前选择切换为另一个 queued / running Review 时继续留在沉浸模式，只更新该 Review 的安全内容。
- 当前选择切换为 terminal Review 时立即回到结果布局，不自动切回仍在运行的其它 Review。
- 派生失败时回退 `RESULT` 或现有安全空态，不得改变 Review 主状态。

### 5.2 AppFrame 协作

沉浸模式属于应用路由布局，不使用覆盖全页面的伪 Modal：

- `AppFrame` 提供内部 `ReviewWorkspaceModeContext`。
- `TaskDetail` 在当前选中 Journey 可靠解析后报告 `LOADING / IMMERSIVE / RESULT`。
- `IMMERSIVE` 时隐藏常规品牌导航和全局操作区，`Content` 去除普通页面最大宽度、外边距和浅色背景。
- `RESULT`、路由离开、组件卸载或数据错误时必须恢复普通 AppFrame。
- 不通过永久 body class、不可清理的 DOM 操作或不可访问的高 `z-index` 遮罩隐藏导航。
- 全局任务队列和失败通知仍按现有机制轮询；沉浸顶栏不重复展示其完整 Modal。

## 6. 前端内部纯展示模型

新增纯数据模型 `ReviewImmersivePresentation`。它只能消费：

- 当前选中的 `ReviewJourney`；
- 已经由 `ReviewJourney` 白名单化的阶段详情和 Agent 摘要；
- 任务基础信息中的安全显示字段；
- 当前任务既有的 changed-files 数字摘要。

建议结构：

```text
ReviewImmersivePresentation
  mode                       LOADING | IMMERSIVE | RESULT
  selectedReviewKey          仅用于选择和组件稳定性，不作为可见调试信息
  engineVisual               AGENT_PARTICLE | STANDARD_FLOW
  identityLabel
  providerModelLabel
  status
  statusLabel
  currentStageId
  currentStageTitle
  headline
  description
  startedAt
  elapsedMs
  heartbeat
    lastHeartbeatAt
    delayed
  stages[]                   复用 ReviewJourneyStage，不重新计算状态
  contextMetrics[]           白名单数字和固定枚举
  activityMetrics[]          白名单心跳、预算和调用计数
  fallbackTransfer           null | 安全固定转交摘要
  hasTaskInfo
```

约束：

- Presentation 层不得接收原始 progress detail、异常对象或 Provider 响应。
- `elapsedMs` 只能由合法真实开始时间和当前浏览器时间计算；开始时间缺失时为 `null`。
- 运行时长只是实际已运行时间，不得转换为百分比或预计剩余时间。
- Canvas 只接收 `engineVisual / status / currentStageId / reducedMotion / ariaLabel`，不得读取业务 API。
- Presentation 或 Canvas 派生失败不得写回 Review 状态、progress 或通知。

### 6.1 阶段一实际组件契约

阶段一固定采用以下内部边界：

```text
TaskDetail
  -> 统一维护 activeReviewKey
  -> 使用现有 buildReviewJourneys / resolveReviewSelectionKey
  -> 只把当前选中的 ReviewJourney 交给 buildReviewImmersivePresentation
  -> 通过 ReviewWorkspaceModeContext 向 AppFrame 报告 LOADING / IMMERSIVE / RESULT

AppFrame
  -> 只在当前路由仍是合法任务详情且报告模式为 IMMERSIVE 时隐藏普通导航
  -> 路由离开立即按路由条件恢复
  -> TaskDetail 错误、RESULT、卸载时通过 Context 清理恢复
```

- `ReviewWorkspaceModeContext` 只保存页面展示模式和稳定的报告函数，不保存 Review 业务对象。
- `TaskDetail` 是当前 `activeReviewKey` 的唯一 UI 状态所有者；普通结果 Tabs 和沉浸顶栏选择器都调用
  同一个选择函数，并同步合法 `reviewKey` 到 URL。
- `CodeQualityReviewsPanel` 改为受控消费当前选择，不再建立第二份可能被轮询重置的选择状态。
- `ReviewJourneyTimeline`、阶段 Drawer、告警 Popover 和焦点恢复继续复用同一组件；沉浸态只增加纵向
  布局修饰，不复制阶段状态或详情内容。
- 阶段一中央舞台直接复用 `AgentReviewAnimation(BRAIN)` 和 `StandardReviewAnimation`；不新增 Canvas、
  动画注册项、资源或依赖。

### 6.2 阶段一数据映射

| 展示字段 | 唯一来源 | 缺失 / 异常处理 |
| --- | --- | --- |
| `mode` | 当前选中 Journey 的 `status / running / historical` | 未加载为 LOADING；未知、历史、异常为 RESULT |
| `identityLabel` | Journey `engineLabel` | 固定“历史任务未记录” |
| `providerModelLabel` | Journey 已清洗展示名 | 固定“Provider/model 未记录” |
| `status / statusLabel` | Journey 主状态 | 不识别时 RESULT，不改写主状态 |
| `currentStage* / stages[]` | Journey `currentStageId / stages` | 不重算；没有可靠阶段时隐藏 |
| `headline / description` | 现有 Hero 固定文案映射 | 固定历史安全文案 |
| `startedAt / elapsedMs` | Journey 合法真实开始时间 | 缺失或未来时间为 `null`，不使用页面加载时间 |
| `heartbeat` | Journey `agentSummary` 白名单心跳 | Standard 或缺失时只显示固定轮询说明 |
| `contextMetrics[]` | Context / Preflight 阶段白名单详情和 changed-files 数字 | 无可靠记录即隐藏 |
| `activityMetrics[]` | Agent 白名单计数或当前阶段安全记录计数 | 不展示非终态 turn 数，不读取原 detail |
| `fallbackTransfer` | Journey `engineKind === FALLBACK` | 仅使用固定 Agent -> Standard 转交文案 |
| `taskSummary` | TaskDetail 显式构造的任务 ID、类型、端类型、事件时间和数字摘要 | 不传入原始事件、错误或代码内容 |

## 7. 目标信息架构

### 7.1 桌面布局

```text
┌──────────────────────────────────────────────────────────────────────┐
│ 极简顶栏：返回｜任务｜Review 身份｜Provider/model｜状态｜选择｜中断 │
├───────────────┬───────────────────────────────┬──────────────────────┤
│ 六阶段时间轴   │                               │ 上下文安全摘要        │
│               │       中央运行主视觉            │                      │
│ 排队与调度     │   Agent Particle / Provider   │ Agent/Provider 活动   │
│ 确定性预检     │                               │                      │
│ 上下文准备     │       当前阶段真实文案          │ 心跳与预算安全摘要    │
│ 模型 Review    │                               │                      │
│ 解析与保存     │                               │                      │
│ 终态           │                               │                      │
├───────────────┴───────────────────────────────┴──────────────────────┤
│ 真实开始时间｜已运行时长｜最近心跳或固定安全提示                     │
└──────────────────────────────────────────────────────────────────────┘
```

桌面使用 `100dvh` 主视口。极简顶栏和底部状态条固定占位，中间工作区自行管理最小高度和溢出，
不得让普通任务详情卡片继续占据沉浸首屏。

### 7.2 极简顶栏

必须保留：

- 返回上一层；
- 任务 ID 和安全任务标题；
- Agent / Standard / Agent -> Standard fallback 身份；
- Provider/model 安全展示名；
- Review 主状态；
- 多 Review 选择器，仅多个结果时显示；
- 当前 Review 可中断时的中断操作；
- “任务信息”入口，打开只含现有安全任务概要的 Drawer。

不得放入：

- 全站质量治理、设置、版本更新等完整导航；
- 重新执行和复制重跑等 terminal / 调试操作；
- 原始事件、Worker、容器或基础设施入口。

### 7.3 左侧六阶段

- 继续使用 `ReviewJourneyStage` 的固定六阶段和七种状态。
- 桌面和 1024px 使用纵向阶段轨道，当前阶段高亮但不显示完成比例。
- 阶段主体点击继续打开现有 Drawer；WARNING / FAILED 感叹号继续打开独立 Popover。
- 状态必须同时使用图标、文字和颜色。
- 没有可靠记录的可选阶段继续遵守现有隐藏规则，不为填满视觉而制造节点。
- Drawer 的内容、安全白名单、轮询保持、阶段消失关闭和焦点恢复继续沿用 `docs/48`。

### 7.4 中央主视觉

阶段一：

- 在新的中央舞台中放大复用现有 BRAIN 或 Standard Provider 动效。
- 不改变 BRAIN 的状态语义，不增加风格切换。

阶段二：

- Agent 使用原生 Canvas 2D 粒子核心、轨道和柔和光晕。
- Standard 使用同一舞台尺寸的克制 Provider 数据流，不显示 Agent 大脑或取证粒子语义。
- 中央只显示当前真实阶段标题和固定安全说明。
- queued 使用低动态等待状态；running 根据已有 Agent 子阶段或统一 Review 阶段调整运动强度。
- fallback 仍在运行时明确展示“Agent 已转交 Standard Review”，并切换为 Standard 接管视觉。
- terminal 不继续展示全屏 Canvas，页面切回结果布局。

### 7.5 右侧安全摘要

“上下文概览”最多展示：

- 变更文件数等已有安全数字；
- Context Pack 是否可靠可用；
- 本地仓库准备、Planner / Retriever、Requested Context 的固定状态；
- 预算裁剪和未注入证据数量；
- AUTO_PREFLIGHT 固定状态。

“安全活动摘要”最多展示：

- 当前 Agent 子阶段或 Provider 固定活动；
- 最近合法心跳时间和“可能延迟”固定提示；
- 工具调用次数；
- 证据调用已用 / 上限；
- 源码返回字节已用 / 上限；
- terminal 前不可见的 turn 数不得提前展示。

固定规则：

- 没有可靠记录的卡片或字段隐藏，不使用 `0`、装饰图或其它字段补造。
- 可使用固定、`aria-hidden` 的抽象点线装饰，但不得一对一映射文件、路径、查询或依赖关系。
- 不得把活动摘要命名为“推理流”“思考过程”或“模型正在判断”。

### 7.6 底部状态

- 显示合法真实开始时间。
- 开始时间存在时显示实际已运行时长，按秒刷新只影响展示，不写入状态。
- 显示最近心跳或固定的“进度数据可能延迟”提示。
- 时间缺失时显示“历史任务未记录”或隐藏对应字段。
- 不显示百分比、进度条、预计剩余时间、置信度或阶段权重。

## 8. 视觉规范

- 运行态使用深黑蓝背景、紫蓝主光、少量青色辅助光，形成沉浸感但保持企业后台可读性。
- 所有信息卡使用半透明深色表面、清晰边框和稳定对比度，不依赖大面积模糊滤镜。
- 状态色仍遵守成功绿、警告橙、失败红、取消灰；状态语义不能只靠主视觉颜色。
- 中央光效不得覆盖阶段文字、按钮、Popover 或 Drawer。
- Canvas 和装饰层设置 `pointer-events: none`，所有交互由语义化 DOM 承担。
- 不使用远程图片、CDN 字体、视频或生成式背景。
- 当前普通 BRAIN 保留为 Canvas 初始化失败、Canvas context 不可用和降级场景的静态兜底。

## 9. Canvas 2D 契约

### 9.1 渲染边界

- 使用一个前景 Canvas 和 CSS 背景渐变，不引入 WebGL 或第三方渲染库。
- 使用固定种子和确定性粒子分布，轮询或 React 重渲染不得改变粒子拓扑。
- Canvas 实例以 `reviewKey + engineVisual` 为稳定边界；阶段变化只更新参数，不销毁并重建实例。
- 粒子数量按断点设固定上限，不读取业务数据决定粒子个数，避免把装饰误解为文件或 finding 数。
- 使用设备像素比适配清晰度，但设置 DPR 上限，避免高分屏无界放大绘制成本。
- 使用 `ResizeObserver` 处理容器尺寸；零尺寸时暂停并等待下一次有效尺寸。

### 9.2 生命周期

- 页面可见且当前 Review 为 queued / running 时才运行 `requestAnimationFrame`。
- 标签页隐藏、模式切换为 RESULT、路由离开或组件卸载时立即暂停并清理。
- 同一页面最多存在一个运行中的主 Canvas 动画循环。
- 轮询只更新状态参数，不增加监听器、Observer、timer 或动画循环。
- Canvas 初始化或绘制异常由局部错误边界处理，回退静态 BRAIN / Provider 图，不影响页面轮询。
- 不把异常正文、堆栈或 Canvas 能力信息展示给用户。

### 9.3 状态映射

| 状态 | Agent 粒子核心 | Standard 数据流 |
| --- | --- | --- |
| 排队 | 低频呼吸，轨道粒子静止或缓慢漂移 | Provider 与结果节点低频等待 |
| 分析 | 核心向外扩散，保持克制亮度 | 数据包从输入流向 Provider |
| 受控取证 | 轨道定向移动 | Provider 与安全结果节点往返 |
| 收敛 | 粒子向核心收拢 | 数据流减少并向结果侧集中 |
| 提交 | 单次定向汇聚 | Provider 向保存节点定向流动 |
| fallback 运行态 | 橙色固定转交提示后切换 Standard 视觉 | 显示接管状态 |

动画只表达平台当前阶段，不声称复现模型真实推理。

## 10. 响应式布局

### 10.1 1440px 及以上

- 单视口三栏：左侧阶段轨道、中央主视觉、右侧两张安全摘要卡。
- 中央主视觉获得最大可用空间，左右栏设置稳定宽度和内部滚动上限。
- 页面本身不出现水平滚动。

### 10.2 1024px

- 继续保留左侧纵向阶段轨道。
- 中央视觉优先，右侧摘要压缩为较窄栏；高度不足时右侧内部滚动。
- Provider/model、任务标题和阶段文案截断并提供 Tooltip。
- 不通过缩小字体或按钮命中区强行维持桌面比例。

### 10.3 390px

- 使用粘性紧凑顶栏；多 Review 选择器独占一行或使用可访问下拉菜单。
- 内容按“中央视觉 → 当前阶段 → 纵向六阶段 → 安全摘要 → 底部状态”自然纵向滚动。
- 不要求一个物理屏幕同时容纳所有模块，但首屏必须看到 Review 身份、当前阶段和主视觉。
- 阶段 Drawer 使用 `100vw × 100dvh`。
- 任务信息和操作使用 Drawer / 菜单，不把所有桌面按钮挤在顶栏。
- 页面不得出现横向溢出。

## 11. 交互、轮询与焦点

- Enter / Space 打开阶段 Drawer 或操作菜单，Escape 关闭最上层浮层。
- 阶段 Drawer 关闭后焦点返回对应阶段节点；轮询后节点仍存在时保持 Drawer 和焦点目标。
- 当前阶段消失时安全关闭 Drawer；页面从 IMMERSIVE 切换 RESULT 后仍存在同一阶段时可保持 Drawer。
- 多 Review 选择后更新 URL `reviewKey`，不得因进入或退出沉浸模式丢失参数。
- 轮询不得重置滚动位置、多 Review 选择、当前阶段、Drawer 或 Canvas 动画起点。
- 中断操作继续调用现有接口并使用现有确认语义；本专项不新增操作接口。
- “任务信息”Drawer 只负责在沉浸态补充现有安全任务概要，不成为第二套任务详情页面。

## 12. 无障碍与 reduced-motion

- 沉浸模式使用语义化 `header / main / nav / aside / footer`。
- Canvas 提供随 Journey 更新的 `aria-label`，绘图本身标记为装饰，不产生大量可读节点。
- 所有文字与深色背景达到可读对比度；focus-visible 使用高对比描边。
- 状态同时提供文字、图标和颜色，不用粒子速度表达唯一信息。
- `prefers-reduced-motion: reduce` 时停止循环、轨道移动、呼吸、闪烁和大范围过渡：
  - Agent 显示静态粒子核心或静态 BRAIN；
  - Standard 显示静态 Provider 数据流；
  - 状态和阶段文字继续实时更新。
- 页面不自动播放声音，不自动抢焦点，不重复播报每次心跳和每秒运行时长。
- IMMERSIVE / RESULT 切换使用短暂、可关闭的 CSS 过渡；reduced-motion 下直接切换。

## 13. 安全与兼容边界

沉浸工作台只允许展示：

- Review 身份、Provider/model 安全展示名和固定状态；
- ReviewJourney 六阶段、七种状态、合法时间和可计算真实耗时；
- `runId`、`claimAttempt` 等既有安全序号仅在现有阶段详情需要时展示；
- 固定活动、固定错误码、心跳、预算和非负数字摘要；
- Context Pack、预检和上下文准备的现有白名单派生信息。

禁止展示：

- Prompt、查询、工具参数、源码、diff 内容、文件路径；
- Worker ID、容器、网络地址和基础设施拓扑；
- 异常原文、assistant 原文、模型原文或模型推理；
- Key、query hash、path hash 或原始 progress detail；
- 虚构百分比、预计剩余时间、置信度和模型思考过程。

兼容规则：

- 旧任务或字段缺失：保持结果布局并显示“历史任务未记录”，不强制进入空的沉浸页。
- 损坏 detail：只使用 ReviewJourney 已有固定安全回退，不直接解析或展示原字符串。
- 时间缺失或未来时间：不显示运行时长，不用本地加载时间冒充开始时间。
- Canvas、Presentation、动画或布局失败：回退现有安全 UI，不改变 Review 主状态。
- Agent 可见数据安全白名单不因画布或抽象图扩展。
- 当前 `reviewKey` 的 Journey 是唯一模式来源；其它 Review 的 queued / running 状态不会覆盖当前
  terminal 选择。
- AppFrame 不接收 Review、progress 或原始错误；它只接受经归一化的模式报告，并同时核对当前路由，
  因此路由离开不依赖子组件 effect 完成后才恢复。
- TaskDetail 的错误只作为“恢复普通框架”的布尔安全回退条件传入 Presentation，不把异常正文交给
  Presentation 或沉浸工作台。
- 沉浸 Task 信息 Drawer 只使用显式任务安全摘要；普通结果页原有基础信息、Finding、Diff、Patch、
  补证据、反馈、评估样本、重试和 Push 审核继续走既有组件。

## 14. 实施范围

允许修改：

- `frontend/src/App.jsx`；
- `frontend/src/reviewJourneyPresentation.js`；
- 新增必要的沉浸 Presentation 和 Canvas 纯函数 / 组件文件；
- `frontend/src/styles.css`；
- 对应前端纯函数和组件契约测试；
- `docs/38`、`docs/48` 和本文。

不得修改：

- Java Backend、Python Backend、数据库或公开 API；
- ReviewJourney 阶段和状态语义；
- Review 结果、Review Card schema、Standard Review 或 fallback 行为；
- Agent 调度、队列、租约、Worker 或通知；
- Provider、Prompt、预算或工具白名单；
- `docs/36`；
- 已暂停的 `docs/49` 实现、依赖或资源。

必须保留：

- Review 身份、多模型选择和 `reviewKey` URL 直达；
- 多结果事件隔离和 task-level AUTO_PREFLIGHT 白名单共享；
- 现有轮询和选择保持；
- 阶段 Drawer、Popover、焦点恢复和安全执行记录；
- Finding、Diff、Patch、补证据、反馈和评估样本；
- 重试、中断、Push 审核和任务信息；
- Agent 可见数据安全白名单。

## 15. 阶段一：沉浸布局与状态切换

### 15.1 前置条件

- `docs/48` 三阶段代码和使用反馈已进入当前基线。
- `docs/49` 保持暂停且没有未提交实现。
- 开始前检查工作树，发现未知 tracked 改动时停止，不得覆盖或重写。

### 15.2 实施内容

- 先更新本文状态为“阶段一实施中”、组件契约和兼容边界。
- 新增 `ReviewImmersivePresentation` 纯函数及模式派生测试。
- 建立 `ReviewWorkspaceModeContext`，确保 AppFrame 在运行态隐藏、终态和卸载时恢复。
- 实现极简顶栏、任务信息 Drawer、三栏工作区、纵向六阶段、中央舞台、右侧安全摘要和底部状态。
- 阶段一只放大复用现有 BRAIN / Provider 动效，不实现 Canvas。
- queued / running 使用沉浸布局；terminal 和历史任务继续使用现有结果优先布局。
- 保持当前 `reviewKey`、轮询、Drawer、Popover、Finding、Diff、Patch、补证据、反馈、评估、重试和中断。
- 更新 `docs/38` 的实际入口说明。

### 15.3 测试

- queued / running / terminal / historical 模式派生；
- Agent、Standard、fallback 和多 Review；
- URL 直达、选择切换和轮询不重置；
- AppFrame 进入、终态恢复、路由离开恢复和错误回退；
- 阶段 Drawer、Popover、Enter / Space / Escape 和焦点恢复；
- Finding、Diff、Patch、补证据、反馈、评估、重试和中断不回归；
- 1440 / 1024 / 390 浏览器检查；
- 全部前端测试和 `scripts\run-frontend.cmd build`；
- 安全禁显字段 diff 审计。

### 15.4 停止点

完成本文阶段一结果、实际测试、浏览器检查和遗留风险回填后停止。等待用户确认全屏范围、布局、
信息密度、终态恢复和移动端体验；未经确认不得进入阶段二、提交、推送或部署。

### 15.5 阶段一实施结果

阶段一于 2026-07-30 完成本地实施，实际落点如下：

- 新增 `frontend/src/reviewImmersivePresentation.js`，以当前选中的 `ReviewJourney`、现有白名单阶段详情、
  Agent 安全摘要和显式任务安全摘要派生 `LOADING / IMMERSIVE / RESULT`；Presentation 不接收也不解析
  原始 progress detail。
- `TaskDetail` 成为 `activeReviewKey` 的唯一 UI 状态所有者；URL 合法 `reviewKey` 可直达，普通结果 Tabs
  与沉浸顶栏选择器使用同一更新入口，轮询和列表重排不重置用户选择。
- `AppFrame` 与 `TaskDetail` 通过内部 `ReviewWorkspaceModeContext` 协作。只有当前任务详情路由且当前
  Review 为 queued / running 时隐藏普通导航并解除 Content 的普通页面约束；terminal、派生失败、
  路由离开和组件卸载均回到普通结果布局。
- 新增路由级 `ReviewImmersiveWorkspace`：极简顶栏、纵向 ReviewJourney 时间轴、中央舞台、右侧
  “安全活动摘要”、真实时间底栏和白名单任务信息 Drawer 已落地。Agent 复用现有 BRAIN，
  Standard / fallback 复用现有 Provider 数据流；fallback 明确显示 Agent -> Standard 转交。
- 阶段 Drawer、WARNING / FAILED Popover、任务级 AUTO_PREFLIGHT、Enter / Space / Escape 和焦点恢复
  继续复用既有组件契约；terminal Finding、Diff、Patch、补证据、反馈、评估样本、重试、中断和
  Push 审核布局未重构。
- 响应式覆盖桌面三栏、1024px 辅助栏压缩和 390px 单列滚动。浏览器验收发现并修复了移动端按钮
  隐藏文字时图标同时继承 `font-size: 0` 的问题，返回、中断和任务信息图标已恢复可见。
- 未使用 Fullscreen API、body class、Canvas、WebGL、ENERGY、Lottie、远程资源或新动画依赖；
  Backend、数据库、公开 API、ReviewJourney 和结果 schema 均未修改。

### 15.6 实际验证

自动化验证：

- `node --test frontend/tests/*.test.mjs`：50 / 50 通过，0 失败。
- `scripts\run-frontend.cmd build`：通过；Vite 产物生成成功。保留既有单 JS chunk 超过 500 kB 的
  非阻塞提示，本阶段没有新增依赖或拆包范围。
- 新增 Presentation / AppFrame 契约测试覆盖 Agent 与 Standard 的 queued、running、success、
  failed、cancelled、skipped，fallback、历史 / 缺失字段、三种页面模式、多 `reviewKey`、
  路由恢复、Drawer / Popover / 键盘与 reduced-motion CSS 契约；既有 Finding、Diff、Patch、
  补证据、反馈、评估、重试、中断和 Push 审核测试继续通过。

浏览器验收只连接本地安全合成 API（`127.0.0.1:8080`），未连接真实 Backend：

- 1440 × 900：Agent running 为单视口三栏，实测列宽约 274 / 786 / 317px；普通品牌导航隐藏，
  页面无横向或纵向外层溢出。阶段 Drawer、Escape 和焦点恢复通过。
- 1024 × 800：实测列宽约 230 / 508 / 238px，中央舞台保持优先；Standard running 仅显示
  Provider 数据流，不出现 BRAIN 或 Agent 取证语义；fallback 使用 Provider 视觉并明确展示
  Agent -> Standard，独立告警 Popover 的打开、Escape 和焦点恢复通过。
- 390 × 844：粘性紧凑顶栏、中央舞台、当前阶段 / 纵向时间轴、安全摘要和底部状态按顺序滚动；
  文档 `scrollWidth` 与 `clientWidth` 一致。任务信息和阶段 Drawer 实测为 390 × 844，
  Enter / Space / Escape 与触发点焦点恢复通过。
- 多 Review：从 `agent-running` 切换到 `standard-terminal` 后 URL 更新并恢复普通结果布局；
  当前 terminal 未被同任务另一个 running Review 抢占。
- 轮询恢复：安全合成任务 `polling-review` 在不刷新页面的情况下由 running 进入 terminal，
  AppFrame 自动恢复普通导航和结果优先布局，URL 保持不变。
- 安全检查：运行态 DOM 未出现合成响应中故意植入的 Prompt、Worker、异常原文、分支 / 文件路径；
  页面未显示百分比、预计剩余时间、token 进度或模型思考过程。

### 15.7 遗留风险与阶段二前置条件

- reduced-motion 已由 CSS 契约测试覆盖；本次受控浏览器没有切换操作系统媒体偏好，仍建议人工验收时
  在系统开启“减少动态效果”后确认现有 BRAIN / Provider 动效静止且文案继续更新。
- Vite 的既有单 chunk 体积提示未在阶段一处理；它不影响本次布局和状态切换验收。
- 移动端采用单列长页面，右侧安全摘要信息较多；信息密度是否需要进一步收敛由本次人工验收决定，
  不在未确认状态下自行删减白名单信息。
- 阶段二的必要前置条件仍是：用户明确确认阶段一的全屏范围、布局、信息密度、终态恢复和移动端体验；
  阶段一代码进入后续基线；届时再单独更新本文并实施原生 Canvas 2D。当前不得提前进入阶段二。

## 16. 阶段二：原生 Canvas 粒子核心

### 16.1 前置条件

- 用户明确确认阶段一。
- 阶段一代码已经提交并进入当前基线。
- 沉浸模式切换、响应式和安全摘要已经稳定。

### 16.2 实施内容

- 先更新本文状态为“阶段二实施中”、Canvas 生命周期和性能预算。
- 新增原生 Canvas 2D Agent 粒子核心与 Standard 数据流。
- 使用固定种子、DPR 上限、ResizeObserver 和单一动画循环。
- 完成阶段参数更新、标签页隐藏暂停、零尺寸等待、卸载清理和轮询不重建。
- 完成 reduced-motion 静态构图和 Canvas 不可用 / 绘制失败的静态 BRAIN / Provider 回退。
- 不安装新动画依赖，不添加远程资源、风格菜单或偏好。

#### 16.2.1 Canvas 生命周期契约

- 中央舞台只挂载一个 Canvas 展示组件；实例稳定边界为当前
  `selectedReviewKey + engineVisual`。同一 Review 的阶段变化、5 秒轮询和 Presentation 文案更新只调用
  `setRenderParameters`，不得替换 Canvas DOM、重复创建 `ResizeObserver`、重复注册
  `visibilitychange` 或启动第二个 `requestAnimationFrame`。
- Canvas 控制器初始化时只获取一次 2D context、注册一个 `ResizeObserver` 和一个页面可见性监听器；
  卸载时取消待执行 RAF、断开 Observer、移除监听器并清空引用。切换 RESULT、离开任务路由或切换到
  其它 `reviewKey + engineVisual` 时均通过 React 卸载走同一清理路径。
- `ResizeObserver` 是尺寸变化的唯一绘制缓冲区入口。容器宽或高小于等于零时取消 RAF、不调整为伪造
  尺寸、不持续空绘；收到下一次合法尺寸后再同步 backing store 并按页面可见性恢复。
- 页面隐藏时立即取消 RAF；恢复可见时先绘制当前参数帧，再在非 reduced-motion 且尺寸合法时恢复唯一
  循环。reduced-motion 只在初始化、合法 resize 或渲染参数变化时绘制静态帧，不启动持续循环。
- Canvas 组件只接收 `ReviewImmersivePresentation` 中的 `selectedReviewKey / engineVisual /
  engineIdentity / heroState / currentStageId / ariaLabel`、reduced-motion、合法容器尺寸和 DPR；
  不接收 Review、原始 progress detail、Provider 响应或业务回调。

#### 16.2.2 性能预算

- 固定种子为代码常量；粒子拓扑使用归一化坐标确定性生成，不按文件、Finding、工具调用或其它业务数量
  改变。宽度 `<= 480px` 上限 48 个、`<= 1180px` 上限 80 个、更宽视口上限 120 个；
  Standard 数据流最多消费同一上限中的 24 个装饰数据点。
- DPR 最低按 1 处理、最高限制为 2；Canvas backing store 只在合法尺寸或 DPR 实际变化时调整。
  1440、1024、390px 均以单 Canvas、单 RAF 为硬约束，目标平均绘制耗时不超过 8ms/帧，
  长时间安全合成轮询不得出现 RAF、Observer、监听器或 Canvas 实例累积。
- 绘制只使用 Canvas 2D 基础路径、渐变和固定颜色；CSS 负责舞台背景，不使用阴影滤镜堆叠、
  像素读取、离屏大图、WebGL、图片、视频、字体或远程资源。标签页隐藏和零尺寸期间绘制次数必须为零。
- 性能观测只记录本地测试中的帧数、绘制耗时、实例和监听器计数，不采集 Review 数据，不向 Backend
  上报，也不改变页面状态。
- Canvas shell 只通过只读 `data-review-canvas-*` 属性暴露当前控制器的帧数、平均 / 最大绘制耗时、
  粒子数、DPR、RAF 运行态及 Observer / visibility listener 状态，供本地浏览器验收读取；属性不包含
  Review、阶段 detail、源码或其它业务数据，不提供控制方法。

#### 16.2.3 失败回退契约

- `canvas.getContext('2d')` 不可用、初始化抛错、resize 同步失败或任一帧绘制抛错时，控制器只触发一次
  本地失败信号并立即停止 RAF、断开 Observer、移除监听器；异常正文和能力信息不进入 DOM。
- Agent 失败时恢复阶段一现有静态 `BRAIN`；Standard 与 fallback 失败时恢复阶段一现有静态 Provider
  视觉。fallback 的固定“Agent 已转交 Standard Review”提示继续由 Presentation 展示。
- 失败回退只替换中央视觉，不写 Review 状态、不暂停或重启任务轮询、不改变当前 `reviewKey`、页面模式、
  Drawer、结果数据或操作能力。切换到新的稳定实例边界时允许重新尝试 Canvas，失败实例本身不自动重试。
- reduced-motion 不是失败：Canvas 可用时显示静态 Canvas 构图；只有 Canvas 不可用或绘制失败才使用
  阶段一静态 BRAIN / Provider。

#### 16.2.4 本地安全验收启动契约

- 阶段二浏览器验收使用仓库脚本统一启动 Vite 与可识别的 docs/50 安全 mock，不再由 Agent 直接以前台
  命令等待长驻进程退出。启动器必须在创建进程后立即记录 launcher PID，并在 ready 后记录实际端口 owner
  PID；stdout / stderr 写入 `.local/`。
- 启动前分别检查 frontend 与 mock 端口。端口已监听时，只有 HTTP 页面、mock 专用 health 标识和
  frontend 代理后的同一 health 标识全部匹配才允许复用；端口被真实 Backend、其它 Vite 或未知服务占用时
  必须停止并提示改用其它验收端口，不得把“端口存在”误判为 docs/50 验收环境 ready。
- mock 暴露固定的本地 health 响应，不读取 Backend、数据库或真实 Review。Vite 启动时通过显式
  `ApiProxyTarget` 覆盖本机通用 `.local/gitlab.env`，该覆盖只作用于验收子进程，不修改用户环境文件。
- ready 使用有界轮询同时核对：launcher / service 仍存活或端口已有明确 owner、端口处于 LISTENING、
  frontend 根页面返回 200、mock 直连 health 返回固定标识、frontend 代理 health 返回相同固定标识。
  任一条件超时即报告日志并只清理由本次启动器创建的 PID。
- 默认端口仍为 frontend `5173`、mock `8080`；端口被用户已有服务占用且身份不匹配时可显式传入独立端口
  完成安全验收。浏览器验收结束只允许停止状态文件记录且仍拥有对应端口的本次 service PID。

### 16.3 测试

- 固定种子和状态映射纯函数；
- Agent / Standard / fallback 运行态；
- 初始化、resize、零尺寸、DPR 上限和绘制失败；
- 页面隐藏暂停、恢复、卸载和单实例约束；
- 轮询更新不重建 Canvas、不增加监听器；
- reduced-motion 静态状态；
- 1440 / 1024 / 390 视觉和性能检查；
- 长时间本地安全合成轮询观察；
- 全部前端测试和 `scripts\run-frontend.cmd build`；
- 无远程资源请求、无新动画依赖和安全禁显字段审计。

### 16.4 停止点

完成本文阶段二结果、实际测试、性能数据、浏览器检查和部署前置条件回填后停止。等待用户确认部署验证；
不得自动恢复 `docs/49`、提交、推送、部署或执行真实 Agent Review。

### 16.5 阶段二实施结果

- 新增 `frontend/src/reviewCanvasRenderer.js`，以固定种子 `0x50c0de` 生成归一化确定性粒子拓扑；
  Canvas 容器宽度 `<= 480px`、`<= 1180px` 和更宽时对应硬上限 48 / 80 / 120，Standard 数据流最多
  消费 24 个装饰点，DPR 上限为 2。
- 新增 `ReviewImmersiveCanvas`，中央舞台只渲染一个 Canvas。组件稳定边界为
  `selectedReviewKey + engineVisual`；同一 Review 的 `heroState / currentStageId / reducedMotion`
  变化只调用控制器参数更新，不替换 Canvas DOM。
- Agent 使用原生 Canvas 2D 粒子核心、三层轨道和柔和光晕；Standard 使用输入、Provider、结果三节点的
  克制数据流。Presentation 新增固定 `AGENT / STANDARD / FALLBACK` 安全身份，fallback 保持
  Standard 数据流与阶段一固定转交提示，不显示 Agent 大脑。
- 控制器只创建一个 2D context、一个 `ResizeObserver`、一个 `visibilitychange` 监听器和最多一个待执行
  RAF。零尺寸取消循环并等待合法 resize；页面隐藏暂停、恢复可见后按当前参数继续；卸载统一取消 RAF、
  断开 Observer 并移除监听器。
- reduced-motion 使用静态 Canvas 构图，不启动持续 RAF。context 不可用、初始化失败、resize / 绘制抛错
  时只触发一次局部失败信号并清理控制器；Agent 回退阶段一静态 BRAIN，Standard / fallback 回退阶段一
  静态 Provider，不改变 Review 状态、轮询、当前 `reviewKey`、Drawer 或结果数据。
- Canvas 不接收 Review、原始 progress detail、Prompt、查询、工具参数、源码、diff、路径、异常或模型原文；
  只消费 Presentation 白名单状态、当前阶段、安全身份、reduced-motion、合法尺寸和 DPR。
- 为安全浏览器验收新增 tracked `scripts/docs50-mock-server.mjs`、`run-docs50-acceptance.cmd/.ps1` 和显式
  frontend `ApiProxyTarget / HostAddress / Port / StrictPort` 参数。启动器能识别 mock 专用 health、
  区分真实 Backend / 未知端口占用、记录 launcher / service PID、端口和日志，并支持按状态文件精确停止。

### 16.6 自动化验证与构建

- `node --test frontend/tests/*.test.mjs`：最终 61 / 61 通过，0 失败；其中包含阶段一全部回归、
  Canvas 专项测试和 4 项验收启动脚本契约 / 最小 detached helper 返回测试。
- `scripts\run-frontend.cmd build`：通过；Vite 成功生成产物。保留既有单 JS chunk 超过 500kB 的非阻塞
  提示，本阶段未增加 frontend 依赖。
- Canvas 专项测试覆盖固定种子、粒子上限、六种运行态确定性映射、Agent / Standard / fallback、
  ResizeObserver、零尺寸、DPR 上限、resize、初始化 / 绘制失败、标签页隐藏 / 恢复、reduced-motion、
  单 Canvas、单 RAF、轮询参数更新不累积监听器和卸载清理。
- Presentation / 阶段一回归测试继续覆盖当前 `reviewKey` 模式来源、多 Review 选择保持、URL 直达、
  AppFrame 恢复、Drawer / Popover / 键盘契约，以及 Finding、Diff、Patch 等既有结果能力源码契约。
- 启动环境契约测试覆盖显式代理覆盖顺序、mock 固定 health、PID / 端口 / HTTP ready、无
  `WaitForExit` 和最小 detached helper 快速返回。15173 / 18080 曾实际达到 frontend、mock 直连 health
  与 frontend 代理 health 全部 ready；Windows 下完整 `run-docs50-acceptance.cmd` 的 command-exit
  复验仍按用户要求暂停，不作为已通过项。

### 16.7 浏览器验收、性能数据与遗留风险

- 浏览器通过人工准备的 frontend `127.0.0.1:5173` 和安全 mock `127.0.0.1:8080` 完成验收。先核对
  frontend 页面和代理后的任务响应，确认任务 42 返回“安全合成项目”，未连接真实 Review 数据。
- 1440px 验证 Agent running、Standard running、Agent -> Standard fallback、terminal 结果页和同一任务
  多 `reviewKey` 切换：三种运行身份均只有一个 Canvas；Standard 不显示 Agent 大脑或受控取证语义；
  fallback 明确显示“Agent 已转交 Standard Review”并切换为 Provider 数据流；切换到
  `standard-terminal` 后 URL 与当前选择保持，其他 running Review 未抢占页面。
- 1024px 验证 Agent 与 fallback 三栏压缩布局，390px 验证 Agent、Standard 单列布局和 terminal 结果页；
  三档均未出现文档级横向溢出。terminal 页面、任务列表路由均不保留 Canvas 或沉浸工作台节点。
- 阶段 Drawer 和告警 Popover 可打开，Escape 关闭后焦点恢复到触发按钮；Finding 展开、Diff 和 Patch
  入口继续存在。验收时运行中的旧 mock 仍返回历史 `diff` 字段，Diff 弹窗因此显示“未保存该文件 diff”；
  tracked fixture 已改为前端契约字段 `diffText` 并补测试，但因不得重启用户服务，本轮未用新进程复验内容。
- Canvas shell 的只读诊断显示：1440px 中央容器宽度落入 48 粒子档，DPR 为 1；Agent 5 秒观察的平均绘制
  耗时约 `0.188ms`、最大约 `0.6ms`，Standard 约 `0.150ms` / `0.5ms`，fallback 约
  `0.159ms` / `0.5ms`，均低于 `8ms/帧` 预算。观察期间始终为一个 Canvas，RAF 持续推进，
  `ResizeObserver` 与 visibility listener 各保持一个活动实例，没有实例或监听器累积。
- 安全合成运行态额外持续观察 10 秒，Canvas 身份、实例数和监听器计数保持稳定；切换 terminal 和离开任务
  路由后 Canvas 数归零。当前运行中的旧 mock 不包含最新 reset / complete 控制端点，因此未在浏览器中
  强制完成 running -> terminal 的同一响应轮询跃迁；参数更新不重建和终态清理由自动化测试覆盖。
- 受控浏览器当前不能模拟 `prefers-reduced-motion`、不能可靠把被测页切换为隐藏标签页，也不开放
  Canvas context / draw 异常注入。这三项未冒充浏览器实测通过；静态构图、隐藏暂停 / 恢复以及初始化 /
  绘制失败回退由控制器测试覆盖，仍建议部署验证时使用可控制媒体特性和页面可见性的浏览器再抽查一次。
- 页面可见 DOM 资源只有本地 Vite client 和入口模块，未发现远程 URL；禁显 Prompt、Worker、异常合成串
  未进入页面。控制台没有 Canvas 运行异常，仅观察到既有 Ant Design `Space.direction`、
  `Alert.message` 和 `Descriptions span` 弃用 / 布局告警。
- Windows Codex 环境中长驻子进程的 detached / Job Object 边界仍存在 command-exit 复验风险。
  service ready 与 launcher command-exit 必须继续作为两项独立契约；不得因工具仍 Running 重复启动实例。
- 未修改 Backend、数据库、公开 API、ReviewJourney、Review 结果 schema、Provider、Prompt、预算、
  工具白名单、调度、队列、租约、Worker、通知、`docs/36` 或 `docs/49`；未提交、推送、部署、执行真实
  Agent Review 或 Run 18。

## 17. 验收矩阵

| 场景 | 页面模式 | 主视觉 | 关键行为 |
| --- | --- | --- | --- |
| Agent queued | IMMERSIVE | 低动态 Agent 视觉 | 调度阶段真实高亮，无百分比 |
| Agent running | IMMERSIVE | 粒子核心 | 显示真实当前阶段和白名单活动 |
| Standard queued/running | IMMERSIVE | Provider 数据流 | 不显示 Agent 大脑或取证语义 |
| fallback 接管中 | IMMERSIVE | 转交后 Standard 视觉 | 明确 Agent -> Standard |
| success | RESULT | 现有紧凑 Hero / 时间轴 | Finding、Diff、Patch 优先 |
| failed/cancelled/skipped | RESULT | 现有终态表现 | 保留告警、重试或结果语义 |
| 历史任务 | RESULT | 历史安全回退 | 不补造阶段、时间或沉浸内容 |
| 多 Review | 由当前选择决定 | 当前 reviewKey 对应视觉 | URL 和轮询不重置选择 |
| Drawer 已打开后轮询 | 保持当前模式 | 动画不重建 | 阶段存在则保持，消失则关闭 |
| Canvas 失败 | IMMERSIVE | 静态 BRAIN / Provider | Review 状态和轮询不受影响 |
| reduced-motion | 同原模式 | 静态构图 | 文案和真实状态继续更新 |
| 1440px | IMMERSIVE | 三栏单视口 | 无水平滚动 |
| 1024px | IMMERSIVE | 中央视觉优先 | 辅助栏安全压缩 |
| 390px | IMMERSIVE | 首屏主视觉 | 纵向阶段、全屏 Drawer |

## 18. 实施验证要求

自动化：

```text
node --test frontend/tests/*.test.mjs
scripts\run-frontend.cmd build
```

浏览器检查：

- 只使用安全本地合成响应，不连接真实 Backend。
- 1440、1024 和 390px 分别检查布局、滚动、截断、Drawer、Popover 和操作命中区。
- 验证 selected reviewKey queued/running -> terminal 的无刷新模式切换。
- 验证多 Review 切换、5 秒轮询、当前 Drawer 和 Canvas 实例稳定。
- 验证 reduced-motion、标签页隐藏和 Canvas 失败回退。

安全审计：

- 搜索新增 UI 文案和数据映射，确认没有百分比、预计时间、置信度或推理流。
- 检查最终 diff 不包含 Prompt、查询、工具参数、源码、diff 内容、文件路径、Worker ID、容器、
  网络地址、异常原文、assistant / 模型原文、模型推理、Key、query hash 或 path hash。
- Canvas、观测和 UI 派生失败不得改变 Review 主状态。

## 19. 文档、提交与部署边界

- 每个阶段开始前先更新本文，再修改前端代码。
- 每个阶段只提交本阶段相关前端、测试、`docs/38` 和本文。
- 保留用户已有未跟踪文件，不修改、删除、暂存或提交。
- 每个阶段完成后必须停止等待用户确认，不自动进入下一阶段。
- 未经用户明确要求，不得提交、推送、部署、执行真实 Agent Review 或运行验收回放。
- `docs/49` 保持暂停；本专项验收不等于恢复动画风格扩展。

## 20. 总控 Prompt

```text
请只按 docs/50-review-running-immersive-workspace-plan.md 推进 Review 运行态沉浸式工作台。

开始前完整阅读根目录 AGENTS.md 和 docs/50，使用 rg 按需核对 docs/38、docs/48、docs/49、
ReviewJourney、ReviewJourneyPresentation、AppFrame、TaskDetail、现有 Hero/时间轴/Drawer/Popover、
styles 和对应测试。检查 git status，保留用户改动；存在未知 tracked 改动或上一阶段未进入基线时停止。

每次只实施 docs/50 的一个阶段。ReviewJourney 是唯一阶段数据源；当前选中 reviewKey 为 QUEUED/RUNNING
时进入路由级沉浸工作台，terminal 和历史任务继续使用结果优先详情。Agent 与 Standard 共用布局但使用
不同视觉。不得显示百分比、预计时间、置信度或模型推理。

允许修改 React 前端、纯展示模型、Canvas 组件、样式、对应测试、docs/38、docs/48 和 docs/50；
不得修改 Backend、数据库、API、ReviewJourney 语义、Review 结果、Standard/fallback 行为、调度、
队列、租约、Worker、Provider、Prompt、预算、工具白名单、Review Card schema 或 docs/36。
docs/49 保持暂停，不实现 ENERGY、Lottie、动画风格切换或偏好。

阶段完成后执行全部前端测试、scripts\run-frontend.cmd build、1440/1024/390 浏览器检查和安全 diff
审计，回填 docs/50 后停止等待用户确认。不得自动进入下一阶段、提交、推送、部署或执行真实 Review。
```

## 21. 阶段一 Prompt

```text
请只实施 docs/50 的阶段一“沉浸布局与状态切换”。

开始前：
1. 完整阅读 AGENTS.md 和 docs/50。
2. 使用 rg 按需核对 docs/38、docs/48、docs/49、reviewJourney.js、
   reviewJourneyPresentation.js、App.jsx、styles.css 和现有前端测试。
3. 检查 git status，确认 docs/48 基线完整、docs/49 没有实现且保持暂停；保留用户文件。
4. 先更新 docs/50 的阶段一实施状态、组件契约和兼容边界，再改前端。

目标：
1. 新增 ReviewImmersivePresentation，以当前选中 ReviewJourney 派生 LOADING/IMMERSIVE/RESULT。
2. 建立 AppFrame 与 TaskDetail 的 ReviewWorkspaceModeContext；queued/running 隐藏普通应用导航，
   terminal、错误、卸载和路由离开可靠恢复。
3. 实现极简顶栏、任务信息 Drawer、三栏工作区、纵向六阶段、中央舞台、右侧安全摘要和底部真实时间。
4. Agent 与 Standard 共用布局；本阶段中央只放大复用现有 BRAIN / Provider 动效。
5. 保留 reviewKey URL、轮询选择、Drawer、Popover、Finding、Diff、Patch、补证据、反馈、评估、
   重试、中断和 Push 审核。
6. 不显示百分比、预计时间、置信度或模型推理。

边界：
- 不实现 Canvas、ENERGY、Lottie、动画切换或偏好。
- 不修改 Backend、API、ReviewJourney 语义或 Review 行为。
- terminal 和历史任务继续使用现有结果优先详情。

验证：
- 覆盖 queued/running/terminal、Agent/Standard/fallback/历史、多 reviewKey 和轮询切换；
- 覆盖 AppFrame 恢复、Drawer/Popover、键盘、焦点和既有结果能力；
- 执行全部 frontend/tests/*.test.mjs 和 scripts\run-frontend.cmd build；
- 完成 1440/1024/390 安全合成浏览器检查和安全 diff 审计。

完成后回填 docs/50 阶段一结果并停止，等待用户确认；不得进入阶段二、提交、推送或部署。
```

## 22. 阶段二 Prompt

```text
仅在用户确认阶段一且阶段一已经进入当前基线后，实施 docs/50 的阶段二“原生 Canvas 粒子核心”。

开始前：
1. 完整阅读 AGENTS.md 和 docs/50，核对阶段一结果和遗留风险。
2. 检查 git status 和提交基线；阶段一未提交或存在未知 tracked 改动时停止。
3. 先更新 docs/50 的阶段二实施状态、Canvas 生命周期、性能和回退契约。

目标：
1. 使用原生 Canvas 2D 实现 Agent 粒子核心、轨道和光晕。
2. 为 Standard 实现同舞台的克制 Provider 数据流，不显示 Agent 大脑。
3. 固定粒子种子和数量上限，设置 DPR 上限，使用 ResizeObserver 和单一动画循环。
4. 轮询与阶段变化只更新参数，不重建实例；标签页隐藏、RESULT、卸载和路由离开时清理。
5. reduced-motion 使用静态构图；Canvas 不可用或绘制失败回退静态 BRAIN / Provider。
6. fallback 接管中明确转交并切换 Standard 视觉。

边界：
- 不安装动画依赖，不使用 WebGL、Lottie、图片、视频或远程资源。
- 不恢复 docs/49，不实现风格切换或偏好。
- Canvas 不读取原始 progress detail，不影响 Review 状态或轮询。

验证：
- 覆盖状态映射、固定种子、resize、零尺寸、DPR、失败回退、后台暂停、卸载和单实例；
- 覆盖 Agent/Standard/fallback、多 reviewKey、轮询稳定和 reduced-motion；
- 执行全部 frontend/tests/*.test.mjs 和 scripts\run-frontend.cmd build；
- 完成 1440/1024/390、长时间合成轮询、性能、无远程请求和安全 diff 审计。

完成后回填 docs/50 阶段二结果并停止，等待部署验证；不得提交、推送、部署、执行真实 Agent Review
或自动恢复 docs/49。
```
