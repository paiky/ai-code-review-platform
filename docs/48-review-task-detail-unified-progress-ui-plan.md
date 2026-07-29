# 任务详情统一 Review 进度 UI 改造计划

## 1. 状态与目标

- 文档状态：计划已确认，等待按阶段实施。
- 关联文档：
  - `docs/38-review-lifecycle-and-frontend-entrypoints.md`：当前 Review 生命周期与任务详情入口。
  - `docs/39-review-accuracy-and-material-ui-roadmap.md`：任务详情 MUI 外层框架和全站视觉原则。
  - `docs/40-review-evidence-pipeline-and-multi-target-roadmap.md`：确定性 Preflight、Context Pack 和 Planner / Retriever。
  - `docs/46-agent-review-runtime-observability-plan.md`：Agent 心跳、预算和安全执行轨迹。
  - `docs/47-agent-review-multi-worker-pool-and-queue-governance-plan.md`：多 Worker、租约接管和队列治理。
  - `docs/49-review-progress-animation-style-extension-plan.md`：第一版大脑动画稳定后的能量球和本地 Lottie 风格扩展。
- 本文目标：把任务详情中的 Agent Review、普通 Review、高准确模式、确定性检查和执行过程收敛为一套
  可一眼识别 Review 类型、可跟踪当前阶段、可回看阶段详情的统一体验。
- 本文只定义前端 UI、内部派生模型、兼容规则和分阶段实施方式；不在计划阶段直接修改前端代码。

## 2. 当前问题

当前任务详情的 Review 信息被拆成多层导航：

```text
任务详情顶层 Tabs
  -> 代码质量 Review
       -> AI Review 结果
       -> 高准确模式流转
       -> 执行过程
  -> 确定性检查
```

由此产生以下问题：

1. Agent Review 与普通 Review 是两套执行机制，但单 Agent 任务仍显示“高准确模式流转”入口；没有对应
   progress 时会得到空页面，用户无法先判断当前 Review 类型。
2. Agent 已经有分析、取证、收敛、提交、心跳和预算数据，但当前主要以普通卡片和纵向事件列表展示，
   缺少直观的“正在思考 / 当前阶段”视觉。
3. 结果、高准确模式和执行过程相互分离；运行中的任务进入详情后仍默认落在结果视图，用户需要再次切换
   才能看到进度。
4. 确定性检查既是 Review 前置阶段，又作为独立 Tab 存在，破坏一次 Review 的连续时间感。
5. 多模型、Agent / Standard 对照和 fallback 同时存在时，当前标签能表达部分引擎信息，但缺少统一的
   选择器和一致时间轴。
6. 调试事件、业务结果和高准确模式诊断拥有相近视觉权重，首屏信息密度高且不易扫描。

## 3. 设计目标与非目标

### 3.1 设计目标

- 进入代码质量 Review 后，第一眼看到“本次是什么 Review、现在处于什么状态、当前执行到哪一步”。
- Agent 与 Standard 使用同一个阶段模型和时间轴组件，不再维护两套页面导航。
- 运行中进度优先；成功、失败、取消等终态结果优先，但仍能直接回看紧凑时间轴。
- 高准确模式和确定性检查成为时间轴阶段详情，不再单独占据导航入口。
- 多结果按当前选中的 `reviewKey` 展示，互不串线；Agent fallback 在同一条时间轴上完成语义转交。
- 继续展示现有安全摘要，不伪造百分比、阶段、耗时或模型思考过程。
- 桌面、窄屏、键盘操作和 reduced-motion 均可用。

### 3.2 非目标

- 不新增或修改数据库结构。
- 不新增公开 API、轮询请求或 WebSocket。
- 不改变 Agent、Standard、fallback、租约、`max_attempts` 或结果保存逻辑。
- 不修改 Provider、模型、Endpoint、Prompt、Thinking Mode、reasoning effort、预算或工具白名单。
- 不实现逐 token 流式输出，不展示 Chain of Thought。
- 不把多个 Review 合并成任务级并行泳道。
- 不重写 Finding、Diff Viewer、Patch Preview、反馈、评估样本或补证据业务。
- 本专项第一版不新增 Lottie、图片包、动画播放器或其它前端依赖；后续可选风格按 `docs/49` 独立实施。

## 4. 目标信息架构

### 4.1 页面结构

