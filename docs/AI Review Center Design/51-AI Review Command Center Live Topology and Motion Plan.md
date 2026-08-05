# 51 · AI Review Command Center 动态拓扑与实时侧栏计划

## 0. 文档状态

- 文档日期：`2026-08-04`
- 当前状态：`M2 COMPLETE — M2-1 IMPLEMENTED — WAITING FOR USER VISUAL VERIFICATION`
- 文档用途：冻结 AI Review 指挥中心中部拓扑的侧栏数据、连接端口、活动动画和分阶段实施契约。
- 当前授权：M2-1 实现、自动化验证和当前可用视口浏览器验收已完成；只允许报告结果或修复用户视觉验收发现的本阶段缺陷，不得实现 M3 持续动画或自动进入 M3。
- 停止点：等待用户视觉确认；确认后由用户明确输入“继续 M3”。

本计划是独立的新专项，不续写或修改已完成的：

- `AI Review Command Center Information Architecture Optimization Plan.md`
- `AI Review Command Center Current Flow Audit.md`
- `AI Review Command Center Homepage vNext Implementation Plan.md`
- `AI Review Command Center Evolution Plan v2.md`

顶部 5 项当前状态和底部近 24 小时质量产出已经冻结，本专项不得重新调整其指标、顺序或时间口径。

---

## 1. 目标与问题

当前中部拓扑已经表达“入口 → 引擎选择 → Agent / Standard Review → 结果落库”，但存在以下体验问题：

1. SVG 路径使用固定坐标，连接线在卡片内部淡出，连接点没有形成清晰的边缘接口；
2. 动态流光只有入口侧 3 条路径，节奏约 8 秒且轨迹较弱，右侧路径和 Agent → Standard 路径没有动态层；
3. 引擎圆环没有旋转，运行中的 Review 卡片只做低强度透明度呼吸，难以感知真实任务正在执行；
4. 左侧仍是静态触发类型说明，不能回答“当前有哪些任务正在排队或执行”；
5. 右侧仍是结构性“结果持久化”说明，不能回答“今天已经产生了多少成功、失败或进行中的 Review 结果”。
6. M2 虽已完成真实 DOM 端口测量，但当前 Review 卡片会填满剩余宽度，线路走廊被压缩成贴边括号形短线；通用大三角箭头、单层曲线和紧邻卡片的端口仍有明显流程图感。

本专项目标：

- 将左右说明节点替换为真实数据节点；
- 让连接端点贴合真实卡片边缘，并在缩放和响应式布局变化后自动重算；
- 让排队、运行、双轨和 fallback 状态具有明显但可信的动态反馈；
- 不新增虚假完成事件，不改变 Review / Scheduler / Agent / Provider 状态机。

### 1.1 M2-1 参考图评估

静态视觉方向以 [`assets/02.png`](assets/02.png) 为主要参考。当前实际视角用于识别现状问题，参考图用于冻结目标关系，二者对比后的结论如下：

- 可行：现有 DOM + SVG、真实端口测量和单一 ResizeObserver 可以继续复用，不需要修改 Runtime、数据库或业务状态机；
- 必须先调布局再调路径：只修改贝塞尔参数无法解决线路拥挤，必须限制双 Review 最大宽度并为三段横向线路预留显式走廊；
- M2-1 负责静态构图：节点比例、线路走廊、路径几何、端口和多层线缆外观；
- M3 负责状态动画：流光、粒子、双环反转、霓虹边框和活动强度，不在 M2-1 提前激活动画；
- 参考图中的示例任务、数量和装饰文案不是数据契约，不得复制成模拟业务数据；页面仍只展示真实 Runtime 数据；
- 参考图是视觉方向而非像素级临摹；可访问性、真实语义、既有响应式断点和无横向溢出优先级更高。

对参考图进一步拆解后，M2-1 还需要覆盖以下原计划未完整描述的静态视觉差异：

| 区域 | 当前视角 | 参考图方向 | 阶段归属 |
| --- | --- | --- | --- |
| 策略路由引擎 | 椭圆胶囊外框包住圆环和图例 | 以多层正圆轨道为视觉主体，外层容器接近透明，图例落在独立轻透明面板 | M2-1 重构静态外形；M3 旋转双环 |
| 底部质量卡 | 图标、数字和说明为纯文本结构 | 增加基于真实分布的微型图形或明确为装饰的信号纹理 | M2-1 |
| 卡片材质 | 多处使用不对称小圆角、较实的白底和明显分隔线 | 统一大圆角、半透明轻表面、双层细描边、低强度同色辉光 | M2-1 |
| 中部地图 | 规则网格为主，节点与背景层次接近 | 静态电路纹理、稀疏光点、角落技术刻线，节点保持主要对比度 | M2-1 |
| 动画 | 尚未启用 | 圆环反转、线路流光、脉冲和活动卡片霓虹 | M3，不提前到 M2-1 |

---

## 2. 已冻结决策

### 2.1 左侧业务语义

- 左侧命名为“任务队列”；
- 实际语义是“最近活动 ReviewTask 列表”，不是 Agent 与 Standard 的统一严格执行顺序；
- 使用 Runtime `activeTasks`，保持后端现有“最近更新时间倒序”；
- 桌面端最多展示 3 项，超出部分仅显示数量提示和通用任务列表入口；
- 不在左侧重复 Agent / Standard 中部模块已有的队列长度、容量或下一任务。

### 2.2 右侧统计语义

- 右侧命名为“今日 Review 结果”；
- 统计实体为 `code_quality_review_results` 的 Result，不按 ReviewTask 折叠；
- 时间口径固定为北京时间自然日 `00:00—当前`，不是滚动 24 小时；
- 顶部和底部既有摘要保持不变；右侧必须明确显示“今日”，底部继续明确显示“近 24 小时”。

### 2.3 引擎图例

引擎模块删除原文案：

> 自动触发选择 Agent 但 Agent 不可用时，可按策略直接进入 Standard Review。

图例固定为 3 条：

1. 紫色：`Agent → Agent Review`；
2. 橙色：`Standard → Standard Review`；
3. 青蓝色：`Agent Review → Standard Review`。

