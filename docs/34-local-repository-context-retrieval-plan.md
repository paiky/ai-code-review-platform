# 本地仓库上下文检索与高准确 AI Review 落地方案

## 状态

- 当前状态：V2-F-13 版本更新页收口已落地；任务 663 已验证本地 mirror / worktree 模式可用，任务 669 暴露出的“仓库已准备但 DTO / VO 字段变更尚未检索、前端角色流转解释不足”已先通过 V2-F-11 角色流转与 V2-F-12 缺口看板形成可解释和可聚合依据，并已在版本更新页对高准确模式主线做用户可读收口。当前停止等待用户验证；下一阶段进入 V2-F-14 DTO / VO 字段引用检索。
- 编写时间：2026-06-11
- 前置版本：
  - `docs/32-review-feedback-v2-mainline-roadmap.md`
  - `docs/33-review-learning-capability-roadmap.md`
- 当前决策：
  - “本地 clone / fetch + 引用搜索 + bounded Context Pack”的高准确 Review 模式已完成首轮生产验证。
  - 已补齐 workspace 清理与磁盘保护，避免长期运行时 `worktrees/` 和 `mirrors/` 无界增长。
  - 已通过 V2-F-11 增加高准确模式角色流转视图，解释 Planner、requested contexts、Retriever、Snippet 和预算裁剪之间的关系。
  - 已通过 V2-F-12 从 `CONTEXT_PACK_BUILT` progress 安全摘要聚合跨任务规则缺口，作为后续补齐 DTO / VO 字段引用检索等 Retriever 能力的优先级依据。
  - 已通过 V2-F-13 在版本更新页置顶说明高准确模式主线、部署注意和“不把完整项目源码交给模型”的边界。
  - 当前 Retriever 只支持 `METHOD_DELETED / METHOD_SIGNATURE_CHANGED`，DTO / VO 字段变更会进入 Planner 和 requested contexts，但不会触发本地引用搜索；后续扩展 DTO / VO 字段引用检索应以规则缺口看板数据作为优先级输入。
  - 反馈池、项目策略、上下文不足人工标记等“人工沉淀能力”先保留后端和数据结构，但在生产产品界面默认屏蔽，不作为当前验证主线。
  - 不删除 V0 到 V2-F-3 已落地能力；把它们作为可回退、可复用的治理底座。

## 一、核心结论

只看 diff 的 AI Review 适合作为低成本起点，但无法稳定判断很多真实风险：

- 删除方法是否仍有调用方。
- 方法签名变更是否影响调用方、接口实现或测试。
- DTO 字段变更是否影响 Controller、Mapper、前端或外部调用。
- DB / SQL / mapper 变更是否和 entity、schema、迁移脚本一致。
- 缓存写入 / 删除是否和读取、key 构造、过期策略一致。
- MQ topic / group / listener 配置是否和生产消费语义一致。
- 配置项变更是否有读取点、默认值和环境覆盖。

因此后续主线应从：

```text
diff-only review
```

升级为：

```text
GitLab webhook/API
  -> 本地仓库 mirror clone / fetch
  -> task worktree checkout
  -> Context Planner 决定需要什么证据
  -> Local Context Retriever 检索引用 / 调用方 / 相关片段
  -> Context Pack 控制预算后注入 AI Review
  -> progress / 前端展示检索摘要
```

注意：本地仓库检索不是把整个项目交给 AI，而是在本地允许更充分地搜索，再把有限、可解释、预算内的证据交给 AI。

## 二、与 docs/32 / docs/33 的关系

### 与 docs/32 的关系

`docs/32` 继续作为 V2 主线和已落地记录文档。V2-F-1 到 V2-F-3 已经完成：

- Context Pack V0。
- 同文件上下文片段。
- Context Planner 最小规则。

本文件接管 V2-F-3 后的后续实现细节：

```text
V2-F-4 起：本地仓库上下文检索 / 高准确 Review 模式
```

### 与 docs/33 的关系

`docs/33` 继续负责长期“Review 学习能力”蓝图，包括反馈自动归因、评估集、聚类、候选生成和灰度治理。

本文件聚焦单次 Review 的证据质量：

```text
本地仓库检索：解决模型看不到上下文的问题。
反馈学习治理：解决系统如何长期变准、可追溯、可评估的问题。
```

两者互补。当前本地检索已完成首轮生产验证，短期优先级调整为：

```text
先补齐高准确模式的本地 workspace 清理与磁盘保护
再恢复 / 简化 / 继续建设人工沉淀与自我学习治理
```

## 三、产品策略：人工沉淀能力先“熄灯”

当前已经完成的反馈池、项目策略、上下文不足反馈统计不建议直接删除。

推荐策略：

```text
保留后端能力
保留数据库表
保留 API
默认关闭前端入口
生产主界面不展示人工沉淀操作
```

### 需要屏蔽的前端入口

后续实施时应优先加开关，默认关闭这些产品入口：

- 顶部导航中的“反馈池”入口。
- 任务详情中的“提交反馈”入口。
- 反馈弹窗中的“建议沉淀为项目策略”入口。
- 反馈池中的“生成策略”操作。
- 反馈池中的“项目策略”tab。
- 设置页或其它页面中的项目策略管理入口。
- 上下文不足人工标记相关展示入口。

### 后端能力处理

后端不删除：

- `review_item_feedbacks`
- `project_review_policies`
- Review Feedback API
- Project Review Policy API
- Context Pack / Context Planner

可选新增后端开关：

```text
PROJECT_REVIEW_POLICY_INJECTION_ENABLED=false
REVIEW_LEARNING_API_ENABLED=true
```

说明：

- `PROJECT_REVIEW_POLICY_INJECTION_ENABLED=false` 用于生产验证高准确模式时避免项目策略影响 Review 结论。
- `REVIEW_LEARNING_API_ENABLED=true` 保留 API 兼容和后台调试能力。
- 前端展示由 `REVIEW_LEARNING_UI_ENABLED=false` 或等价前端配置控制。

## 四、总体架构

```text
GitLab MR / Push webhook
  -> 保存任务、changed files、diff text
  -> Context Planner 识别需要的上下文
  -> Local Repository Workspace Manager
       -> mirror clone / fetch
       -> checkout task worktree
  -> Local Context Retriever
       -> rg 引用搜索
       -> 截取 bounded snippets
       -> 生成 reference context
  -> Context Pack Builder
       -> 合并 changed files summary
       -> 合并 same-file snippets
       -> 合并 local reference snippets
       -> 控制总预算
  -> AI Review Provider
  -> 保存 result / progress
  -> 前端展示 AI Review 结果与检索摘要
```

### 角色定位

高准确模式中的几个名词不是同义词，而是流水线里的不同角色：

| 角色 | 任务中的定义 | 当前输入 | 当前输出 | 669 暴露的问题 |
|---|---|---|---|---|
| GitLab diff intake | 变更入口，负责保存 MR / Push 的 changed files 和 diff | webhook payload、GitLab API diff | changed files summary、diff text、任务元数据 | 已可用 |
| Context Pack Builder | 上下文打包器，把 diff、同文件片段、Planner 输出、本地检索摘要和不可用上下文合并进模型输入 | changed files、same-file snippets、planner、local reference | `reviewContext / contextPack` 和 `CONTEXT_PACK_BUILT` progress | 预算裁剪只显示 `truncated=true`，缺少裁剪明细 |
| Context Planner | 上下文规划器，基于 diff 的轻量规则判断“应该补什么证据” | changed file path、diff 新增 / 删除行、历史上下文不足统计 | `plannerSignals`、`requestedContexts`、planner unavailable contexts | 前端只展示数量，不展示信号类型和支持状态 |
| Local Repository Manager | 本地仓库准备器，维护 mirror 并为 task checkout worktree | project repository URL、task head ref | `localRepositoryContext`、`LOCAL_REPO_PREPARED / FAILED` progress | 已能解释仓库是否可用 |
| Local Context Retriever | 本地证据检索器，在 task worktree 内搜索引用并截取 bounded snippets | worktree、planner signals | `localReferenceSearch`、`localReferenceContext`、`LOCAL_CONTEXT_RETRIEVED / FAILED` progress | 只支持方法删除 / 签名变更，DTO / VO 字段变更尚未检索 |
| Budget Controller | 预算控制器，决定哪些证据可进入 Prompt，哪些被裁剪 | 完整 context pack 候选内容 | 裁剪后的 prompt text、`truncated` 标记 | 缺少“裁剪了什么”的安全摘要 |
| Provider Executor | 模型执行器，调用具体 AI Review provider | prompt、profile、provider config | raw output、provider progress | 已有 provider 请求 / 响应 / 解析事件 |
| Result Parser / Saver | 结果解析和落库角色 | provider output | structured findings、review result、FINISHED progress | 已可用 |

这些角色后续应在前端以独立 tab 展示，避免用户把“仓库已准备”“Planner 已命中”“Retriever 已执行”“Snippet 已注入”混成一个状态。

## 五、本地 clone / fetch 设计

### 工作目录

建议默认使用仓库 `.local/` 下的独立目录，方便本地开发和生产部署挂载：

```text
.local/review-workspaces/
  mirrors/
    {projectId}.git
  worktrees/
    {taskId}/
      head/
      base/
```

生产可通过环境变量改到持久化磁盘：