```text
任务详情页头
  └─ 任务概要（任务、项目、触发类型、作者、整体状态）

代码质量 Review
  ├─ Review 选择器
  │    ├─ Agent Review · DeepSeek · 运行中
  │    └─ 普通 Review · OpenAI · 已完成
  │
  ├─ 运行中
  │    ├─ Review 状态 Hero（Agent 大脑动画 / Standard 轻量 Provider 动效）
  │    ├─ 完整统一阶段时间轴
  │    └─ 当前可用的安全摘要
  │
  └─ 已结束
       ├─ 结果摘要与操作
       ├─ 紧凑可点击时间轴
       └─ Finding / Diff / Patch / 反馈与评估能力

其它顶层 Tabs
  ├─ Push 审核（仅 Push 任务）
  ├─ 提醒卡片（按任务配置）
  ├─ 分析结果
  └─ 原始事件摘要
```

顶层“确定性检查”Tab 删除；“结果 / 高准确模式流转 / 执行过程”分段选择器删除。

### 4.2 默认首屏规则

| Review 状态 | 默认首屏 |
| --- | --- |
| `QUEUED` / `RUNNING` | 状态 Hero + 完整统一时间轴 |
| `SUCCESS` / `COMPLETED` | 结果摘要优先 + 紧凑时间轴 + Finding |
| `FAILED` / `SKIPPED` | 失败或跳过摘要优先 + 紧凑时间轴 |
| `CANCELLED` | 取消摘要优先 + 紧凑时间轴 |
| 无 Review 结果 | 明确空状态与重试入口，不显示高准确模式空卡片 |

默认行为由服务端 Review 状态派生，不跨任务记忆用户上次选择，保证每次进入页面都可预测。

### 4.3 多 Review 选择器

- 同一任务只有一个 Review 时仍展示紧凑身份栏，不创建无意义的单项 Tabs。
- 多个 Review 使用横向可滚动选择器，每项固定展示：
  - `Agent Review` 或 `普通 Review`；
  - Provider / model 的安全展示名；
  - 运行状态；
  - fallback 时展示“Agent → Standard fallback”。
- `?reviewKey=...` 继续优先选中目标 Review。
- 轮询刷新只更新选中项内容，不改变当前选择；当前 key 消失时才回退到列表第一项。
- 不把不同 `reviewKey` 的事件合并到同一时间轴。

## 5. Review 身份规则

身份只从现有结果字段派生：

| 条件 | 页面名称 | 主色 |
| --- | --- | --- |
| `requestedEngine=AGENT` 且 `effectiveEngine=AGENT` | Agent Review | 紫蓝 |
| `requestedEngine=AGENT` 且 `effectiveEngine=STANDARD_FALLBACK` | Agent → Standard fallback | 橙色 |
| `requestedEngine=STANDARD` | 普通 Review | 蓝灰 |
| 字段缺失的旧任务 | 普通 Review（历史） | 中性灰 |

- `requestedEngine` 表示用户或项目策略要求的引擎。
- `effectiveEngine` 表示最终实际引擎，不允许用 Provider 名称反推 Agent。
- Provider、model 和 displayName 只用于补充说明，不覆盖引擎身份。
- fallback 结果不得显示为“Agent 成功”；时间轴必须保留 Agent 失败或不可用和 Standard 接管两个阶段。

## 6. 前端内部 ReviewJourney 模型

新增前端纯数据派生层，不改变 API：

```text
ReviewJourney
  reviewKey
  requestedEngine
  effectiveEngine
  engineLabel
  status
  running
  terminal
  currentStageId
  startedAt
  finishedAt
  stages[]

ReviewJourneyStage
  id
  title
  status
  visible
  startedAt
  finishedAt
  durationMs
  summary
  warningSummary
  events[]
  detailKind
  subStages[]
```

阶段状态固定为：

```text
WAITING
ACTIVE
SUCCESS
WARNING
FAILED
SKIPPED
CANCELLED
```

### 6.1 状态优先级

同一阶段命中多个事件时：

```text
FAILED / CANCELLED
  > ACTIVE
  > WARNING
  > SUCCESS
  > SKIPPED
  > WAITING
```

终态 Review 不得保留 `ACTIVE`；事件损坏或时间缺失时只影响阶段详情，不能改变 Review 主状态。

### 6.2 时间与耗时

- 优先使用阶段第一条和最后一条有效事件时间。
- Review 总耗时继续优先使用 `startedAt / finishedAt`。
- 时间损坏、未来时间或只有一个事件时显示 `-`，不计算负耗时。
- 运行中只显示真实已运行秒数，不显示伪造完成百分比或预计剩余时间。