青蓝色使用独立变量 `--cc-fallback: #0f8fd8`，不得复用 Agent 紫色、Standard 橙色或结果青绿色。

### 2.4 技术边界

- 保持 `GET /api/command-center/runtime`，不新增独立接口；
- 保持 `command-center-runtime-v2`，以向后兼容的新增字段扩展，不升级 Schema Version；
- 不新增数据库表、列或迁移；
- 连接线继续使用 DOM + SVG，不启用 Canvas；
- 动画不使用业务 `requestAnimationFrame` 循环；
- 只在真实 Runtime 证据存在时激活路径，不推断完成抵达或 fallback 转交瞬间。
- 顶部 5 项和底部 4 项冻结的是指标、顺序、来源与时间口径，不冻结卡片圆角、材质、图标容器和微型可视化等纯展示样式；
- M2-1 不为底部卡片新增时间桶或趋势接口。没有真实序列的数据不得画成趋势图，也不得用随机柱高制造“实时统计”印象。

---

## 3. Runtime v2 数据契约

### 3.1 `activeTasks[]` 新增字段

在现有 `ActiveTaskSnapshot` 上追加以下可空字段：

| 字段 | 来源 | 页面用途 |
| --- | --- | --- |
| `authorName` | `review_tasks.author_name` | 作者主展示 |
| `authorUsername` | `review_tasks.author_username` | 作者补充或回退 |
| `externalUrl` | `review_tasks.external_url` | MR / Commit 精确链接 |
| `repositoryUrl` | `projects.repository_url` | 无精确链接时的项目 GitLab 回退 |
| `sourceBranch` | `review_tasks.source_branch` | 分支或 MR 来源 |
| `targetBranch` | `review_tasks.target_branch` | MR 目标分支 |
| `commitSha` | `review_tasks.commit_sha` 或 `after_sha` | Push / Commit 摘要 |

约束：

- 全部字段只读且可空；历史任务缺失时不得补造；
- `externalUrl` 优先于 `repositoryUrl`；
- 后端只输出数据库原值，不负责拼接前端导航；
- API `activeLimit` 和 `coverage.activeTasks=BOUNDED` 继续生效。

### 3.2 新增 `todayResults`

Runtime v2 顶层增加：

```json
{
  "todayResults": {
    "status": "LIVE",
    "scope": "TODAY",
    "date": "2026-08-04",
    "timezone": "UTC+08:00",
    "from": "2026-08-03T16:00:00.000Z",
    "to": "2026-08-04T12:30:00.000Z",
    "totalCount": 20,
    "completedCount": 17,
    "successCount": 15,
    "failureCount": 1,
    "skippedCount": 1,
    "runningCount": 3,
    "otherCount": 0,
    "statusCounts": {
      "SUCCESS": 15,
      "FAILED": 1,
      "SKIPPED": 1,
      "RUNNING": 3
    }
  }
}
```

统计契约：

- 北京时间使用固定 `UTC+08:00`，本项目不引入新的系统时区配置；
- `from` 为当天北京时间 00:00 转换后的 UTC，`to` 为本次快照生成时间；
- 查询范围为 `updated_at >= from AND updated_at < to`；
- 继承 Runtime 的 `projectId` / `groupId` 过滤；
- `totalCount` 为范围内 Result 总数；
- `successCount`：`SUCCESS`；
- `failureCount`：`FAILED`；
- `skippedCount`：`SKIPPED`、`CANCELLED`、`TIMED_OUT`；
- `runningCount`：`QUEUED`、`PENDING`、`CLAIMED`、`RUNNING`；
- `otherCount`：未纳入以上分组的状态；
- `completedCount = successCount + failureCount + skippedCount`；
- `statusCounts` 保留原始状态计数，主计数不得与它矛盾；
- 空集合返回真实零值；查询失败由 Runtime 资源错误处理，不返回伪造零值。

Coverage 同步增加：

- `coverage.sections.todayResults = FULL`；
- `coverage.scanned.todayResults = totalCount`。

### 3.3 兼容规则

- 后端实现完成后，正常 Runtime 快照必须包含 `todayResults`；
- 前端仍兼容旧 Runtime v2：字段缺失时右侧显示“今日结果暂不可用”，不得将缺失解释为零；
- Runtime `ERROR_RETAINED` 时保留最后成功的任务列表和今日结果，并显示保留快照提示；
- Runtime `ERROR_EMPTY` 时左右数据节点均显示不可用状态，连接和动画暂停。

---

## 4. 左右数据节点设计

### 4.1 左侧“任务队列”

头部：

- eyebrow：`实时任务`
- title：`任务队列`
- subtitle：`最近活动 · 非跨引擎执行顺序`
- 数量：`展示 N / 活动 M`

单项卡片展示顺序：

1. 项目名；
2. 作者：优先 `authorName`，其次 `@authorUsername`，否则“未记录作者”；
3. 触发徽标：Manual / Merge Request / Push / Retry；
4. `sourceBranch → targetBranch`，无目标分支时显示 Commit 短 SHA；
5. 当前阶段中文标签和相对更新时间；
6. 内部“查看任务”与外部“打开 GitLab”两个独立操作。

交互约束：

- 内部任务详情固定为 `/tasks/{taskId}`；
- 外部链接只允许解析后协议为 `http:` 或 `https:`；
- 外部链接使用 `target="_blank"` 和 `rel="noopener noreferrer"`；
- URL 缺失或不安全时不渲染外部操作；
- 卡片操作必须可键盘访问并有明确焦点样式；
- 空态显示“当前无活动 ReviewTask”；
- API 活动数大于 3 时显示“另有 X 项活动任务”，不增加第四张卡。

### 4.2 右侧“今日 Review 结果”

头部：

- eyebrow：`北京时间自然日`
- title：`今日 Review 结果`
- subtitle：`00:00—当前`

内容：

- 主值：`完成 {completedCount}`；
- 2×2 指标：成功、失败、跳过、进行中；
- 辅助值：`共 {totalCount} 个 Result`；
- `otherCount > 0` 时追加“其他状态 N”，否则不占空间；
- 通用入口继续指向 `/tasks`，文案为“查看审查任务”；
- 不添加“只看今日”的链接，直到任务列表具备同口径 URL 过滤契约。

