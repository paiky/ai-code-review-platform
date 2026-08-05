# Review 准确率与 Material 3 前端后续推进计划

## 状态

- 当前状态：阶段 5.6 设置页和版本更新页 MUI 迁移已落地，阶段 5 Material Design 3 / MUI 分阶段迁移完成，等待用户验证；后续阶段必须逐阶段推进。
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

### 2026-07-09：阶段 3 Context Pack 裁剪规则升级

- 改了什么：Context Pack 在 Local Retriever 的 `evidenceCandidates` 之上新增候选评分、`selectedEvidence` 安全摘要、分层预算策略和 `budgetAuditSummary`；保留 diff、变更文件摘要和已有直接 snippets 的优先级，caller / callee 关系证据优先各保留 1 条；未注入的高优先级候选进入 `notInjectedEvidence`，只暴露 `safeSummary`、相对路径、关系和计数，不暴露源码片段。
- 为什么：阶段 2 已能产生关系证据候选，但如果仍按顺序删除 snippets，预算紧张时会丢掉最关键的 caller / callee、接口实现、Controller -> Service、Service -> Mapper、DB / Mapper 和缓存证据，模型也无法区分“未命中”和“已命中但未注入”。
- 如何验证：运行 `tests/unit/test_local_retriever.py`、`tests/unit/test_review_context_pack.py`、`tests/unit/test_code_quality_prompt.py`，并补跑 `test_code_quality_api_contract.py` 中 Context Pack / Local Reference / retry same-file context 相关 contract 用例。
- 遗留风险：候选评分仍是启发式和固定配额，不是 AST / LSP 级精确调用图；MQ、配置、跨端 API、测试覆盖 Retriever 仍未实现；预算极端紧张时仍可能只保留摘要而非源码片段。
- 下一阶段：阶段 4 质量治理页面收敛；未经用户确认不继续推进。

### 2026-07-09：阶段 4 质量治理页面收敛

- 改了什么：顶部“质量治理”下拉统一承载质量看板、评估样本、规则缺口、验收记录和回放记录；`/rule-gaps`、`/acceptance-gates`、`/evaluation-runs` 直接路由和页面能力继续保留；质量治理页面页头不再散落跨页导航按钮；反馈池继续只在 `VITE_REVIEW_LEARNING_UI_ENABLED=true` 时展示。
- 为什么：质量治理入口过度分散会让页面页头和下拉框职责重叠；统一由顶部“质量治理”下拉承担导航，页面页头只保留本页必要操作。
- 如何验证：运行 `scripts/run-frontend.cmd build`；打开顶部“质量治理”确认可进入“质量看板 / 评估样本 / 规则缺口 / 验收记录 / 回放记录”；直接访问 `/rule-gaps`、`/acceptance-gates`、`/evaluation-runs` 确认仍可用；质量治理各页面页头不再出现跨页导航按钮。
- 遗留风险：本阶段只调整入口层级和文档，不做 Material 3 / MUI 迁移，不重构现有 Ant Design 页面，也不改变后端 API 或历史数据。
- 下一阶段：阶段 5 Material Design 3 / MUI 前端重构第一小步；未经用户确认不继续推进。

### 2026-07-09：阶段 5 第一小步 Material Design 3 / MUI 前端基础设施

- 改了什么：新增 `@mui/material`、`@emotion/react`、`@emotion/styled` 依赖；新增 `MuiAppShell`，在 React 根节点接入 MUI `ThemeProvider` 和 `CssBaseline`；新增 MUI 主题文件，提供 light / dark color schemes、基础 palette、shape、typography 和少量组件默认值；旧 Ant Design 页面继续原样运行。
- 为什么：先建立 MUI / Emotion 和主题基础，让后续质量看板、评估样本等页面可以逐步迁移到 Material Design 3 风格，而不是一次性替换全部前端。
- 如何验证：运行 `scripts/run-frontend.cmd build`；确认前端能在 MUI ThemeProvider + CssBaseline + Ant Design reset 共存下完成生产构建。
- 遗留风险：本阶段只接入基础设施，没有迁移质量看板和评估样本页面；暗色方案目前随系统偏好生效，尚未提供用户可见主题切换；bundle 体积因新增 MUI 依赖继续触发 Vite 大 chunk 警告。
- 下一阶段：阶段 5 后续小步迁移质量看板和评估样本到 MUI 布局；未经用户确认不继续推进。

### 2026-07-09：阶段 5.2 质量看板 MUI 布局迁移