### 6.3 事件隔离与共享

- 每个 Review 只读取 `event.reviewKey === review.reviewKey` 的作用域事件。
- 仅以下任务级事件允许作为本次调度共享事件合并：
  - `DETERMINISTIC_PRECHECK_STARTED`
  - `DETERMINISTIC_PRECHECK_COMPLETED`
  - `DETERMINISTIC_PRECHECK_FAILED`
- `DETERMINISTIC_PRECHECK_REUSED` 使用当前 Review 自己的作用域事件。
- 共享事件在阶段详情标记“本次调度共享”，不复制为新的后端记录。
- 其它 `reviewKey=null` 事件不得自动混入多个 Review。
- Agent 轨迹继续按最新 `runId + claimAttempt` 隔离，沿用现有接管和去重规则。

## 7. 统一时间轴阶段

### 7.1 阶段一：排队与调度

覆盖事件：

```text
QUEUED
AGENT_QUEUED
STARTED
REQUEST_BUILT
PROVIDER_SELECTED
REQUEST_VALIDATED
```

展示内容：

- 排队、启动和请求准备状态；
- Review 引擎、Provider、Profile 的安全标识；
- 排队或启动时间；
- Agent 敏感路径排除只显示计数和既有安全路径摘要。

### 7.2 阶段二：确定性预检

覆盖事件：

```text
DETERMINISTIC_PRECHECK_STARTED
DETERMINISTIC_PRECHECK_COMPLETED
DETERMINISTIC_PRECHECK_FAILED
DETERMINISTIC_PRECHECK_REUSED
```

展示规则：

- 成功：显示检查类型、触发方式、扫描文件数、新增行数、命中数和耗时。
- 失败或不可用：显示 fail-open 警告，明确“检查失败未改变 Review 主结果”。
- 同次多模型复用：显示“复用本次调度结果”。
- 历史任务没有事件时不伪造完成；时间轴可隐藏该阶段，详情入口不出现空面板。
- 现有手动“运行 / 重新运行敏感信息扫描”按钮移入该阶段 Drawer。
- 手动结果标记为“任务级最新记录”，不改写已完成 Review 的 AUTO_PREFLIGHT 阶段状态。

### 7.3 阶段三：上下文准备

覆盖事件：

```text
CONTEXT_PACK_BUILT
LOCAL_REPO_PREPARED
LOCAL_REPO_PREPARE_FAILED
LOCAL_CONTEXT_RETRIEVED
LOCAL_CONTEXT_RETRIEVE_FAILED
```

Drawer 内按以下子区组织：

1. Context Pack 摘要；
2. 本地仓库准备；
3. Planner / Retriever；
4. Requested Context 可用性；
5. 预算裁剪与未注入证据摘要；
6. Finding 级补证据摘要；
7. 规则缺口诊断入口。

没有上述事件时不渲染“高准确模式”空入口。部分失败使用 `WARNING`，不得把 Retriever 不可用解释为
Review 失败或没有风险。

### 7.4 阶段四：模型 Review

#### Agent 子阶段

```text
分析变更
  -> 受控只读取证
  -> 收敛结论
  -> 提交 Review Card
```

对应事件：

```text
AGENT_RECLAIMED
AGENT_ANALYZING
AGENT_TOOL_ACTIVITY
AGENT_CONVERGING
AGENT_SUBMITTING
AGENT_HEARTBEAT（仅摘要，不作为节点）
```

Drawer 继续展示：

- 最新 `runId + claimAttempt`；
- 最近心跳；
- tools、evidence、source bytes 和预算白名单；
- 重复活动折叠摘要；
- `AGENT_RECLAIMED` 的脱敏租约接管说明。

#### Standard 子阶段

对应事件：

```text
PROVIDER_START
HTTP_REQUEST_START
OPENAI / ANTHROPIC / DEEPSEEK / XIAOMIMO / GLM / CUSTOM REQUEST
对应 RESPONSE
PROVIDER_FAILED 或对应 FAILED
```

页面只显示 Provider 状态、时间、耗时和既有安全错误摘要；调试输出默认折叠到“高级执行记录”。

### 7.5 阶段五：解析与保存

覆盖事件：

