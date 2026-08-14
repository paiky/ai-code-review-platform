# Review 任务详情 Phase 2 Safe Trace Implementation Plan

## 1. 状态与前置条件

- 文档状态：计划已创建，等待 Phase 1 实施并完成人工验收后再申请实施授权。
- 当前授权：只允许创建和完善本计划；不授权修改前端代码、Backend、数据库、API 或部署环境。
- 实施前置条件：
  1. `Review任务详情Phase1实施计划.md` 已完成实现、自动化、构建、响应式、深链和轮询验收；
  2. Phase 1 文档已回填实际验证结果；
  3. 用户已明确确认 Phase 1，并授权开始 Phase 2；
  4. Phase 1 的 Result -> Findings -> Journey 信息架构、六阶段语义和顶部“查看 Review 流程”入口保持稳定。
- 改动量等级：**中**。涉及 Agent Trace 安全派生模型、模型 Review 阶段 Drawer、轮询更新、fallback / 历史
  兼容、安全审计和响应式回归，但不修改后端数据结构、公开 API、Review 行为或 Finding 契约。

## 2. Goal

将“模型 Review”阶段 Drawer 从字段表为主的诊断面板升级为脱敏、按序号组织的 Safe Trace，使用户能够看懂
系统可安全证明的 Agent 活动类型、状态、单次耗时和有界计数，同时把运行配额降级到默认折叠的高级信息。

Phase 2 回答的是：

> 系统能够安全证明 Agent 做过哪些类型的动作。

Phase 2 不回答：

> Agent 在某个精确时刻看了什么、搜索了什么、如何推理或为什么形成某个 Finding。

## 3. Non-goals

Phase 2 明确不做：

- 不修改 Python Backend、Java Backend、数据库、API、schema 或 Progress 持久化格式；
- 不新增全局 Review Trace Drawer；
- 不改变 Phase 1 的 Result -> Findings -> Journey 顺序；
- 不改变现有六阶段、阶段状态、reviewKey 隔离或 fallback 语义；
- 不展示工具实际发生时钟，不把 Progress `createdAt` 解释为工具执行时间；
- 不展示 Prompt、query、query hash、path、path summary、arguments、input、output、源码、Diff、模型原文或
  reasoning；
- 不展示 Worker、容器、网络地址、基础设施异常原文或自由文本错误；
- 不把 `itemCount` 命名为“证据数量”；
- 不把 `evidenceCallsUsed` 命名为“已获得证据数”；
- 不显示执行中的候选 Finding 数；
- 不实现 typed evidence、Finding 与 Evidence 关联或 Evidence Chain；
- 不增加 Agent 子阶段精确耗时或根据事件推算模型思考时间；
- 不为 Standard Review 伪造 Agent 工具活动；
- 不触发真实 Agent Review，不产生模型费用；
- 不进入 Phase 3。

## 4. 不可破坏安全契约

### 4.1 UI 不接触原始 detail

数据流固定为：

```text
原始 Agent Progress
  -> Agent Trace 作用域与去重
  -> ReviewJourney 安全派生
  -> SafeTraceViewModel
  -> Drawer
```

Drawer、Timeline 和展示组件不得接收、解析或保留原始 `detail / message`。原始 Progress 新增字段时，除非显式
进入本计划白名单，否则不能出现在 `SafeTraceViewModel`。

### 4.2 固定枚举映射

- UI 文案只由 `activityType` 经过前端固定映射生成。
- 禁止 Backend 或原始 detail 通过 `displayLabel`、自由文本 `message` 等字段控制 UI 文案。
- 未知 `activityType` 不展示原始值，使用固定“未识别的安全活动”或直接忽略，并记录在测试覆盖范围内。
- `status` 只接受固定白名单；未知值归一为 `UNKNOWN`，不得直出原始字符串。
- `errorCode` 必须继续通过现有安全枚举格式校验，非法值丢弃。

### 4.3 不伪造时间和完成状态

- Trace 节点使用 `#sequence`，不显示 `HH:mm:ss` 等事件时钟。
- `durationMs` 只表示当前白名单工具事件自己记录的耗时，不用于反推开始或结束时间。
- 不累加工具耗时生成 Agent 总耗时；Agent 总耗时只使用现有可靠 `agentRunSummary.durationMs`。
- `AGENT_ANALYZING` 只表达“开始分析”或“已记录分析开始”，不得因为 Review 最终成功而显示“分析已完成”。
- `AGENT_FINISHED` 才能表达正式结果已保存；`SUBMIT_REVIEW` 成功只表达 Review Card 提交活动成功。
- 缺少可靠事件时宁可不展示节点，不补造“获取上下文”“生成结论”或候选 Finding 数。