- 改了什么：只迁移“质量看板”页面的页面壳、页头、筛选区、指标卡、治理摘要区和规则缺口归因摘要容器到 MUI；质量维度表格继续使用现有 Ant Design Table；按浏览器反馈收敛为后台密度布局，修正浅色背景上的低对比文字和过大的顶部按钮；页头改为左侧标题说明、右侧仅保留本页刷新操作；主题主色从绿色改为蓝 / 粉系，指标卡改为白底多色强调线；MUI 主题先固定为 light palette，避免 Ant Design 与 MUI 共存阶段受系统暗色偏好影响；数据请求、过滤参数和 `/api/review-quality/dashboard` 契约保持不变。
- 为什么：阶段 5.1 只接入了基础设施，用户在页面上感知不到明显变化；阶段 5.2 让质量治理主入口先呈现 Material 3 风格的 surface、outline、按钮、输入框、状态区和响应式指标布局，同时避免一次性迁移复杂表格带来回归。
- 如何验证：运行 `scripts/run-frontend.cmd build`；确认质量看板仍能按项目、Provider、Profile、风险类型和 verdict 过滤；规则缺口、验收记录和回放记录统一从顶部“质量治理”下拉进入。
- 遗留风险：Ant Design Table、Tag 和 Spin 仍与 MUI 外壳共存；未做真实浏览器截图验证；暗色模式已暂停，后续需要在全站 MUI 迁移更完整后再做产品化主题切换；bundle 体积继续触发 Vite 大 chunk 警告。
- 下一阶段：阶段 5.3 评估样本 MUI 布局迁移；未经用户确认不继续推进。

### 2026-07-09：阶段 5.3 评估样本 MUI 布局迁移

- 改了什么：迁移“评估样本”页面的页面壳、页头、筛选区和规则缺口归因弹窗到 MUI；页头沿用左侧标题说明，右侧不放跨页导航按钮；筛选控件改为 MUI TextField / Select / Button；样本列表和 Rule Gap 摘要表继续使用 Ant Design Table；`/api/evaluation-cases` 和 `/api/evaluation-cases/{caseId}/rule-gap-attribution` 契约保持不变。
- 为什么：评估样本是质量治理主入口之一，需要与质量看板保持一致的后台密度、可扫描布局和操作区位置，同时避免重写宽表和归因业务逻辑。
- 如何验证：运行 `scripts/run-frontend.cmd build`；确认评估样本仍可按项目、Provider、Profile、风险类型和 verdict 查询，任务跳转、编辑归因、保存归因和高级诊断入口不回归。
- 遗留风险：样本主表、任务链接、Tag、Empty 和 Rule Gap 摘要表仍与 MUI 外壳共存；未做真实浏览器截图验证；暗色模式仍暂停；bundle 体积继续触发 Vite 大 chunk 警告。
- 下一阶段：阶段 5.4 质量治理高级诊断统一壳；未经用户确认不继续推进。

### 2026-07-09：阶段 5.4 质量治理高级诊断统一壳

- 改了什么：新增统一 MUI 高级诊断页壳，规则缺口诊断、验收记录、验收详情、回放记录和回放详情统一使用“高级诊断”标签、左侧标题说明、右侧仅放本页必要操作、直接路由说明和 MUI surface；筛选容器和列表容器改为 MUI Paper；复杂统计图、Tabs、宽表、详情 Descriptions、创建 / 编辑验收记录 Modal 和后端 API 保持不变。
- 为什么：规则缺口、验收记录和回放记录需要视觉定位一致，同时跨页导航统一回到顶部“质量治理”下拉框，避免页头按钮和顶部下拉重复。
- 如何验证：运行 `scripts/run-frontend.cmd build`；确认 `/rule-gaps`、`/acceptance-gates`、`/acceptance-gates/{gateId}`、`/evaluation-runs`、`/evaluation-runs/{runId}` 直接路由仍可访问，筛选、刷新、详情跳转和创建 / 编辑验收记录不回归。
- 遗留风险：高级诊断页内部仍有 Ant Design Table、Tabs、Card、Descriptions、Modal 与 MUI 壳共存；未做真实浏览器截图验证；暗色模式仍暂停；bundle 体积继续触发 Vite 大 chunk 警告。
- 下一阶段：阶段 5.5 任务列表和任务详情主框架；未经用户确认不继续推进。

### 2026-07-10：阶段 5.5 任务列表和任务详情主框架 MUI 迁移

