# AI Review 误判反馈闭环方案

> 状态说明：本文是**尚未实现**的产品方案。当前代码库还没有 finding feedback / review memory 表与 API；如需落地请先读 `docs/16-ai-review-feedback-loop-implementation-guide.md`。

日期：2026-05-10

> 2026-05-11 补充：后续实施请优先阅读 `docs/16-ai-review-feedback-loop-implementation-guide.md`。本文保留完整产品方案，`docs/16` 记录当前代码基线和 Phase 1 落地切入点。

## 1. 背景

代码质量 AI Review 当前已使用 HTTP Provider，支持 OpenAI、Anthropic、DeepSeek、XiaoMIMO 和 Custom OpenAI-compatible，并支持 profile、prompt、执行过程和前端结果展示。历史 `CODEX_CLI` 已停用。

但 AI Review 的结论天然存在不确定性：

- 可能把团队认可的实现判定为质量问题。
- 可能缺少项目上下文，例如框架约定、上游保障、历史兼容策略。
- 可能重复报告已经被团队确认无需处理的问题。
- 可能把“提醒型变更”和“代码质量缺陷”混在一起。

所以后续不能只依赖一份更长的 prompt 来解决误判问题。更稳妥的方向是建立“人工反馈 -> 审查记忆 -> Prompt 注入 -> 规则沉淀”的闭环。

## 2. 调研结论

市面上较成熟的 AI Code Review 产品通常不会把“AI 自己自动改规则”作为默认路径，而是采用以下机制组合：

- 团队级审查偏好或 learnings：把团队反馈沉淀为后续审查上下文。
- Repository / Project 级 custom instructions：通过项目级指令约束输出范围。
- 对评论进行人工反馈：标记误报、不采纳或已处理。
- 聚焦 actionable findings：尽量只报告会造成线上问题、安全问题、数据一致性问题、测试缺口的问题。
- 保留人工 reviewer 的最终判断权：AI 负责候选问题，不直接替代人工裁决。

对当前系统来说，推荐方案是：

```text
AI 提出候选质量问题
  -> 人在前端标记误判或不采纳
  -> 后端保存结构化反馈
  -> 下次 Review 前按项目、文件、分类检索相关反馈
  -> 把反馈作为审查记忆注入 Agent Prompt
  -> 周期性聚合为候选规则优化
  -> 人工确认后才固化到 Profile / Prompt / 规则模板
```

不建议让 AI 在每次 Review 时自动改本地规则。误判理由经常只适用于某个项目、某类代码或某次上下文，自动固化容易把规则越改越偏。

## 3. 目标

### 3.1 产品目标

- 允许用户在前端取消某条 AI 代码质量问题。
- 取消时必须填写原因，避免只删除不沉淀。
- 取消后的问题不再作为当前任务的有效问题展示。
- 取消原因沉淀为项目级审查记忆。
- 后续 AI Review 能读取相关审查记忆，降低重复误报。
- 管理员可以查看、启用、禁用、归档审查记忆。
- 高频误判可以被聚合成候选规则调整，但需要人工确认后生效。

### 3.2 非目标

- 不让 AI 自动修改数据库中的正式规则模板。
- 不让 AI 自动修改 profile prompt。
- 不在第一阶段做复杂向量检索。
- 不在第一阶段把反馈同步到 GitLab MR discussion。
- 不把“取消”理解为真实代码问题已修复；取消只表示当前团队不采纳该 AI 结论。

## 4. 核心概念

### 4.1 AI Finding

AI provider 输出的候选代码质量问题。

当前系统中对应 `code_quality_review_results.findings_json` 里的每一项。

### 4.2 Finding Feedback

用户对某条 AI Finding 的处理反馈。

典型动作：

- `FALSE_POSITIVE`：误判，不是质量问题。
- `NOT_ACTIONABLE`：描述不够可执行，暂不采纳。
- `ACCEPTED`：认可该问题。
- `FIXED`：问题已处理。
- `IGNORED`：已知问题，本次不处理。

