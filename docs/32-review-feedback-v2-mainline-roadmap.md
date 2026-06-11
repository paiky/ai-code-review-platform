# Review 反馈学习 V2 主线推进路线：项目策略、上下文反馈与后续 Context Pack

## 状态

- 当前状态：V2-A / V2-B / V2-C / V2-D / V2-E 已落地并通过相关测试；V2-F-1 / V2-F-2 / V2-F-3 已落地；V2-F-5 本地仓库 mirror clone / fetch / worktree 最小闭环与 V2-F-6 `METHOD_DELETED / METHOD_SIGNATURE_CHANGED` 引用搜索 Retriever MVP 已落地。V2-F-3 后短期主线调整为 `docs/34-local-repository-context-retrieval-plan.md` 的本地仓库上下文检索 / 高准确 Review 模式，人工沉淀能力先在产品界面默认屏蔽。
- 编写时间：2026-06-10
- 前置版本：
  - `docs/29-review-feedback-v1-implementation.md`
  - `docs/30-review-feedback-v2-policy-plan.md`
  - `docs/31-review-context-aware-v1_5-plan.md`
- 延伸愿景：`docs/33-review-learning-capability-roadmap.md`
- 高准确 Review 主方案：`docs/34-local-repository-context-retrieval-plan.md`
- 目标：在 V1 反馈闭环和 V1.5 上下文状态表达已具备的基础上，重新排序 V2 主线和 31 阶段 3~5，明确哪些现在做、哪些轻量补、哪些暂缓。

说明：本文件不弃用，继续负责 V2 主线执行顺序和已落地记录；`docs/33-review-learning-capability-roadmap.md` 负责长期自我学习蓝图，包括反馈信号分流、自动化等级阶梯、自动归因、自动聚类、候选生成、效果评估和低风险灰度生效；`docs/34-local-repository-context-retrieval-plan.md` 负责 V2-F-3 之后的本地 clone / fetch / 引用搜索 / Context Pack 高准确 Review 方案。

## 一、结论

当前应优先推进 V2 主线，不建议继续按 `docs/31` 原阶段 3 的 `METHOD_DELETED` 专项作为下一阶段。

推荐路线：

```text
已完成：V1 反馈记录闭环
已完成：V1.5 阶段 2，上下文状态表达
已完成：V2-A 项目策略库与反馈转策略 API
已完成：V2-B 项目策略 Prompt 注入与可观测
已完成：V2-C 前端反馈池生成策略与项目策略管理
已完成：V2-D 文档、示例与验收链路
已完成：V2-E 上下文不足反馈轻量统计
已完成：V2-F-1 通用 Context Pack V0 后端最小闭环
已完成：V2-F-2 同文件上下文片段 V0
已完成：V2-F-3 Context Planner 最小规则
已完成：V2-F-5 本地仓库 mirror clone / fetch / worktree 最小闭环
已完成：V2-F-6 METHOD_DELETED / METHOD_SIGNATURE_CHANGED 引用搜索 Retriever MVP
下一步：V2-F-7 起按 docs/34 推进本地引用证据注入 Context Pack
```

原因：

1. `METHOD_DELETED` 是真实误判场景，但只是上下文不足问题的一种表现，不适合作为当前主线阶段目标。
2. V2 项目策略注入能直接解决“项目规范导致反复误判”的主线问题，是反馈池从记录台账变成产品能力的关键。
3. V1.5 已经让 finding 支持 `contextStatus / evidence / missingContext / contextSummary`，足够支撑 V2 先行，不会阻塞策略注入。
4. 上下文不足反馈和动态上下文补充仍有价值，但应降级为 V2 之后的轻量增强或通用 Context Pack，而不是单点专项。

## 二、31 阶段 3~5 取舍

| 来源阶段 | 原目标 | 是否补齐 | 调整结论 |
|---|---|---|---|
| 31 阶段 3 | `METHOD_DELETED` 动态上下文补充 | 不按原专项补齐 | 暂缓。后续改为通用 `Context Pack V0`，删除方法只是策略之一。 |
| 31 阶段 4 | 反馈池接入 `CONTEXT_MISSING` | 已轻量补齐 | 已在 V2-E 补充筛选、缺失上下文类型和统计；不自动影响 prompt、策略或风险等级。 |
| 31 阶段 5 | 恢复 V2 项目策略落地 | 必须推进 | 立即成为当前主线，也就是 V2-A 到 V2-D。 |

### 为什么不补原阶段 3

原阶段 3 的收益是降低“删除方法误判”，但落地会快速牵出：

- 方法删除识别。
- 同文件结构摘要。
- 引用搜索。
- 本地仓库路径配置。
- GitLab 远端文件搜索或 raw file 批量读取。
- 多语言方法解析差异。

这些能力值得做，但不应该以 `METHOD_DELETED` 作为产品主线。更好的抽象是：