```text
LOCAL_REPO_CONTEXT_ENABLED=false
LOCAL_REPO_WORKSPACE_ROOT=/app/.local/review-workspaces
LOCAL_REPO_WORKSPACE_HOST_DIR=./review-workspaces
LOCAL_REPO_MAX_FETCH_SECONDS=120
LOCAL_REPO_MAX_SEARCH_SECONDS=30
LOCAL_REPO_CLEANUP_ENABLED=true
LOCAL_REPO_WORKTREE_RETENTION_HOURS=24
LOCAL_REPO_MIRROR_RETENTION_DAYS=30
```

### clone / fetch 流程

每个 GitLab 项目维护一个 mirror 缓存：

```text
mirrors/{projectId}.git
```

任务执行流程：

```text
1. 根据 project.git_project_id / repository_url 找到仓库。
2. 如果 mirror 不存在，执行 git clone --mirror。
3. 如果 mirror 已存在，执行 git fetch --prune。
4. 为当前 task 创建 detached worktree 到指定 commitSha / afterSha。
5. 如需要 base 侧上下文，再 checkout beforeSha / baseSha 到 base worktree。
6. Retriever 只在 worktree 内执行搜索。
7. 任务完成后可由后台清理策略异步清理过期 worktree；mirror 缓存保留并按闲置时间清理。
```

### 认证

优先复用 GitLab API 配置：

```text
GITLAB_BASE_URL
GITLAB_TOKEN
```

要求 token 至少具备：

```text
read_repository
```

Git HTTP clone / fetch 使用临时 Git env config 注入 Basic Auth header（`Authorization: Basic base64("oauth2:<token>")`），
不把 token 拼进 clone URL。日志与 progress 中不得输出 token、带 token 的 clone URL、Basic Auth base64 或完整认证头。

## 六、首期 Retriever 范围

首期只做最能验证效果的窄切片：

```text
METHOD_DELETED
METHOD_SIGNATURE_CHANGED
```

原因：

- diff-only 最容易误判删除方法和签名变更。
- 引用搜索可以直接给出是否仍有调用方。
- 不需要一开始引入复杂 AST / LSP。
- 可以用 `rg` 快速落地并在生产观察效果。

### 输入

来自 Context Planner：

```json
{
  "type": "METHOD_DELETED",
  "filePath": "src/main/java/demo/OrderService.java",
  "details": {
    "methodNames": ["cancelOrder"]
  },
  "requestedContextTypes": ["REFERENCE_SEARCH", "CALLER_CONTEXT"]
}
```

### 输出

Local Retriever 输出：

```json
{
  "type": "REFERENCE_SEARCH",
  "query": "cancelOrder",
  "filePath": "src/main/java/demo/OrderService.java",
  "matchedFileCount": 3,
  "includedSnippetCount": 5,
  "truncated": false,
  "snippets": [
    {
      "path": "src/main/java/demo/OrderController.java",
      "startLine": 41,
      "endLine": 71,
      "matchLine": 55,
      "reason": "METHOD_REFERENCE"
    }
  ]
}
```

progress 只能记录摘要，不记录源码片段：

```json
{
  "plannerSignalTypes": ["METHOD_DELETED"],
  "queryCount": 1,
  "matchedFileCount": 3,
  "includedSnippetCount": 5,
  "truncated": false
}
```

## 七、搜索策略

首期优先用 `rg`，不引入重型语义索引：

```text
rg --fixed-strings "cancelOrder" <worktree>
```

默认排除：

```text
.git/
node_modules/
dist/
build/
target/
.venv/
__pycache__/
.pytest_cache/
.codegraph/
```

后续可逐步增加：

- tree-sitter 方法边界识别。
- Java / Python / TypeScript 轻量符号解析。
- LSP / language server 索引。
- 项目内倒排索引。
- 向量检索或 RAG。

但首期不做这些。

## 八、Context Pack 预算

本地可以搜索很多，但注入 AI 的内容必须受预算限制。

建议首期默认：

```text
LOCAL_CONTEXT_MAX_QUERIES=8
LOCAL_CONTEXT_MAX_MATCHED_FILES_PER_QUERY=10
LOCAL_CONTEXT_MAX_SNIPPETS_PER_QUERY=6
LOCAL_CONTEXT_SNIPPET_CONTEXT_LINES=30
LOCAL_CONTEXT_MAX_SNIPPET_CHARS=3000
LOCAL_CONTEXT_MAX_TOTAL_CHARS=12000
```

超预算时：

- 优先保留 changed file 直接相关引用。
- 优先保留业务源码，降低测试、生成代码、配置示例优先级。
- 保留文件路径、命中行号、查询词和截断标记。
- 不把全部搜索结果塞进 Prompt。

## 九、排序与去噪

引用搜索结果应排序：

优先级高：

- 当前 changed file 同包 / 同模块。
- `src/main` 下业务源码。
- Controller / Service / Mapper / Repository 等关键调用链。
- 非测试代码中的调用方。

优先级低：

- `src/test`。
- generated / build / target / dist。
- 文档、注释、README。
- lock 文件、快照文件。
- 只在删除定义本身附近命中的结果。

首期可以用路径和文件名启发式排序，后续再引入符号级解析。

## 十、安全与运行边界

必须满足：

- 不在日志、progress、前端展示 token。
- 所有 worktree 路径必须解析后确认位于 `LOCAL_REPO_WORKSPACE_ROOT` 内。
- 清理 worktree 前必须校验绝对路径，避免误删。
- clone / fetch / search 必须有超时。
- 单项目 mirror 和单任务 worktree 必须有磁盘大小或保留周期策略。
- 失败不阻断 AI Review，降级为 diff-only + unavailable context。
- 不把检索失败解释为代码无风险。

## 十一、进度事件与前端可观测

新增 progress phase 建议：

```text
LOCAL_REPO_PREPARE_START
LOCAL_REPO_PREPARED
LOCAL_REPO_PREPARE_FAILED
LOCAL_CONTEXT_RETRIEVE_START
LOCAL_CONTEXT_RETRIEVED
LOCAL_CONTEXT_RETRIEVE_FAILED
```

detail 只记录：

- projectId
- taskId
- commitSha / ref 摘要
- clone/fetch/worktree 状态
- planner signal 数量
- 查询数量
- 命中文件数量
- 注入 snippet 数量
- unavailable 数量
- 是否超预算 / 截断

不记录：

- token
- clone URL 中的认证信息
- 大段源码
- 大段 diff

前端任务详情可以展示：

- 高准确模式是否启用。
- 本地仓库准备是否成功。
- 本地检索命中了哪些 signal。
- 找到了多少引用文件 / snippet。
- 哪些上下文仍不可用。

### 角色流转 tab 设计

任务详情页后续应在“代码质量 Review”中新增一个 tab，例如：

```text
AI Review 结果
高准确模式流转
执行过程
修复预览
```

“高准确模式流转”展示的是角色链路，不展示源码片段：

```text
变更接入
  -> Context Pack 构建
  -> Context Planner 规划
  -> 本地仓库准备
  -> Local Retriever 检索
  -> Budget Controller 裁剪
  -> Provider 执行
  -> 结果解析与落库
```

首版可以基于现有 progress 事件映射：

| 前端角色节点 | 可映射的已有事件 | 可展示内容 | 当前粒度缺口 |
|---|---|---|---|
| 变更接入 | 任务详情 / changed files summary | 触发类型、MR / Push、变更文件数、diff 来源 | 无单独 progress 事件 |
| Context Pack 构建 | `CONTEXT_PACK_BUILT` | changed file 数、diffBytes、promptLength、truncated、unavailableContextCount | 裁剪明细不足 |
| Context Planner 规划 | `CONTEXT_PACK_BUILT.detail.summary` 中的 planner 统计 | plannerSignalCount、requestedContextTypeCounts、plannerUnavailableContextCount | 缺少 signal type counts、supported / unsupported 分类 |
| 本地仓库准备 | `LOCAL_REPO_PREPARED / LOCAL_REPO_PREPARE_FAILED` | enabled、status、mirrorStatus、worktreeStatus、durationMs、cleanup 摘要 | 已基本足够 |
| Local Retriever 检索 | `LOCAL_CONTEXT_RETRIEVED / LOCAL_CONTEXT_RETRIEVE_FAILED` | queryCount、matchedFileCount、includedSnippetCount、truncated | 缺少“哪些 signal 被跳过以及原因” |
| Budget Controller 裁剪 | `CONTEXT_PACK_BUILT.meta.truncated` | 是否截断、promptLength、maxTotalChars | 缺少被裁剪对象计数 |
| Provider 执行 | `{PROVIDER}_REQUEST / HTTP_REQUEST_START / {PROVIDER}_RESPONSE` | provider、model、请求 / 响应状态、耗时 | 已有事件偏技术化 |
| 结果解析与落库 | `OUTPUT_EXTRACTED / JSON_PARSE_START / *_PARSE_RESULT / RESULT_SAVED / FINISHED` | findingCount、overallLevel、保存状态 | 已基本足够 |

V2-F-11 应补齐的后端安全摘要字段：

- `plannerSignalTypeCounts`：Planner 命中的信号类型计数。
- `retrieverSupportedSignalTypes`：当前 Retriever 支持的 signal 类型。
- `retrieverUnsupportedSignalTypeCounts`：命中但暂未支持检索的 signal 类型计数。
- `requestedContextAvailability`：requested context 的 available / unavailable 计数和原因类型。
- `budgetCutSummary`：裁剪对象计数，例如 local reference snippets、same-file snippets、changed files summary；不记录源码内容。
- `ruleGapSummary`：本次任务暴露的规则缺口摘要，例如“Planner 命中 DTO_FIELD_CHANGED，但 Retriever 暂未支持”。
- `ruleGapItems`：本次任务的规则缺口明细，只记录类型、signal、requested context、建议能力和优先级原因，不记录源码。