- 改了什么：新增任务页统一 MUI 外层壳，任务列表页头、筛选 surface 和表格容器迁移到 MUI；任务详情页头、返回 / 重新执行 / 复制重跑操作区、概要信息 surface 和 Tabs 外层容器迁移到 MUI；任务列表筛选、分页、Ant Design Table、任务详情 Tabs 内部内容、Diff viewer、Patch 预览、AI Review finding 展示、`reviewKey` 直达和轮询逻辑保持不变。
- 为什么：任务列表和任务详情是普通开发与 Reviewer 的日常主入口，需要与质量治理页面一样具备清晰的 Material 3 surface、outline 和紧凑后台布局，同时避免一次性重写复杂 Review 内容造成行为回归。
- 如何验证：运行 `scripts/run-frontend.cmd build`；确认 `/tasks`、`/tasks/{taskId}` 和 `/tasks/{taskId}?reviewKey=...` 路由仍可访问，任务列表筛选 / 分页、详情 tab 切换、重新执行审阅、复制为新任务重跑、AI Review 轮询、高准确模式流转和确定性检查入口不回归。
- 遗留风险：任务详情内部复杂 Ant Design Tabs 内容、Descriptions、Table、Diff / Patch 代码视图、finding 展开区和设置类弹窗仍未迁移；本阶段未做真实浏览器截图验证；暗色模式仍暂停；bundle 体积继续触发 Vite 大 chunk 警告。
- 下一阶段：阶段 5.6 设置页和版本更新页；未经用户确认不继续推进。

### 2026-07-10：阶段 5.6 设置页和版本更新页 MUI 迁移

- 改了什么：复用统一 MUI 后台页面壳，设置页页头、刷新操作和 Collapse 外层容器迁移到 MUI；版本更新页页头和时间线外层容器迁移到 MUI，并把原绿色强调色调整为蓝 / 粉系；接入帮助页页头和内容外层容器迁移到 MUI；设置页内部复杂 Ant Design Collapse、表单、表格、Provider 测试、Prompt 预览、项目组配置和 Push 策略逻辑保持不变。
- 为什么：设置页、版本更新页和接入帮助页是阶段 5 最后一批高层页面，需要与任务页、质量治理页形成一致的 Material 3 surface、outline 和紧凑后台布局，同时避免一次性重写复杂设置表单导致保存行为回归。
- 如何验证：运行 `scripts/run-frontend.cmd build`；确认 `/settings`、`/releases` 和 `/help` 可构建通过，设置页刷新、配置保存、Provider 测试、Prompt 预览、项目组配置、Push 策略维护等内部行为未改动 API 契约。
- 遗留风险：设置页内部 Ant Design Collapse、Card、Table、Form 控件和 Modal 仍未逐项迁移；版本更新和接入帮助未做真实浏览器截图验证；暗色模式仍暂停；bundle 体积继续触发 Vite 大 chunk 警告。
- 下一阶段：`docs/39` 阶段 5 已完成；后续回到 `docs/36` 的 M11 业务 Retriever 扩展循环或由用户确认新的专项计划。

### 2026-08-05：设置页卡片信息层级优化