```text
Context Planner
  -> 生成上下文请求
Context Retriever
  -> 在预算内补充上下文片段
Context Pack
  -> 注入 AI Review prompt
```

因此后续如果要补动态上下文，应做 `V2-F 通用 Context Pack V0`，先支持“同文件上下文、变更文件摘要、上下文可用性说明”，再逐步加入引用搜索。删除方法可以作为第一个 Planner 规则，而不是单独阶段。

### 为什么保留阶段 4

`CONTEXT_MISSING` 反馈不是策略注入的前置条件，但它能回答两个问题：

- 哪些项目、哪些风险类型经常因为上下文不足被标记误判。
- 后续 Context Planner 应该优先补哪类上下文。

所以它应作为轻量统计能力保留，但不应自动影响 prompt、策略或风险等级。

### 为什么立即恢复阶段 5

V2 项目策略注入解决的是“项目规范 / 团队约定 / 架构事实”导致的误判，和上下文不足是互补关系：

```text
项目策略：告诉模型这个项目有什么已确认规则。
上下文增强：告诉模型这次变更周边还有什么证据。
```

当前 V1 反馈池已经具备记录和状态流转，V1.5 已具备上下文状态表达，因此可以进入 V2。

## 三、重大方向优先级

### P0：项目策略库

必须优先落地。

核心价值：

- 把 `VALID` 或 `suggestAsProjectRule=true` 的反馈转成项目级策略。
- 让反馈池形成长期记忆，而不是一次性记录。
- 按项目隔离，避免跨项目污染。

首版只真正启用：

- `PROJECT_RULE`
- `CONTEXT_FACT`

暂缓：

- `IGNORE_RULE`
- `RISK_LEVEL_POLICY`

暂缓原因：忽略和等级策略容易诱导模型漏报或过度降级，首版应先只提供项目事实和确认规则。

### P0：策略 Prompt 注入与可观测

必须尽快落地，建议紧跟项目策略库之后。

要求：

- 只注入同 `project_id`、`enabled=true` 的策略。
- 只注入 `PROJECT_RULE / CONTEXT_FACT`。
- 单次最多 20 条。
- 单条内容最多 1000 字符。
- 总注入文本最多 8000 字符。
- Prompt 明确策略不能覆盖安全、数据一致性、线上正确性硬风险。
- progress event 记录 `PROJECT_POLICIES_INJECTED`，只记录策略数量、id、标题、类型和风险类型，不记录过长全文。
- rendered prompt 支持 `projectId` 预览。

### P1：前端反馈池生成策略与项目策略管理

有必要落地，但可以在后端闭环后推进。

建议最小页面：

- 反馈池增加“生成策略”操作。
- 反馈池内新增“项目策略”tab。
- 支持按项目筛选。
- 支持编辑、启用、停用。
- 展示来源反馈。

不建议新增顶层导航，避免主导航膨胀。

### P1：文档、示例与验收链路

必须作为 V2 收口阶段。

需要补：

- README 使用说明。
- `docs/03-api-contract.md` API 契约。
- 最小请求示例。
- 本地验证步骤。

### P2：上下文不足反馈统计

有必要，但不阻塞 V2。

最小范围：

- 反馈池支持按 `reasonType=CONTEXT_MISSING` 筛选。
- 反馈提交时可选择缺失上下文类型。
- 反馈池展示上下文不足数量和风险类型分布。
- 不自动改 prompt。
- 不自动创建项目策略。
- 不自动影响后续 Review。

### P2：通用 Context Pack V0

保留为后续增强，不建议现在做。

建议目标：

- 不绑定 `METHOD_DELETED`。
- 为每次 AI Review 构造 `reviewContext`。
- 先注入“同文件上下文片段、变更文件摘要、上下文可用性说明”。
- 明确哪些上下文不可用，例如 GitLab API 未配置、base/head ref 缺失、文件过大。
- 先不做全项目引用搜索。
- 后续再把删除方法、签名变更、DB 字段、缓存/MQ 读写对作为 Planner 规则接入。

## 四、新阶段拆分

### V2-A：后端策略库与反馈转策略 API

目标：

建立项目策略库，打通从 V1 feedback 到 project policy 的后端闭环。

范围：

- `backend-python/app/project_review_policy/*`
- `backend-python/app/review_feedback/service.py`
- `backend-python/app/review_feedback/api.py`
- `backend-python/app/main.py`
- `backend-python/migrations/bootstrap_sql/V35__project_review_policies.sql`
- `backend-python/tests/contract/test_project_review_policy_api_contract.py`
- `docs/32-review-feedback-v2-mainline-roadmap.md` 验证记录

接口：