视觉：

- 成功使用青绿色；
- 失败使用红色；
- 跳过使用中性灰蓝；
- 进行中使用蓝紫色；
- 数据变化可做一次短促强调，但不得按动画补算不存在的中间数值。

---

## 5. 动态连接端口

### 5.1 连接定义

固定 6 条连接：

| ID | 起点 | 终点 | 颜色 |
| --- | --- | --- | --- |
| `queue-engine` | 任务队列右侧 | 引擎左侧 | 蓝色 |
| `engine-agent` | 引擎右上 | Agent Review 左侧 | 紫色 |
| `engine-standard` | 引擎右下 | Standard Review 左侧 | 橙色 |
| `agent-result` | Agent Review 右侧 | 今日结果左上 | 紫色 |
| `standard-result` | Standard Review 右侧 | 今日结果左下 | 橙色 |
| `agent-standard` | Agent Review 下侧 | Standard Review 上侧 | 青蓝色 |

### 5.2 端口样式

- 每个端口升级为 10–12px 双层接口：白色或浅色核心、2px 路线色内环、18–24px 低透明外光晕；
- 端口中心位于卡片边缘外侧约 6px，并增加 8–14px 短“接头颈部”，形成从卡片边缘伸出的接口，而不是把圆点嵌在图形中；
- 同一节点存在多条线路时，端口按真实路径方向分开，不得重叠或共用一个不可区分的圆点；
- 取消突出的大三角箭头作为主体视觉，方向改为目标前 14–22px 的小型内嵌尖角或短箭羽；不得覆盖端口或卡片边框；
- Agent → Standard 结构关系保持虚线基轨，活动时叠加青蓝流光。

### 5.3 M2-1 线路几何

M2-1 不再用一个通用横向三次贝塞尔函数处理 5 条横向连接，而是按拓扑语义生成 4 类静态线缆：

1. `queue-engine`：保持近似水平直连，只在端口接头处保留短颈部；
2. `engine-agent` / `engine-standard`：从引擎径向端口水平伸出，在专用走廊内使用小半径圆角转折，再水平进入 Review；上下两条关于引擎中心近似对称；
3. `agent-result` / `standard-result`：从 Review 水平伸出，在结果侧走廊形成两条可区分的平行线束，再分别进入结果节点的上、下端口；允许视觉靠拢，但不得合并为一条导致活动状态无法独立表达；
4. `agent-standard`：使用 Agent 下端口到 Standard 上端口的单向垂直关系桥，标签置于两卡之间的专用 fallback 走廊；只保留向 Standard 的方向提示，不复制可能造成双向含义的装饰箭头。

所有线路共用同一份 `d` 几何并渲染静态三层：

1. 8–10px 低透明同色辉光；
2. 2.5–3px 实色基轨；
3. 1–1.5px 高亮内芯。

M3 在同一几何之上追加流光和粒子层，不得再维护第二套路径坐标。圆角转折优先使用 `L/H/V + Q` 或等价短曲线，不使用横跨整个走廊的大幅 S 形三次贝塞尔，以降低流程图观感。

### 5.4 测量机制

- 为地图容器和端口增加稳定 `data-*` 标识；
- 单个 React `useLayoutEffect` 创建一个 `ResizeObserver`；
- 测量端口 `getBoundingClientRect()`，转换为地图容器局部坐标；
- 仅尺寸或位置变化时更新路径数据，相同坐标不重复 setState；
- 组件卸载时断开 Observer；
- 不建立持续 RAF、轮询计时器或第二套窗口 resize 监听器；
- 首次尚未取得合法尺寸时隐藏装饰 SVG，语义 DOM 仍完整可用。

### 5.5 M2-1 静态未来科技视觉基底

#### 5.5.1 策略路由引擎

- 移除当前明显的椭圆胶囊轮廓；引擎节点外层保持无实底或约 60%–78% 透明浅色表面，仅用极细描边和低透明阴影界定范围；
- 圆环成为主体，桌面建议直径 128–156px，保持 `aspect-ratio: 1`，由外轨、主轨、内轨和中心 AI 核心构成；
- 轨道增加静态断口、刻度和 2–4 个轨道节点，表现为圆形调度轨迹，不在 M2-1 旋转；
- AI 核心使用 54–66px 渐变圆盘、内高光和低透明外晕，文字保持正向；
- “策略路由 / 引擎选择 / 可用性检查 · 安全门禁”作为紧凑标题组置于圆环下方；
- 三条路线图例置于独立的近透明圆角面板中，建议背景透明度 58%–72%、1px 浅蓝细边、轻微模糊回退；图例使用短线路样本而不是厚重色块；
- M3 只接管外轨顺时针、内轨逆时针和 AI 核心发光，不再修改引擎静态几何。

#### 5.5.2 卡片形态与层次

- 增加统一视觉变量：主表面、次级表面、细边、内高光、Agent/Standard/Result 柔光、主卡片圆角和小卡片圆角；避免各模块单独散落不一致的半径与阴影；
- HUD、Review、任务队列、今日结果和底部质量卡使用 14–22px 的同族圆角；移除当前 `13px 3px`、`14px 4px` 等明显不对称切角；
- 主卡片采用 82%–94% 半透明白底、1px 冷色细边、内侧白色高光和低强度投影；Agent、Standard、Result 只在边缘和角部保留紫、橙、青绿柔光，不用大面积高饱和底色；
- `backdrop-filter` 只能作为增强，必须保留不支持模糊时仍清晰的半透明/近白色背景和边框回退；
- Review 头部统一为“圆角图标芯片 + 英文专有名词眉题 + 中文/专有标题 + 描述 + 状态胶囊”，状态胶囊增加真实状态圆点，不改变状态语义；
- Review 六组指标收进一层 10–12px 圆角的浅色内面板，用分组留白替代贯穿整卡的强分隔线；运行项继续作为独立底行，空态不伪造任务；
- 任务队列使用圆润双层边框、轻量虚线任务行和底部文字操作；今日结果使用顶部悬浮结果徽章、2×2 轻量统计格与弱填充 CTA，数据及入口保持不变；
- 顶部 HUD 只统一表面、圆角、图标圆盘和阴影，不修改 5 项指标、顺序或文案口径；导航栏结构和页面入口不在本阶段重做。

