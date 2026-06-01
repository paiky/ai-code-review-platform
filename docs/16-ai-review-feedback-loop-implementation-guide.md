# AI Review 误判反馈闭环落地指引

> 状态说明：**Phase 1 尚未落地。** 本文描述 finding feedback 的实施切入点；完整产品方案见 `docs/14-ai-review-feedback-loop-plan.md`。当前 AI Review 结果尚无 fingerprint / feedback API。

日期：2026-05-11

## 1. 目的

本文是 `docs/14-ai-review-feedback-loop-plan.md` 的实施入口，用于后续新对话快速接续“AI Review 误判反馈闭环”开发。

`docs/14` 保留完整产品方案、数据结构、交互设计和长期演进；本文只描述基于当前代码状态的下一步落地顺序。

## 2. 当前代码基线

截至本文：

- 代码质量 AI Review 已使用 HTTP Provider，支持 OpenAI、Anthropic、DeepSeek、XiaoMIMO 和 Custom OpenAI-compatible。
- Provider 输入来自平台保存的 `diffText` / `changedFiles`，不再读取被审查项目本地仓库或 `HEAD`。
- AI Review 结果通过 `code_quality_review_results` 保存，核心字段包括 `findings_json`、`finding_count`、`raw_output`、`status`。
- 后端 response `CodeQualityReviewResultResponse` 当前直接返回 `findings` JSON，没有 finding fingerprint 和 feedback 信息。
- `CodeQualityFinding` 当前字段为 severity、category、filePath、startLine、endLine、title、body、suggestion、confidence、source。
- 还没有 finding feedback / review memory 表、API 和前端交互。

## 3. 新对话开始方式

建议新对话直接这样开始：

```text
请阅读 AGENTS.md、README.md、docs/14-ai-review-feedback-loop-plan.md、docs/16-ai-review-feedback-loop-implementation-guide.md，以及当前 codequality 模块代码。接下来先落地 AI Review 误判反馈闭环 Phase 1：finding fingerprint + feedback 存储/API + code quality result response 携带 feedback，先不做 review memory 和前端复杂管理页。
```

如果只读 `docs/14` 也可以，但不够理想。`docs/14` 是完整方案，范围较大；新对话应同时读本文，避免一上来做 Phase 2/3 或继续处理已被 diff-only 取代的 Codex 范围问题。

## 4. 推荐先落地 Phase 1

目标：

让用户能对某条 AI finding 标记“误判 / 不采纳”，并让任务结果查询能返回该 finding 的反馈状态。当前阶段只做后端闭环和最小 API，不做 review memory 注入。

优先级：

1. 新增 finding fingerprint 生成逻辑。
2. 新增 finding feedback 数据表、domain、repository、service。
3. 新增 feedback API。
4. 查询 code quality result 时，为每条 finding 补充 `fingerprint` 和 `feedback`。
5. `findingCount` 增加“有效问题数”语义：已标记 `FALSE_POSITIVE` / `NOT_ACTIONABLE` 的 finding 不计入有效数量。
6. 补 API 契约、README 示例和单元测试。

## 5. 后端改动建议

### 5.1 新增 bootstrap migration

新增：

```text
backend-python/migrations/bootstrap_sql/V33__code_quality_finding_feedbacks.sql
```

建议第一阶段只建 feedback 表：

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
  memory_enabled TINYINT(1) NOT NULL DEFAULT 0,
  scope_type VARCHAR(32) NULL,
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

说明：

- `memory_enabled` 第一阶段建议默认 `0` 或虽接收但暂不生成 memory，避免承诺 Phase 2 行为。
- `scope_type` / `scope_value` 可以先保留，为后续 review memory 复用。

### 5.2 新增 models / repository / service / api

建议新增：

```text
backend-python/app/code_quality/models.py
backend-python/app/code_quality/repository.py
backend-python/app/code_quality/service.py
backend-python/app/code_quality/api.py
```

第一阶段 action 至少支持：

```text
FALSE_POSITIVE
NOT_ACTIONABLE
```

可以先预留但不在 UI 暴露：

```text
ACCEPTED
FIXED
IGNORED
```

reasonType 建议先支持：