- `POST /api/risk-feedback/{feedbackId}/convert-to-policy`
- `GET /api/projects/{projectId}/review-policies`
- `PUT /api/project-review-policies/{policyId}`
- `PUT /api/project-review-policies/{policyId}/enabled`

验收：

- `VALID` 或 `suggestAsProjectRule=true` 的反馈可转策略。
- `INSUFFICIENT / IGNORED` 反馈默认不可转策略。
- 转换后 feedback 状态可变为 `CONVERTED`。
- 策略按 `project_id` 隔离。
- 首版只允许注入型策略：`PROJECT_RULE / CONTEXT_FACT`。

### V2-B：策略 Prompt 注入与可观测

目标：

让已启用项目策略真正影响后续 AI Review 输入，同时可预览、可排障。

范围：

- `backend-python/app/project_review_policy/service.py`
- `backend-python/app/code_quality/service.py`
- `backend-python/app/code_quality/prompt.py`
- `backend-python/app/code_quality/api.py`
- `backend-python/tests/unit/test_project_review_policy_prompt.py`
- `backend-python/tests/contract/test_code_quality_api_contract.py`
- `docs/32-review-feedback-v2-mainline-roadmap.md` 验证记录

验收：

- AI Review 执行时读取同项目启用策略。
- Prompt 只注入 `PROJECT_RULE / CONTEXT_FACT`。
- 停用策略后不再注入。
- rendered prompt 支持 `projectId`。
- progress 中可看到 `PROJECT_POLICIES_INJECTED`。
- 策略注入遵守数量和长度预算。

### V2-C：前端反馈池生成策略与项目策略管理

目标：

让管理员能从反馈池完成策略生成、编辑和启停。

范围：

- `frontend/src/App.jsx`
- `frontend/src/styles.css`
- `docs/32-review-feedback-v2-mainline-roadmap.md` 验证记录

验收：

- 反馈池可筛选建议沉淀反馈。
- 支持打开“生成策略”弹窗。
- 策略标题、内容、类型、风险类型有默认草稿。
- 项目策略 tab 可查看、编辑、启用、停用策略。
- 前端 build 通过。

### V2-D：文档与示例收口

目标：

补齐用户可验证链路和 API 契约。

范围：

- `README.md`
- `docs/03-api-contract.md`
- `docs/30-review-feedback-v2-policy-plan.md`
- `docs/32-review-feedback-v2-mainline-roadmap.md`
- `examples/` 如需新增示例

验收：

- 写清如何从反馈生成项目策略。
- 写清如何验证策略注入 rendered prompt。
- 写清如何查看本次 Review 注入策略。
- 记录本地测试结果。

### V2-E：上下文不足反馈轻量统计

目标：

把 `CONTEXT_MISSING` 从普通原因变成可筛选、可统计的上下文质量信号。

范围：

- `backend-python/app/review_feedback/*`
- `frontend/src/App.jsx`
- `frontend/src/styles.css`
- 相关 tests
- `docs/32-review-feedback-v2-mainline-roadmap.md` 验证记录

验收：

- 反馈弹窗可选择缺失上下文类型。
- 反馈池可筛选 `CONTEXT_MISSING`。
- 反馈池或统计区能看到上下文不足数量。
- 不自动创建策略。
- 不自动影响 AI Review。

### V2-F：通用 Context Pack V0

目标：

替代原 31 阶段 3 的单点 `METHOD_DELETED` 专项，建立更通用的上下文包能力。

范围建议：

- 可新增 `backend-python/app/review_context/*`
- `backend-python/app/code_quality/service.py`
- `backend-python/app/code_quality/prompt.py`
- 相关 tests
- `docs/32-review-feedback-v2-mainline-roadmap.md` 验证记录

验收：

- AI Review request 中有 `reviewContext`。
- 能注入同文件上下文片段和变更文件摘要。
- 能说明哪些上下文不可用。
- 控制上下文预算。
- 删除方法只是首批 Planner 规则之一，不作为唯一目标。

## 五、总控 Prompt

```text
请阅读 AGENTS.md、README.md、docs/29-review-feedback-v1-implementation.md、docs/30-review-feedback-v2-policy-plan.md、docs/31-review-context-aware-v1_5-plan.md、docs/32-review-feedback-v2-mainline-roadmap.md。

当前已完成 V1 反馈记录闭环和 V1.5 上下文状态表达。接下来以 docs/32 为后续主线计划，优先推进 V2 项目策略闭环，不按 docs/31 原阶段 3 的 METHOD_DELETED 专项继续扩展。

每次只推进一个阶段。允许自主修改 backend-python、frontend、docs、examples、tests 中与当前阶段直接相关的文件；不要修改 legacy Java backend；不要实现当前阶段外的自动 Prompt 改写、自动降级、模型评测、RAG、向量库、跨项目策略共享或全项目扫描。

每个阶段完成后必须停止，输出“改了什么、为什么、如何验证”，等待用户验证并明确回复“继续下一阶段”后再推进。
```