#### 5.5.3 底部微型可视化

底部 4 张质量卡保留现有标题、主数值、详情、顺序和近 24 小时口径，在右侧增加轻量微型可视化：

| 卡片 | 可用真实字段 | M2-1 视觉 |
| --- | --- | --- |
| 近 24 小时审查任务 | `reviewTasks.count` | 保留主数字；右侧只使用 `aria-hidden` 的静态扫描栅格/信号刻线作为装饰，不画伪趋势柱 |
| Provider 执行结果 | `successCount`、`failureCount`、`totalCount` | 使用真实成功/失败比例绘制双段微型堆叠条或双柱；无记录时显示中性空轨 |
| 发现问题数 | `severityCounts`、`findingCount` | 按真实严重级别分布绘制最多 4 段微型柱组；未知级别归入其他，不随机补齐 |
| 受影响任务 | `affectedTaskCount`、`highestRisk` | 使用最高风险映射 4 级风险阶梯，同时保留受影响任务数字；不得把 Finding 严重级别冒充任务分布 |

约束：

- 有业务含义的微图必须从现有 Presentation 真实字段确定性生成，零值、缺失、retained 和 error 状态可区分；
- 不增加后端查询、Runtime 字段或时间序列；没有真实时间桶就不出现折线图、趋势箭头或“逐小时”含义；
- 文本仍是主要信息载体；重复文本含义的图形可 `aria-hidden`，新增分布含义则提供隐藏摘要或可访问名称；
- 微图在 M2-1 保持静态，M3 也不为底部质量卡增加循环动画。

#### 5.5.4 背景与细节

- 中部地图背景在现有网格上叠加低对比度静态电路折线、稀疏径向光点和四角技术刻线；仅使用 CSS/SVG 装饰层，不新增位图背景或 Canvas；
- 背景装饰透明度必须低于节点和线路，不得穿过正文形成阅读噪声；错误、retained 和 reduced-motion 状态不需要切换背景动画，因为本阶段背景始终静止；
- 图标统一放入浅色圆形或圆角方形芯片，描边、尺寸和基线一致；保留 Agent 紫、Standard 橙、Result 青绿、Intake 蓝四类语义色；
- 眉题使用小号字重与有限字距，主数字保持最高对比度，次级说明统一弱化；中文不得因过度字距影响可读性；
- 状态胶囊、任务链接和 CTA 统一 hover/focus-visible 反馈；装饰辉光不得代替键盘焦点；
- 空态、错误态和保留快照使用同一圆润组件语言，但降低彩色柔光，避免错误状态看起来仍在活跃运行。

---

## 6. 活动状态与动画

### 6.1 页面活动状态

页面根节点增加：

- `data-command-center-activity="paused|idle|queued|running"`；
- Agent / Standard 模块分别保留 `data-queued`、`data-running`；
- 每条连接增加 `data-active="true|false"`；
- fallback 路径增加 `data-fallback-active="true|false"`。

状态规则：

| 状态 | 条件 | 动画 |
| --- | --- | --- |
| `paused` | loading、STALE、ERROR_EMPTY、ERROR_RETAINED | 全部暂停 |
| `idle` | Runtime FRESH 且双轨 queued/running 均为 0 | 清晰静态线路，无持续动画 |
| `queued` | 任一执行轨 queued > 0 且无 running | 中速圆环、对应路径流光、柔和边框 |
| `running` | 任一执行轨 running > 0 | 快速双环、强路线流光、明显霓虹边框 |

路径激活规则：

- `queue-engine`：任一执行轨有 queued 或 running；
- `engine-agent`：Agent queued 或 running；
- `engine-standard`：Standard queued 或 running；
- `agent-result`：Agent running，仅表达执行链路活动，不表达完成抵达；
- `standard-result`：Standard running，仅表达执行链路活动，不表达完成抵达；
- `agent-standard`：Standard 的 runningItems 或 nextQueued 中存在真实 `fallback=true` Item。

### 6.2 引擎双环

- 外环顺时针、内环逆时针；
- `queued`：外环 4.8 秒一圈，内环 3.6 秒一圈；
- `running`：外环 1.8 秒一圈，内环 1.25 秒一圈；
- `idle/paused`：停止在静态位置；
- 中心 AI 图标只做轻微发光，不旋转文字。

### 6.3 路线流光

M2-1 已为每条连接提供辉光、基轨和高亮内芯三层静态线缆。M3 只在同一个 `d` 上增加两层活动覆盖，不替换静态层：

1. 4–5px 重复短划线流光带；
2. 1–2 个视觉上分离的高亮短脉冲，通过 `stroke-dasharray` / `stroke-dashoffset` 表达沿线方向，不使用逐帧 JavaScript 移动物体。

节奏：

- `queued`：约 2.4 秒完成一次路径循环；
- `running`：约 1.1 秒完成一次路径循环；
- 非活动路径只显示静态基轨并降低到约 35% 透明度；
- Agent 与 Standard 独立激活，双轨运行时允许两组动画同时存在；
- 不绘制一次性“完成抵达”Beacon，除非未来新增可证明的终态事件契约。

### 6.4 Review 卡片霓虹边框

- queued 使用慢速低亮度边缘游走；
- running 使用约 1.6 秒一圈的高亮走马灯；
- 通过伪元素的 conic-gradient / mask 实现，保留原实线边框作为兼容回退；
- Agent 使用紫色，Standard 使用橙色；
- 活动卡片增加受控外发光，不改变内容区域背景对比度；
- 同时最多动画两个 Review 卡片，不对 HUD 或底部质量卡应用霓虹效果。

---

## 7. 响应式、无障碍与性能

### 7.1 桌面布局