V2-F-11 不要求新增业务检索能力，只做可解释性和前端角色流转。所有新增 progress / summary 字段仍不得记录源码、token、认证头、本地绝对路径或大段 diff。

### 规则缺口定义

规则缺口不是代码风险，而是平台能力缺口。它用于告诉维护者：这次 Review 里哪些上下文“应该补”，但当前系统还不会补。

首版规则缺口类型：

| 类型 | 触发条件 | 示例 | 后续动作 |
|---|---|---|---|
| `UNSUPPORTED_PLANNER_SIGNAL` | Planner 命中 signal，但 Local Retriever 不支持该 signal | 任务 669 的 `DTO_FIELD_CHANGED` | 补对应 Retriever |
| `UNAVAILABLE_REQUESTED_CONTEXT` | Planner 请求了上下文，但系统没有对应获取能力 | `RELATED_FILE`、`CALLER_CONTEXT`、`TEST_RESULT_CONTEXT` | 评估是否补检索器、测试集成或仅保留提示 |
| `RETRIEVAL_FAILED` | Retriever 支持该 signal，但执行失败或超时 | `rg` 超时、worktree 不可用 | 排查稳定性或降级策略 |
| `BUDGET_CUT` | 已检索到证据，但 Context Pack 预算裁剪 | snippets 被裁剪 | 调整排序、预算或摘要压缩 |

前端“高准确模式流转”tab 中应有一个“规则缺口”区域：

- 展示本任务缺失的 Planner / Retriever 能力。
- 展示为什么本次 `引用查询数=0` 或 `snippet=0`。
- 展示建议补齐方向，例如 `DTO_FIELD_CHANGED -> DTO / VO 字段引用检索`。
- 明确这些是平台能力 backlog，不是本次代码风险。

沉淀策略：

- V2-F-11 只把规则缺口作为当前任务 progress / Context Pack summary 的安全摘要持久化，依托已有 `code_quality_review_progress_events`。
- V2-F-12 再做跨任务聚合 API / 看板，从已持久化的规则缺口摘要中统计高频缺口和建议优先级。

## 十二、分阶段落地计划

### V2-F-4：本地仓库检索主方案与前端人工沉淀熄灯

目标：

- 确认高准确模式成为 V2-F-3 后的短期主线。
- 新增本方案文档。
- 在 docs/32 / docs/33 重排路线。
- 后续实现时先屏蔽人工沉淀入口，保留后端能力。

范围：

- `docs/34-local-repository-context-retrieval-plan.md`
- `docs/32-review-feedback-v2-mainline-roadmap.md`
- `docs/33-review-learning-capability-roadmap.md`
- 后续编码阶段再改 `frontend/src/App.jsx` / `frontend/src/styles.css`

验收：

- 文档明确本地 clone / fetch / worktree / rg 搜索方案。
- 文档明确人工沉淀能力先产品熄灯。
- 文档明确每阶段停止等待用户验收。

### V2-F-5：本地仓库 mirror clone / fetch / worktree 最小闭环

目标：

让后端能基于 GitLab 项目和任务 commit 准备本地源码工作区。

范围建议：

- `backend-python/app/review_context/local_repo.py`
- `backend-python/app/review_context/service.py`
- `backend-python/app/core/config.py`
- 相关 tests
- docs/34 落地记录

验收：

- 可按 project repository URL 创建 mirror。
- 可 fetch 更新 mirror。
- 可为 task checkout head worktree。
- 失败时写入 unavailable context，不阻断 AI Review。
- progress 记录本地仓库准备摘要。
- token 不进入日志、progress 或模型输入。

### V2-F-6：METHOD_DELETED / METHOD_SIGNATURE_CHANGED 引用搜索 Retriever MVP

目标：

基于 V2-F-3 planner signal，在本地 worktree 用 `rg` 搜索删除方法和签名变更方法的引用。

范围建议：

- `backend-python/app/review_context/local_retriever.py`
- `backend-python/app/review_context/service.py`
- 相关 tests
- docs/34 落地记录

验收：

- 只对 `METHOD_DELETED / METHOD_SIGNATURE_CHANGED` 执行引用搜索。
- 搜索范围限制在当前 task worktree。
- 排除依赖和构建产物目录。
- 返回 bounded snippets。
- progress 只记录检索摘要。

### V2-F-7：本地引用证据注入 Context Pack

目标：

把本地引用搜索结果合并进 `reviewContext / contextPack`，让 AI Review 使用证据判断风险。

范围建议：

- `backend-python/app/review_context/*`
- `backend-python/app/code_quality/prompt.py`
- `backend-python/app/code_quality/service.py`
- 相关 tests
- docs/34 落地记录

验收：

- Context Pack 新增 `localReferenceContext` 或等价结构。
- Prompt 明确本地引用证据是辅助证据，不能覆盖硬风险。
- 总 Context Pack 预算仍受控。
- 缺失或失败的本地检索写入 `unavailableContexts`。

### V2-F-8：前端展示高准确模式证据摘要，并屏蔽人工沉淀入口

目标：

生产界面聚焦 AI Review 与高准确模式证据摘要，暂不展示人工沉淀能力。

范围建议：

- `frontend/src/App.jsx`
- `frontend/src/styles.css`
- 如需，后端 settings / config API
- docs/34 落地记录

验收：

- 默认隐藏反馈池入口。
- 默认隐藏任务详情提交反馈入口。
- 默认隐藏生成项目策略 / 项目策略管理入口。
- 任务详情展示本地检索摘要：是否启用、命中 signal、引用文件数、snippet 数、不可用上下文数。
- 前端 build 通过。

### V2-F-9：生产验证与效果复盘

目标：

用生产真实 MR / Push 验证高准确模式是否降低误判、是否引入明显性能和稳定性问题。

验收指标建议：

- 本地仓库准备成功率。
- 本地检索成功率。
- 平均 clone/fetch/search 耗时。
- Context Pack 截断率。
- AI Review 误判反馈变化。
- 用户主观评价。
- Provider 调用成本和耗时变化。

本阶段完成后再决定：

- 先补 V2-F-10 本地 workspace 清理与磁盘保护。
- 再决定是否继续扩展 DTO / DB / 缓存 / MQ / 配置检索。
- 再决定是否恢复部分反馈入口。
- 再决定是否进入 V3 评估集。

### V2-F-10：本地 workspace 清理与磁盘保护

目标：

让本地仓库上下文检索可长期灰度运行，避免 `worktrees/` 和 `mirrors/` 随 MR / Push 任务无界增长。

范围建议：

- `backend-python/app/review_context/local_repo.py`
- `backend-python/app/core/config.py`
- 如需新增轻量清理入口，可接入应用启动或 AI Review 任务结束后的 best-effort 清理
- 相关 unit tests
- README / docs/34 配置说明

验收：

- 新增配置项：
  - `LOCAL_REPO_WORKTREE_RETENTION_HOURS`，默认 24。
  - `LOCAL_REPO_MIRROR_RETENTION_DAYS`，默认 30。
  - `LOCAL_REPO_CLEANUP_ENABLED`，默认开启；AI Review 主流程中仅在本地仓库上下文启用时触发。
- 能安全清理超过 TTL 的 `worktrees/{taskId}`。
- 能按闲置时间清理长期未使用的 `mirrors/{projectId}.git`。
- 清理前必须解析绝对路径并确认目标位于 `LOCAL_REPO_WORKSPACE_ROOT` 内。
- 不删除当前正在准备或正在搜索的 task worktree。
- 清理失败不影响 AI Review 主流程。
- 清理进度只记录数量、大小、耗时和错误摘要，不记录源码、token 或 clone URL 凭据。
- 清理 mirror 后，后续同项目 MR 会重新 `git clone --mirror`，正确性不受影响，只增加首次准备耗时。

### V2-F-11：高准确模式角色流转可观测

目标：

让用户能看懂高准确模式里每个角色做了什么、哪些做成功了、哪些没有做、为什么没有做。重点解决任务 669 中“仓库已准备但引用查询数为 0 容易误解”的问题。

范围建议：

- `backend-python/app/review_context/service.py`
- `backend-python/app/code_quality/service.py`
- `frontend/src/App.jsx`
- `frontend/src/styles.css`
- 相关 contract / unit tests
- docs/34 落地记录

验收：

- 前端代码质量 Review 区域新增“高准确模式流转”tab 或等价视图。
- 用进度条 / Steps / Timeline 展示角色链路：变更接入、Context Pack、Planner、本地仓库、Retriever、预算裁剪、Provider、结果解析。
- 展示 Planner signal 类型计数、requested context 类型计数、available / unavailable 分类。
- 展示当前 Retriever 支持哪些 signal，以及本次哪些 signal 因暂未支持而跳过。
- 展示预算裁剪摘要：是否截断、最大预算、实际 promptLength、被裁剪对象计数。
- 展示本任务规则缺口：缺口类型、关联 signal / requested context、建议补齐能力和优先级原因。
- 继续隐藏源码片段、本地绝对路径、token、认证头和大段 diff。
- 不扩展新的业务 Retriever，不做 AST / LSP / RAG，不恢复人工沉淀入口。

