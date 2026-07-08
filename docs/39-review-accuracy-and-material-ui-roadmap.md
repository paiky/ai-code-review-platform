# Review 准确率与 Material 3 前端后续推进计划

## 状态

- 当前状态：阶段 2 源码检索能力升级已落地，等待用户验证；后续阶段必须逐阶段推进。
- 关联文档：
  - `docs/36-review-platform-current-roadmap.md`：近期总控入口。
  - `docs/37-review-platform-target-product-roadmap.md`：完整产品目标。
  - `docs/38-review-lifecycle-and-frontend-entrypoints.md`：Review 生命周期和前端入口。
- 本文用途：把后续“源码检索能力、Context Pack 裁剪、质量治理页面收敛、Material Design 3 前端重构”拆成可逐个交给 Agent 落地的阶段。

## 总体原则

后续不把整个仓库源码直接塞给模型，而是让平台在服务器侧维护 Git mirror / task worktree，由后端按 diff 定向检索相关证据，再把预算内证据和未注入证据摘要写入 Context Pack。

推进优先级：

```text
源码工作区可靠性
  -> 源码索引与关系检索
  -> Context Pack 证据排序与裁剪
  -> 质量治理入口收敛
  -> Material Design 3 / MUI 分阶段迁移
```

每个阶段完成后必须停止，输出“改了什么、为什么、如何验证”，等待用户验证并确认“继续下一阶段”后再推进。

## 进度记录规则

- 每个阶段完成后必须在本文“阶段落地记录”中追加一条记录。
- 记录必须包含：完成日期、阶段、改了什么、为什么、如何验证、遗留风险、下一阶段。
- 若阶段包含代码改动，同步更新 `docs/36-review-platform-current-roadmap.md` 的近期落地记录。
- 记录完成后再输出最终说明；不得只在对话中说明而不落文档。

## 阶段落地记录

### 2026-07-08：阶段 1 源码工作区可靠性与可观测性

- 改了什么：补充安全的源码工作区诊断摘要，覆盖 mirror / worktree 存在状态、脱敏 remote URL、最近拉取 / 检出时间、清理策略和清理结果；任务详情高准确模式展示这些诊断。
- 为什么：用户在本地和远程 Docker 目录中看到 `review-workspaces` 为空，需要在任务级 progress 中直接区分未启用、clone / fetch 失败、checkout 失败、worktree 已清理和 Retriever 未命中。
- 如何验证：运行 `tests/unit/test_local_repo_context.py`、`tests/unit/test_review_context_pack.py`、相关 `test_code_quality_api_contract.py` 用例，以及 `scripts/run-frontend.cmd build`。
- 遗留风险：尚未升级源码关系检索，仍以现有 `rg` 兜底和局部规则检索为主。
- 下一阶段：阶段 2 源码检索能力升级。

### 2026-07-08：阶段 2 源码检索能力升级

- 改了什么：新增 `EvidenceCandidate / EvidenceRelation / EvidencePriority / EvidenceSource / EvidenceBudgetHint` 内部证据模型；Local Retriever 增加受控 worktree 内 Java / XML 轻量源码索引，输出方法 caller / callee、interface implementation、Controller -> Service、Service -> Mapper、MyBatis namespace / id、DTO / field reference 关系证据；继续保留 `rg` snippets 兜底。
- 为什么：只依赖 diff 和字符串 snippets 时，远程 Review 很难知道“谁调用了变更方法、接口实现在哪里、Mapper XML 对应哪个方法、字段在哪里被访问”，容易把上下文不足误判为没有风险或高置信风险。
- 如何验证：运行 `tests/unit/test_local_retriever.py`、`tests/unit/test_review_context_pack.py`、`tests/unit/test_local_repo_context.py` 和相关 `test_code_quality_api_contract.py` 用例。
- 遗留风险：当前源码索引是正则启发式，不是 AST / LSP；完整 evidence-first 排序、分层预算和 prompt 注入控制放到阶段 3。
- 下一阶段：阶段 3 Context Pack 裁剪规则升级；未经用户确认不继续推进。