- `>= 1440px`：使用“任务队列｜线路走廊｜引擎｜线路走廊｜双 Review｜线路走廊｜今日结果”七列骨架；三段线路走廊是独立布局空间，不得依赖普通 `column-gap` 碰运气；
- `>= 1440px`：任务队列建议 230–270px，引擎 220–250px，结果区 230–260px；双 Review 宽度使用约 `clamp(620px, 40vw, 760px)`，两张卡片同宽、同一水平起点，不再填满全部剩余空间；
- `1200–1439px`：保持完整拓扑，但侧栏、引擎和 Review 进入紧凑档；Review 目标宽度 480–620px，每段横向线路走廊仍至少保留约 24px，不允许线路端口彼此贴合；
- 双 Review 内部保留现有 6 组数据，不删除指标；通过收紧列权重、内边距和长文本省略消除松散感；
- Agent 与 Standard 之间保留约 52–68px 的专用 fallback 走廊，标签、虚线和端口不得压在卡片内容或边框上；
- 约 `1920×900`、100% 缩放为主验收视角；
- `1536×727` 作为 125% 等效验收视角；
- 保持双 Review 卡片紧凑高度，不以新增线路走廊重新拉高整个画布；节点与线路整体应接近 `assets/02.png` 的居中、留白和比例关系。

### 7.2 中小屏

- `901–1199px`：任务队列与引擎压缩展示，今日结果移至拓扑底部整行；
- `701–900px`：连接 SVG 隐藏，各节点改为单列语义顺序，允许纵向滚动；
- `<=700px`：继续使用既有移动端路由摘要，隐藏任务队列、引擎、fallback 和今日结果侧节点；双 Review 与底部质量卡保持既有顺序；
- 所有断点禁止文档横向溢出。

### 7.3 动效降级

- `prefers-reduced-motion: reduce`：所有旋转、流光、霓虹和变化强调关闭；
- `<=700px`：关闭连续动画；
- Runtime 非 FRESH：关闭连续动画；
- 动画只能改变 transform、opacity、stroke-dashoffset 或装饰层，不触发布局重排；
- 浏览器控制台不得出现 ResizeObserver loop、React key 或无效 SVG 属性警告。

### 7.4 静态视觉降级

- 不支持 `backdrop-filter` 时使用近白色不透明度更高的表面，文字对比度和边界不得依赖模糊效果；
- `forced-colors` 或高对比模式下保留真实边框、端口轮廓、焦点样式和文本，不以阴影/辉光作为唯一分组依据；
- `<=900px` 收起会挤占信息宽度的微型图形和部分背景装饰，优先保留数字、标签和操作；
- 打印或截图环境下所有静态关系仍可辨认，不依赖 M3 动画解释方向或状态。

---

## 8. 测试与验收矩阵

### 8.1 Python

- ActiveTask 新字段正常、全空和历史数据兼容；
- `externalUrl` 与 `repositoryUrl` 来源不混淆；
- 北京时间 00:00 对应 UTC 前一日 16:00；
- 00:00 边界包含、`to` 上界排除；
- SUCCESS / FAILED / SKIPPED / 活动 / 未知状态分桶；
- `completedCount` 和 `totalCount` 恒等关系；
- projectId / groupId 过滤；
- 空集合返回真实零值；
- Coverage 新 section 和 scanned 数正确；
- Runtime Schema 与现有契约测试通过。

### 8.2 前端模型与 Presentation

- 旧 Runtime 缺少新增字段时不崩溃且不伪造今日零值；
- 任务列表最多 3 项，保持后端顺序；
- 作者、分支、Commit、触发类型和阶段回退文案；
- HTTP(S) 外链通过，javascript/data/相对外链被拒绝；
- 今日结果正常、零值、未知状态和 retained；
- activity 状态与 Agent / Standard 独立激活矩阵；
- fallback 只有真实 Item 时激活。
- Provider 微图只使用真实成功/失败计数；Finding 微图只使用真实 severityCounts；风险阶梯只使用 highestRisk；缺失和零值不生成伪分布；
- ReviewTask 单值卡的信号纹理固定为无业务含义装饰，不暴露趋势或时间序列标签。

### 8.3 连接与资源所有权

- 6 条连接均从端口中心生成；
- 端口坐标基于真实 DOM rect；
- 双 Review 在 `1920×900` 与 `1536×727` 下均命中约定最大宽度，不再无上限拉伸；
- 三段桌面横向走廊和 fallback 走廊均有正向可用空间，端口、标签和卡片边框不重叠；
- `queue-engine` 为近似直线，引擎分支为圆角折线路径，结果侧为两条可区分线束，fallback 保持单向；
- 每条路径的辉光、基轨和内芯复用同一个 `d`；M2-1 不存在持续动画；
- 尺寸改变后路径更新，坐标未变不重复更新；
- 始终只有 1 个 ResizeObserver；
- 卸载后 Observer 清零；
- 不新增业务 RAF、轮询 timer 或重复 visibility listener；
- 首次零尺寸和测量失败时 DOM 内容完整。

### 8.4 浏览器

- 真实 Runtime 正常、真实零值、接口失败和 retained；
- 无任务、1 项、3 项、超过 3 项任务；
- 今日成功、失败、跳过、进行中和混合状态；
- idle 无持续动画；
- Agent queued / running；
- Standard queued / running；
- 双轨 running；
- 真实 fallback；
- `1920×900`、`1536×727`、900px 和 390px 无横向溢出；
- 100% / 125% 缩放后端口仍贴合卡片边缘；
- 参考图对比检查通过：Review 不松散、左右线路有可见伸展空间、端口呈现为边缘接口、整体不再是贴边括号式流程图；
- 引擎主轮廓为正圆轨道且图例位于独立近透明面板；主要卡片圆角、细描边、轻表面和色彩层级与参考图方向一致；
- 底部 Provider、Finding 和风险微图与文本真实值一致；无记录、Runtime/Governance error 与 retained 状态不伪造图形数据；
- 无 `backdrop-filter` 回退样式、高对比/键盘焦点和 900px 微图收起行为可用；
- reduced-motion 和移动端无连续动画；
- 控制台无 error / warning。

### 8.5 构建

- Python Command Center 专项测试通过；
- 前端全部 Node 测试通过；
- `scripts/run-frontend.cmd build` 通过；
- 既有主 Chunk 大小警告可记录为非阻塞项，本专项不顺带拆包。

---

## 9. 分阶段实施

### M0：文档与契约冻结（已完成）

产出：