- 目标：不改变 Provider、Profile、项目组、Agent、钉钉和 Push 策略接口契约，为设置页的业务配置块补充统一的醒目标题、语义图标、作用域 / 状态标签和简短说明，使用户不展开字段也能判断配置范围与影响。
- 主卡片：项目组管理、项目归属与 Review 配置、端类型自动识别规则、项目组 AI Review 通用策略、普通 Review 初始 Prompt、AI 模型 Provider、Agent Review 接入配置、Agent 执行预算、平台全局能力。设置页不展示 Agent 运行概况和队列 / Worker Pool 明细卡片；Agent 启用状态、Worker 在线状态和排队数量仅保留在折叠栏摘要中。
- 子卡片：项目组钉钉通知、修复预览策略、Push 审核策略。子卡片使用较小图标和标题；修复预览与 Push 策略继续跟随对应开关条件渲染。
- 视觉约束：主标题、图标、标签同一标题区呈现，描述说明“配置什么、影响什么”；字段标签、单项指标、Alert 和高级参数不重复套卡片；操作按钮保持在所属卡片底部或标题区右侧；窄屏允许标题、标签和操作自然换行。
- Agent 预算布局：标题区与内容区保持明确的垂直间距；全部基础与收敛参数在同一固定紧凑宽度网格中左对齐排列，不再单独折叠“高级收敛参数”；输入框不随大屏无限拉伸；只保留越界或跨字段约束等无效配置错误，不展示“高于默认预算”的一般性提醒。
- 表单宽度：普通 Review Prompt 和项目归属配置按字段内容分配栅格宽度，短枚举字段收窄，可能包含较长项目名称的下拉框加宽，不使用机械等宽布局。
- 设置页容器：Collapse 直接占用页面内容宽度，不再叠加最外层 MUI Paper 边框；折叠内容、内部 Card 与业务卡片使用紧凑内边距，避免多层 surface 造成大面积空白；“平台全局能力”使用与其他业务设置一致的有边框卡片。
- 授权边界：本次只调整 React 结构、标题文案和 CSS，不改变保存、测试连接、Prompt 预览、刷新、条件开关、API payload 或后端行为。
- 验收：运行设置页相关前端测试和 `scripts/run-frontend.cmd build`；在 `/settings` 逐组确认 9 张主卡片和 3 张子卡片的标题层级，确认 Agent 区域只保留接入配置与执行预算，确认修复预览 / Push 子卡片条件显示、表格与表单可用、桌面布局无明显挤压，控制台无新增错误。
- 实施结果：已抽取统一 `SettingsCardHeader`，完成 9 张主卡片和 3 张子卡片的标题、图标、描述、标签和响应式操作区；Agent Review 只保留接入配置和执行预算两个区块；项目组钉钉通知继续只在编辑项目组时出现。顶部“任务”入口使用更醒目的文件审查图标，与其他导航按钮保持一致。
- 验证结果：设置页定向测试 3 项通过，生产构建通过；浏览器逐组确认全部主卡片标题可见，修复预览与 Push 子卡片单独开启和同时开启均正确显示，临时开关未保存且验收后已通过页面重载恢复。控制台无新增运行异常，仅保留既有 Ant Design 弃用提示。

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

- 顶部“质量治理”下拉统一承载质量看板、评估样本、规则缺口、验收记录和回放记录。
- 规则缺口、验收记录、回放记录保留直接路由和后端能力，但页面页头不再散落跨页导航按钮。
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
5.1 MUI / Emotion 基础设施（已完成）
  -> 5.2 质量看板 MUI 布局迁移（已完成）
  -> 5.3 评估样本 MUI 布局迁移（已完成）
  -> 5.4 质量治理高级诊断统一壳（已完成）
  -> 5.5 任务列表和任务详情主框架（已完成）
  -> 5.6 设置页和版本更新页（已完成）