## 阶段 1：源码工作区可靠性与可观测性

目标：

- 保持 `git clone --mirror + git worktree add` 架构。
- 明确 mirror 是项目级源码缓存，worktree 是 task 级临时 checkout。
- 在高准确模式流转中区分未启用、clone / fetch 失败、worktree checkout 失败、task worktree 已清理、Retriever 未命中。
- 不新增业务 Retriever，不改变 AI Review 结论。

产出：

- `CONTEXT_PACK_BUILT` 和 `LOCAL_REPO_PREPARED / LOCAL_REPO_PREPARE_FAILED` progress 增加安全源码工作区摘要。
- 前端“高准确模式”展示 mirror / worktree 存在状态、远程 URL 脱敏摘要、最近拉取 / 检出时间、清理策略和清理结果。
- README 补充推荐保留策略：worktree 72 小时、mirror 180 天。

验收：

- local repo disabled / clone failed / worktree missing / prepared 均有可区分摘要。
- progress、前端和测试输出不包含 GitLab token、本地绝对路径或源码片段。

## 阶段 2：源码检索能力升级

目标：

- 新增统一内部证据模型：`EvidenceCandidate / EvidenceRelation / EvidencePriority / EvidenceSource / EvidenceBudgetHint`。
- Local Retriever 从“signal -> rg query -> snippets”升级为“源码索引 / 关系检索 + rg 兜底”。
- 第一轮优先覆盖 Java / Spring / MyBatis 的通用高收益关系。

首批能力：

- 方法 caller / callee。
- interface -> implementation。
- Controller -> Service -> Mapper。
- MyBatis XML `namespace / id` 与 Mapper 方法关联。
- DTO 字段 getter / setter / 直接字段引用。

边界：

- 不一次性做万能调用链。
- MQ、配置、跨端 API、测试覆盖继续按 evaluation cases 和验收记录进入后续单项 Retriever 循环。

## 阶段 3：Context Pack 裁剪规则升级

目标：

- 从按顺序删片段升级为证据候选评分和分层预算。
- 增加高优先级证据保底配额。
- 被裁剪的高优先级证据必须进入 `notInjectedEvidence`。

分层：

- 必保层：diff、变更文件摘要、直接变更符号。
- 高优先级层：caller / callee、接口实现、DB / Mapper、缓存 / 配置 / MQ 证据。
- 辅助层：测试、历史反馈、项目策略、低相关 snippets。
- 摘要层：未注入证据只保留安全摘要和路径计数。

新增预算审计摘要：

```text
candidateCount
selectedCount
summaryOnlyCount
droppedCount
protectedCandidateCount
highPriorityDroppedCount
```

## 阶段 4：质量治理页面收敛

目标：

- 顶部默认只突出“质量看板”和“评估样本”。
- 规则缺口、验收记录、回放记录保留直接路由，但降级为高级诊断入口。
- 反馈池继续由 feature flag 控制，默认隐藏。

页面定位：

- 质量看板：判断 Review 质量问题集中在哪里。
- 评估样本：沉淀人工真值和误判 / 漏报 / 上下文不足样本。
- 规则缺口：解释上下文为什么不足，不作为唯一实现优先级来源。
- 验收记录：记录能力改动准入和退出。
- 回放记录：对比 baseline / candidate。

## 阶段 5：Material Design 3 / MUI 前端重构

目标：

- 新增 MUI / Emotion 依赖。
- 新增 MUI App Shell、主题和 light / dark color schemes。
- 分阶段迁移页面，不一次性替换全部 Ant Design。

迁移顺序：

```text
质量看板和评估样本
  -> 任务列表和任务详情主框架
  -> 设置页和版本更新页
```

设计要求：

- 优先使用 MUI 组件，不自造复杂视觉系统。
- Material 3 风格圆角、surface、outline、按钮、输入框和状态层。
- Gemini 式 AI 产品感：留白充足、输入框突出、卡片轻量、交互克制。
- 不做传统后台模板。
- hover / focus / disabled 状态必须覆盖。
- 支持响应式和暗色模式。

