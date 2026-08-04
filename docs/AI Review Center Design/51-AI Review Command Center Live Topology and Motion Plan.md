# 51 · AI Review Command Center 动态拓扑与实时侧栏计划

## 0. 文档状态

- 文档日期：`2026-08-04`
- 当前状态：`M0 COMPLETE — WAITING FOR M1 AUTHORIZATION`
- 文档用途：冻结 AI Review 指挥中心中部拓扑的侧栏数据、连接端口、活动动画和分阶段实施契约。
- 当前授权：仅完成 M0 文档落地；不得修改 Runtime / Governance 接口、数据库、前端页面、样式、测试或部署配置。
- 停止点：等待用户确认“继续 M1”。

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

本专项目标：

- 将左右说明节点替换为真实数据节点；
- 让连接端点贴合真实卡片边缘，并在缩放和响应式布局变化后自动重算；
- 让排队、运行、双轨和 fallback 状态具有明显但可信的动态反馈；
- 不新增虚假完成事件，不改变 Review / Scheduler / Agent / Provider 状态机。

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

- 每个端口为 10px 圆点，白色中心、2px 路线色描边；
- 端口中心位于卡片边缘外侧约 6px，避免线条嵌入内容区；
- 端口外增加 4px 低透明度光晕；
- 连接线先从端口向外走 12px 短直线，再进入贝塞尔曲线；
- 箭头停在目标端口前，不覆盖端口或卡片边框；
- Agent → Standard 结构关系保持虚线基轨，活动时叠加青蓝流光。

### 5.3 测量机制

- 为地图容器和端口增加稳定 `data-*` 标识；
- 单个 React `useLayoutEffect` 创建一个 `ResizeObserver`；
- 测量端口 `getBoundingClientRect()`，转换为地图容器局部坐标；
- 仅尺寸或位置变化时更新路径数据，相同坐标不重复 setState；
- 组件卸载时断开 Observer；
- 不建立持续 RAF、轮询计时器或第二套窗口 resize 监听器；
- 首次尚未取得合法尺寸时隐藏装饰 SVG，语义 DOM 仍完整可用。

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

每条连接由三层组成：

1. 2–3px 静态基轨；
2. 4–5px 重复短划线流光；
3. 低透明度同色辉光。

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

- `>= 1200px`：完整四列拓扑；任务队列建议 250–280px，引擎 220–260px，结果区 240–260px，双 Review 继续占主要宽度；
- 约 `1920×900`、100% 缩放为主验收视角；
- `1536×727` 作为 125% 等效验收视角；
- 保持双 Review 卡片当前紧凑高度，不以新增侧栏重新拉高整个画布。

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

### 8.3 连接与资源所有权

- 6 条连接均从端口中心生成；
- 端口坐标基于真实 DOM rect；
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

停止点：等待用户确认“继续 M3”。

### M3：状态驱动动画

允许范围：

- activity 状态；
- 引擎双环、路线流光、霓虹边框；
- reduced-motion、异常态、小屏降级；
- 动画、资源所有权和性能测试；
- 回写本文件 M3 结果。

禁止范围：

- 不制造完成抵达或 fallback 转交事件；
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
完成前端专项测试、全量测试、构建和静态浏览器验收，回写 M2 结果后停止，等待“继续 M3”。
不得提交、推送、部署或自动进入下一阶段。
```

### M3 Prompt

```text
继续 51 · AI Review Command Center 动态拓扑与实时侧栏计划，执行 M3。

开始前只读取：
1. 根目录 AGENTS.md；
2. 本计划第 5、6、7、8、9 节和 M2 完成记录；
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
2. 本计划第 8、9 节和 M1-M3 完成记录；
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

- 从 M0 进入 M1，或进入任何下一阶段；
- 修改 Runtime / Governance 之外的后端业务模块；
- 修改数据库表、列、索引或迁移；
- 改变顶部、底部指标或时间口径；
- 新增真实完成事件、消息流或状态机；
- 创建提交、推送、部署或发布。

### 当前停止点

M0 文档与契约已完成。停止等待用户确认：`继续 M1`。