- 新建本专题文档；
- 冻结数据契约、视觉规则、动画状态、测试矩阵和阶段边界；
- 不修改产品代码。

停止点：等待用户确认“继续 M1”。

### M1：Runtime 任务详情与今日 Result

状态：已完成（`2026-08-04`）。

实施结果：

- `ActiveTaskSnapshot` 已追加作者、GitLab 外链、项目仓库、来源/目标分支和 Commit 可空字段；`commitSha` 仅从真实 `commit_sha` 或 `after_sha` 回退获取；
- Runtime v2 已增加 `todayResults`，以固定 `UTC+08:00` 自然日边界查询 `updated_at >= from AND updated_at < to`，并输出完成、成功、失败、跳过、进行中、其他及原始状态计数；
- 今日 Result 聚合继承 `projectId` 与 `groupId` 过滤；Coverage 已增加 `sections.todayResults=FULL` 与 `scanned.todayResults`；
- 为保持 Runtime 查询数上限，ReviewTask 的窗口总数和活跃总数合并为同一条条件聚合查询；新增今日聚合后专项场景仍不超过 20 条查询；
- 前端 Runtime normalizer 已保留新增任务字段并规范化 `todayResults`；旧 Runtime 缺少该字段时返回 `null`，不伪造零值；
- 未修改数据库 Schema、页面 JSX、CSS、顶部五项状态或底部近 24 小时摘要。

验证结果：

- Python Command Center 专项：`37 passed`；
- 本阶段 Python 文件定向 Ruff：通过；仓库封装 lint 会扫描全后端并命中 5 个与本阶段无关的既有问题，本阶段未扩散修改；
- 前端相关模型与 Presentation：`18 passed`；
- 前端全量 Node 测试：`119 passed / 0 failed`；
- `scripts/run-frontend.cmd build`：通过，仅保留既有大 chunk 提示；
- `git diff --check`：通过。

允许范围：

- Python Command Center Schema、Repository、Service 和对应测试；
- 前端 Runtime normalizer 与纯 Presentation 契约测试；
- 回写本文件 M1 结果。

禁止范围：

- 不改 JSX 页面结构或 CSS；
- 不改数据库 Schema；
- 不进入 M2。

完成条件：Python 专项测试和相关前端模型测试通过。

停止点：等待用户确认“继续 M2”。

### M2：左右数据节点与动态端口

状态：已完成（`2026-08-04`）。

实施结果：

- 左侧已由静态“审查入口”改为 Runtime 最近活动 ReviewTask，保持后端顺序且最多展示 3 项；展示项目、作者、触发类型、分支/Commit、阶段、相对更新时间及任务操作；
- 外部 GitLab 操作仅接受可解析的 `http:` / `https:` URL，优先任务 `externalUrl`，其次项目 `repositoryUrl`；不安全或相对 URL 不渲染外链；
- 右侧已由“结果持久化”改为北京时间自然日今日 Result，展示完成、成功、失败、跳过、进行中、总数和可选其他状态；旧 Runtime 缺字段时显示不可用，不伪造零值；
- 引擎模块已删除自动降级说明，新增青蓝色 `Agent Review → Standard Review` 图例；
- 固定 `1200×440` SVG 坐标已替换为真实 DOM 端口测量，覆盖任务队列到引擎、引擎到双 Review、双 Review 到结果以及 Agent 到 Standard 共 6 条路径；
- 单个 React `useLayoutEffect` 只创建一个 ResizeObserver；坐标基于 `getBoundingClientRect()` 转换为地图局部坐标，相同路径签名不重复更新，卸载时只断开一次；未新增 RAF、轮询计时器或窗口 resize 监听器；
- 端口已移至卡片边缘外侧，使用白色中心、路线色描边和低透明光晕；路径从源端口中心开始，箭头在目标端口前保留 9px 间距；fallback 使用青蓝虚线；
- M2 路线和 Review 卡片保持静态；既有连续流光与呼吸规则已取消激活，动画留待 M3；
- `901–1199px` 使用三列加底部结果布局，`701–900px` 使用单列语义顺序并隐藏 SVG，`<=700px` 保留移动摘要且隐藏侧节点；同时补充 `761–1000px` 顶部导航换行规则，消除 900px 文档横向溢出。

验证结果：

- M2 Presentation、URL 安全、拓扑测量和页面契约专项：`39 passed`；
- 前端全量 Node 测试：`124 passed / 0 failed`；
- `scripts/run-frontend.cmd build`：通过，仅保留既有大 chunk 提示；
- 浏览器真实 Runtime 为 `FRESH`，今日 Result 和真实零活动任务正常展示；
- `1920×900` 与 `1536×727`：6 条路径均存在，所有路径起点与源端口中心误差为 `0`，箭头与目标端口间距为 `9px`，无横向溢出；
- `900px`：侧节点按单列顺序展示、装饰 SVG 隐藏、文档宽度与客户端宽度一致；
- `390px`：移动摘要和双 Review 保留，任务队列、引擎、fallback、今日结果隐藏，无横向溢出；
- 浏览器控制台：无 warning / error；M2 拓扑节点无活动动画；
- `git diff --check`：通过。

允许范围：

- 左右节点 JSX、Presentation、URL 安全工具；
- DOM 端口、SVG 路径测量、ResizeObserver 资源所有权；
- 桌面和响应式布局；
- 对应前端测试、构建和浏览器静态验收；
- 回写本文件 M2 结果。

禁止范围：

- 不实现持续动画；
- 不修改后端口径；
- 不进入 M3。

停止点：新增 M2-1 后，等待用户确认“继续 M2-1”。

### M2-1：静态拓扑构图与未来科技视觉基底

状态：已实现，等待用户视觉确认（`2026-08-04`）。

实施结果：