### V2-F-12：规则缺口沉淀与优先级看板

目标：

把单次任务里的规则缺口沉淀成跨任务 backlog，让维护者能基于真实 Review 数据决定下一步补哪个 Planner / Retriever 能力，而不是只靠个案判断。

范围建议：

- `backend-python/app/review_context/*` 或新增轻量 query service
- `backend-python/app/code_quality/api.py` 或相关 API router
- `frontend/src/App.jsx`
- `frontend/src/styles.css`
- 相关 contract / unit tests
- docs/34 落地记录

验收：

- 能按时间范围、项目、项目组、端类型、Provider / Profile 聚合规则缺口。
- 至少展示：
  - 缺口类型分布。
  - Planner signal 类型分布。
  - unsupported signal 排名。
  - unavailable requested context 排名。
  - budget cut 次数和影响对象。
  - 关联任务数和最近任务。
- 给出建议补齐方向和优先级解释，例如：
  - `DTO_FIELD_CHANGED` 高频且 Retriever 不支持 -> 建议补 DTO / VO 字段引用检索。
  - `DB_SQL_MAPPER_CHANGED` 高频且缺 `DB_SCHEMA_CONTEXT` -> 建议设计 DB / Mapper / Entity 检索。
- 首版可复用 `code_quality_review_progress_events` 中的 `CONTEXT_PACK_BUILT.detail` 安全摘要进行聚合，不强制新增表；如查询性能不足，再新增汇总表。
- 不展示源码、本地绝对路径、token、认证头、大段 diff 或 provider raw output。
- 不自动改 Planner / Retriever 规则，不自动改 Prompt，不自动降级或隐藏 finding。

### V2-F-13：版本更新页收口

目标：

在 V2-F-11 角色流转可观测和 V2-F-12 规则缺口看板落地后，更新前端“版本更新”页面，把 V0 到 V2-F-12 的高准确模式主线整理成一个面向用户的版本说明。

范围建议：

- `frontend/src/releaseNotes.js`
- 如需样式微调：`frontend/src/styles.css`
- docs/34 落地记录

版本更新页内容边界：

- 只讲已经成为当前产品主线的高准确模式：
  - Context Pack。
  - Context Planner。
  - 本地仓库 mirror / worktree。
  - 本地引用检索和 bounded snippets。
  - workspace 清理与磁盘保护。
  - 高准确模式流转 tab。
  - 规则缺口沉淀与优先级看板。
- 不提已经默认隐藏的人工沉淀能力：
  - 不提误判标识。
  - 不提反馈池。
  - 不提“生成项目策略”。
  - 不提项目策略管理。
  - 不提上下文不足人工标记。
- 不把内部阶段号堆给普通用户；可在标题或 tag 中轻量保留“高准确模式”。
- 文案应强调“不会把完整项目源码交给模型”，而是本地检索后注入预算内证据。
- 补充部署注意：启用高准确模式需要 GitLab token 具备 `read_repository`，并配置本地 workspace 挂载 / 清理参数。

验收：

- 版本更新页新增一条置顶 release note。
- 前端 build 通过。
- 新增文案不暴露源码、token、内部仓库绝对路径或历史隐藏能力。
- 文案能让用户理解从 diff-only 到高准确模式的变化。

### V2-F-14：DTO / VO 字段引用检索 Retriever

目标：

补齐任务 669 这类 DTO / VO 字段变更的第一优先级检索能力，让 `DTO_FIELD_CHANGED / FIELD_DELETED` 能在 task worktree 内搜索字段引用，并把有限 snippets 注入 Context Pack。

范围建议：

- `backend-python/app/review_context/local_retriever.py`
- `backend-python/app/review_context/service.py`
- `backend-python/app/code_quality/prompt.py` 如需补充说明
- 相关 unit / contract tests
- docs/34 落地记录

验收：

- 支持 `DTO_FIELD_CHANGED / FIELD_DELETED` signal。
- 从 `details.fieldNames` 生成有限查询，例如字段名、getter、setter；查询数受 `LOCAL_CONTEXT_MAX_QUERIES` 控制。
- 搜索范围只限当前 task head worktree，并继续排除依赖、构建产物和缓存目录。
- 结果排序优先保留 Controller / Service / Mapper / Repository / DTO / VO / Excel VO / API 相关文件，降低测试、文档、生成代码优先级。
- snippet reason 区分为 `FIELD_REFERENCE` 或 `DTO_FIELD_REFERENCE`，避免和方法引用混淆。
- progress 只记录查询数、命中文件数、snippet 数、支持 / 跳过 signal 摘要，不记录源码。
- Prompt 明确字段引用 snippets 是有限证据，未命中不等同于无风险。

### V2-F-15：DB / Mapper / Entity 关联检索

目标：

在 DTO 字段引用检索验证稳定后，再补 DB / SQL / Mapper / Entity 相关证据检索，优先支持后端项目高频数据一致性风险。

范围建议：

- Mapper XML / SQL 文件和 Java Mapper / Repository / Entity 的关联搜索。
- SQL 字段、表名、实体字段、Mapper 方法名的有限查询。
- 不连接运行期数据库，不读取生产 schema；只基于当前 worktree 源码和迁移脚本。

完成后再评估是否继续缓存、MQ、配置检索。

## 十三、总控 Prompt

```text
请阅读 AGENTS.md、README.md、docs/32-review-feedback-v2-mainline-roadmap.md、docs/33-review-learning-capability-roadmap.md、docs/34-local-repository-context-retrieval-plan.md。

当前 V2-F-12 已完成，高准确本地仓库上下文检索模式已经具备 mirror clone / fetch、task worktree、METHOD_DELETED / METHOD_SIGNATURE_CHANGED 引用搜索、bounded snippets 注入 Context Pack、前端证据摘要展示、workspace 清理、高准确模式角色流转可观测和跨任务规则缺口看板。任务 669 暴露出的 Planner / Retriever / Snippet / 预算裁剪解释不足已先通过 V2-F-11 / V2-F-12 形成可解释与可聚合依据；DTO / VO 字段变更尚未触发本地检索的问题留到 V2-F-14。下一阶段只推进 V2-F-13：版本更新页收口。

同时，反馈池、项目策略、上下文不足人工标记等人工沉淀能力先保留后端和数据结构，但生产前端默认屏蔽入口；不要删除已实现能力，不要删表，不要破坏现有 API 兼容。

每次只推进一个阶段。当前优先按 docs/34 的 V2-F-13 做版本更新页收口，不扩展新的业务 Retriever。V2-F-13 验收后，再按用户确认进入 V2-F-14 DTO / VO 字段引用检索。不要修改 legacy Java backend；不要做全项目无限扫描；不要把整个项目源码塞进 Prompt；不要接向量库或复杂 RAG；不要自动降级或自动忽略 finding；不要自动改 Prompt。

每个阶段完成后必须停止，输出“改了什么、为什么、如何验证”，等待用户验证并明确回复“继续下一阶段”后再推进。
```

## 十四、分阶段落地 Prompt

### V2-F-5 Prompt：本地仓库 mirror clone / fetch / worktree 最小闭环

```text
请只落地 docs/34 的 V2-F-5：本地仓库 mirror clone / fetch / worktree 最小闭环。

范围：
- backend-python/app/review_context/local_repo.py
- backend-python/app/review_context/service.py 中必要接入
- backend-python/app/core/config.py 中必要配置
- 相关 tests
- docs/34 V2-F-5 落地记录

要求：
- 通过配置开关启用，默认关闭。
- 基于项目 repositoryUrl / GitLab 配置准备 mirror 仓库。
- 支持 fetch 更新。
- 支持为 task checkout head worktree。
- 所有路径必须限制在 LOCAL_REPO_WORKSPACE_ROOT 内。
- token 不得进入日志、progress、模型输入。
- clone/fetch/worktree 失败不阻断 AI Review，写入 unavailableContexts。
- 不做引用搜索，不注入源码片段。

完成后运行相关后端测试并停止。
```

### V2-F-6 Prompt：删除方法 / 签名变更引用搜索 Retriever MVP

```text
请只落地 docs/34 的 V2-F-6：METHOD_DELETED / METHOD_SIGNATURE_CHANGED 引用搜索 Retriever MVP。

范围：
- backend-python/app/review_context/local_retriever.py
- backend-python/app/review_context/local_repo.py 如需
- backend-python/app/review_context/service.py
- 相关 tests
- docs/34 V2-F-6 落地记录

要求：
- 只对 Context Planner 的 METHOD_DELETED / METHOD_SIGNATURE_CHANGED signal 执行本地引用搜索。
- 使用 rg 或等价快速搜索工具。
- 搜索必须限制在 task worktree 内。
- 避开依赖、构建产物和缓存目录。
- 输出 bounded snippets 和检索摘要。
- progress 只记录查询数、命中文件数、snippet 数、截断状态，不记录源码。
- 不做 AST / LSP / 向量库 / RAG。
- 不自动降级或忽略 finding。

完成后运行相关后端测试并停止。
```

### V2-F-7 Prompt：本地引用证据注入 Context Pack