### 4.4 数量语义

- `itemCount`：显示为“返回条目 N”，不显示为证据数；
- 单事件 `sourceBytes`：显示为“返回 N bytes”；
- `evidenceCallsUsed`：显示为“证据调用累计 N / Limit”；
- `toolCallCount`：显示为“工具调用 N / Limit”；
- `sourceBytesReturned`：显示为“源码返回 N / Limit bytes”；
- `turnCount`：只在现有契约允许的终态显示“模型回合 N / Limit”；
- `submitAttemptCount`：显示为“提交尝试 N / Limit”；
- 数字缺失时隐藏对应项，不显示 `0` 代替未知。

## 5. Safe ViewModel Contract

### 5.1 SafeTraceEvent

```text
SafeTraceEvent
  sequence: non-negative integer
  sequenceEnd?: non-negative integer
  groupCount?: positive integer
  activityType: allowlisted enum
  status: allowlisted enum
  durationMs?: non-negative integer
  itemCount?: non-negative integer
  sourceBytes?: non-negative integer
  errorCode?: validated enum token
```

允许的 `activityType` 首版固定为现有可验证活动：

```text
ANALYZING
LIST_FILES
SEARCH_CODE
READ_FILE_RANGE
READ_DIFF_RANGE
SUBMIT_REVIEW
RECLAIMED
FINISHED
FALLBACK
CANCELLED
```

允许的 `status` 首版固定为：

```text
STARTED
RUNNING
SUCCESS
FAILED
WARNING
CANCELLED
UNKNOWN
```

### 5.2 SafeTraceSummary

```text
SafeTraceSummary
  runId?: non-negative integer
  claimAttempt?: non-negative integer
  agentDurationMs?: non-negative integer
  toolCallsUsed?: non-negative integer
  toolCallsLimit?: non-negative integer
  evidenceCallsUsed?: non-negative integer
  evidenceCallsLimit?: non-negative integer
  sourceBytesUsed?: non-negative integer
  sourceBytesLimit?: non-negative integer
  modelTurnsUsed?: non-negative integer
  modelTurnsLimit?: non-negative integer
  submitAttempts?: non-negative integer
  submitAttemptLimit?: non-negative integer
```

### 5.3 SafeTraceViewModel

```text
SafeTraceViewModel
  reviewKey: stable safe key
  state: AVAILABLE | PARTIAL | UNAVAILABLE
  events: SafeTraceEvent[]
  summary: SafeTraceSummary
```

禁止进入任一 Safe ViewModel 的字段：

```text
detail
message
displayLabel
query
queryHash
path
pathSummary
arguments
input
output
reasoning
prompt
rawResponse
failureMessage
workerId
```

ViewModel 必须是可序列化、可安全快照测试的纯数据，不能携带原始事件对象引用。

## 6. Data Mapping and Derivation

| Safe 字段 | 现有来源 | 派生规则 |
| --- | --- | --- |
| Trace 作用域 | 最新 `runId + claimAttempt` | 继续复用现有隔离、接管和去重规则 |
| `sequence` | 白名单 Agent trace detail | 有界非负整数；缺失时不补造工具顺序 |
| `sequenceEnd / groupCount` | 连续同类安全活动聚合 | 只合并相邻且 activity/status 一致的事件 |
| `activityType` | 现有固定 activity enum | 未知值不透传 |
| `status` | 现有固定 trace 状态或阶段事实 | 缺失时使用 `UNKNOWN`，不由终态批量改成成功 |
| `durationMs` | 单个安全 audit event | 非负有界；缺失隐藏 |
| `itemCount` | 单个安全 audit event | 显示“返回条目” |
| `sourceBytes` | 单个安全 audit event | 显示单次返回字节 |
| `errorCode` | 现有安全错误码 | 继续校验后展示 |
| `runId / claimAttempt` | `journey.agentSummary` | 缺失隐藏 |
| Agent 总耗时 | `review.agentRunSummary.durationMs` | 不从事件累加 |
| 工具调用 | `journey.agentSummary.toolCallCount` | Limit 来自白名单有效预算 |
| 证据调用累计 | `journey.agentSummary.evidenceCallsUsed` | Limit 来自 `maxEvidenceCalls` |
| 源码返回 | `journey.agentSummary.sourceBytesReturned` | Limit 来自 `maxSourceBytes` |
| 模型回合 | 终态 `journey.agentSummary.turnCount` | 运行中未知时隐藏 used 值 |
| 提交尝试 | 现有安全 submission summary | Limit 只使用有界白名单值 |