- 页面阶段标识更新为 `LIVE_TOPOLOGY_M2_1`，动画所有权保持 `STATIC_M2_1`；未启用流光、圆环旋转、霓虹走马灯或业务 RAF；
- `1200px+` 改为四个业务节点加三段显式线路走廊的七列骨架；双 Review 同宽并受上限约束，fallback 走廊固定为 58px；
- 六条线路按 direct、branch、result、fallback 四类生成，取消横跨走廊的通用三次贝塞尔；圆角折线使用 `H/V/Q`，队列和结果侧存在高差或短走廊时也能真实抵达目标端口；
- 每条线路复用同一 `d` 渲染辉光、基轨和高亮内芯三层，端口增加双层核心、外光晕和接头颈部；目标前使用小型箭羽，fallback 保持单向虚线；
- 策略路由引擎改为多层正圆轨道、静态轨道节点和 62px AI 核心；图例与标题进入独立近透明面板，为 M3 双环反转预留稳定 DOM；
- HUD、任务队列、Review、今日结果和底部质量卡统一为圆润半透明表面、细描边、内高光和低强度语义色柔光；中部地图增加静态电路纹理与角落技术刻线；
- Review 六组数据进入圆角内面板；任务队列任务行改为轻量虚线；今日结果增加悬浮结果徽章、圆润 2×2 统计格和弱填充 CTA；
- 新增纯前端质量微图工具：Provider 使用真实成功/失败比例，Finding 使用真实 Severity 计数，受影响任务使用真实最高风险阶梯；ReviewTask 单值卡只显示 `aria-hidden` 静态信号纹理，不冒充趋势；
- `<=1199px` 隐藏会跨越底部结果区的装饰 SVG 和端口，保留完整语义节点；`<=900px` 隐藏底部微图，`<=700px` 继续沿用移动端摘要和双 Review 主内容；
- 增加不支持 `backdrop-filter` 的近白表面回退及 forced-colors 边框/线路/焦点回退；未修改 Runtime、后端、数据库或顶部/底部指标口径。

验证结果：

- M2-1 拓扑、页面契约和质量微图专项：`19 passed / 0 failed`；
- 前端全量 Node 测试：`128 passed / 0 failed`；
- `scripts/run-frontend.cmd build`：通过，仅保留既有大 chunk 提示；
- `git diff --check`：通过；
- 当前浏览器桌面 CSS 视口 `1600×900`：双 Review 均为 641px，间距 58px，引擎圆环 144×144px，任务→引擎 / 引擎→Review / Review→结果可见走廊分别为 92 / 100 / 48px；页面滚动高度等于视口高度且无横向溢出；
- 桌面六条线路均存在，合计 18 个静态 SVG 层；所有线路起点与源端口中心误差为 0–0.1px，目标端与目标端口统一保留 10px，未检测到持续动画；
- 当前浏览器中等 CSS 视口 `967×1140`：装饰线路和端口按规则隐藏，Standard 与底部今日结果保持 10px 间隔，文档宽度与客户端宽度一致；
- 桌面和中等视口浏览器控制台无 warning / error；
- 当前 in-app Browser 未提供任意视口尺寸设置能力，本阶段无法重新取得精确 `1920×900`、`1536×727`、900px、390px 四档截图；900px/390px 既有语义降级由 M2 已验收，本阶段相关媒体查询和结构契约测试继续通过，精确四档最终复验仍保留在 M4。

目标：

- 以 `assets/02.png` 为视觉方向，先解决 Review 过宽、线路走廊被挤压、端口贴边和通用流程图曲线问题；
- 将引擎、HUD、Review、任务队列、今日结果和底部质量卡统一为更圆润、轻盈的未来科技视觉；
- 为 M3 提供稳定且唯一的路径几何、线路分层和动画挂载点，不在本阶段激活连续动画。

允许范围：

- 桌面七列空间骨架、双 Review 最大宽度和内部紧凑度；
- fallback 垂直间距及标签布局；
- 6 条路径的分型几何、双层端口、接头颈部、小型方向提示和静态三层线缆；
- 引擎正圆多轨外形、近透明图例面板和静态轨道节点；
- Command Center 页面内 HUD、中部节点、Review 内面板、今日结果和底部质量卡的统一圆角、半透明表面、细描边、图标芯片与静态背景装饰；
- 基于现有真实字段的 Provider/Finding/风险微图，以及 ReviewTask 卡片明确无业务含义的静态信号纹理；
- 现有拓扑测量纯函数及其测试；
- Command Center Canvas、Page、Presentation 和 CSS 的必要展示改动；
- `1200px+` 响应式静态布局、无模糊回退、高对比与小屏降级、前端测试、构建和浏览器对比验收；
- 回写本文件 M2-1 结果。

禁止范围：

- 不实现流光、粒子、双环旋转、霓虹走马灯或任何持续动画；
- 不修改 Runtime、后端、数据库、业务状态或顶部/底部指标；
- 不改变顶部 5 项与底部 4 项的内容、顺序、来源和时间口径；
- 不把单值或装饰纹理表述成趋势数据，不新增虚假的时间桶或统计分布；
- 不复制参考图中的示例任务或统计数字；
- 不引入 Canvas、业务 RAF 或第二个 ResizeObserver；
- 不进入 M3。

完成条件：

- `1920×900` 与 `1536×727` 下双 Review 宽度受控，三段线路走廊能够明显伸展，fallback 内容不重叠；
- 六条路径符合第 5.3 节分型，端口符合第 5.2 节接口样式，静态视觉与 `assets/02.png` 的结构方向一致；
- 引擎呈现为多层正圆轨道、图例为独立近透明面板；页面主要卡片使用统一圆润轻表面，不再保留明显不对称切角；
- 底部真实微图与 Provider/Severity/Risk 字段一致，ReviewTask 装饰纹理不冒充趋势；数据缺失和故障状态不伪造可视化；
- 900px、390px 既有降级行为和无横向溢出继续成立；
- 前端专项测试、全量测试、构建、浏览器控制台检查和 `git diff --check` 通过。

停止点：等待用户确认“继续 M3”。

### M3：状态驱动动画

允许范围：

- activity 状态；
- 基于 M2-1 唯一路径几何实现引擎双环、路线流光、方向粒子和霓虹边框；
- reduced-motion、异常态、小屏降级；
- 动画、资源所有权和性能测试；
- 回写本文件 M3 结果。

禁止范围：

- 不制造完成抵达或 fallback 转交事件；
- 不重新设计 M2-1 已冻结的节点比例、线路走廊或路径坐标体系；
- 不引入 Canvas 或业务 RAF；
- 不进入 M4。