第一阶段重点落地 `FALSE_POSITIVE` 和 `NOT_ACTIONABLE`。

### 4.3 Review Memory

从人工反馈中沉淀出的审查记忆。

它不是正式规则，而是下次 AI Review 的上下文材料。它的语气应该是“过去团队认为以下情况通常不是问题”，而不是“永远不要报告”。

示例：

```text
项目 ljdw-client-internal 中，RefundServiceImpl 的部分缓存删除逻辑由上游事务后置事件保证一致性。
除非本次变更移除了事件发布或改变了 key 生成逻辑，否则不要重复报告“缓存删除时机不一致”。
```

### 4.4 Rule Suggestion

由系统根据多条反馈聚合出的候选规则调整。

它需要人工确认，确认后才可以写入：

- AI Review Profile prompt
- 项目级 prompt 附加说明
- 规则模板配置
- 忽略路径或忽略模式

## 5. 推荐交互设计

### 5.1 AI Review 结果卡片

每条 AI 质量问题增加操作：

- 认可
- 误判
- 不采纳
- 复制问题

第一阶段可以只做：

- `误判`
- `不采纳`

点击后弹出表单：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| 处理类型 | 是 | 误判 / 不采纳 |
| 原因分类 | 是 | 预期行为 / 已有保障 / 测试已覆盖 / 框架约定 / 非本次变更 / 描述不准确 / 其他 |
| 详细原因 | 是 | 用户填写具体说明 |
| 是否用于后续审查记忆 | 否 | 默认开启 |
| 适用范围 | 是 | 当前文件 / 当前目录 / 当前项目 |

提交后：

- 当前 finding 标记为已取消。
- 默认从“有效问题数”中扣除。
- 在卡片上显示“已标记误判”或“已不采纳”。
- 保留查看原始 AI 结论的入口。

### 5.2 结果统计

AI Review 结果区建议拆分统计：

```text
发现 6 条候选问题，当前有效 4 条，已取消 2 条。
```

这样可以保留审计痕迹，又不会让误判继续干扰用户判断。

### 5.3 审查记忆管理页

可以放在“模板配置”中新增一个 Tab：

- AI Review Profile
- 审查记忆
- API Key
- 全局设置

审查记忆列表字段：

| 字段 | 说明 |
| --- | --- |
| 项目 | 关联项目 |
| 分类 | TRANSACTION / SQL / CACHE / MQ / SECURITY / TEST 等 |
| 文件范围 | 文件、目录或 glob |
| 摘要 | 由用户原因或系统摘要生成 |
| 状态 | ENABLED / DISABLED / ARCHIVED |
| 来源 | 来自哪条 finding feedback |
| 命中次数 | 后续 Review 被注入或参考的次数 |
| 更新时间 | 最近更新时间 |

操作：

- 启用 / 禁用
- 编辑摘要
- 调整适用范围
- 归档

## 6. 后端数据结构

### 6.1 新增表：`code_quality_finding_feedbacks`

用于保存用户对某条 AI finding 的处理反馈。