```text
请只落地 docs/34 的 V2-F-7：本地引用证据注入 Context Pack。

范围：
- backend-python/app/review_context/*
- backend-python/app/code_quality/service.py
- backend-python/app/code_quality/prompt.py
- 相关 tests
- docs/34 V2-F-7 落地记录

要求：
- Context Pack 新增 localReferenceContext 或等价结构。
- 只注入预算内引用证据片段。
- 保留 requestedContexts 和 unavailableContexts。
- Prompt 说明本地引用证据只是辅助证据，不能覆盖安全、数据一致性、事务一致性、线上正确性硬风险。
- progress 不记录源码片段。
- 不做自动降级、不自动忽略 finding、不自动改 Prompt。

完成后运行相关后端测试并停止。
```

### V2-F-8 Prompt：前端高准确模式摘要与人工沉淀熄灯

```text
请只落地 docs/34 的 V2-F-8：前端展示高准确模式证据摘要，并屏蔽人工沉淀入口。

范围：
- frontend/src/App.jsx
- frontend/src/styles.css
- 如需，backend-python/app/code_quality/api.py 或 settings 相关接口
- docs/34 V2-F-8 落地记录

要求：
- 默认隐藏反馈池顶层入口。
- 默认隐藏任务详情提交反馈入口。
- 默认隐藏生成项目策略和项目策略管理入口。
- 不删除后端 API 和数据库表。
- 任务详情展示本地检索摘要：启用状态、仓库准备状态、planner signal 数、引用查询数、命中文件数、snippet 数、不可用上下文数。
- 前端文案聚焦“高准确模式 / 本地仓库上下文检索”，不突出人工学习闭环。

完成后运行前端 build，必要时运行相关后端测试，并停止。
```

### V2-F-9 Prompt：生产验证与复盘记录

```text
请只落地 docs/34 的 V2-F-9：生产验证与效果复盘记录。

范围：
- docs/34-local-repository-context-retrieval-plan.md
- README.md 如需补充部署配置
- docs/10-local-dev-pitfalls.md 如发现新坑

要求：
- 记录生产验证配置项。
- 记录验证指标：仓库准备成功率、检索成功率、耗时、截断率、误判反馈、用户评价。
- 给出是否继续扩展 DTO / DB / 缓存 / MQ / 配置检索的建议。
- 不编码。

完成后停止，等待用户确认下一阶段。
```

### V2-F-10 Prompt：本地 workspace 清理与磁盘保护

```text
请只落地 docs/34 的 V2-F-10：本地 workspace 清理与磁盘保护。

范围：
- backend-python/app/review_context/local_repo.py
- backend-python/app/core/config.py
- 相关 tests
- README.md
- docs/34 V2-F-10 落地记录

要求：
- 新增 worktree TTL 清理和 mirror 闲置清理配置。
- 默认清理过期 `worktrees/{taskId}`，mirror 只按较长闲置周期清理。
- 清理前必须校验绝对路径位于 LOCAL_REPO_WORKSPACE_ROOT 内，不允许删除 root 本身。
- 不删除当前 task 的 worktree，不影响正在执行的 AI Review。
- 清理失败不阻断 AI Review，只记录摘要。
- progress / 日志不记录源码、token、带凭据 URL 或认证头。
- 不扩展新的业务 Retriever，不做 AST / LSP / RAG，不恢复人工沉淀入口。

完成后运行相关后端测试并停止。
```

### V2-F-11 Prompt：高准确模式角色流转可观测

```text
请只落地 docs/34 的 V2-F-11：高准确模式角色流转可观测。

范围：
- backend-python/app/review_context/service.py
- backend-python/app/code_quality/service.py
- frontend/src/App.jsx
- frontend/src/styles.css
- 相关 tests
- docs/34 V2-F-11 落地记录

要求：
- 在任务详情的代码质量 Review 区域新增“高准确模式流转”tab 或等价视图。
- 用 Steps / Timeline 展示角色链路：变更接入、Context Pack、Planner、本地仓库、Retriever、预算裁剪、Provider、结果解析。
- 后端 progress / Context Pack summary 补安全摘要字段：planner signal 类型计数、Retriever 支持 signal 类型、本次未支持 signal 类型计数、requested context available/unavailable 分类、预算裁剪摘要、规则缺口摘要。
- 前端解释“仓库已准备但引用查询数为 0”的原因：没有支持的 signal、Retriever 被跳过、或检索失败。
- 前端展示本任务规则缺口：缺口类型、关联 signal / requested context、建议补齐能力和优先级原因。
- 不展示源码片段、本地绝对路径、token、认证头、大段 diff 或 provider raw output。
- 不扩展新的业务 Retriever，不做 DTO / DB / 缓存 / MQ / 配置检索。
- 不恢复人工沉淀入口，不修改 legacy Java backend。

完成后运行相关后端测试和前端 build，并停止。
```

### V2-F-12 Prompt：规则缺口沉淀与优先级看板

```text
请只落地 docs/34 的 V2-F-12：规则缺口沉淀与优先级看板。

范围：
- backend-python/app/review_context/* 或新增轻量 query service
- backend-python/app/code_quality/api.py 或相关 API router
- frontend/src/App.jsx
- frontend/src/styles.css
- 相关 tests
- docs/34 V2-F-12 落地记录

要求：
- 基于 V2-F-11 已写入 progress / Context Pack summary 的 ruleGapSummary / ruleGapItems 做跨任务聚合。
- 支持按时间范围、项目、项目组、端类型、Provider / Profile 聚合。
- 展示缺口类型分布、Planner signal 分布、unsupported signal 排名、unavailable requested context 排名、budget cut 次数、关联任务数和最近任务。
- 给出建议补齐方向和优先级解释，但不自动改规则。
- 首版可复用 code_quality_review_progress_events；如查询性能不足，再设计汇总表。
- 不展示源码、本地绝对路径、token、认证头、大段 diff 或 provider raw output。
- 不扩展业务 Retriever，不做 DTO / DB / 缓存 / MQ / 配置检索。
- 不自动改 Prompt，不自动降级、不自动忽略 finding。

完成后运行相关后端测试和前端 build，并停止。
```

### V2-F-13 Prompt：版本更新页收口

```text
请只落地 docs/34 的 V2-F-13：版本更新页收口。

前置条件：
- V2-F-11 高准确模式角色流转可观测已完成并验收。
- V2-F-12 规则缺口沉淀与优先级看板已完成并验收。

范围：
- frontend/src/releaseNotes.js
- frontend/src/styles.css 如需
- docs/34 V2-F-13 落地记录

要求：
- 在版本更新页新增一条置顶 release note，面向用户说明高准确模式从 diff-only 升级为本地仓库上下文检索。
- 文案聚焦当前产品主线：Context Pack、Context Planner、本地 mirror / worktree、本地引用检索、bounded snippets、workspace 清理、高准确模式流转 tab、规则缺口看板。
- 不提已经默认隐藏的人工沉淀能力：误判标识、反馈池、生成项目策略、项目策略管理、上下文不足人工标记。
- 不堆内部阶段号，不写源码、token、本地绝对路径或大段内部实现。
- 明确说明不会把完整项目源码交给模型，而是本地检索后注入预算内证据。
- 补充部署注意：启用高准确模式需要 GitLab token 具备 read_repository，并配置 workspace 挂载和清理参数。

完成后运行前端 build，并停止。
```

### V2-F-14 Prompt：DTO / VO 字段引用检索 Retriever

```text
请只落地 docs/34 的 V2-F-14：DTO / VO 字段引用检索 Retriever。

范围：
- backend-python/app/review_context/local_retriever.py
- backend-python/app/review_context/service.py
- backend-python/app/code_quality/prompt.py 如需
- 相关 tests
- docs/34 V2-F-14 落地记录

要求：
- 支持 Context Planner 的 DTO_FIELD_CHANGED / FIELD_DELETED signal。
- 从 details.fieldNames 生成有限查询，至少包含字段名，可按语言习惯补 getter / setter 查询；所有查询总数受 LOCAL_CONTEXT_MAX_QUERIES 控制。
- 搜索必须限制在当前 task head worktree 内，并继续避开依赖、构建产物和缓存目录。
- 输出 bounded snippets，snippet reason 使用 FIELD_REFERENCE / DTO_FIELD_REFERENCE。
- 结果排序优先 Controller / Service / Mapper / Repository / DTO / VO / Excel VO / API 相关文件，降低测试、文档、生成代码优先级。
- progress 只记录摘要：查询数、命中文件数、snippet 数、支持 signal 类型、跳过 signal 类型和截断状态；不记录源码。
- Prompt 说明字段引用 snippets 是有限证据，未命中不等同于无风险。
- 不做 AST / LSP / RAG，不自动降级、不自动忽略 finding。

完成后运行相关后端测试并停止。
```

### V2-F-15 Prompt：DB / Mapper / Entity 关联检索设计

```text
请只设计 docs/34 的 V2-F-15：DB / Mapper / Entity 关联检索。

要求：
- 先输出设计，不编码。
- 说明如何从 DB_SQL_MAPPER_CHANGED signal 提取表名、字段名、Mapper 方法名和 Entity 字段名。
- 说明如何限制搜索范围、排序结果、控制预算和脱敏 progress。
- 不连接运行期数据库，不读取生产 schema。
- 不做缓存、MQ、配置检索。

完成后停止，等待用户确认是否进入实现。
```

## 十五、Agent 授权边界

Agent 可自主推进：