```text
OUTPUT_EXTRACTED
JSON_PARSE_START
JSON_PARSE_FAILED
各 Provider PARSED
SAVE_RESULT
RESULT_SAVED
SAVE_FAILED
```

展示解析状态、结构化 finding 数、保存状态和耗时；不展示模型原文或完整响应。

### 7.6 阶段六：终态与 fallback

覆盖事件与结果状态：

```text
AGENT_FINISHED
AGENT_FALLBACK
AGENT_FALLBACK_QUEUED
AGENT_CANCELLED
FINISHED
FAILED
review.status / requestedEngine / effectiveEngine
```

fallback 表现为同一时间轴上的显式转交：

```text
Agent 执行失败或超时
  -> Standard fallback 排队
  -> Standard Provider 执行
  -> 解析并保存 Standard 结果
```

`effectiveEngine=STANDARD_FALLBACK` 时，即使缺少部分历史事件，也必须通过结果字段展示 fallback 身份，
但不得补造不存在的详细阶段。

## 8. 运行状态 Hero 与动画

### 8.1 Agent 动画

使用代码内原生 SVG 和 CSS：

- 中心为简化大脑轮廓；
- 节点和连线使用低频神经脉冲；
- 外圈只做轻量呼吸，不做高饱和大面积发光；
- 动画只表达“任务仍在运行”，不映射真实模型推理。

第一版实现必须通过统一 `AgentReviewAnimation` 渲染契约接收 Review 状态、Agent 子阶段、
reduced-motion 和无障碍文案，并把大脑实现注册为固定 `BRAIN` 风格。`docs/48` 不显示动画切换入口，
也不交付其它风格，但不得把大脑 SVG、状态映射和 Hero 布局耦合为无法替换的单体组件。后续 `ENERGY`
与 `LOTTIE` 的注册表、偏好和切换入口只由 `docs/49` 扩展。

状态表现：

| 状态 | 视觉 |
| --- | --- |
| 排队 | 静态轮廓 + 低频呼吸 |
| 分析 / 取证 | 节点脉冲沿连线移动 |
| 收敛 | 外圈收拢，脉冲频率降低 |
| 提交 | 向结果图标汇聚 |
| 成功 | 停止循环，显示成功状态 |
| fallback | 橙色转交箭头，不显示 Agent 成功 |
| 失败 | 停止循环，显示错误状态 |
| 取消 | 灰色静态状态 |

### 8.2 Standard 动效

Standard 使用同一 Hero 布局，但只显示克制的 Provider 请求脉冲或数据流图标，不绘制 Agent 大脑，
避免再次混淆两种机制。

### 8.3 无障碍

- 动画容器提供可读的 `aria-label`，例如“Agent Review 正在受控取证”。
- `prefers-reduced-motion: reduce` 时关闭位移、闪烁和循环脉冲，只保留静态状态。
- 状态不能只依赖颜色，必须同时提供图标和文字。
- 动画不抢占焦点，不使用自动播放音频。

## 9. 时间轴交互

### 9.1 阶段节点

- 桌面端使用横向六阶段时间轴；阶段过多或宽度不足时允许横向滚动。
- 390px 窄屏切换为纵向时间轴。
- 当前阶段使用 `ACTIVE` 视觉，不显示百分比。
- 未参与本次 Review 的可选阶段不占空节点。
- 节点支持鼠标、键盘 Enter 和 Space 打开详情。

### 9.2 详情 Drawer

- 桌面宽度使用 `min(880px, 100vw)`；窄屏全屏。
- 标题固定显示阶段名、状态、开始时间、结束时间和耗时。
- 内容按“简要结论 → 子阶段 → 安全指标 → 高级执行记录”组织。
- 关闭后焦点返回原阶段节点。
- 轮询更新时保持当前 Drawer 和阶段选择；阶段消失时安全关闭。

### 9.3 告警 Popover

- 只有 `WARNING / FAILED` 节点显示感叹号。
- 点击感叹号打开短 Popover，最多展示状态、固定原因摘要和建议动作。
- 点击节点主体仍打开完整 Drawer，二者事件不得互相触发。
- Agent 告警只展示错误码和平台生成的安全文案，不展示异常原文或基础设施信息。

### 9.4 高级执行记录

现有 DEBUG、stdout/stderr 和辅助 progress 不占首屏：

- 按阶段归类后放入 Drawer 底部折叠区；
- 无法归类的事件进入时间轴后的“其它执行记录”折叠区；
- Agent 事件继续执行严格白名单格式化；
- 不删除现有排障能力，但默认不展开。