```sql
CREATE TABLE code_quality_finding_feedbacks (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  project_id BIGINT NOT NULL,
  finding_fingerprint VARCHAR(128) NOT NULL,
  finding_index INT NOT NULL,
  action VARCHAR(32) NOT NULL,
  reason_type VARCHAR(64) NOT NULL,
  reason_text TEXT NOT NULL,
  memory_enabled TINYINT(1) NOT NULL DEFAULT 1,
  scope_type VARCHAR(32) NOT NULL,
  scope_value VARCHAR(512) NULL,
  operator_name VARCHAR(128) NULL,
  operator_username VARCHAR(128) NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_task_finding_feedback (task_id, finding_fingerprint),
  KEY idx_project_action (project_id, action),
  KEY idx_project_created_at (project_id, created_at)
);
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `finding_fingerprint` | finding 的稳定指纹，避免依赖数组下标 |
| `finding_index` | 原始 findings_json 中的位置，便于兼容展示 |
| `action` | `FALSE_POSITIVE` / `NOT_ACTIONABLE` / `ACCEPTED` / `FIXED` / `IGNORED` |
| `reason_type` | 原因分类 |
| `memory_enabled` | 是否允许生成或更新审查记忆 |
| `scope_type` | `FILE` / `DIRECTORY` / `PROJECT` |
| `scope_value` | 文件路径、目录路径；项目级可为空 |

### 6.2 新增表：`code_quality_review_memories`

用于保存可注入 Prompt 的审查记忆。

```sql
CREATE TABLE code_quality_review_memories (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  category VARCHAR(64) NULL,
  title VARCHAR(255) NOT NULL,
  memory_text TEXT NOT NULL,
  scope_type VARCHAR(32) NOT NULL,
  scope_value VARCHAR(512) NULL,
  status VARCHAR(32) NOT NULL,
  source_feedback_id BIGINT NULL,
  hit_count INT NOT NULL DEFAULT 0,
  last_hit_at DATETIME NULL,
  created_by VARCHAR(128) NULL,
  updated_by VARCHAR(128) NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  KEY idx_project_status (project_id, status),
  KEY idx_project_category (project_id, category),
  KEY idx_source_feedback (source_feedback_id)
);
```

状态：

- `ENABLED`：可用于 Prompt 注入。
- `DISABLED`：保留但不注入。
- `ARCHIVED`：历史归档。

### 6.3 Finding 指纹生成

建议后端生成稳定指纹：

```text
sha256(
  provider + "\n" +
  profileCode + "\n" +
  severity + "\n" +
  category + "\n" +
  normalizedFilePath + "\n" +
  startLineBucket + "\n" +
  normalizedTitle
)
```

说明：

- `startLineBucket` 可按 5 行或 10 行分桶，降低小范围行号变化带来的失配。
- `normalizedTitle` 去掉空白、标点差异和风险等级前缀。
- 第一阶段也可以使用 `taskId + findingIndex`，但不利于跨任务识别重复误判。

## 7. API 设计

### 7.1 标记 finding 反馈

```http
POST /api/review-tasks/{taskId}/code-quality-findings/{fingerprint}/feedback
Content-Type: application/json
```

请求：

```json
{
  "action": "FALSE_POSITIVE",
  "reasonType": "EXPECTED_BEHAVIOR",
  "reasonText": "该缓存删除由事务后置事件统一处理，本次变更没有改变事件发布逻辑。",
  "memoryEnabled": true,
  "scopeType": "FILE",
  "scopeValue": "src/main/java/com/demo/RefundServiceImpl.java"
}
```

响应：

```json
{
  "id": 1,
  "taskId": 10001,
  "findingFingerprint": "7f83b1...",
  "action": "FALSE_POSITIVE",
  "memoryId": 10
}
```

### 7.2 查询任务 finding 反馈

```http
GET /api/review-tasks/{taskId}/code-quality-finding-feedbacks
```

响应：

```json
[
  {
    "findingFingerprint": "7f83b1...",
    "action": "FALSE_POSITIVE",
    "reasonType": "EXPECTED_BEHAVIOR",
    "reasonText": "该缓存删除由事务后置事件统一处理。",
    "memoryEnabled": true,
    "createdAt": "2026-05-10T12:00:00"
  }
]
```

### 7.3 撤销反馈

```http
DELETE /api/review-tasks/{taskId}/code-quality-findings/{fingerprint}/feedback
```

行为：

- 删除或软删除当前任务上的反馈。
- 如果该反馈生成了 review memory，默认不自动删除 memory，只把 source feedback 保留为历史来源。
- 前端可以提供“同时禁用对应审查记忆”的复选项，第二阶段再做。

### 7.4 查询审查记忆

```http
GET /api/code-quality-review-memories?projectId=1&status=ENABLED&pageNo=1&pageSize=20
```

### 7.5 更新审查记忆

```http
PUT /api/code-quality-review-memories/{memoryId}
Content-Type: application/json
```

请求：

```json
{
  "title": "RefundService 缓存删除由事务后置事件保证",
  "memoryText": "RefundServiceImpl 中的缓存删除由事务后置事件统一处理。除非本次变更移除了事件发布或改变 key 生成逻辑，否则不要重复报告缓存删除时机不一致。",
  "scopeType": "FILE",
  "scopeValue": "src/main/java/com/demo/RefundServiceImpl.java",
  "status": "ENABLED"
}
```

## 8. Prompt 注入策略

### 8.1 检索策略

每次 AI Review 执行前，根据以下条件检索审查记忆：

- `projectId` 必须匹配。
- `status = ENABLED`。
- `scopeType = PROJECT` 直接候选。
- `scopeType = DIRECTORY` 时，changed file 在该目录下才候选。
- `scopeType = FILE` 时，changed file 精确命中或路径归一化后命中。
- `category` 与本次 finding 还未生成，所以第一阶段只能按 changed files 和 profile category 过滤。

数量控制：

- 最多注入 10 条。
- 每条最多 300 字。
- 总长度最多 3000 字。
- 优先级：文件级 > 目录级 > 项目级，最近命中 > 最近创建。

### 8.2 Prompt 文案

建议插入到“用户自定义审核规则”之后、“输出要求”之前。

```text
历史误判参考：
以下是本项目过去被团队标记为误判或不采纳的审查结论。它们不是绝对规则，但你必须参考。
除非本次变更出现新的明确证据，否则不要重复报告相同类型的问题。