## 六、分阶段落地 Prompt

### V2-A Prompt：后端策略库与反馈转策略 API

```text
请只落地 docs/32 的 V2-A：后端策略库与反馈转策略 API。

范围：
- backend-python/app/project_review_policy/*
- backend-python/app/review_feedback/service.py 和 api.py 中必要的 convert-to-policy 接口
- backend-python/app/main.py router 注册
- backend-python/migrations/bootstrap_sql/V35__project_review_policies.sql
- backend-python/tests/contract/test_project_review_policy_api_contract.py
- docs/32 V2-A 验证记录

要求：
- 新增 project_review_policies 表和运行期 schema 兜底。
- 支持从 VALID 或 suggestAsProjectRule=true 的反馈生成策略。
- 生成后反馈状态可变为 CONVERTED。
- 策略按 project_id 隔离。
- 首版只允许 PROJECT_RULE / CONTEXT_FACT 作为可注入策略。
- 不做 prompt 注入，不改前端。

完成后运行后端相关测试并停止。
```

### V2-B Prompt：策略 Prompt 注入与可观测

```text
请只落地 docs/32 的 V2-B：策略 Prompt 注入与可观测。

范围：
- backend-python/app/project_review_policy/service.py
- backend-python/app/code_quality/service.py
- backend-python/app/code_quality/prompt.py
- backend-python/app/code_quality/api.py
- backend-python/tests/unit/test_project_review_policy_prompt.py
- backend-python/tests/contract/test_code_quality_api_contract.py
- docs/32 V2-B 验证记录

要求：
- AI Review 执行时读取同项目 enabled=true 的 PROJECT_RULE / CONTEXT_FACT。
- 注入内容有数量、单条长度和总长度限制。
- Prompt 明确策略不能覆盖安全、数据一致性、线上正确性硬风险。
- rendered prompt 支持 projectId 预览。
- progress 记录 PROJECT_POLICIES_INJECTED 摘要。
- 不做前端策略管理，不做自动降级，不做 RAG。

完成后运行后端相关测试并停止。
```

### V2-C Prompt：前端反馈池生成策略与项目策略管理

```text
请只落地 docs/32 的 V2-C：前端反馈池生成策略与项目策略管理。

范围：
- frontend/src/App.jsx
- frontend/src/styles.css
- docs/32 V2-C 验证记录

要求：
- 反馈池可筛选建议沉淀反馈。
- 从反馈池可打开生成策略弹窗。
- 可查询、编辑、启用、停用项目策略。
- 项目策略管理优先放在反馈池页面 tab 内，不新增顶层导航。
- 不做新的 prompt 注入后端逻辑。

完成后运行前端 build 并停止。
```

### V2-D Prompt：文档与示例收口

```text
请只落地 docs/32 的 V2-D：文档与示例收口。

范围：
- README.md
- docs/03-api-contract.md
- docs/30-review-feedback-v2-policy-plan.md
- docs/32-review-feedback-v2-mainline-roadmap.md
- examples/ 如需新增最小请求示例

要求：
- 写清如何从反馈生成项目策略。
- 写清如何验证策略注入 rendered prompt。
- 写清如何查看本次 Review 注入策略。
- 记录本地已知测试结果。

完成后停止，等待用户最终验收。
```

### V2-E Prompt：上下文不足反馈轻量统计

```text
请只落地 docs/32 的 V2-E：上下文不足反馈轻量统计。

范围：
- backend-python/app/review_feedback/*
- frontend/src/App.jsx
- frontend/src/styles.css
- 相关 tests
- docs/32 V2-E 验证记录

要求：
- 反馈原因支持 CONTEXT_MISSING 的筛选和统计。
- 可选择缺失上下文类型。
- 不自动创建项目策略。
- 不自动影响后续 Review。
- 不自动改 Prompt。

完成后停止。
```

### V2-F Prompt：通用 Context Pack V0

```text
请只落地 docs/32 的 V2-F：通用 Context Pack V0。

范围：
- 可新增 backend-python/app/review_context/*
- backend-python/app/code_quality/service.py
- backend-python/app/code_quality/prompt.py
- 相关 tests
- docs/32 V2-F 验证记录

要求：
- 不按 METHOD_DELETED 专项实现，而是建立通用 reviewContext / contextPack。
- 先支持同文件上下文片段、变更文件摘要和上下文可用性说明。
- 控制上下文预算。
- 不做全项目扫描，不接向量库，不做复杂 RAG。
- 删除方法可作为首批 Planner 规则之一，但不是唯一目标。

完成后停止。
```

## 七、Agent 授权边界

Agent 可自主推进：