- 新增本地仓库 workspace manager。
- 新增本地引用搜索 retriever。
- 新增 bounded Context Pack 结构。
- 新增 progress 摘要事件。
- 新增高准确模式角色流转 tab 和安全可解释性摘要。
- 新增规则缺口摘要和跨任务优先级看板。
- 扩展 DTO / VO 字段引用检索 Retriever。
- 新增配置开关。
- 新增前端高准确模式摘要展示。
- 默认隐藏人工沉淀相关前端入口。
- 更新 docs/32、docs/33、docs/34、README 和相关 tests。

Agent 不可自主推进：

- 不删除反馈池、项目策略、上下文不足反馈相关后端代码、表或 API。
- 不修改 legacy Java backend。
- 不做全项目无限制扫描。
- 不把整个项目源码注入 Prompt。
- 不接向量库或复杂 RAG。
- 不做自动风险降级。
- 不自动忽略 finding。
- 不自动改 Prompt。
- 不跨项目共享策略或源码上下文。
- 不在日志、progress、前端或模型输入中暴露 token。
- 不执行未校验路径的递归删除。

## 十六、每阶段停止规则

每个阶段完成后必须停止，并等待用户验证。

只有用户明确回复“继续下一阶段”后，才进入下一阶段。

如果某阶段发现本地 clone / fetch 在生产环境权限、磁盘、网络或 GitLab token 上不可行，应先记录阻塞和替代方案，不要绕过安全边界继续做无限制扫描。

## 十七、V2-F-5 落地记录

落地时间：2026-06-11。

已完成：

- 新增 `backend-python/app/review_context/local_repo.py`，负责本地仓库 workspace 管理。
- 新增配置项：
  - `LOCAL_REPO_CONTEXT_ENABLED=false`
  - `LOCAL_REPO_WORKSPACE_ROOT=.local/review-workspaces`
  - `LOCAL_REPO_MAX_FETCH_SECONDS=120`
- 本地仓库能力默认关闭；关闭时只在 Context Pack 中记录最小 `DISABLED` 状态，不增加 unavailable context。
- 开启后基于项目 `repositoryUrl` 准备 `mirrors/{projectId}.git` mirror 仓库；如果 mirror 已存在，执行 `git fetch --prune` 更新。
- 支持为当前 task 的 head commit/ref checkout detached worktree 到 `worktrees/{taskId}/head`。
- 所有 mirror / worktree 路径均由 `LOCAL_REPO_WORKSPACE_ROOT` 派生，并在解析绝对路径后校验不能逃逸 root。
- GitLab token 通过 Git 临时 env config 注入为 Basic Auth header，不写入 clone URL、命令参数、progress 或模型输入；失败原因会做 URL 凭据、PRIVATE-TOKEN、Authorization 和 Basic Auth base64 脱敏。
- clone / fetch / worktree 失败不会阻断 AI Review，会写入 `unavailableContexts` 的 `LOCAL_REPOSITORY` 项，并在 progress 中记录 `LOCAL_REPO_PREPARE_FAILED` 摘要。
- 成功准备时 progress 记录 `LOCAL_REPO_PREPARED` 摘要；`CONTEXT_PACK_BUILT` 继续只记录 meta / summary，不记录源码片段。
- Context Pack 新增 `localRepositoryContext`，只包含启用状态、准备状态、短 ref、mirror/worktree 状态、耗时和 `sourceIncluded=false`。

明确未做：

- 不做引用搜索。
- 不读取 related files。
- 不读取 worktree 源码片段。
- 不接向量库 / RAG。
- 不自动降级。
- 不自动忽略 finding。
- 不自动改 Prompt。
- 不删除反馈池、项目策略、上下文不足反馈相关后端代码、表或 API。
- 不修改 legacy Java backend。

新增和调整文件 / 测试：

- `backend-python/tests/unit/test_local_repo_context.py`
- `backend-python/tests/unit/test_review_context_pack.py`
- `backend-python/tests/contract/test_code_quality_api_contract.py`
- `backend-python/tests/conftest.py`

已验证：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_local_repo_context.py tests\unit\test_review_context_pack.py tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_prepares_local_repo_context_without_leaking_token tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_includes_same_file_context_snippets
```

结果：14 passed。

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_local_repo_context.py tests\unit\test_review_context_pack.py tests\unit\test_code_quality_prompt.py tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_prepares_local_repo_context_without_leaking_token tests\contract\test_code_quality_api_contract.py::test_manual_review_injects_project_review_policies_and_records_progress tests\contract\test_code_quality_api_contract.py::test_deepseek_manual_review_saves_result_and_progress tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_uses_saved_changed_files tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_includes_same_file_context_snippets
```

结果：23 passed。

下一阶段建议：

```text
V2-F-6 已完成；如继续增强 V2-F，下一阶段进入 V2-F-7：本地引用证据注入 Context Pack。
```

## 十八、V2-F-6 落地记录

落地时间：2026-06-11。

已完成：

- 新增 `backend-python/app/review_context/local_retriever.py`，作为本地引用搜索 Retriever MVP。
- 只处理 Context Planner 输出的 `METHOD_DELETED / METHOD_SIGNATURE_CHANGED` signal，并只使用 `details.methodNames` 生成查询。
- 使用 `rg --json --fixed-strings` 执行引用搜索；搜索 cwd 固定为当前 task 的 head worktree，匹配结果再做路径校验，确保不会读取 worktree 外文件。
- 搜索默认排除 `.git/`、`node_modules/`、`dist/`、`build/`、`target/`、`.venv/`、`__pycache__/`、`.pytest_cache/`、`.codegraph/`，并在解析结果时二次过滤这些目录。
- Retriever 输出 bounded snippets：限制查询数、单查询命中文件数、单查询 snippet 数、snippet 上下文行、单 snippet 字符数和总字符数。
- `backend-python/app/review_context/local_repo.py` 新增 `task_head_worktree_path`，供 service 在不暴露本地路径的前提下解析 task head worktree。
- `backend-python/app/review_context/service.py` 在本地仓库 `PREPARED` 后调用 Retriever，并把 `localReferenceSearch` 检索摘要放入 Context Pack；本阶段不把引用源码 snippets 注入 provider prompt，完整证据注入留到 V2-F-7。
- `backend-python/app/code_quality/service.py` 新增 `LOCAL_CONTEXT_RETRIEVED / LOCAL_CONTEXT_RETRIEVE_FAILED` progress 事件；detail 只记录 `queryCount / matchedFileCount / includedSnippetCount / truncated`，不记录源码、查询片段、本地路径或 token。
- 本阶段不做 AST / LSP / 向量库 / RAG，不自动降级，不自动忽略 finding，不删除反馈池、项目策略、上下文不足反馈相关后端代码、表或 API，不修改 legacy Java backend。

新增和调整测试：

- `backend-python/tests/unit/test_local_retriever.py`
- `backend-python/tests/unit/test_review_context_pack.py`
- `backend-python/tests/contract/test_code_quality_api_contract.py`

已验证：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_local_retriever.py tests\unit\test_review_context_pack.py
```

结果：13 passed。

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_prepares_local_repo_context_without_leaking_token tests\contract\test_code_quality_api_contract.py::test_manual_review_records_local_reference_search_progress_without_source tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_includes_same_file_context_snippets
```

结果：4 passed。

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_local_repo_context.py tests\unit\test_local_retriever.py tests\unit\test_review_context_pack.py tests\unit\test_code_quality_prompt.py tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_prepares_local_repo_context_without_leaking_token tests\contract\test_code_quality_api_contract.py::test_manual_review_records_local_reference_search_progress_without_source tests\contract\test_code_quality_api_contract.py::test_manual_review_injects_project_review_policies_and_records_progress tests\contract\test_code_quality_api_contract.py::test_deepseek_manual_review_saves_result_and_progress tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_uses_saved_changed_files tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_includes_same_file_context_snippets
```

结果：30 passed。

下一阶段建议：

```text
V2-F-7 已完成；如继续增强 V2-F，下一阶段进入 V2-F-8：前端展示高准确模式证据摘要，并屏蔽人工沉淀入口。
```

## 十九、V2-F-7 落地记录

落地时间：2026-06-11。

已完成：

- `reviewContext / contextPack` 新增 `localReferenceContext`，注入 V2-F-6 检索到的本地引用 bounded snippets。
- 保留 `localReferenceSearch` 作为轻量检索摘要；`localReferenceContext` 承载 `status / sourceIncluded / summary / searches / snippets`。
- 本地引用证据只来自当前 task head worktree；不读取 worktree 外文件，不注入完整项目源码。
- Context Pack 总预算继续受 `CONTEXT_PACK_MAX_TOTAL_CHARS` 控制；超预算时优先裁剪本地引用 snippets，并同步 `includedSnippetCount / truncated / sourceIncluded`。
- `requestedContexts` 和 `unavailableContexts` 继续保留；当本地引用 snippets 已注入时，`REFERENCE_SEARCH` 标记为可用，`CALLER_CONTEXT` 仍不等同于完整调用方分析。
- Prompt 新增约束：本地引用证据只表示当前 task worktree 中检索到的有限引用片段，不能仅凭未命中引用判定无风险，也不能覆盖安全、数据一致性、事务一致性或线上正确性硬风险。
- `CONTEXT_PACK_BUILT` progress 仍只记录 meta / summary，不记录源码片段；`LOCAL_CONTEXT_RETRIEVED` detail 仍只记录 `queryCount / matchedFileCount / includedSnippetCount / truncated`。
- 本阶段不做 AST / LSP / 向量库 / RAG，不自动降级，不自动忽略 finding，不自动改 Prompt，不删除反馈池、项目策略、上下文不足反馈相关后端代码、表或 API，不修改 legacy Java backend。

新增和调整测试：

- `backend-python/tests/unit/test_review_context_pack.py`
- `backend-python/tests/unit/test_code_quality_prompt.py`
- `backend-python/tests/contract/test_code_quality_api_contract.py`
- `backend-python/tests/unit/test_local_retriever.py`

已验证：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_local_retriever.py tests\unit\test_review_context_pack.py tests\unit\test_code_quality_prompt.py
```