## 10. 终态结果布局

终态默认顺序：

```text
Review 身份与结果摘要
  -> 紧凑统一时间轴
  -> 敏感路径 / fallback / 失败提示
  -> Review 元数据
  -> Finding 列表
  -> Diff / Patch / 补证据 / 反馈 / 评估样本
```

- 结果摘要保留状态、风险等级、finding 数和重试 / 对照 / 中断等现有操作。
- 时间轴紧凑模式仍可点击每个阶段，不折叠成不可发现的按钮。
- 失败和跳过任务必须先说明“为什么没有结果”，再展示空 Finding。
- 运行中不展示“暂无结构化问题”作为主视觉，避免被理解为已经审查完成且无风险。

## 11. 视觉规范

- 继续使用现有 MUI 页面壳；时间轴内部允许复用 Ant Design 的 Tag、Drawer、Popover、Descriptions、
  Collapse 和 Table，避免一次性重写全部复杂内容。
- 主色遵循现有蓝 / 粉系，Agent 使用紫蓝强调；错误红、警告橙、成功绿只用于状态。
- Hero 保持后台密度，不做占据整屏的大型营销式插画。
- 卡片圆角、outline、间距和 Typography 与任务详情现有 MUI surface 对齐。
- hover、focus-visible、active、disabled 和 loading 状态必须完整。
- 长 Provider、model、阶段标题和 warning 文案必须截断并提供 Tooltip。

## 12. 安全与兼容边界

### 12.1 Agent 安全白名单

Agent Hero、时间轴、Popover 和 Drawer 只能展示：

- `runId`、`claimAttempt`、安全序号和阶段枚举；
- 固定活动、状态和错误码；
- duration、item/tool/evidence/source/diff 等非负数字；
- 预算白名单；
- 文件后缀和目录深度等既有脱敏摘要；
- Backend 生成的心跳时间。

不得展示 Prompt、查询、工具参数、源码、diff、相对或绝对路径、Worker ID、容器、网络地址、异常原文、
assistant 原文、模型原文、模型推理、API Key、query hash 或 path hash。

### 12.2 历史兼容

- 缺失 `requestedEngine / effectiveEngine`：按普通 Review（历史）展示。
- 缺失 `reviewKey`：只使用该结果的现有兼容事件，不和其它结果混合。
- 缺失 Agent heartbeat：继续使用轨迹或结果终态，不提示“卡死”。
- 缺失高准确事件：不显示空入口。
- 损坏 detail：显示安全的阶段文案和“详情不可用”，不直接输出原字符串。
- Standard、旧 Agent Run、comparisonMode、多模型和 fallback 必须保持可见。

## 13. 实施范围

预期主要改动：

- 新增 `frontend/src/reviewJourney.js`：Review 身份、事件隔离、阶段映射、状态与默认布局纯函数。
- 重构 `frontend/src/App.jsx` 中任务详情 Review 面板、进度视图、高准确模式和确定性检查的组合关系。
- 扩展 `frontend/src/styles.css` 和前端纯函数测试；实施完成后更新 `docs/38` 的实际入口说明。

不得修改：

- `backend/` Java 后端；
- Python Backend 数据结构、API 或 Review 行为；
- Provider、Prompt、预算、工具白名单和 Review Card schema；
- Standard Review、Standard fallback、Agent 调度或通知语义。

如果实施中发现现有事件无法可靠区分必要阶段，应停止并报告具体缺口；不得自行新增 Backend 字段或接口。

## 14. 分阶段实施

### 阶段一：统一 ReviewJourney 模型与 Review 身份

目标：

- 建立纯函数 Journey 模型、事件隔离和阶段状态。
- 统一 Agent、Standard、fallback 和历史结果标签。
- 多 Review 选择器能明确展示引擎、Provider 和状态。
- 暂不删除旧分段导航，不实现动画和 Drawer。

测试：

- Agent / Standard 的排队、运行、成功、失败、取消和跳过；
- Agent fallback；
- `reviewKey` 多结果隔离；
- task-level 确定性预检白名单合并；
- 租约接管最新 attempt；
- 旧字段、缺失时间、损坏 detail 和乱序事件。

停止点：

- 纯函数测试和 frontend production build 通过后停止；
- 不继续阶段二，等待用户检查 Review 身份和选择器。

### 阶段二：进度 Hero、统一时间轴与动画