- 新增 Python 后端项目策略模块。
- 新增 MySQL bootstrap SQL。
- 新增和调整 V2 策略相关 API。
- 新增契约 / 单元测试。
- 新增前端反馈池生成策略和项目策略管理交互。
- 更新 docs/30、docs/32、README、API 契约和 examples。
- 后续在 V2-E / V2-F 中补轻量上下文反馈统计和通用 Context Pack。

Agent 不可自主推进：

- 不修改 legacy Java backend。
- 不做自动 Prompt 改写。
- 不做模型微调。
- 不做自动风险降级或自动忽略 finding。
- 不接向量库或复杂 RAG。
- 不做跨项目或项目组策略共享。
- 不默认启用任何未经人工确认的策略。
- 不把 `CONTEXT_MISSING` 反馈自动转换为项目策略。
- 不做全项目扫描或无限制文件读取。

## 八、每阶段停止规则

每个阶段完成后必须停止，并等待用户完成本地验证。只有用户明确回复“继续下一阶段”后，才进入下一阶段。

如果某阶段发现当前计划与真实代码冲突，先更新本计划中的“调整记录”，输出分析结论和最小改动建议，再等待用户确认。

## 九、V2-A 落地记录

落地时间：2026-06-10。

已完成：

- 新增 `project_review_policies` 表结构和运行期 schema 兜底。
- 新增 `backend-python/app/project_review_policy/*`，支持策略模型、查询、编辑、启停和反馈转策略。
- 新增 `POST /api/risk-feedback/{feedbackId}/convert-to-policy`。
- 新增 `GET /api/projects/{projectId}/review-policies`。
- 新增 `PUT /api/project-review-policies/{policyId}`。
- 新增 `PUT /api/project-review-policies/{policyId}/enabled`。
- `review_item_feedbacks.status` 后端枚举扩展 `CONVERTED`。
- 转换规则限制为 `VALID` 或 `suggestAsProjectRule=true` 的反馈；`INSUFFICIENT / IGNORED / CONVERTED` 不可转。
- `CONTEXT_MISSING` 反馈不可转项目策略，后续应进入上下文不足统计或 Context Pack backlog。
- 首版只允许创建可注入策略类型 `PROJECT_RULE / CONTEXT_FACT`，暂不开放 `IGNORE_RULE / RISK_LEVEL_POLICY`。
- 策略按 `project_id` 隔离；V2-A 不做 Prompt 注入、不改前端。

新增测试：

- `backend-python/tests/contract/test_project_review_policy_api_contract.py`

已验证：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\contract\test_project_review_policy_api_contract.py
```

结果：4 passed。

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\contract\test_review_feedback_api_contract.py tests\contract\test_project_review_policy_api_contract.py
```

结果：6 passed。

下一阶段建议：

```text
V2-B 已完成；当前下一阶段为 V2-C：前端反馈池生成策略与项目策略管理。
```

## 十、V2-B 落地记录

落地时间：2026-06-10。

已完成：

- AI Review 执行前读取同项目 `enabled=true` 的项目策略。
- 仅注入 `PROJECT_RULE / CONTEXT_FACT`，不注入 `IGNORE_RULE / RISK_LEVEL_POLICY`。
- 策略注入遵守预算：最多 20 条，单条 content 最多 1000 字符，策略段落总长最多 8000 字符。
- Prompt 中新增项目策略段落，并明确项目策略不能覆盖明确的安全、数据一致性或线上正确性硬风险。
- `GET /api/code-quality-review-profiles/{profileCode}/rendered-prompt` 支持 `projectId` query，用于预览同项目策略注入结果。
- AI Review progress 新增 `PROJECT_POLICIES_INJECTED` 事件，只记录策略数量、id、标题、类型、风险类型和来源反馈 id，不记录策略正文。
- V2-B 不做前端策略管理、不自动改 Prompt、不做自动降级、不做 RAG。

新增和调整测试：

- `backend-python/tests/unit/test_project_review_policy_prompt.py`
- `backend-python/tests/contract/test_code_quality_api_contract.py`

已验证：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_code_quality_prompt.py tests\unit\test_project_review_policy_prompt.py tests\contract\test_code_quality_api_contract.py::test_rendered_prompt_uses_java_stronger_default tests\contract\test_code_quality_api_contract.py::test_rendered_prompt_can_preview_project_review_policies tests\contract\test_code_quality_api_contract.py::test_manual_review_injects_project_review_policies_and_records_progress tests\contract\test_project_review_policy_api_contract.py
```

结果：17 passed。

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\contract\test_review_feedback_api_contract.py tests\contract\test_project_review_policy_api_contract.py tests\unit\test_project_review_policy_prompt.py
```

结果：10 passed。

下一阶段建议：

```text
V2-C 已完成；当前下一阶段为 V2-D：文档与示例收口。
```

## 十一、V2-C 落地记录

落地时间：2026-06-10。

已完成：