结果：20 passed。

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_prepares_local_repo_context_without_leaking_token tests\contract\test_code_quality_api_contract.py::test_manual_review_records_local_reference_search_progress_without_source tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_includes_same_file_context_snippets
```

结果：4 passed。

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_local_repo_context.py tests\unit\test_local_retriever.py tests\unit\test_review_context_pack.py tests\unit\test_code_quality_prompt.py tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_prepares_local_repo_context_without_leaking_token tests\contract\test_code_quality_api_contract.py::test_manual_review_records_local_reference_search_progress_without_source tests\contract\test_code_quality_api_contract.py::test_manual_review_injects_project_review_policies_and_records_progress tests\contract\test_code_quality_api_contract.py::test_deepseek_manual_review_saves_result_and_progress tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_uses_saved_changed_files tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_includes_same_file_context_snippets
```

结果：31 passed。

下一阶段建议：

```text
当前停止等待用户验收 V2-F-7；如继续增强 V2-F，下一阶段进入 V2-F-8：前端展示高准确模式证据摘要，并屏蔽人工沉淀入口。
```

## 二十、V2-F-8 落地记录

落地时间：2026-06-12。

已完成：

- 前端新增默认关闭的人工沉淀 UI 开关：`VITE_REVIEW_LEARNING_UI_ENABLED` 默认不启用，顶部导航不再展示“反馈池”入口，直接访问 `/risk-feedback` 会回到任务页。
- 前端新增独立项目策略 UI 开关：`VITE_PROJECT_REVIEW_POLICY_UI_ENABLED` 默认不启用；即使后续恢复反馈查看，也不会默认恢复“生成策略”和“项目策略”管理入口。
- 任务详情中的提醒项和 AI finding 默认不再展示“提交反馈”控件；反馈弹窗、上下文不足人工标记和“建议沉淀”入口不会出现在默认生产界面。
- 后端 Review Feedback API、Project Review Policy API、`review_item_feedbacks` 和 `project_review_policies` 表均未删除，相关后端代码保持兼容。
- 代码质量 Review 详情新增“高准确模式 · 本地仓库上下文检索”摘要卡片，直接从已有 progress 中读取：
  - 启用状态。
  - 仓库准备状态。
  - Planner Signal 数。
  - 引用查询数。
  - 命中文件数。
  - Snippet 数。
  - 不可用上下文数。
  - 检索预算是否截断。
- 执行过程补充本地仓库上下文检索相关 phase 的中文文案：`CONTEXT_PACK_BUILT`、`LOCAL_REPO_PREPARED`、`LOCAL_REPO_PREPARE_FAILED`、`LOCAL_CONTEXT_RETRIEVED`、`LOCAL_CONTEXT_RETRIEVE_FAILED`。
- 前端文案聚焦“高准确模式 / 本地仓库上下文检索”，不突出人工学习闭环。

明确未做：

- 不修改 Python 后端 API、数据库表或 schema。
- 不删除反馈池、项目策略、上下文不足反馈相关后端代码、表或 API。
- 不做 AST / LSP / 向量库 / RAG。
- 不自动降级或忽略 finding。
- 不修改 legacy Java backend。

已验证：

```powershell
.\scripts\run-frontend.cmd build
```

结果：build passed；仅保留既有 Vite chunk size warning。

下一阶段建议：

```text
V2-F-8 已落地；下一阶段进入 V2-F-9：生产验证与效果复盘。
```

## 二十一、V2-F-9 验收记录

验收时间：2026-06-12。

已确认：

- 用户已完成 V2-F-9 生产验证与效果复盘验收。
- 任务 `663` 已验证本地仓库模式可用：
  - `LOCAL_REPO_CONTEXT_ENABLED=true`。
  - `LOCAL_REPO_PREPARED` 已记录。
  - `localRepositoryStatus=PREPARED`。
  - `mirrorStatus=CLONED/FETCHED`。
  - `worktreeStatus=CHECKED_OUT`。
  - `worktrees/663/head` checkout 到任务 head commit。
- Docker Compose 模板已支持 workspace 挂载：
  - `${LOCAL_REPO_WORKSPACE_HOST_DIR:-./review-workspaces}:/app/.local/review-workspaces`
  - `LOCAL_REPO_WORKSPACE_ROOT=/app/.local/review-workspaces`

验证结论：

- 当前高准确模式的本地 clone / fetch / worktree 主链路可以进入生产灰度。
- 任务 `663` 未注入本地引用 snippets 是当前 Retriever 范围导致：首期只对 `METHOD_DELETED / METHOD_SIGNATURE_CHANGED` 执行引用搜索；该任务主要是常量、VO 字段、Excel 字段和参数组装逻辑变更。
- 当前还没有自动清理 `worktrees/` 和长期闲置 `mirrors/` 的实现，长期生产运行前应先补 V2-F-10。

下一阶段建议：

```text
V2-F-10：本地 workspace 清理与磁盘保护。
```

## 二十二、V2-F-10 落地记录

落地时间：2026-06-12。

已完成：

- 新增本地仓库 workspace 清理配置：
  - `LOCAL_REPO_CLEANUP_ENABLED=true`
  - `LOCAL_REPO_WORKTREE_RETENTION_HOURS=24`
  - `LOCAL_REPO_MIRROR_RETENTION_DAYS=30`
- 启用本地仓库上下文时，`prepare_local_repository_context` 会执行 best-effort 清理摘要：
  - 清理超过 TTL 的 `worktrees/{taskId}` 目录。
  - 按较长闲置周期清理 `mirrors/{projectId}.git`。
  - 跳过当前 task worktree 和当前项目 mirror。
- 清理前复用并加强绝对路径校验：目标必须解析到 `LOCAL_REPO_WORKSPACE_ROOT` 内，且不会删除 workspace root、`worktrees/` 根目录或 `mirrors/` 根目录。
- 清理和 mirror / worktree 准备使用相同的本地锁 key，遇到正在准备的 worktree 或 mirror 会跳过，不强行删除。
- 清理失败不会阻断 AI Review；清理摘要只保留启用状态、保留周期、扫描数量、删除数量、跳过数量、删除字节数、耗时和脱敏错误摘要。
- 清理摘要不记录源码、token、带凭据 URL、认证头或本地绝对路径。
- 清理摘要进入既有本地仓库 progress summary，不新增业务 Retriever 或新的执行阶段。
- mirror 成功 clone / fetch 后会刷新 mirror 目录 mtime，后续按闲置时间判断是否可清理。

明确未做：

- 不扩展新的业务 Retriever。
- 不做 AST / LSP / 向量库 / RAG。
- 不恢复人工沉淀前端入口。
- 不删除反馈池、项目策略、上下文不足反馈相关后端代码、表或 API。
- 不修改 legacy Java backend。

新增和调整测试：

- `backend-python/tests/unit/test_local_repo_context.py`
- `backend-python/tests/unit/test_review_context_pack.py`
- `backend-python/tests/conftest.py`

已验证：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_local_repo_context.py
```

结果：8 passed。

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_local_repo_context.py tests\unit\test_local_retriever.py tests\unit\test_review_context_pack.py tests\unit\test_code_quality_prompt.py tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_prepares_local_repo_context_without_leaking_token tests\contract\test_code_quality_api_contract.py::test_manual_review_records_local_reference_search_progress_without_source tests\contract\test_code_quality_api_contract.py::test_manual_review_injects_project_review_policies_and_records_progress tests\contract\test_code_quality_api_contract.py::test_deepseek_manual_review_saves_result_and_progress tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_uses_saved_changed_files tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_includes_same_file_context_snippets
```

结果：35 passed。

停止规则：

```text
V2-F-10 已完成；当前停止等待用户验证，不继续推进 V3 评估集或更多 Retriever。
```

## 二十三、V2-F-10 后续规划调整

调整时间：2026-06-12。

背景：

- 任务 669 的本地仓库准备成功，`mirrorStatus=FETCHED`、`worktreeStatus=CHECKED_OUT`。
- Planner 命中 DTO / VO 字段变更相关 signal，但当前 Local Retriever 只支持 `METHOD_DELETED / METHOD_SIGNATURE_CHANGED`。
- 因此任务 669 出现 `Planner Signal 数 > 0` 但 `引用查询数 = 0`，前端摘要不足以解释“哪些角色已执行、哪些被跳过、为什么跳过”。

调整结论：