```text
EXPECTED_BEHAVIOR
EXISTING_GUARANTEE
TEST_COVERED
FRAMEWORK_CONVENTION
NOT_THIS_CHANGE
INACCURATE_DESCRIPTION
OTHER
```

### 5.3 Fingerprint 规则

建议实现稳定指纹：

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

细节：

- `normalizedFilePath`：`\` 转 `/`，trim，空值使用 `-`。
- `startLineBucket`：可按 10 行分桶；空值使用 `-`。
- `normalizedTitle`：trim，合并空白，去掉常见风险前缀。
- 第一阶段不要只用 finding index，否则后续跨任务反馈难复用。

## 6. API 建议

### 6.1 创建或更新 feedback

```http
POST /api/review-tasks/{taskId}/code-quality-findings/{fingerprint}/feedback
```

请求：

```json
{
  "action": "FALSE_POSITIVE",
  "reasonType": "EXPECTED_BEHAVIOR",
  "reasonText": "该逻辑由上游事务后置事件保证，本次 diff 没有改变事件发布逻辑。",
  "memoryEnabled": false,
  "scopeType": "FILE",
  "scopeValue": "src/main/java/com/demo/RefundServiceImpl.java"
}
```

行为：

- 校验 task 存在且已有 code quality result。
- 根据 result 中的 findings 重新计算 fingerprint，确认目标 fingerprint 存在。
- 同一 task + fingerprint 重复提交时更新 feedback。
- 第一阶段不生成 review memory，即使请求带 `memoryEnabled=true`，也可以保存字段但不触发后续动作。

### 6.2 查询任务 feedback

```http
GET /api/review-tasks/{taskId}/code-quality-finding-feedbacks
```

返回当前任务全部 feedback，供前端刷新状态。

### 6.3 删除 feedback

```http
DELETE /api/review-tasks/{taskId}/code-quality-findings/{fingerprint}/feedback
```

第一阶段可以物理删除，后续如果需要审计再改软删除。

## 7. Result Response 调整

调整 `backend-python/app/code_quality/repository.py` 的结果查询或其上层 service：

- 读取 `findings_json`。
- 为每条 finding 计算 `fingerprint`。
- 查询当前 task 的 feedback map。
- 给每条 finding 附加：

```json
{
  "fingerprint": "7f83b1...",
  "feedback": {
    "action": "FALSE_POSITIVE",
    "reasonType": "EXPECTED_BEHAVIOR",
    "reasonText": "该逻辑由上游保障。",
    "createdAt": "2026-05-11T23:00:00"
  }
}
```

有效 finding count：

- `FALSE_POSITIVE`、`NOT_ACTIONABLE` 不计入有效数量。
- 原始候选数量可以后续新增字段 `candidateFindingCount`，第一阶段如果不改 response 字段，可以先让 `findingCount` 表示有效数量。

## 8. 测试计划

至少补：

- `CodeQualityFindingFingerprintTest`
  - 路径分隔符归一化。
  - 行号小范围变化同 bucket。
  - title 空白归一化。
- `CodeQualityFindingFeedbackRepositoryTest`
  - 保存、更新、按 task 查询、删除。
- `CodeQualityFindingFeedbackServiceTest`
  - fingerprint 不存在时失败。
  - 重复提交更新。
  - reasonText 必填和长度校验。
- `CodeQualityReviewResultRepositoryTest` 或 service 测试
  - result response 中 finding 带 fingerprint。
  - feedback 合并到 finding。
  - 已取消 finding 不计入有效 findingCount。

## 9. 暂不做

第一阶段不要做：

- review memory 表和 prompt 注入。
- 规则建议聚合。
- 前端复杂管理页。
- GitLab MR discussion 同步。
- 让 AI 自动修改 prompt 或规则。

## 10. 验收标准

- 用户可以对某个 AI finding 提交 `FALSE_POSITIVE` 或 `NOT_ACTIONABLE`。
- 刷新任务详情后，该 finding 仍带 feedback 状态。
- 已取消 finding 不计入有效 findingCount。
- 删除 feedback 后，该 finding 恢复为有效。
- 后端测试通过：

```powershell
.\scripts\run-backend.cmd -q test
```