## 总控 Prompt

```text
请阅读 AGENTS.md、README.md、docs/36-review-platform-current-roadmap.md、docs/37-review-platform-target-product-roadmap.md、docs/38-review-lifecycle-and-frontend-entrypoints.md、docs/39-review-accuracy-and-material-ui-roadmap.md。

当前后续推进以 docs/39 为本轮准确率和前端体验专项路线，以 docs/36 为近期总控入口。每次只推进 docs/39 的一个阶段。允许修改 backend-python、frontend、docs、examples、tests 中与当前阶段直接相关的文件；不要修改 legacy Java backend；不要做自动 Prompt 改写、自动风险降级、自动忽略 finding、模型微调、复杂 RAG、跨项目策略共享或无限制全项目扫描。

阶段完成后必须停止，输出“改了什么、为什么、如何验证”，等待用户验证并明确回复“继续下一阶段”后再推进。
```

## 阶段 1 Prompt

```text
请只落地 docs/39 的阶段 1：源码工作区可靠性与可观测性。

目标：
- 保持 git clone --mirror + git worktree add 架构。
- 补充本地源码缓存状态诊断：mirror 是否存在、最近 fetch 时间、remote URL 脱敏摘要；worktree 是否存在、当前 task checkout 状态、失败阶段；cleanup 配置和最近清理结果。
- 在任务详情“高准确模式流转”中明确区分 LOCAL_REPO_CONTEXT_ENABLED=false、clone/fetch 失败、worktree checkout 失败、task worktree 已清理、Retriever 未命中。
- README / 部署文档补充推荐配置：LOCAL_REPO_CONTEXT_ENABLED=true、LOCAL_REPO_WORKTREE_RETENTION_HOURS=72、LOCAL_REPO_MIRROR_RETENTION_DAYS=180。
- 不新增业务 Retriever，不改变 Review 结论。

完成后运行相关 Python 单元 / 契约测试和前端 build，并停止等待验证。
```

## 阶段 2 Prompt

```text
请只落地 docs/39 的阶段 2：源码检索能力升级。

目标：
- 新增统一内部证据模型。
- 在 Local Retriever 中加入 Java / Spring / MyBatis 源码索引和关系检索层，保留 rg 兜底。
- 第一轮只覆盖方法 caller / callee、interface implementation、Controller -> Service -> Mapper、MyBatis namespace / id 和 DTO 字段引用。
- 不实现 MQ、配置、跨端 API、测试覆盖或万能调用链。

完成后补单元测试，并停止等待验证。
```

## 阶段 3 Prompt

```text
请只落地 docs/39 的阶段 3：Context Pack 裁剪规则升级。

目标：
- 用证据候选评分和分层预算替换单纯按顺序删除片段。
- 增加高优先级 signal、caller / callee 和直接证据保底。
- progress 增加预算审计摘要。
- 保持 notInjectedEvidence 脱敏和 Prompt 约束。

完成后补 Context Pack 单元测试，并停止等待验证。
```

## 阶段 4 Prompt

```text
请只落地 docs/39 的阶段 4：质量治理页面收敛。

目标：
- 顶部质量治理默认只展示质量看板和评估样本。
- 规则缺口、验收记录、回放记录保留直接路由，并从质量看板 / 评估样本 / 规则缺口推荐进入。
- 更新 docs/38 的生命周期说明。

完成后运行前端 build，并停止等待验证。
```

## 阶段 5 Prompt

```text
请只落地 docs/39 的阶段 5 第一小步：Material Design 3 / MUI 前端基础设施。

目标：
- 新增 MUI / Emotion 依赖。
- 增加 MUI ThemeProvider、CssBaseline、light / dark color schemes 和 App Shell 基础。
- 不一次性迁移所有页面；优先让质量看板和评估样本可以在新布局中运行。
- 新页面优先使用 MUI 组件，旧 Ant Design 页面允许短期共存。

完成后运行前端 build，并停止等待验证。
```