```text
V2-F-11：高准确模式角色流转可观测（已完成）
  -> 先补前端 tab 和后端安全摘要字段，解释 Planner / Retriever / Snippet / 预算裁剪的角色和执行结果
  -> 展示当前任务规则缺口，例如 Planner 命中但 Retriever 暂不支持的 signal
  -> 不扩展业务 Retriever

V2-F-12：规则缺口沉淀与优先级看板（已完成）
  -> 聚合跨任务规则缺口，形成补齐 Planner / Retriever 能力的优先级依据
  -> 不自动改规则，不自动改 Prompt

V2-F-13：版本更新页收口
  -> 在版本更新页集中说明高准确模式主线
  -> 不提已默认隐藏的误判标识、反馈池、生成项目策略、项目策略管理或上下文不足人工标记

V2-F-14：DTO / VO 字段引用检索 Retriever
  -> 再支持 DTO_FIELD_CHANGED / FIELD_DELETED 的字段引用搜索
  -> 覆盖任务 669 这类真实 DTO / VO 字段变更场景

V2-F-15：DB / Mapper / Entity 关联检索设计
  -> 等 DTO Retriever 验证后再设计，不直接编码
```

停止规则：

```text
V2-F-12 已完成后，下一阶段只推进 V2-F-13。V2-F-13 完成后必须停止，等待用户验证并明确确认继续后，才进入 V2-F-14。
```

## 二十四、V2-F-11 落地记录

落地时间：2026-06-12。

已完成：

- `CONTEXT_PACK_BUILT` progress summary 新增高准确模式安全摘要字段：
  - `plannerSignalTypeCounts`
  - `retrieverSupportedSignalTypes`
  - `retrieverUnsupportedSignalTypeCounts`
  - `requestedContextAvailability`
  - `budgetCutSummary`
  - `ruleGapSummary`
  - `ruleGapItems`
- `ruleGapItems` 只记录缺口类型、signal、requested context、建议能力和优先级原因，不记录源码片段、本地绝对路径、token、认证头、大段 diff 或 provider raw output。
- progress detail 生成时做 compact JSON 和主动限长，避免依赖数据库层 4000 字符截断导致前端无法解析。
- 任务详情的代码质量 Review 区域新增“高准确模式流转”子页，按角色展示：
  - 变更接入
  - Context Pack
  - Planner
  - 本地仓库
  - Retriever
  - 预算裁剪
  - Provider
  - 结果解析
- “高准确模式流转”展示 Planner / Retriever 摘要、requested context 可用性、预算裁剪摘要和本任务规则缺口。
- 当本地仓库已准备但引用查询数为 `0` 时，前端会解释原因：
  - 没有 Retriever 当前支持的 signal。
  - Retriever 被跳过。
  - Retriever 检索失败或不可用。
- 多模型 Review 下，每个模型 tab 内展示对应 `reviewKey` 的高准确模式流转和执行过程。
- README 补充任务详情页中高准确模式流转视图说明。

明确未做：

- 不扩展 DTO / DB / 缓存 / MQ / 配置 Retriever。
- 不新增 DTO / VO 字段引用检索。
- 不做 AST / LSP / RAG。
- 不自动降级、不自动忽略 finding、不自动改 Prompt。
- 不恢复反馈池 / 人工沉淀入口。
- 不修改 legacy Java backend。

新增和调整测试：

- `backend-python/tests/unit/test_review_context_pack.py`
- `backend-python/tests/contract/test_code_quality_api_contract.py`
- `frontend/src/App.jsx`
- `README.md`

已验证：

```powershell
$env:NO_PAUSE='1'; .\scripts\run-backend.cmd test tests\unit\test_review_context_pack.py tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_records_local_reference_search_progress_without_source
```

结果：11 passed。

```powershell
$env:NO_PAUSE='1'; .\scripts\run-backend.cmd test tests\unit\test_local_repo_context.py tests\unit\test_local_retriever.py tests\unit\test_review_context_pack.py tests\unit\test_code_quality_prompt.py tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_prepares_local_repo_context_without_leaking_token tests\contract\test_code_quality_api_contract.py::test_manual_review_records_local_reference_search_progress_without_source tests\contract\test_code_quality_api_contract.py::test_manual_review_injects_project_review_policies_and_records_progress tests\contract\test_code_quality_api_contract.py::test_deepseek_manual_review_saves_result_and_progress tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_uses_saved_changed_files tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_includes_same_file_context_snippets
```

结果：35 passed。

```powershell
.\scripts\run-frontend.cmd build
```

结果：build passed；仅保留既有 Vite chunk size warning。

停止规则：

```text
V2-F-11 已完成；当前停止等待用户验证，不继续推进 V2-F-12。
```

## 二十五、V2-F-12 落地记录

落地时间：2026-06-13。

已完成：

- 新增只读聚合接口 `GET /api/code-quality-reviews/rule-gaps`，从已有 `code_quality_review_progress_events` 中的 `CONTEXT_PACK_BUILT` detail 读取 `ruleGapItems / ruleGapSummary`。
- 支持筛选：
  - `projectId`
  - `gapType`
  - `signal`
  - `recentDays`
  - `limit`
- 聚合维度和返回字段包含：
  - `gapType`
  - `signal`
  - `requestedContext`
  - `suggestedCapability`
  - 出现次数
  - 影响项目数 / 任务数 / review 数
  - 最近出现时间
  - 影响项目摘要
  - 最近任务样例，包含 `projectId / projectName / taskId / reviewKey`
- 聚合逻辑只按白名单字段重组输出，不透传 progress 原始 detail。
- 历史 progress detail 为空、被截断或 JSON 不可解析时会跳过，并在接口 `summary` 中返回 `skippedEventCount / parseFailedEventCount`，不影响其它聚合结果。
- 新增前端顶栏“规则缺口”入口，展示跨任务规则缺口聚合列表。
- 看板支持按项目、缺口类型、Signal、最近天数和 limit 筛选。
- 看板可查看最近任务样例，并跳转到任务详情；多模型样例会携带 `reviewKey`。
- 任务详情“高准确模式流转”的“本任务规则缺口”卡片增加“查看看板”入口。
- README 补充规则缺口看板接口示例和前端入口说明。

安全边界：

- 不新增 DB 表，不新增迁移。
- 不读取源码，不返回源码片段。
- 不返回本地绝对路径、token、认证头、大段 diff 或 provider raw output。
- 不扩展 DTO / DB / 缓存 / MQ / 配置 Retriever。
- 不做 DTO / VO 字段引用检索。
- 不做 AST / LSP / RAG。
- 不自动改规则、不自动改 Prompt。
- 不自动降级、不自动忽略 finding。
- 不恢复反馈池 / 人工沉淀入口。
- 不修改 legacy Java backend。

新增和调整测试：

- `backend-python/app/code_quality/rule_gap_dashboard.py`
- `backend-python/app/code_quality/api.py`
- `backend-python/app/code_quality/service.py`
- `backend-python/tests/contract/test_code_quality_rule_gaps_api_contract.py`
- `frontend/src/App.jsx`
- `frontend/src/styles.css`
- `README.md`
- `docs/32-review-feedback-v2-mainline-roadmap.md`
- `docs/33-review-learning-capability-roadmap.md`
- `docs/34-local-repository-context-retrieval-plan.md`

已验证：

```powershell
$env:NO_PAUSE='1'; .\scripts\run-backend.cmd test tests\contract\test_code_quality_rule_gaps_api_contract.py
```

结果：4 passed。

```powershell
$env:NO_PAUSE='1'; .\scripts\run-backend.cmd test tests\contract\test_code_quality_rule_gaps_api_contract.py tests\unit\test_review_context_pack.py tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_records_local_reference_search_progress_without_source
```

结果：15 passed。

```powershell
.\scripts\run-frontend.cmd build
```

结果：build passed；仅保留既有 Vite chunk size warning。

停止规则：

```text
V2-F-12 已完成；当前停止等待用户验证，不继续推进 V2-F-13。
```

## 二十六、V2-F-13 落地记录

落地时间：2026-06-13。

已完成：

- 前端“版本更新”页面新增置顶 release note：`v0.16.0 高准确模式：本地仓库上下文检索与规则缺口看板`。
- 文案面向用户说明代码质量 Review 已从 diff-only 审查升级为高准确模式。
- 版本说明聚焦当前产品主线：
  - Context Pack。
  - Context Planner。
  - 本地 mirror / worktree。
  - 本地引用检索。
  - bounded snippets。
  - workspace 清理与磁盘保护。
  - 高准确模式流转 tab。
  - 规则缺口看板。
- 明确说明不会把完整项目源码交给模型，而是在本地检索后只注入排序后、预算内的证据片段。
- 补充部署注意：启用高准确模式需要 GitLab token 具备 `read_repository` 权限，并配置 workspace 挂载、worktree 保留时间和 mirror 保留周期。
- docs/32、docs/33、docs/34 当前状态已同步到 V2-F-13 完成，下一阶段为 V2-F-14 DTO / VO 字段引用检索。

明确未做：

- 不扩展 DTO / VO 字段引用检索 Retriever。
- 不扩展 DB / 缓存 / MQ / 配置 Retriever。
- 不做 AST / LSP / RAG。
- 不自动改规则、不自动改 Prompt。
- 不自动降级、不自动忽略 finding。
- 不恢复反馈池 / 人工沉淀入口。
- 不修改 legacy Java backend。

新增和调整文件：

- `frontend/src/releaseNotes.js`
- `docs/32-review-feedback-v2-mainline-roadmap.md`
- `docs/33-review-learning-capability-roadmap.md`
- `docs/34-local-repository-context-retrieval-plan.md`

已验证：

```powershell
.\scripts\run-frontend.cmd build
```

结果：build passed；仅保留既有 Vite chunk size warning。

停止规则：

```text
V2-F-13 已完成；当前停止等待用户验证，不继续推进 V2-F-14。
```