- 反馈池页面新增 `反馈记录 / 项目策略` tab，不新增顶层导航。
- 反馈记录支持 `建议沉淀` 筛选，后端补充 `policyCandidate=true` 查询参数，避免分页下只做前端当前页过滤。
- 反馈记录表格新增沉淀状态展示和 `生成策略` 操作。
- 生成策略弹窗支持策略类型、风险类型、标题、内容和启用状态编辑，并调用 `POST /api/risk-feedback/{feedbackId}/convert-to-policy`。
- 项目策略 tab 支持按项目、启用状态、策略类型、风险类型查询。
- 项目策略 tab 支持编辑、启用和停用策略。
- 反馈状态展示新增 `CONVERTED / 已沉淀`。
- `CONTEXT_MISSING` 反馈不会进入建议沉淀候选，也不能在前端触发生成策略。
- V2-D 前补充体验修补：禁用的“生成策略”按钮会通过 tooltip 说明不可点击原因。

新增和调整测试：

- `backend-python/tests/contract/test_review_feedback_api_contract.py`
- `frontend/src/App.jsx`
- `frontend/src/styles.css`

已验证：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\contract\test_review_feedback_api_contract.py tests\contract\test_project_review_policy_api_contract.py
```

结果：7 passed。

```powershell
$env:NO_PAUSE="1"; .\scripts\run-frontend.cmd build
```

结果：build passed；仅保留既有 Vite chunk size warning。

浏览器验证记录：

- `http://localhost:5173/risk-feedback` 本地页面可返回 200。
- 本次尝试使用 Codex in-app Browser 做页面 DOM 验证时，浏览器运行时初始化阶段连续断开，未完成截图级验证。

下一阶段建议：

```text
继续 V2-D：文档与示例收口。
```

## 十二、V2-D 落地记录

落地时间：2026-06-11。

已完成：

- README 补充项目策略使用说明、前端验收路径、命令行验证步骤和策略注入验证方式。
- `docs/03-api-contract.md` 补充 Review Feedback 与项目策略 API，包括 `policyCandidate=true`、反馈状态、转策略限制、项目策略管理接口、rendered prompt `projectId` 预览和 `PROJECT_POLICIES_INJECTED` 进度事件。
- `docs/30-review-feedback-v2-policy-plan.md` 更新 V2-D 收口记录。
- 新增 `examples/project-review-policy-convert-request.json`，用于本地验证 `POST /api/risk-feedback/{feedbackId}/convert-to-policy`。
- `examples/README.md` 补充从反馈生成项目策略、查询策略和预览 Prompt 注入的示例。

已验证：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\contract\test_review_feedback_api_contract.py tests\contract\test_project_review_policy_api_contract.py tests\unit\test_project_review_policy_prompt.py tests\contract\test_code_quality_api_contract.py::test_rendered_prompt_can_preview_project_review_policies tests\contract\test_code_quality_api_contract.py::test_manual_review_injects_project_review_policies_and_records_progress
```

结果：13 passed。

```powershell
$env:NO_PAUSE="1"; .\scripts\run-frontend.cmd build
```

结果：build passed；仅保留既有 Vite chunk size warning。

V2-A 到 V2-D 已形成可验收闭环：

```text
任务详情提交反馈
  -> 反馈池筛选候选
  -> 生成项目策略
  -> 项目策略编辑 / 启停
  -> rendered prompt 预览策略注入
  -> 后续 AI Review progress 可见 PROJECT_POLICIES_INJECTED
```

下一阶段建议：

```text
V2-E 已完成；如继续增强，进入 V2-F：通用 Context Pack V0。
```

## 十三、V2-E 落地记录

落地时间：2026-06-11。

已完成：

- `review_item_feedbacks` 新增 `missing_context_types_json`，并补充运行期 schema 兜底和 bootstrap migration `V36__review_feedback_missing_context.sql`。
- 提交反馈时，当 `reasonType=CONTEXT_MISSING` 可记录 `missingContextTypes`；非上下文不足反馈不会保存该字段。
- 反馈池支持 `reasonType` 和 `missingContextType` 查询参数。
- 反馈池响应新增 `contextMissingStats`，包含上下文不足总数、风险类型分布和缺失上下文类型分布。
- 前端反馈弹窗在选择“上下文不足”时展示“缺失上下文”多选框。
- 前端反馈池新增“反馈原因”“缺失上下文”筛选和上下文不足统计展示。
- 本阶段不自动创建项目策略、不自动影响 Prompt、不自动改变风险等级。

新增和调整测试：

- `backend-python/tests/contract/test_review_feedback_api_contract.py`

已验证：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\contract\test_review_feedback_api_contract.py tests\contract\test_project_review_policy_api_contract.py
```

结果：7 passed。

```powershell
$env:NO_PAUSE="1"; .\scripts\run-frontend.cmd build
```