停止点：等待用户确认“继续 M4”。

### M4：真实数据验收与收口

允许范围：

- 真实 Runtime 数据验收；
- 隔离 mock 的错误、retained 和活动状态验收；
- 多视口、缩放、控制台、测试和构建；
- 发现本专项缺陷时修复并补测试；
- 回写最终结果。

禁止范围：

- 不自动提交、推送、部署；
- 不开启新的信息架构或指标专项。

停止点：等待用户决定创建提交、部署或继续优化。

---

## 10. 分阶段 Prompt

### M1 Prompt

```text
继续 51 · AI Review Command Center 动态拓扑与实时侧栏计划，执行 M1。

开始前只读取：
1. 根目录 AGENTS.md；
2. 本计划第 2、3、8、9 节；
3. Command Center 当前 Schema、Repository、Service、Model 和相关测试命中范围。

只实现 ActiveTask 新字段和 todayResults 自然日 Result 聚合，不修改数据库、不调整页面 JSX/CSS。
完成 Python 专项测试和相关前端模型测试，回写 M1 结果后停止，等待“继续 M2”。
不得提交、推送、部署或自动进入下一阶段。
```

### M2 Prompt

```text
继续 51 · AI Review Command Center 动态拓扑与实时侧栏计划，执行 M2。

开始前只读取：
1. 根目录 AGENTS.md；
2. 本计划第 4、5、7、8、9 节和 M1 完成记录；
3. Command Center Canvas、Presentation、CSS 和相关测试命中范围。

实现左右数据节点、URL 安全、6 条真实 DOM 端口连接和响应式布局。
本阶段保持线路静态，不实现 M3 持续动画，不修改后端口径。
完成前端专项测试、全量测试、构建和静态浏览器验收，回写 M2 结果后停止。新增 M2-1 后，下一授权口令为“继续 M2-1”。
不得提交、推送、部署或自动进入下一阶段。
```

### M2-1 Prompt

```text
继续 51 · AI Review Command Center 动态拓扑与实时侧栏计划，执行 M2-1。

开始前只读取：
1. 根目录 AGENTS.md；
2. 本计划第 1.1、5、7、8、9 节和 M2 完成记录；
3. assets/02.png；
4. Command Center Canvas、Topology、CSS 和相关测试命中范围。

先实现桌面七列空间骨架、双 Review 宽度约束和 fallback 走廊，再按语义重做 6 条静态路径、双层端口与三层线缆。
随后对标参考图完成引擎正圆多轨、透明图例面板、统一圆润轻表面、静态电路背景和底部真实微图；没有序列的数据不得伪装成趋势。
本阶段不得实现任何持续动画，不修改 Runtime 或后端，不改变顶部/底部指标，不复制参考图示例数据。
完成前端专项测试、全量测试、构建以及 1920×900、1536×727、900px、390px 浏览器对比验收，回写 M2-1 结果后停止，等待“继续 M3”。
不得提交、推送、部署或自动进入下一阶段。
```

### M3 Prompt

```text
继续 51 · AI Review Command Center 动态拓扑与实时侧栏计划，执行 M3。

开始前只读取：
1. 根目录 AGENTS.md；
2. 本计划第 5、6、7、8、9 节和 M2-1 完成记录；
3. Command Center 动画状态、Canvas JSX、CSS 和相关测试命中范围。

按真实 queued/running/fallback 证据实现双环反转、活动路线流光和 Review 霓虹边框。
必须保留 idle、异常、reduced-motion 和移动端静止状态；不得引入 Canvas、业务 RAF 或虚假完成事件。
完成测试、构建和浏览器动画验收，回写 M3 结果后停止，等待“继续 M4”。
不得提交、推送、部署或自动进入下一阶段。
```

### M4 Prompt

```text
继续 51 · AI Review Command Center 动态拓扑与实时侧栏计划，执行 M4。

开始前只读取：
1. 根目录 AGENTS.md；
2. 本计划第 8、9 节和 M1、M2、M2-1、M3 完成记录；
3. 与验收失败直接相关的实现和测试命中范围。

使用真实 Runtime 和隔离 mock 完成数据、故障、retained、活动动画、多视口和缩放验收。
只修复本专项验收发现的缺陷；完成全部测试与构建并回写最终结果后停止。
不得提交、推送、部署或自动开启新专项。
```

---

## 11. 总控 Prompt

```text
推进 51 · AI Review Command Center 动态拓扑与实时侧栏计划。

先读取根目录 AGENTS.md 和本计划当前状态，只执行用户明确授权的 M 阶段。
每次先把本计划状态更新为对应阶段 IN PROGRESS，再执行获授权范围。

必须遵守：
- 顶部 5 项和底部近 24 小时质量摘要不变；
- 左侧是最近活动 ReviewTask，不冒充统一执行顺序；
- 右侧是北京时间自然日 Result；
- 不修改数据库 Schema 或 Runtime 状态机；
- 不制造完成抵达或 fallback 转交事件；
- 不引入 Canvas 或业务 RAF；
- M2-1 先冻结静态空间骨架与线缆几何，M3 只能在同一几何上增加状态动画；
- 每阶段完成测试、构建、浏览器验收和文档回写后必须停止；
- 未经明确授权不得提交、推送、部署或进入下一阶段。
```

---

## 12. Agent 自主推进边界

### 当前可自主执行

- 只读核对本计划与现有实现；
- 回写当前已获授权阶段的状态、结果和真实验收证据；
- 运行该阶段约定的测试、构建和本地浏览器验收；
- 修复当前阶段验收发现且不扩大契约的缺陷。

### 必须等待用户明确授权

- 从 M0 进入 M1，或进入任何下一阶段（包括新增的 M2-1）；
- 修改 Runtime / Governance 之外的后端业务模块；
- 修改数据库表、列、索引或迁移；
- 改变顶部、底部指标或时间口径；
- 新增真实完成事件、消息流或状态机；
- 创建提交、推送、部署或发布。

### 当前停止点

M2-1 静态拓扑构图与未来科技视觉基底已实现并完成自动化及当前可用视口验收。停止等待用户视觉确认；确认后输入：`继续 M3`。