1. [缓存一致性][src/main/java/com/demo/RefundServiceImpl.java]
RefundServiceImpl 中的缓存删除由事务后置事件统一处理。除非本次变更移除了事件发布或改变 key 生成逻辑，否则不要重复报告缓存删除时机不一致。

2. [SQL][src/main/java/com/demo/OrderMapper.xml]
该查询只用于后台离线任务，调用方保证时间范围不超过一天。除非本次变更扩大查询范围，否则不要仅因缺少分页报告问题。
```

### 8.3 注入边界

Prompt 中必须声明：

- 历史误判参考不是豁免全部问题。
- 如果本次变更引入了新的明确风险，仍然要报告。
- 不得因为存在历史误判就忽略安全、数据损坏、事务不一致等高风险问题。

建议加一段保护：

```text
注意：历史误判参考只用于降低重复误报。若本次 diff 明确引入数据损坏、安全漏洞、事务不一致、缓存/MQ 不一致或测试缺口，仍必须报告。
```

## 9. 规则沉淀策略

### 9.1 不自动改正式规则

正式规则包括：

- `code_quality_review_profiles.review_instructions`
- `rule_templates`
- 项目默认 profile

这些都不应由 AI 自动修改。

### 9.2 候选规则建议

后续可以新增表 `code_quality_rule_suggestions`：

```sql
CREATE TABLE code_quality_rule_suggestions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  suggestion_type VARCHAR(64) NOT NULL,
  title VARCHAR(255) NOT NULL,
  suggestion_text TEXT NOT NULL,
  evidence_count INT NOT NULL,
  status VARCHAR(32) NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL
);
```

触发条件示例：

- 同一项目、同一 category、相似 title 的误判超过 5 次。
- 同一文件目录下同类误判超过 3 次。
- 同一 profile 中相同规则描述被多次不采纳。

管理员确认后：

- 可以转成 review memory。
- 可以追加到项目级 prompt。
- 可以更新默认 profile。
- 可以加入 ignored paths 或 category 过滤。

## 10. 前端改动点

### P0：结果展示支持反馈状态

改动范围：

- AI Review 结果列表。
- Finding 卡片。
- 结果统计区域。

能力：

- 每条 finding 显示反馈状态。
- 已取消 finding 默认折叠或置灰。
- 有开关可显示“已取消项”。
- finding 数量拆成候选数量、有效数量、已取消数量。

### P1：误判 / 不采纳弹窗

弹窗字段：

- 处理类型
- 原因分类
- 详细原因
- 是否沉淀为审查记忆
- 适用范围

校验：

- 详细原因至少 10 个字符。
- 选择“当前文件”时 finding 必须有 filePath。
- 选择“当前目录”时从 filePath 自动推导，可允许用户编辑。

### P2：审查记忆管理

放在模板配置页中。

能力：

- 按项目筛选。
- 按状态筛选。
- 编辑 memory 文案。
- 启用 / 禁用 / 归档。
- 查看来源 feedback。

### P3：Prompt 预览展示审查记忆

当前已有 rendered prompt 预览能力。后续需要让预览接口支持：

```http
GET /api/code-quality-review-profiles/{profileCode}/rendered-prompt?taskId=10001&includeMemories=true
```

前端在预览中展示：

- 基础 profile prompt。
- 动态审查范围。
- 注入的历史误判参考。
- 输出格式约束。

## 11. 后端改动点

### P0：Finding 指纹与反馈存储

新增：

- `CodeQualityFindingFingerprint`
- `CodeQualityFindingFeedback`
- `CodeQualityFindingFeedbackRepository`
- `CodeQualityFindingFeedbackService`
- `CodeQualityFindingFeedbackController`

调整：

- 查询 code quality result 时，为每条 finding 补充 `fingerprint` 和 `feedback`。
- 如果 finding 已被 `FALSE_POSITIVE` 或 `NOT_ACTIONABLE`，则有效 finding count 不包含它。

### P1：Review Memory 存储与生成

新增：

- `CodeQualityReviewMemory`
- `CodeQualityReviewMemoryRepository`
- `CodeQualityReviewMemoryService`
- `CodeQualityReviewMemoryController`

行为：

- 用户提交反馈且 `memoryEnabled=true` 时，生成一条 `ENABLED` memory。
- 第一阶段 memory 文案直接使用用户填写的原因，不调用 AI 二次总结。
- 后续可以加入 AI 摘要，但必须让用户可编辑。

### P2：Provider 请求前注入 memory

调整：

- `backend-python/app/code_quality/service.py`
- `backend-python/app/code_quality/prompt.py`
- `backend-python/app/code_quality/providers.py`
- `backend-python/app/code_quality/repository.py`

建议实现方式：

- 在构造 `CodeQualityReviewRequest` 时增加 `reviewMemories` 字段。
- provider 层只负责把 `reviewMemories` 拼进最终 prompt。
- rendered prompt 接口也走同一套拼装逻辑，避免预览和实际执行不一致。

### P3：审计与安全

需要记录：

- 谁取消了 finding。
- 取消理由。
- 是否用于后续记忆。
- 哪些 memory 被注入了某次 review。

建议新增表：

```sql
CREATE TABLE code_quality_review_memory_usages (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  memory_id BIGINT NOT NULL,
  created_at DATETIME NOT NULL,
  UNIQUE KEY uk_task_memory (task_id, memory_id)
);
```

用途：

- 任务详情中可解释“本轮使用了哪些历史误判参考”。
- 后续判断某条 memory 是否真的降低了误报。

## 12. API 契约补充点

后续实施时需要同步更新 `docs/03-api-contract.md`：

- Code Quality Finding Feedback API。
- Code Quality Review Memory API。
- Code Quality Result response 中的 finding feedback 字段。
- Rendered Prompt API 的 `includeMemories` 参数。

建议 response 中 finding 增加：

```json
{
  "fingerprint": "7f83b1...",
  "severity": "MAJOR",
  "category": "CACHE",
  "filePath": "src/main/java/com/demo/RefundServiceImpl.java",
  "title": "缓存删除时机可能导致脏读",
  "body": "...",
  "feedback": {
    "action": "FALSE_POSITIVE",
    "reasonType": "EXPECTED_BEHAVIOR",
    "reasonText": "该缓存删除由事务后置事件统一处理。",
    "createdAt": "2026-05-10T12:00:00"
  }
}
```

## 13. 测试计划

### 13.1 单元测试

- Finding fingerprint 稳定性测试。
- 相同 finding 在行号小幅变化时是否生成相同或可匹配指纹。
- feedback repository 保存、更新、查询测试。
- review memory repository 状态过滤测试。
- memory 检索按文件、目录、项目作用域排序测试。
- prompt 注入长度限制测试。

### 13.2 集成测试

- 创建 AI Review 结果后，标记某条 finding 为误判。
- 再次查询结果，确认有效 finding count 减少。
- 标记误判后生成 review memory。
- 重新触发审阅时，确认 rendered prompt 中包含相关 memory。
- 禁用 memory 后，确认后续 prompt 不再注入。

### 13.3 前端验证

- 误判弹窗必填校验。
- 已取消 finding 折叠展示。
- 显示 / 隐藏已取消项。
- 审查记忆列表的启用、禁用、编辑。
- Prompt 预览能看到注入的历史误判参考。

## 14. 分阶段落地建议

### Phase 1：最小反馈闭环

目标：让用户可以取消 AI 误判，并保存结构化原因。

改动：

- 新增 `code_quality_finding_feedbacks`。
- AI Review 结果返回 finding fingerprint 和 feedback。
- 前端增加“误判 / 不采纳”操作。
- 当前任务有效 finding count 排除已取消项。

验收：

- 用户能取消一条 finding。
- 刷新页面后取消状态仍存在。
- 已取消项不会计入当前有效问题数。

### Phase 2：审查记忆注入

目标：让下一轮 AI Review 能参考历史误判。

改动：

- 新增 `code_quality_review_memories`。
- 提交反馈时生成 memory。
- Review 执行前检索相关 memory。
- Prompt 拼装注入“历史误判参考”。
- rendered prompt 可预览注入内容。

验收：

- 对同一项目重新触发审阅时，prompt 中包含相关 memory。
- 禁用 memory 后不再注入。
- 单次注入数量和长度受控。

### Phase 3：审查记忆管理页

目标：让团队能维护沉淀下来的记忆。

改动：

- 模板配置页新增“审查记忆”区域。
- 支持项目筛选、编辑、启用、禁用、归档。
- 显示来源 finding 和命中次数。

验收：

- 管理员可以调整 memory 文案和范围。
- 禁用/归档立即影响后续 prompt 注入。

### Phase 4：规则建议沉淀

目标：把高频误判聚合成可人工确认的规则优化建议。

改动：

- 统计高频误判。
- 生成候选规则建议。
- 管理员确认后写入 profile prompt 或项目级附加说明。

验收：

- 系统能列出高频误判建议。
- 人工确认前不会改变正式规则。

## 15. 推荐优先级

建议下一步直接从 Phase 1 开始。

原因：

- 工作量可控。
- 不依赖复杂模型能力。
- 立刻改善前端使用体验。
- 为后续 Prompt 注入和规则沉淀提供真实数据。

优先级排序：

1. `P0`：Finding feedback 数据结构、API、前端取消操作。
2. `P1`：Review memory 表和最小生成逻辑。
3. `P2`：Prompt 注入和 rendered prompt 预览。
4. `P3`：审查记忆管理页。
5. `P4`：规则建议聚合。

## 16. 风险与注意事项

- 误判反馈可能包含敏感业务信息，必须避免在日志中完整打印。
- Prompt 注入过多历史记忆会稀释本轮 diff 关注点，需要严格限长。
- 文件路径重命名会影响 memory 命中，后续可增加目录级和项目级补偿。
- 用户误把真实问题标记为误判时，系统不能永久屏蔽高风险问题。
- 审查记忆应该支持禁用和归档，避免错误经验长期污染审查。
- 对安全漏洞、数据损坏、事务不一致等高风险类别，Prompt 中必须保留“有明确证据仍要报告”的保护条款。

## 17. 一句话结论

不要追求一份万能 AI Code Review prompt，也不要让 AI 自动改规则。当前系统最适合演进为“AI 候选问题 + 人工反馈 + 项目级审查记忆 + 人工确认的规则沉淀”。