结果：build passed；仅保留既有 Vite chunk size warning。

下一阶段建议：

```text
V2-F-1 已完成；等待用户验收后再决定是否继续 V2-F 后续增强。
```

## 十四、V2-F-1 落地记录

落地时间：2026-06-11。

已完成：

- 新增 `backend-python/app/review_context/*`，构造通用 `reviewContext / contextPack`。
- AI Review 执行前构建 Context Pack，并注入 provider 输入。
- Context Pack V0 包含 changed files 摘要、同文件上下文可用性说明、上下文不足反馈统计摘要和 `unavailableContexts`。
- Context Pack 只使用当前任务 / 请求中已有的 changed files、diff 文本和同项目 `CONTEXT_MISSING` 反馈统计。
- 控制 Context Pack 预算：changed files 数量、反馈统计 bucket、路径长度和总 prompt 字符数均有上限。
- Prompt 明确 `Context Pack / reviewContext` 只是辅助证据，不能覆盖或削弱安全、数据一致性、事务一致性、线上正确性硬风险。
- progress 新增 `CONTEXT_PACK_BUILT`，detail 只记录 meta / summary / 数量，不记录 diff 正文或大段源码。

明确未做：

- 不做全项目扫描。
- 不做引用搜索、调用方 / 被调用方搜索。
- 不接向量库或 RAG。
- 不做自动降级。
- 不自动忽略 finding。
- 不自动改 Prompt。
- 不把 `CONTEXT_MISSING` 反馈转成项目策略。

新增和调整测试：

- `backend-python/tests/unit/test_review_context_pack.py`
- `backend-python/tests/unit/test_code_quality_prompt.py`
- `backend-python/tests/contract/test_code_quality_api_contract.py`

已验证：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_review_context_pack.py tests\unit\test_code_quality_prompt.py tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_injects_project_review_policies_and_records_progress tests\contract\test_code_quality_api_contract.py::test_deepseek_manual_review_saves_result_and_progress tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_uses_saved_changed_files
```

结果：13 passed。

下一阶段建议：

```text
V2-F-2 已完成；当前停止等待用户验收 V2-F-2。
```

## 十五、V2-F-2 落地记录

落地时间：2026-06-11。

已完成：

- Context Pack 支持在 GitLab API、项目 GitLab ID 和 head ref 可用时，为 changed files 读取同文件 raw file。
- 只读取当前任务 / 请求里的 changed files，不扫描全项目，不读取 related files。
- 只注入变更 hunk 附近有限窗口片段，默认上下各 30 行；不注入完整文件源码。
- 同文件上下文片段纳入总 Context Pack 预算；同时限制 source context 文件数、单文件片段数、单片段字符数和总字符数。
- GitLab API 未启用、base-url / token 缺失、head ref 缺失、删除文件、diff hunk 行号缺失、raw file 读取失败等场景均写入 `unavailableContexts`，不阻断 AI Review。
- `CONTEXT_PACK_BUILT` progress detail 继续只记录 meta / summary / 数量，包括 `sameFileSourceSnippetCount` 和 `sameFileSourceFileCount`，不记录源码片段。
- Prompt 继续声明 Context Pack 只是辅助证据，不能覆盖或削弱安全、数据一致性、事务一致性、线上正确性硬风险。

明确未做：

- 不做引用搜索。
- 不做调用方 / 被调用方搜索。
- 不做全项目扫描。
- 不接向量库或 RAG。
- 不自动降级。
- 不自动忽略 finding。
- 不自动改 Prompt。
- 不把 `CONTEXT_MISSING` 反馈转成项目策略。

新增和调整测试：

- `backend-python/tests/unit/test_review_context_pack.py`
- `backend-python/tests/contract/test_code_quality_api_contract.py`

已验证：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_review_context_pack.py tests\unit\test_code_quality_prompt.py tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_injects_project_review_policies_and_records_progress tests\contract\test_code_quality_api_contract.py::test_deepseek_manual_review_saves_result_and_progress tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_uses_saved_changed_files tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_includes_same_file_context_snippets
```

结果：15 passed。

下一阶段建议：

```text
V2-F-3 已完成；当前停止等待用户验收 V2-F-3。
```

## 十六、V2-F-3 落地记录

落地时间：2026-06-11。

已完成：