实现应优先复用 `agentReviewTrace.js` 现有作用域选择、去重和相邻活动聚合，但在 ReviewJourney / Presentation
边界生成新的安全 ViewModel。展示组件不得回退到 `formatAgentTraceDetail(detail)` 或自行 `JSON.parse`。

## 7. Target Drawer Information Architecture

### 7.1 Agent 模型 Review

```text
模型 Review
  -> 阶段状态、Review 身份、可靠阶段时间 / Agent 总耗时
  -> 运行概览（Run、领取尝试等白名单字段）
  -> 运行记录（SafeTraceEvent[]，按序号）
  -> 运行配额（默认折叠）
  -> 既有高级执行记录（保持安全折叠；不得与新 Trace 重复泄露原始 detail）
```

- 有安全事件时显示纵向事件流。
- `PARTIAL` 时显示固定“仅展示现有可靠活动记录”提示。
- `UNAVAILABLE` 时显示明确空状态，保留现有阶段概览和安全指标，不创建假节点。
- 运行中轮询只追加或更新同一作用域内的安全事件，Drawer 保持打开，滚动位置不得被强制重置。
- scope 切换到新的 `claimAttempt` 时只显示最新作用域，并用固定接管节点解释 `RECLAIMED`；不混入旧尝试工具序列。

### 7.2 Standard Review

- 不渲染 Agent Safe Trace。
- 保留现有 Provider 状态、阶段时间、可靠耗时和固定安全执行记录。
- 不把 Provider Request/Response 包装成 Agent 工具活动。

### 7.3 Agent -> Standard fallback

- 继续显示现有 Agent -> Standard 显式转交。
- 有可靠 Agent Trace 时可显示 Agent 安全活动；无可靠记录时显示固定缺失状态。
- Standard 接管部分继续使用现有固定阶段记录，不与 Agent 工具序列合并。

### 7.4 历史与损坏数据

- 历史任务没有 `runId / claimAttempt / sequence` 时不补造 Safe Trace。
- detail 损坏、字段越界或包含禁止字段时，ViewModel 丢弃非法字段并保持页面可用。
- 原始敏感字段即使存在于 fixture，也不得出现在 ViewModel JSON、DOM、Tooltip、aria-label 或错误提示中。

## 8. Interaction Contract

- 顶部“查看 Review 流程”继续滚动到六阶段，不因 Phase 2 改成打开 Drawer。
- 用户点击“模型 Review”阶段节点后才打开该阶段 Drawer。
- Drawer 关闭后焦点继续返回原阶段节点。
- `Escape`、Enter、Space、键盘 Tab 顺序和现有告警 Popover 隔离不回归。
- 同 `reviewKey + runId + claimAttempt` 轮询更新保持 Drawer、折叠状态和滚动位置。
- 切换 `reviewKey` 时关闭旧 Review Drawer，不能把旧 Trace 暂存在新 Review 下。
- “运行配额”默认折叠；用户展开后，同一 Drawer 生命周期内轮询不自动收起。
- 不新增复制原始 JSON、查看输入输出或下载 Trace 的入口。

## 9. Expected File Scope

- `frontend/src/agentReviewTrace.js`：仅在需要时扩展安全标准化、作用域和聚合纯函数；
- `frontend/src/reviewJourney.js` 或独立 Presentation 文件：生成 `SafeTraceViewModel`，阻断原始 detail；
- `frontend/src/App.jsx`：模型 Review Drawer 的安全事件流和配额折叠组件；
- `frontend/src/styles.css`：纵向 Trace、Drawer 响应式、状态与长数字布局；
- `frontend/tests/agentReviewTrace.test.mjs`：作用域、去重、聚合、状态和敏感字段测试；
- `frontend/tests/reviewJourneyPresentation.test.mjs`：ViewModel 与运行/终态/fallback 派生；
- `frontend/tests/reviewJourneyInformationArchitecture.test.mjs`：Drawer 不解析 raw detail、禁止字段与入口契约；
- 必要时新增 `frontend/tests/safeTracePresentation.test.mjs`；
- 本计划文档：实施后回填 Phase 2 验证结果。