```

设计要求：

- 优先使用 MUI 组件，不自造复杂视觉系统。
- Material 3 风格圆角、surface、outline、按钮、输入框和状态层。
- 管理后台页面优先采用紧凑、可扫描的信息架构，不做大 Hero、不让操作按钮漂在页面中间。
- 页面页头采用“左侧标题 / 说明，右侧本页主操作”的两栏布局；宽屏右对齐，窄屏再自然换行；跨页导航统一交给顶部“质量治理”下拉框。
- 页面页头不放“任务 / 质量治理 / 高级诊断 / 设置”等分类 chip；页面所在模块由顶部导航和标题表达。
- 页面页头不放纯刷新按钮；需要重新查询时优先使用筛选区的搜索 / 筛选动作，只有新建、返回、保存等明确业务主操作才放在页头右侧。
- 说明性提示不要作为独立 alert 占用首屏主视觉空间；能并入页头描述时优先并入页头描述。
- 顶部操作按钮必须固定紧凑高度和内容宽度，不能在宽屏下被容器拉伸变大。
- Gemini 式 AI 产品感只体现在轻量 surface、清晰输入区和克制状态层，不牺牲后台页面密度和可读性。
- 质量治理、设置、任务等后台页面保留表格用于 Top 维度、列表、记录和横向比较；外层可用 MUI surface，但不要为了卡片化而替代表格。
- 色系避免单独大面积绿色；主色优先蓝 / 粉等更明快的多巴胺色系，指标卡可用白底多色强调线，而不是整块高饱和色块。
- hover / focus / disabled 状态必须覆盖。
- Ant Design 与 MUI 共存阶段先固定 light palette，避免暗色方案导致浅色背景低对比；暗色模式等全站 MUI 迁移更完整后再产品化。

### 阶段 5.1：MUI / Emotion 基础设施（已完成）

目标：

- 新增 MUI / Emotion 依赖。
- 增加 MUI ThemeProvider、CssBaseline、light / dark color schemes 和 App Shell 基础。
- 旧 Ant Design 页面允许短期共存，不做页面迁移。

验收：

- 前端 build 通过。
- 现有页面路由、顶部导航和 Ant Design 页面不回归。

### 阶段 5.2：质量看板 MUI 布局迁移（已完成）

目标：

- 只迁移“质量看板”页面的页面壳、页头、筛选区、指标卡和治理摘要区。
- 数据请求、过滤参数、表格数据和后端 API 保持不变。
- 复杂表格可以继续使用 Ant Design Table，外层布局与视觉容器优先改成 MUI。
- 明确呈现 Material 3 风格的 surface、outline、按钮、输入框、状态区和响应式布局。

边界：

- 不迁移任务列表、任务详情、设置页。
- 不改 `/api/review-quality/dashboard` 契约。
- 不做全站主题切换产品化。

验收：

- 前端 build 通过。
- 质量看板在桌面和窄屏下无明显重叠、截断或按钮文本溢出。
- 质量看板仍可按项目、Provider、Profile、风险类型和 verdict 过滤。

### 阶段 5.3：评估样本 MUI 布局迁移（已完成）

目标：

- 迁移“评估样本”页面的页面壳、页头、筛选区、操作入口和规则缺口归因弹窗外观。
- 表格可以短期继续使用 Ant Design Table。
- 保持“编辑归因”、任务跳转和筛选行为不变；跨页导航统一交给顶部“质量治理”下拉框。

边界：

- 不改 `/api/evaluation-cases` 和 `/api/evaluation-cases/{caseId}/rule-gap-attribution` 契约。
- 不恢复反馈池默认展示。
- 不把 evaluation case 与反馈池合并。

验收：

- 前端 build 通过。
- 新建 / 编辑归因弹窗的字段、保存行为和错误提示不回归。
- 评估样本列表仍可按项目、Provider、Profile、风险类型和 verdict 查询。

### 阶段 5.4：质量治理高级诊断统一壳（已完成）

目标：

- 给规则缺口、验收记录、回放记录统一 MUI 风格页面壳、页头和诊断说明区。
- 保留这些页面作为质量治理下拉中的高级诊断入口，不在页面页头重复放跨页导航按钮。
- 复杂表格和历史详情区域可继续短期使用 Ant Design。

边界：

- 不删除直接路由。
- 不删除后端 API、历史数据或诊断能力。
- 不把规则缺口重新提升为实现优先级主入口。

验收：

- 前端 build 通过。
- `/rule-gaps`、`/acceptance-gates`、`/evaluation-runs` 和详情页直接访问正常。
- 从顶部“质量治理”下拉进入规则缺口、验收记录和回放记录的路径正常。

### 阶段 5.5：任务列表和任务详情主框架（已完成）

目标：

- 迁移任务列表和任务详情的页面壳、主导航区域、标题区和高层布局。
- 任务详情内部复杂 tab、diff viewer、AI Review finding 展示和设置类弹窗可分批迁移。
- 保持任务直达链接、`reviewKey` 参数、调度队列、失败通知入口和现有轮询行为。

边界：

- 不改任务详情 API 契约。
- 不重写 diff viewer 或 patch preview 逻辑。
- 不改变 AI Review 结果展示语义。

验收：

- 前端 build 通过。
- `/tasks`、`/tasks/{taskId}`、`?reviewKey=` 直达路径正常。
- 任务列表筛选、任务详情 tab 切换、AI Review 轮询和高准确模式流转不回归。

### 阶段 5.6：设置页和版本更新页（已完成）

目标：

- 迁移设置页、版本更新页和接入帮助页的页面壳与主要 surface。
- 设置页复杂表单按模块逐步迁移，优先保持配置保存和测试连接稳定。
- 版本更新页可改为 MUI 风格时间线或列表。

边界：

- 不改 Provider、Profile、项目组、钉钉 webhook、Push 审核策略 API 契约。
- 不一次性重写所有设置表单组件。

验收：

- 前端 build 通过。
- 设置页保存、测试 Provider、Prompt 预览、项目组配置和 Push 策略维护不回归。
- 版本更新和接入帮助页面在桌面 / 移动宽度下可读。

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
- 顶部质量治理下拉展示质量看板、评估样本、规则缺口、验收记录和回放记录。
- 质量治理页面页头不放跨页导航按钮；规则缺口、验收记录、回放记录保留直接路由。
- 更新 docs/38 的生命周期说明。

完成后运行前端 build，并停止等待验证。
```