前置条件：用户确认阶段一。

目标：

- 落地运行中进度优先、终态结果优先。
- 实现完整 / 紧凑两种时间轴。
- 通过可插拔 `AgentReviewAnimation` 契约实现 `BRAIN` SVG/CSS 大脑动画与 Standard 轻量动效；
  本阶段只注册 `BRAIN`，不显示风格切换。
- 实现阶段 Drawer、告警 Popover 和高级执行记录。
- 保留旧高准确模式与确定性检查入口作为临时兼容，不在本阶段删除。

测试：

- Hero 在 queued/running/terminal/fallback/cancelled 下状态正确；
- 阶段点击、感叹号事件隔离、Drawer 焦点恢复；
- 轮询不改变 reviewKey 和已打开阶段；
- reduced-motion、键盘和窄屏时间轴；
- Agent Drawer 严格白名单。

停止点：

- 纯函数测试、production build 和 1440 / 1024 / 390 浏览器检查通过后停止；
- 等待用户确认动画、密度和交互，再进入阶段三。

### 阶段三：高准确模式和确定性检查信息架构收口

前置条件：用户确认阶段二。

目标：

- 将高准确模式完整内容移入“上下文准备”Drawer。
- 将 AUTO_PREFLIGHT、共享/复用状态和手动检查入口移入“确定性预检”Drawer。
- 删除顶层确定性检查 Tab。
- 删除“结果 / 高准确模式流转 / 执行过程”分段导航和不再使用的空态。
- 更新 `docs/38` 为实际入口说明。

测试：

- 高准确完整、部分失败和无记录；
- 确定性成功、失败、不可用、复用、手动运行和无记录；
- 运行中首次进入、终态首次进入、fallback、旧任务、多模型和 `reviewKey` 直达；
- Finding、Diff、Patch、补证据、反馈、评估样本、重试、中断和 Push 审核不回归；
- 全部前端纯函数测试和 `scripts\run-frontend.cmd build`；
- 最终响应式、无障碍和脱敏审计。

停止点：

- 完成文档回填后停止，等待用户部署验证；
- 不远程部署、不执行真实 Agent Review、不执行 Run 18。

## 15. 验收矩阵

| 场景 | 首屏 | 时间轴 | 详情 |
| --- | --- | --- | --- |
| Agent 排队 | Agent 身份 + 排队 Hero | 调度 ACTIVE | 等待 Worker，不显示思考完成度 |
| Agent 运行 | 大脑动画 + 当前 Agent 子阶段 | 完整时间轴 | 心跳、预算和安全活动 |
| Agent 成功 | 结果摘要优先 | 紧凑、终态成功 | 可回看分析/取证/收敛/提交 |
| Agent fallback | fallback 摘要优先 | 显式 Agent → Standard 转交 | 固定错误码和 Standard 执行 |
| Agent 取消 | 取消摘要 | CANCELLED | 不显示为失败或成功 |
| Standard 运行 | Standard 身份 + Provider 动效 | 同一阶段结构 | Provider 安全摘要 |
| 确定性失败 | Review 仍继续 | 预检 WARNING | fail-open 说明 |
| 高准确无记录 | 不显示空入口 | context 可隐藏 | 无空 Drawer |
| 多模型 | 选择器保留当前 reviewKey | 每个结果独立 | 不串事件 |
| 历史任务 | 历史身份 | 只显示有证据阶段 | 不伪造数据 |
| 390px | 紧凑 Hero | 纵向时间轴 | 全屏 Drawer |

## 16. 实施验证要求

前端自动化：

- 新增 ReviewJourney 纯函数测试；
- 扩展现有 Agent trace 测试；
- 执行全部 `frontend/tests/*.test.mjs`；
- 执行 `scripts\run-frontend.cmd build`。

浏览器验证：

- 1440px 桌面；
- 1024px 小桌面 / 平板横向；
- 390px 移动宽度；
- 鼠标、键盘 Tab / Enter / Space / Escape；
- `prefers-reduced-motion`；
- running 轮询时保持选择和 Drawer；
- 长 Provider/model、失败文案和多 Review 横向滚动。

安全审计：

- 最终 diff 和前端可见测试夹具不包含真实 Key、Prompt、查询、工具参数、源码、diff、路径、模型原文或推理；
- Agent Popover / Drawer 不渲染未知 detail 字段；
- 所有观测和动画失败不得改变 Review 主结果。