不修改 `README.md`，不修改 Phase 1 已冻结的结果页信息架构。

## 10. Acceptance Matrix

### 10.1 Trace 场景

- Agent running：只有 `ANALYZING`；
- Agent running：list/search/read 多事件按 sequence 展示；
- Agent success：submit 与 `FINISHED` 语义分开；
- Agent failure：白名单错误码，不展示异常原文；
- Agent cancelled；
- Agent fallback；
- Agent reclaimed：仅最新 `runId + claimAttempt`；
- 连续同类事件聚合；
- 多 Review 严格按 `reviewKey` 隔离；
- 轮询重复事件去重；
- 缺失 sequence、损坏 detail、未知 activity/status；
- Standard Review 不出现 Agent Safe Trace；
- 历史任务显示安全空状态。

### 10.2 数量和时间语义

- `itemCount=12` 显示“返回条目 12”，DOM 中不出现“12 条证据”；
- `evidenceCallsUsed=6` 显示“证据调用累计 6”，不显示“获取 6 条证据”；
- Trace 不显示工具事件 `HH:mm:ss` 时钟；
- 单事件 duration 缺失时隐藏，不显示 `0ms`；
- Agent 总耗时只来自 `agentRunSummary.durationMs`；
- 运行中 turn 未知时不显示 `0 / limit`；
- Limit 缺失时只显示可靠 used，或整项隐藏，不补默认值。

### 10.3 安全 fixture

构造包含以下字段的原始 Progress fixture：

```text
prompt
query
queryHash
path
pathSummary
arguments
input
output
reasoning
rawResponse
failureMessage
workerId
```

断言它们及其测试值均不出现在：

- `SafeTraceViewModel` 序列化结果；
- 页面 DOM；
- Tooltip；
- aria-label；
- 空状态、告警和错误提示。

### 10.4 响应式与可访问性

- `1440×1000`：Drawer 纵向 Trace 可读，运行配额默认折叠；
- 平板：长活动、数字和状态不产生文档级横向滚动；
- `390×844`：Drawer 全屏，Trace 单列，关闭和返回焦点可用；
- reduced-motion 下不新增依赖运动表达的状态；
- 键盘可打开阶段、展开运行配额并关闭 Drawer。

浏览器验收只使用本地安全 fixture 或 mock，不连接真实 Provider。

## 11. Tests and Verification

最小充分验证：

1. Safe ViewModel 纯函数测试：字段白名单、枚举、边界数字、未知值、深拷贝和敏感字段剔除；
2. Trace 作用域测试：`reviewKey + runId + claimAttempt`、接管、去重、聚合和轮询；
3. Drawer 信息架构测试：UI 只消费 Safe ViewModel，不解析 `detail / message`；
4. Standard、fallback、历史、损坏数据回归；
5. 运行全部前端 Node 测试：

```powershell
node.exe --test frontend/tests/*.test.mjs
```

6. 使用项目脚本执行 production build：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-frontend.ps1 build
```

7. 完成第 10 节桌面、平板、手机和安全 fixture 浏览器验收；
8. 执行 `git diff --check`；
9. 对前端改动执行禁止字段审计，确认 Drawer、ViewModel 和测试快照不含原始 detail、自由文本入口或事件时钟。

## 12. Authorization Boundary and Stop Point

Phase 2 实施只允许在 Phase 1 人工验收并获得明确授权后，修改第 9 节所列前端、测试和本计划文档。

出现以下任一情况必须停止并报告：

- 需要 Backend 新增事件时间、字段、接口或迁移；
- 现有数据无法可靠区分计划要求的活动类型或状态；
- 必须展示 query、path、工具参数、源码、Diff 或自由文本才能满足 UI；
- 需要改变 Finding、Review Card、fallback 或六阶段语义；
- Phase 1 信息架构或交互契约尚未通过人工验收。

Phase 2 完成顺序固定为：

```text
实现安全 ViewModel
  -> 自动化测试
  -> production build
  -> 安全 fixture 审计
  -> 桌面 / 平板 / 手机 Drawer 验收
  -> Standard / fallback / 历史兼容验收
  -> 回填本文件 Phase 2 实施状态与验证结果
  -> STOP
```

未经用户人工确认，不进入 Phase 3，不新增 typed evidence，不修改 Review Card / API / 持久化契约。
