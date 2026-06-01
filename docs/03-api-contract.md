# MVP API 契约

## 1. 通用约定

### 1.1 Base URL

```text
/api
```

### 1.2 响应结构

所有平台 API 使用统一响应结构。

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {},
  "traceId": "20260419120000-demo"
}
```

失败响应示例：

```json
{
  "success": false,
  "code": "PROJECT_NOT_FOUND",
  "message": "Project is not registered",
  "data": null,
  "traceId": "20260419120000-demo"
}
```

### 1.3 分页响应

```json
{
  "items": [],
  "pageNo": 1,
  "pageSize": 20,
  "total": 0
}
```

## 2. GitLab Webhook API

### 2.1 接收 Merge Request webhook

```http
POST /api/webhooks/gitlab/merge-request
```

请求头：

```text
X-Gitlab-Event: Merge Request Hook
X-Gitlab-Token: optional-secret-token
```

请求体：GitLab Merge Request webhook 原始 payload。平台只依赖其中的核心字段，不要求前端调用。

关键字段映射：

```json
{
  "object_kind": "merge_request",
  "project": {
    "id": 1001,
    "name": "demo-service",
    "web_url": "https://gitlab.example.com/group/demo-service"
  },
  "object_attributes": {
    "iid": 12,
    "action": "open",
    "source_branch": "feature/risk-demo",
    "target_branch": "main",
    "last_commit": {
      "id": "abcdef123456"
    },
    "url": "https://gitlab.example.com/group/demo-service/-/merge_requests/12"
  },
  "user": {
    "name": "Alice",
    "username": "alice"
  }
}
```

成功响应：

```json
{
  "success": true,
  "code": "OK",
  "message": "Review task created",
  "data": {
    "taskId": 10001,
    "status": "PENDING"
  },
  "traceId": "20260419120000-demo"
}
```

说明：

- MVP 可在该接口内同步执行完整审查，也可创建任务后由 `ReviewJobExecutor` 执行。
- 若 webhook action 为 close、merge 等非审查触发动作，可返回 `SKIPPED`。

## 3. Review Task API

### 3.1 查询审查任务列表

```http
GET /api/review-tasks
```

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| projectId | Long | 否 | 项目 ID |
| status | String | 否 | PENDING / RUNNING / SUCCESS / FAILED |
| reviewStatus | String[] | 否 | 可重复传入；NOT_TRIGGERED / REVIEWING / NO_RISK / MINOR / MAJOR / CRITICAL / SKIPPED / REVIEW_FAILED / TASK_FAILED |
| riskLevel | String | 否 | NONE / LOW / MEDIUM / HIGH / CRITICAL |
| keyword | String | 否 | 项目名、分支、MR 关键字 |
| pageNo | Integer | 否 | 默认 1 |
| pageSize | Integer | 否 | 默认 20 |

响应 data：

```json
{
  "items": [
    {
      "id": 10001,
      "projectId": 1,
      "projectName": "demo-service",
      "triggerType": "GITLAB_MR_WEBHOOK",
      "externalSourceId": "12",
      "externalUrl": "https://gitlab.example.com/group/demo-service/-/merge_requests/12",
      "sourceBranch": "feature/risk-demo",
      "targetBranch": "main",
      "authorName": "Alice",
      "templateCode": "backend-default",
      "status": "SUCCESS",
      "reviewStatus": "CRITICAL",
      "riskLevel": "HIGH",
      "riskItemCount": 3,
      "createdAt": "2026-04-19T12:00:00+08:00",
      "finishedAt": "2026-04-19T12:00:08+08:00"
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

### 3.2 查询审查任务详情

```http
GET /api/review-tasks/{taskId}
```

响应 data：

```json
{
  "id": 10001,
  "projectId": 1,
  "projectName": "demo-service",
  "triggerType": "GITLAB_MR_WEBHOOK",
  "externalSourceId": "12",
  "externalUrl": "https://gitlab.example.com/group/demo-service/-/merge_requests/12",
  "sourceBranch": "feature/risk-demo",
  "targetBranch": "main",
  "commitSha": "abcdef123456",
  "authorName": "Alice",
  "authorUsername": "alice",
  "templateCode": "backend-default",
  "status": "SUCCESS",
  "riskLevel": "HIGH",
  "errorMessage": null,
  "createdAt": "2026-04-19T12:00:00+08:00",
  "startedAt": "2026-04-19T12:00:01+08:00",
  "finishedAt": "2026-04-19T12:00:08+08:00"
}
```

### 3.3 查询审查结果

```http
GET /api/review-tasks/{taskId}/result
```

响应 data：

```json
{
  "taskId": 10001,
  "riskLevel": "HIGH",
  "riskItemCount": 3,
  "summary": "本次 MR 修改了订单接口、订单表 SQL 和 Redis 缓存逻辑。",
  "changeAnalysis": {
    "changeTypes": ["API", "DB", "CACHE"],
    "changedFileCount": 4,
    "impactedResources": []
  },
  "riskCard": {}
}
```

### 3.4 重新触发审阅

```http
POST /api/review-tasks/{taskId}/rerun
```

基于已有 GitLab MR / Push 任务保存的 raw payload 和 changed files 摘要创建一条新的审查任务，用于调试规则、钉钉模板和前端展示。当前不支持手动任务 replay。

响应 data：

```json
{
  "sourceTaskId": 10001,
  "taskId": 10002,
  "status": "SUCCESS",
  "triggerType": "GITLAB_MR_WEBHOOK"
}
```

## 4. Project API

### 4.1 查询项目列表

```http
GET /api/projects
```

响应 data：

```json
{
  "items": [
    {
      "id": 1,
      "name": "demo-service",
      "gitProvider": "GITLAB",
      "gitProjectId": "1001",
      "repositoryUrl": "https://gitlab.example.com/group/demo-service",
      "defaultTemplateCode": "backend-default",
      "status": "ENABLED"
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

### 4.2 创建项目接入配置

```http
POST /api/projects
```

请求体：

```json
{
  "name": "demo-service",
  "gitProvider": "GITLAB",
  "gitProjectId": "1001",
  "repositoryUrl": "https://gitlab.example.com/group/demo-service",
  "defaultTemplateCode": "backend-default",
  "dingTalkWebhookId": 1,
  "description": "订单服务"
}
```

响应 data：

```json
{
  "id": 1
}
```

## 4.3 项目组 AI Review 模型配置

```http
GET /api/project-groups
POST /api/project-groups
PUT /api/project-groups/{groupId}
```

项目组响应和创建 / 更新请求支持 `aiReviewModels`：

```json
{
  "groupName": "后端业务组",
  "groupCode": "backend",
  "defaultCodeQualityProfileCode": "backend-default-ai-review",
  "defaultProviderCode": "DEEPSEEK",
  "aiReviewModels": [
    {
      "reviewKey": "deepseek-main",
      "providerCode": "DEEPSEEK",
      "modelName": "deepseek-v4-pro",
      "displayName": "DeepSeek 主审",
      "enabled": true,
      "sortOrder": 10
    }
  ]
}
```

说明：

- `defaultProviderCode` 继续保留作旧数据和旧调用方兼容；未配置 `aiReviewModels` 时会回退为单模型执行项。
- `providerCode` 必填；`modelName` 为空时使用 Profile / Provider 默认模型；`displayName` 用于任务详情模型子 tab。
- 同一项目组内 `reviewKey` 稳定标识模型结果；未传时后端根据 provider / model 自动生成。

## 5. Rule Template API

### 5.1 查询规则模板列表

```http
GET /api/rule-templates
```

响应 data：

```json
{
  "items": [
    {
      "id": 1,
      "templateCode": "backend-default",
      "templateName": "后端默认审查模板",
      "targetType": "BACKEND",
      "version": 1,
      "enabledRuleCodes": [
        "API_COMPATIBILITY_CHECK",
        "DB_SCHEMA_CHANGE_CHECK",
        "DB_SQL_CHANGE_CHECK",
        "ORM_MAPPING_CHANGE_CHECK",
        "ENTITY_MODEL_CHANGE_CHECK",
        "DATA_MIGRATION_CHECK",
        "DB_SCHEMA_SYNC_SUSPECT_CHECK",
        "CACHE_KEY_CHANGE_CHECK",
        "CACHE_TTL_CHANGE_CHECK",
        "CACHE_INVALIDATION_CHANGE_CHECK",
        "CACHE_READ_WRITE_CHANGE_CHECK",
        "CACHE_SERIALIZATION_CHANGE_CHECK",
        "MQ_PRODUCER_CHANGE_CHECK",
        "MQ_CONSUMER_CHANGE_CHECK",
        "MQ_MESSAGE_SCHEMA_CHANGE_CHECK",
        "MQ_TOPIC_CONFIG_CHANGE_CHECK",
        "MQ_RETRY_DLQ_CHANGE_CHECK",
        "CONFIG_RELEASE_CHECK"
      ],
      "status": "ENABLED"
    }
  ],
  "pageNo": 1,
  "pageSize": 20,
  "total": 1
}
```

### 5.2 查询规则模板详情

```http
GET /api/rule-templates/{templateCode}
```

响应 data：

```json
{
  "templateCode": "backend-default",
  "templateName": "后端默认审查模板",
  "targetType": "BACKEND",
  "version": 1,
  "enabledRuleCodes": [
    "API_COMPATIBILITY_CHECK",
    "DB_SCHEMA_CHANGE_CHECK",
    "DB_SQL_CHANGE_CHECK",
    "ORM_MAPPING_CHANGE_CHECK",
    "ENTITY_MODEL_CHANGE_CHECK",
    "DATA_MIGRATION_CHECK",
    "DB_SCHEMA_SYNC_SUSPECT_CHECK",
    "CACHE_KEY_CHANGE_CHECK",
    "CACHE_TTL_CHANGE_CHECK",
    "CACHE_INVALIDATION_CHANGE_CHECK",
    "CACHE_READ_WRITE_CHANGE_CHECK",
    "CACHE_SERIALIZATION_CHANGE_CHECK",
    "MQ_PRODUCER_CHANGE_CHECK",
    "MQ_CONSUMER_CHANGE_CHECK",
    "MQ_MESSAGE_SCHEMA_CHANGE_CHECK",
    "MQ_TOPIC_CONFIG_CHANGE_CHECK",
    "MQ_RETRY_DLQ_CHANGE_CHECK",
    "CONFIG_RELEASE_CHECK"
  ],
  "config": {
    "focusChangeTypes": ["API", "DB", "DB_SCHEMA", "DB_SQL", "ORM_MAPPING", "ENTITY_MODEL", "DATA_MIGRATION", "CACHE", "CACHE_KEY", "CACHE_TTL", "CACHE_INVALIDATION", "CACHE_READ_WRITE", "CACHE_SERIALIZATION", "MQ", "MQ_PRODUCER", "MQ_CONSUMER", "MQ_MESSAGE_SCHEMA", "MQ_TOPIC_CONFIG", "MQ_RETRY_DLQ", "CONFIG"],
    "defaultRiskLevel": "LOW"
  }
}
```

## 6. Notification API

钉钉推送当前使用 Markdown 消息。规则审查主要依据 RiskCard 中由规则命中的 `riskItems` 生成“提醒”展示，消息标题固定为“变更提醒”，正文包含作者、变更标题、分支、按 DB / MQ / Redis/缓存 / 配置聚合后的简要提醒，以及“查看平台详情”链接。平台详情链接由 `PLATFORM_BASE_URL` 拼接 `/tasks/{taskId}` 生成；钉钉消息不再额外展示 GitLab 链接。

GitLab MR 自动 AI Review 完成后，也会向同一个钉钉 webhook 推送“代码质量 Review”消息，包含 provider、状态、等级、问题数、摘要、最多 5 条主要 finding 和平台详情链接。多模型任务中的 AI Review 摘要链接会追加 `?reviewKey={reviewKey}`，任务详情页据此直接选中消息对应的模型 Review 子 tab；finding 深链也保留同一个 `reviewKey`。

当前 RiskCard 字段名仍沿用 `risk*` 兼容历史数据和接口；前端与钉钉展示层先统一使用“提醒”语义。后续若需要彻底改名，应分阶段迁移 JSON schema、数据库字段、API DTO 和前端字段。

### 6.1 查询任务推送记录

```http
GET /api/review-tasks/{taskId}/notifications
```

响应 data：

```json
[
  {
    "id": 50001,
    "taskId": 10001,
    "channel": "DINGTALK",
    "target": "订单服务发布群",
    "status": "SUCCESS",
    "sentAt": "2026-04-19T12:00:09+08:00",
    "errorMessage": null
  }
]
```

## 7. Code Quality Review API

### 7.1 手动发起代码质量 Review

```http
POST /api/code-quality-reviews/manual
Content-Type: application/json
```

请求：

```json
{
  "projectId": 1,
  "profileCode": "backend-default-ai-review",
  "repositoryPath": null,
  "mode": "DIFF_TEXT",
  "baseRef": "origin/main",
  "commitSha": null,
  "title": "Manual Codex review",
  "instructions": "Only report actionable correctness, data consistency, or security issues.",
  "diffText": "diff --git a/src/main/java/com/demo/OrderService.java b/src/main/java/com/demo/OrderService.java\n+ public void createOrder() {}",
  "changedFiles": ["src/main/java/com/demo/OrderService.java"]
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `projectId` | 必填，AI Review 会创建一条 `CODE_QUALITY_MANUAL` 类型任务 |
| `profileCode` | 可选，为空时使用项目绑定的默认 AI Review profile |
| `repositoryPath` | 兼容字段；当前 API Provider 只审查传入的 `diffText` |
| `mode` | `BASE`、`COMMIT`、`UNCOMMITTED`、`DIFF_TEXT` |
| `baseRef` | `BASE` 模式下传入，例如 `origin/main` |
| `commitSha` | `COMMIT` 模式下传入 |
| `instructions` | 附加审查要求 |
| `diffText` | 必填，作为唯一审查变更输入 |
| `changedFiles` | diff 对应文件列表，作为最终 finding 输出白名单 |

响应 data：

```json
{
  "taskId": 10002,
  "status": "SUCCESS",
  "profileCode": "backend-default-ai-review",
  "provider": "DEEPSEEK",
  "overallLevel": "HIGH",
  "findingCount": 1
}
```

说明：

- 代码质量 AI Review 全局能力默认关闭。`CODE_QUALITY_REVIEW_ENABLED` 只作为兼容初始化值；已有数据库以设置页 / `reviewEnabled` 为准。
- `OPENAI` 使用 Provider 配置中的 API Key 调用 OpenAI Responses API，并要求 `diffText`。
- `ANTHROPIC` 使用 Provider 配置中的 API Key 调用 Anthropic Messages API，并要求 `diffText`。
- `DEEPSEEK` 与 `CUSTOM` 使用 OpenAI-compatible Chat Completions API，并要求 `diffText`。
- GitLab MR webhook 风险审查成功后，如果 `reviewEnabled=true` 且项目绑定的 AI Review 配置处于启用状态，系统会异步触发 AI Code Review，并将结果保存到同一个 `taskId` 下。
- 项目组可配置多个 `aiReviewModels`。自动触发和重试会为每个启用模型分别保存一条结果，并并行进入调度队列；仅配置单个模型时仍表现为单结果。
- MR 自动 AI Review 启动后会先保存 `RUNNING` 结果，执行完成后更新为 `SUCCESS` 或 `FAILED`，前端可轮询本接口展示进度。
- 所有 API Provider 自动触发都直接使用 MR diff 文本。
- MR 自动 AI Review 受 `reviewEnabled` 全局能力开关和项目绑定 AI Review 配置的启用状态影响；设置页不再提供单独的 MR 自动触发开关。

### 7.2 查询代码质量 Review 结果

```http
GET /api/review-tasks/{taskId}/code-quality-result
```

响应 data：

```json
{
  "taskId": 10002,
  "projectId": 1,
  "profileCode": "backend-default-ai-review",
  "provider": "OPENAI",
  "model": "gpt-5.4",
  "status": "SUCCESS",
  "overallLevel": "HIGH",
  "summary": "发现 1 个事务一致性问题。",
  "findingCount": 1,
  "findings": [
    {
      "severity": "MAJOR",
      "category": "TRANSACTION",
      "filePath": "src/main/java/com/demo/OrderService.java",
      "startLine": 42,
      "endLine": 48,
      "title": "订单创建缺少事务边界",
      "body": "该方法同时写订单和流水，部分失败会造成数据不一致。",
      "suggestion": "为入口方法增加事务，并确认外部调用不在事务内执行。",
      "confidence": "HIGH",
      "source": "OPENAI"
    }
  ],
  "rawOutput": "...",
  "exitCode": null,
  "errorMessage": null,
  "startedAt": "2026-05-08T20:00:00",
  "finishedAt": "2026-05-08T20:00:30"
}
```

说明：

- `status=RUNNING` 时，`finishedAt`、`exitCode`、`rawOutput` 通常为空。
- 任务存在但尚未创建 AI Review 结果时，接口返回 `200` 且 `data=null`，避免普通 Push / 被 Gate 拦截的任务在详情页产生 404 噪声。
- 多模型任务中该兼容接口返回排序第一的结果。新前端应优先调用 `GET /api/review-tasks/{taskId}/code-quality-results` 获取完整结果列表。
- 历史 `CODEX_CLI` 结果只作为历史 provider 字符串展示；新版本不再执行 Codex CLI，也不再对 Codex Markdown raw output 做运行时兜底解析。
- 后端启动时会扫描超过超时阈值仍处于 `RUNNING` 的 AI Review，并标记为 `FAILED`，避免后端重启或 Codex 子进程丢失后页面永久卡住。

### 7.2.1 查询代码质量 Review 结果列表

```http
GET /api/review-tasks/{taskId}/code-quality-results
```

响应 data：

```json
[
  {
    "id": 501,
    "taskId": 10001,
    "reviewKey": "deepseek-deepseek-v4-pro",
    "displayName": "DeepSeek V4 Pro",
    "profileCode": "backend-default-ai-review",
    "provider": "DEEPSEEK",
    "model": "deepseek-v4-pro",
    "status": "SUCCESS",
    "overallLevel": "HIGH",
    "findingCount": 2,
    "findings": []
  }
]
```

说明：

- 单模型任务返回长度为 0 或 1 的数组，前端不需要额外展示模型子 tab。
- `reviewKey` 是同一任务内稳定区分模型结果、进度和修复预览的键。

### 7.3 查询代码质量 Review 执行过程

```http
GET /api/review-tasks/{taskId}/code-quality-progress
```

响应 data：

```json
[
  {
    "id": 1,
    "taskId": 10002,
    "phase": "PROVIDER_START",
    "level": "INFO",
    "message": "开始调用代码质量 Review Provider",
    "detail": "provider=DEEPSEEK",
    "createdAt": "2026-05-09T10:40:00"
  },
  {
    "id": 2,
    "taskId": 10002,
    "phase": "DEEPSEEK_RESPONSE",
    "level": "DEBUG",
    "message": "DeepSeek API 已返回响应",
    "detail": "responseBytes=2048",
    "createdAt": "2026-05-09T10:40:01"
  }
]
```

说明：

- 该接口返回持久化的 AI Review 过程事件，前端在 `RUNNING` 时轮询展示；可追加 `?reviewKey=...` 只查看某个模型的事件。
- API Provider 会记录请求构建、Provider 调用、响应摘要、解析和保存结果等阶段，敏感字段会脱敏或省略。
- 重试 AI Review 会清空同一任务旧过程事件，并重新写入本轮过程。

### 7.4 查询 Push 审核结论

```http
GET /api/review-tasks/{taskId}/code-quality-gate
```

响应 data：

```json
{
  "taskId": 10003,
  "projectId": 1,
  "branchName": "feature/order-risk",
  "decision": "ALLOWED",
  "reasonCode": "RISK_MATCHED",
  "reasonSummary": "Push 命中重点提醒或高风险变更，允许进入 AI Review。",
  "aiReviewScheduled": true,
  "profileCode": "backend-default-ai-review",
  "provider": "DEEPSEEK",
  "metrics": {
    "changedFileCount": 12,
    "diffBytes": 42000,
    "commitCount": 4,
    "riskLevel": "HIGH",
    "focusRiskItemCount": 2,
    "matchedChangeTypes": ["DB_SQL", "CACHE_KEY"],
    "branch": "feature/order-risk",
    "compareSource": "gitlab_compare_api"
  },
  "matchedRules": [
    {
      "code": "riskLevel",
      "label": "风险等级 HIGH",
      "matched": true
    }
  ],
  "createdAt": "2026-05-21T10:00:00"
}
```

说明：

- GitLab Push webhook 会先按 AI Review 配置里的 `pushBranchPatterns` 做入口过滤；不匹配的分支直接返回 `SKIPPED`，不会创建审查任务。
- 该接口用于解释已进入平台的 GitLab Push 为什么允许或不允许自动触发 AI Review。
- 没有 Gate 记录时返回稳定空态，`decision` 为 `NOT_EVALUATED`，前端可展示“尚未进入 Push 审核”。
- Push 审核只影响自动触发；用户点击“重试 AI Review”属于人工显式触发，不受 Gate 拦截。

### 7.5 AI Review 设置与重试

```http
GET /api/code-quality-reviews/settings
PUT /api/code-quality-reviews/settings
GET /api/code-quality-review-providers
PUT /api/code-quality-review-providers/{providerCode}
POST /api/code-quality-review-providers/{providerCode}/set-default
POST /api/code-quality-reviews/tasks/{taskId}/retry
```

`PUT /api/code-quality-reviews/settings` 请求：

```json
{
  "reviewEnabled": true,
  "dingtalkNotificationEnabled": true,
  "defaultProviderCode": "DEEPSEEK"
}
```

设置响应 data：

```json
{
  "reviewEnabled": true,
  "dingtalkNotificationEnabled": true,
  "defaultProviderCode": "DEEPSEEK",
  "updatedAt": "2026-05-09T00:10:00"
}
```

Provider 列表响应 data：

```json
[
  {
    "providerCode": "DEEPSEEK",
    "providerName": "DeepSeek",
    "providerType": "OPENAI_CHAT_COMPATIBLE",
    "endpointUrl": "https://api.deepseek.com",
    "modelName": "deepseek-v4-pro",
    "enabled": true,
    "builtIn": true,
    "defaultProvider": true,
    "apiKeyConfigured": true,
    "apiKeyMasked": "sk-d...abcd"
  }
]
```

`PUT /api/code-quality-review-providers/{providerCode}` 请求：

```json
{
  "endpointUrl": "https://api.deepseek.com",
  "modelName": "deepseek-v4-pro",
  "apiKey": "sk-...",
  "enabled": true
}
```

AI Review Provider 当前保持非流式 HTTP 请求；前端通过任务进度与结果接口轮询刷新，不再提供 Provider 维度流式开关。

重试响应 data：

```json
{
  "taskId": 10002,
  "status": "RUNNING",
  "profileCode": "backend-default-ai-review",
  "provider": "DEEPSEEK",
  "overallLevel": null,
  "findingCount": 0
}
```

### 7.6 代码质量 Review Profile

```http
GET /api/code-quality-review-profiles
GET /api/code-quality-review-profiles/{profileCode}
PUT /api/code-quality-review-profiles/{profileCode}
GET /api/code-quality-review-profiles/{profileCode}/rendered-prompt
POST /api/code-quality-review-profiles/{profileCode}/reset-default-prompt
PUT /api/projects/{projectId}/code-quality-profile
```

`GET /api/code-quality-review-profiles/{profileCode}/rendered-prompt` 响应 data：

```json
{
  "profileCode": "backend-default-ai-review",
  "provider": "DEEPSEEK",
  "model": "gpt-5.4",
  "prompt": "你是代码质量审核助手...",
  "promptHash": "e3b0c44298fc1c149afbf4c8996fb924...",
  "promptLength": 1200
}
```

说明：

- `rendered-prompt` 用于前端预览实际传给 provider 的最终 instructions。
- `reset-default-prompt` 会把指定 profile 的 `reviewInstructions` 恢复为平台内置默认值，其他 profile 配置保持不变。

`PUT /api/projects/{projectId}/code-quality-profile` 请求：

```json
{
  "profileCode": "backend-default-ai-review"
}
```

## 8. DTO / VO 边界

### 8.1 WebhookTriggerCommand

用于从 webhook payload 转成内部任务创建命令。

```json
{
  "gitProvider": "GITLAB",
  "gitProjectId": "1001",
  "mergeRequestIid": "12",
  "externalUrl": "https://gitlab.example.com/group/demo-service/-/merge_requests/12",
  "sourceBranch": "feature/risk-demo",
  "targetBranch": "main",
  "commitSha": "abcdef123456",
  "authorName": "Alice",
  "authorUsername": "alice",
  "rawPayload": {}
}
```

### 8.2 ChangeAnalysisResultDTO

```json
{
  "summary": "本次变更涉及 API、DB 和 CACHE。",
  "changedFileCount": 4,
  "changeTypes": ["API", "DB", "CACHE"],
  "changedFiles": [],
  "impactedResources": [],
  "evidences": []
}
```

### 8.3 RiskCardVO

前端直接消费完整 RiskCard JSON；后端不应再拼接不可解析的展示文本作为主要输出。