## 17. 总控 Prompt

```text
请只按 docs/48-review-task-detail-unified-progress-ui-plan.md 推进任务详情统一 Review 进度 UI。

开始前阅读根目录 AGENTS.md、docs/48，并核对 docs/38、docs/39、docs/40、docs/46、docs/47 与当前
frontend/src/App.jsx、frontend/src/agentReviewTrace.js、frontend/src/styles.css 和相关前端测试。

每次只实施 docs/48 的一个阶段。允许修改现有 React 前端、前端纯函数、样式、对应测试和 docs/38/docs/48；
不得修改 Java 后端、Python Backend、数据库、公开 API、Review 结果语义、Standard fallback、Agent 调度、
Provider、Prompt、预算、工具白名单或 Review Card schema。

必须保留 reviewKey 直达、多模型隔离、轮询、Finding、Diff、Patch、补证据、反馈、评估样本、重试和中断。
Agent 可见详情继续使用严格白名单，不展示 Prompt、查询、工具参数、源码、路径、模型原文、推理、Worker
基础设施或异常原文。不得伪造百分比、耗时或模型思考。

阶段完成后执行对应前端纯函数测试和 scripts\run-frontend.cmd build，回填 docs/48 实施结果并停止，
等待用户验证并明确回复“继续下一阶段”。不得自动进入后续阶段、远程部署、执行真实 Agent Review 或 Run 18。
```

## 18. 阶段一 Prompt

```text
请只实施 docs/48 的阶段一“统一 ReviewJourney 模型与 Review 身份”。

目标：
1. 新增前端纯函数 ReviewJourney 模型，按 reviewKey 隔离事件，只合并白名单任务级确定性预检事件。
2. 固定六阶段和 WAITING/ACTIVE/SUCCESS/WARNING/FAILED/SKIPPED/CANCELLED 状态。
3. 统一 Agent、Standard、Agent -> Standard fallback 和历史结果标签。
4. 多 Review 选择器展示引擎、Provider/model 和状态，保留 reviewKey 直达与轮询选择。
5. 补 Agent/Standard/fallback/多模型/旧任务/损坏数据/租约接管测试。

本阶段不实现动画、Drawer、Popover，不删除高准确模式或确定性检查入口，不修改 Backend。
测试和 build 通过后回填实施结果并停止，等待用户确认。
```

## 19. 阶段二 Prompt

```text
仅在用户确认阶段一后实施 docs/48 的阶段二“进度 Hero、统一时间轴与动画”。

目标：
1. queued/running 首屏展示 Hero 与完整时间轴；终态结果优先并展示紧凑时间轴。
2. 建立可插拔 AgentReviewAnimation 契约并只注册 BRAIN，实现原生 SVG/CSS 大脑动画和 Standard
   轻量 Provider 动效；不显示风格切换，不引入 Lottie 依赖。
3. 实现阶段 Drawer、WARNING/FAILED 感叹号 Popover 和折叠高级执行记录。
4. 支持 fallback 转交、Agent 子阶段、预算/心跳摘要、键盘、焦点恢复和 reduced-motion。
5. 保持现有高准确模式与确定性检查入口作为临时兼容，不在本阶段删除。

本阶段不修改 Backend、不新增依赖、不展示模型思考、不伪造百分比。
完成自动化、production build 和 1440/1024/390 浏览器检查后回填结果并停止。
```

## 20. 阶段三 Prompt

```text
仅在用户确认阶段二后实施 docs/48 的阶段三“高准确模式和确定性检查信息架构收口”。

目标：
1. 把 Context Pack、本地仓库、Planner/Retriever、Requested Context、预算裁剪、补证据和规则缺口移入
   “上下文准备”阶段 Drawer；无记录时不显示空入口。
2. 把 AUTO_PREFLIGHT、共享/复用、fail-open、任务级手动检查和重新运行操作移入“确定性预检”Drawer。
3. 删除顶层确定性检查 Tab 和“结果/高准确模式流转/执行过程”分段导航。
4. 保持 Finding、Diff、Patch、补证据、反馈、评估样本、重试、中断、Push 审核和历史任务兼容。
5. 更新 docs/38，完成全部前端测试、build、响应式、无障碍和脱敏审计。

本阶段不得修改 Backend 或 Review 行为。完成后回填 docs/48 并停止，等待用户确认部署；不得执行真实
Agent Review、远程部署或 Run 18。
```
