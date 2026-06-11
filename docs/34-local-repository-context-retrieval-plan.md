# 本地仓库上下文检索与高准确 AI Review 落地方案

## 状态

- 当前状态：V2-F-5 本地仓库 mirror clone / fetch / worktree 最小闭环已落地并通过相关后端测试；当前停止等待用户验收。
- 编写时间：2026-06-11
- 前置版本：
  - `docs/32-review-feedback-v2-mainline-roadmap.md`
  - `docs/33-review-learning-capability-roadmap.md`
- 当前决策：
  - 优先验证“本地 clone / fetch + 引用搜索 + bounded Context Pack”的高准确 Review 模式。
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

两者互补，但当前生产验证优先级调整为：

```text
先验证高准确本地检索 Review 效果
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
LOCAL_REPO_WORKSPACE_ROOT=.local/review-workspaces
LOCAL_REPO_MAX_FETCH_SECONDS=120
LOCAL_REPO_MAX_SEARCH_SECONDS=30
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
7. 任务完成后清理 worktree；mirror 缓存保留。
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

日志与 progress 中不得输出 token、带 token 的 clone URL 或完整认证头。

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

- 是否继续扩展 DTO / DB / 缓存 / MQ / 配置检索。
- 是否恢复部分反馈入口。
- 是否进入 V3 评估集。

## 十三、总控 Prompt

```text
请阅读 AGENTS.md、README.md、docs/32-review-feedback-v2-mainline-roadmap.md、docs/33-review-learning-capability-roadmap.md、docs/34-local-repository-context-retrieval-plan.md。

当前 V0 到 V2-F-3 已落地。后续短期主线调整为高准确本地仓库上下文检索模式：基于 GitLab webhook / API 保存的任务信息，在后端本地 mirror clone / fetch 仓库，为任务 checkout worktree，再按 Context Planner 的 requestedContexts 做 bounded 引用搜索和源码片段检索，最后注入 Context Pack 给 AI Review。

同时，反馈池、项目策略、上下文不足人工标记等人工沉淀能力先保留后端和数据结构，但生产前端默认屏蔽入口；不要删除已实现能力，不要删表，不要破坏现有 API 兼容。

每次只推进一个阶段。优先按 docs/34 的 V2-F-5 到 V2-F-9 分阶段落地。不要修改 legacy Java backend；不要做全项目无限扫描；不要把整个项目源码塞进 Prompt；不要接向量库或复杂 RAG；不要自动降级或自动忽略 finding；不要自动改 Prompt。

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

## 十五、Agent 授权边界

Agent 可自主推进：

- 新增本地仓库 workspace manager。
- 新增本地引用搜索 retriever。
- 新增 bounded Context Pack 结构。
- 新增 progress 摘要事件。
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
- GitLab token 通过 Git 临时 env config 注入，不写入 clone URL、命令参数、progress 或模型输入；失败原因会做 URL 凭据、PRIVATE-TOKEN、Authorization 脱敏。
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

新增和调整测试：

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
当前停止等待用户验收 V2-F-5；如继续增强 V2-F，下一阶段进入 V2-F-6：METHOD_DELETED / METHOD_SIGNATURE_CHANGED 引用搜索 Retriever MVP。
```