- 在 `reviewContext / contextPack` 中新增 Context Planner 最小输出：`contextPlan`、`plannerSignals`、`requestedContexts`。
- `contextPlan` 只保留版本、命中数量、requested context 类型统计、预算和 advisory note；详细 signals / requested contexts 只保留单份，避免重复撑大 Prompt。
- Planner 只基于当前 changed files、diff text、文件路径和同项目 `CONTEXT_MISSING` 反馈统计做轻量识别。
- 首批识别：
  - 删除方法：`METHOD_DELETED`
  - 方法签名变更：`METHOD_SIGNATURE_CHANGED`
  - 字段删除：`FIELD_DELETED`
  - DTO / request / response 字段变更：`DTO_FIELD_CHANGED`
  - DB / SQL / mapper 变更：`DB_SQL_MAPPER_CHANGED`
  - 缓存写入、过期、驱逐或删除变更：`CACHE_WRITE_DELETE_CHANGED`
  - MQ topic / queue / exchange / binding / consumer / producer 配置变更：`MQ_CONFIG_CHANGED`
  - 配置文件或 `@Value / @ConfigurationProperties` 变更：`CONFIG_FILE_CHANGED`
- 对当前阶段无法获取的上下文，将 planner 请求写入 `requestedContexts`，并把不可用说明合并进 `unavailableContexts`。
- Planner 输出遵守预算：signals、requested contexts、file paths、unavailable contexts 和最终 Context Pack prompt text 都有上限；超预算时仍优先保留类型统计和结构化信号。
- `CONTEXT_PACK_BUILT` progress detail 继续只记录 `meta / summary`，新增 planner 命中数量、requested context 类型统计、planner unavailable 数量，不记录 diff 正文或源码片段。
- Prompt 增加静态说明：Context Planner 只是缺失证据提示，不能作为自动忽略、自动降级或覆盖安全、数据一致性、事务一致性、线上正确性硬风险的依据。

明确未做：

- 不做全项目扫描。
- 不做引用搜索。
- 不读取 related files。
- 不接向量库 / RAG。
- 不做自动降级。
- 不自动忽略 finding。
- 不自动改 Prompt。
- 不把 `CONTEXT_MISSING` 反馈转项目策略。

新增和调整测试：

- `backend-python/tests/unit/test_review_context_pack.py`
- `backend-python/tests/unit/test_code_quality_prompt.py`
- `backend-python/tests/contract/test_code_quality_api_contract.py`

已验证：

```powershell
$env:NO_PAUSE='1'; .\scripts\run-backend.cmd test tests\unit\test_review_context_pack.py tests\unit\test_code_quality_prompt.py tests\contract\test_code_quality_api_contract.py::test_manual_review_builds_context_pack_and_records_progress tests\contract\test_code_quality_api_contract.py::test_manual_review_injects_project_review_policies_and_records_progress tests\contract\test_code_quality_api_contract.py::test_deepseek_manual_review_saves_result_and_progress tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_uses_saved_changed_files tests\contract\test_code_quality_api_contract.py::test_retry_gitlab_mr_ai_review_includes_same_file_context_snippets
```

结果：16 passed。

下一阶段建议：

```text
当前停止等待用户验收 V2-F-3；如继续增强 V2-F，优先按 `docs/34-local-repository-context-retrieval-plan.md` 推进本地仓库上下文检索 / 高准确 Review Spike。
```

## 十七、V2-F 后续路线调整：转向本地仓库上下文检索

调整时间：2026-06-11。

调整结论：

- V2-F-3 后不优先继续推进 V2.5 自动归因、V3 评估集或更多人工沉淀能力。
- 短期主线切换为 `docs/34-local-repository-context-retrieval-plan.md` 中定义的高准确 Review 模式。
- GitLab webhook / API 仍是任务和变更数据源；后端额外通过本地 mirror clone / fetch 和 task worktree 获取可搜索源码。
- Context Planner 继续负责判断“应该补什么证据”；Local Context Retriever 负责真正做本地引用搜索和源码片段检索；Context Pack 负责预算控制后注入 AI Review。
- 反馈池、项目策略、上下文不足人工标记等人工沉淀能力先不删除，但生产产品界面默认屏蔽，避免当前验证阶段的产品复杂度干扰高准确 Review 效果判断。

后续阶段以 docs/34 为准：

```text
V2-F-4：本地仓库检索主方案与前端人工沉淀熄灯
V2-F-5：本地仓库 mirror clone / fetch / worktree 最小闭环（已完成）
V2-F-6：METHOD_DELETED / METHOD_SIGNATURE_CHANGED 引用搜索 Retriever MVP（已完成）
V2-F-7：本地引用证据注入 Context Pack
V2-F-8：前端展示高准确模式证据摘要，并屏蔽人工沉淀入口
V2-F-9：生产验证与效果复盘
```

明确保留但默认不展示：

- Review Feedback API 与反馈表。
- Project Review Policy API 与项目策略表。
- 反馈池页面能力。
- 项目策略管理能力。
- 上下文不足人工标记能力。

明确不做：

- 不删除 V0 到 V2-F-3 已落地能力。
- 不把整个项目源码塞进 Prompt。
- 不做无限制全项目扫描。
- 不接向量库或复杂 RAG。
- 不自动降级、不自动忽略 finding、不自动改 Prompt。