## 阶段 5.1 Prompt

```text
请只落地 docs/39 的阶段 5 第一小步：Material Design 3 / MUI 前端基础设施。

目标：
- 新增 MUI / Emotion 依赖。
- 增加 MUI ThemeProvider、CssBaseline、light / dark color schemes 和 App Shell 基础。
- 不一次性迁移所有页面；优先让质量看板和评估样本可以在新布局中运行。
- 新页面优先使用 MUI 组件，旧 Ant Design 页面允许短期共存。

完成后运行前端 build，并停止等待验证。
```

## 阶段 5.2 Prompt

```text
请只落地 docs/39 的阶段 5.2：质量看板 MUI 布局迁移。

目标：
- 只迁移“质量看板”页面的页面壳、页头、筛选区、指标卡和治理摘要区。
- 使用已接入的 MUI ThemeProvider / CssBaseline / appMuiTheme。
- 数据请求、过滤参数、表格数据和后端 API 保持不变。
- 复杂表格可以继续使用 Ant Design Table，外层布局与视觉容器优先改成 MUI。
- 让页面能明显呈现 Material 3 风格的 surface、outline、按钮、输入框、状态区和响应式布局。

边界：
- 不迁移任务列表、任务详情、设置页。
- 不改 `/api/review-quality/dashboard` 契约。
- 不做全站主题切换产品化。
- 不恢复反馈池默认展示。

完成后运行 `scripts/run-frontend.cmd build`，并停止等待验证。
```

## 阶段 5.3 Prompt

```text
请只落地 docs/39 的阶段 5.3：评估样本 MUI 布局迁移。

目标：
- 迁移“评估样本”页面的页面壳、页头、筛选区、操作入口和规则缺口归因弹窗外观。
- 使用已接入的 MUI 主题和基础壳。
- 表格可以短期继续使用 Ant Design Table。
- 保持“编辑归因”、任务跳转和筛选行为不变；跨页导航统一由顶部“质量治理”下拉承载。

边界：
- 不改 `/api/evaluation-cases` 和 `/api/evaluation-cases/{caseId}/rule-gap-attribution` 契约。
- 不恢复反馈池默认展示。
- 不把 evaluation case 与反馈池合并。

完成后运行 `scripts/run-frontend.cmd build`，并停止等待验证。
```

## 阶段 5.4 Prompt

```text
请只落地 docs/39 的阶段 5.4：质量治理高级诊断统一壳。

目标：
- 给规则缺口、验收记录、回放记录统一 MUI 风格页面壳、页头和诊断说明区。
- 保留这些页面作为顶部“质量治理”下拉中的高级诊断入口，不在页面页头重复放跨页导航按钮。
- 复杂表格和历史详情区域可继续短期使用 Ant Design。

边界：
- 不删除直接路由。
- 不删除后端 API、历史数据或诊断能力。
- 不把规则缺口重新提升为实现优先级主入口。

完成后运行 `scripts/run-frontend.cmd build`，并停止等待验证。
```

## 阶段 5.5 Prompt

```text
请只落地 docs/39 的阶段 5.5：任务列表和任务详情主框架 MUI 迁移。

目标：
- 迁移任务列表和任务详情的页面壳、主导航区域、标题区和高层布局。
- 任务详情内部复杂 tab、diff viewer、AI Review finding 展示和设置类弹窗可分批迁移。
- 保持任务直达链接、`reviewKey` 参数、调度队列、失败通知入口和现有轮询行为。

边界：
- 不改任务详情 API 契约。
- 不重写 diff viewer 或 patch preview 逻辑。
- 不改变 AI Review 结果展示语义。

完成后运行 `scripts/run-frontend.cmd build`，并停止等待验证。
```

## 阶段 5.6 Prompt

```text
请只落地 docs/39 的阶段 5.6：设置页和版本更新页 MUI 迁移。

目标：
- 迁移设置页、版本更新页和接入帮助页的页面壳与主要 surface。
- 设置页复杂表单按模块逐步迁移，优先保持配置保存和测试连接稳定。
- 版本更新页可改为 MUI 风格时间线或列表。

边界：
- 不改 Provider、Profile、项目组、钉钉 webhook、Push 审核策略 API 契约。
- 不一次性重写所有设置表单组件。

完成后运行 `scripts/run-frontend.cmd build`，并停止等待验证。
```
