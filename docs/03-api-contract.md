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

### 3.4 查询风险卡片

```http
GET /api/review-tasks/{taskId}/risk-card
```

响应 data：完整 RiskCard JSON，schema 见 `04-risk-card-schema.md`。

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

钉钉推送当前使用 Markdown 消息，主要依据 RiskCard 中由规则命中的 `riskItems` 生成“提醒”展示。消息标题固定为“变更提醒”，正文包含作者、变更标题、分支、按 DB / MQ / Redis/缓存 / 配置聚合后的简要提醒，以及“查看平台详情”链接。平台详情链接由 `PLATFORM_BASE_URL` 拼接 `?taskId={taskId}` 生成；钉钉消息不再额外展示 GitLab 链接。

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
  "repositoryPath": "D:/projects/ai-code-review-platform",
  "mode": "BASE",
  "baseRef": "origin/main",
  "commitSha": null,
  "title": "Manual Codex review",
  "instructions": "Only report actionable correctness, data consistency, or security issues.",
  "diffText": null,
  "changedFiles": []
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `projectId` | 必填，AI Review 会创建一条 `CODE_QUALITY_MANUAL` 类型任务 |
| `profileCode` | 可选，为空时使用项目绑定的默认 AI Review profile |
| `repositoryPath` | `CODEX_CLI` provider 需要，必须是本地 Git 仓库目录 |
| `mode` | `BASE`、`COMMIT`、`UNCOMMITTED`、`DIFF_TEXT` |
| `baseRef` | `BASE` 模式下传入，例如 `origin/main` |
| `commitSha` | `COMMIT` 模式下传入 |
| `instructions` | 附加审查要求 |
| `diffText` | `OPENAI_API` provider 需要，可直接审查 diff 文本 |
| `changedFiles` | diff 对应文件列表，供 API provider 作为上下文 |

响应 data：

```json
{
  "taskId": 10002,
  "status": "SUCCESS",
  "profileCode": "backend-default-ai-review",
  "provider": "CODEX_CLI",
  "overallLevel": "HIGH",
  "findingCount": 1
}
```

说明：

- 该接口默认关闭，需设置 `CODE_QUALITY_REVIEW_ENABLED=true`。
- `CODEX_CLI` 复用宿主机 Codex CLI 登录态，Windows 默认调用 `codex.cmd`，Linux 默认调用 `codex`。
- `OPENAI_API` 使用 `OPENAI_API_KEY` 或前端保存的 OpenAI API Key 调用 Responses API，并要求 `diffText`。
- `ANTHROPIC_API` 使用 `ANTHROPIC_API_KEY` 或前端保存的 Anthropic API Key 调用 Messages API，并要求 `diffText`。
- GitLab MR webhook 风险审查成功后，如果全局配置已开启且项目绑定 profile 的 `triggerOnMr=true`，系统会异步触发 AI Code Review，并将结果保存到同一个 `taskId` 下。
- MR 自动 AI Review 启动后会先保存 `RUNNING` 结果，执行完成后更新为 `SUCCESS` 或 `FAILED`，前端可轮询本接口展示进度。
- `CODEX_CLI` 自动触发需要后端能定位本地仓库目录；`OPENAI_API` / `ANTHROPIC_API` 自动触发直接使用 MR diff 文本。
- MR 自动 AI Review 还受全局开关 `mrAutoReviewEnabled` 控制。关闭后，新的 MR webhook 不会触发 AI Review；手动 Review 和重试不受该开关影响。

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
  "provider": "OPENAI_API",
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
      "source": "OPENAI_API"
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
- `CODEX_CLI` provider 会保存 Codex Markdown 原始输出，并解析 `- High:`、`- Medium:` 等条目为结构化 `findings`；历史结果如果只有 `rawOutput` 且 `findings_json` 为空，查询时也会兜底解析。
- 后端启动时会扫描超过超时阈值仍处于 `RUNNING` 的 AI Review，并标记为 `FAILED`，避免后端重启或 Codex 子进程丢失后页面永久卡住。

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
    "phase": "CODEX_PROCESS_STARTED",
    "level": "INFO",
    "message": "Codex CLI 子进程已启动",
    "detail": "pid=12345",
    "createdAt": "2026-05-09T10:40:00"
  },
  {
    "id": 2,
    "taskId": 10002,
    "phase": "CODEX_OUTPUT",
    "level": "DEBUG",
    "message": "stdout: {\"type\":\"thread.started\"}",
    "detail": "{\"type\":\"thread.started\"}",
    "createdAt": "2026-05-09T10:40:01"
  }
]
```

说明：

- 该接口返回持久化的 AI Review 过程事件，前端在 `RUNNING` 时轮询展示。
- `CODEX_CLI` 会记录仓库确认、输出文件、命令、子进程 PID、stdout/stderr 行、退出码、解析和保存结果等阶段。
- 重试 AI Review 会清空同一任务旧过程事件，并重新写入本轮过程。

### 7.4 AI Review 设置与重试

```http
GET /api/code-quality-reviews/settings
PUT /api/code-quality-reviews/settings
POST /api/code-quality-reviews/tasks/{taskId}/retry
```

`PUT /api/code-quality-reviews/settings` 请求：

```json
{
  "mrAutoReviewEnabled": false,
  "reviewProvider": "ANTHROPIC_API",
  "openAiApiKey": "sk-...",
  "anthropicApiKey": "sk-ant-..."
}
```

清除 API Key 时传：

```json
{
  "clearOpenAiApiKey": true,
  "clearAnthropicApiKey": true
}
```

设置响应 data：

```json
{
  "mrAutoReviewEnabled": false,
  "reviewProvider": "ANTHROPIC_API",
  "openAiApiKeyConfigured": true,
  "openAiApiKeyMasked": "sk-...abcd",
  "anthropicApiKeyConfigured": true,
  "anthropicApiKeyMasked": "sk-a...wxyz",
  "updatedAt": "2026-05-09T00:10:00"
}
```

重试响应 data：

```json
{
  "taskId": 10002,
  "status": "RUNNING",
  "profileCode": "backend-default-ai-review",
  "provider": "CODEX_CLI",
  "overallLevel": null,
  "findingCount": 0
}
```

### 7.5 代码质量 Review Profile

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
  "provider": "CODEX_CLI",
  "model": "gpt-5.4",
  "prompt": "你是代码质量审核助手...",
  "promptHash": "e3b0c44298fc1c149afbf4c8996fb924...",
  "promptLength": 1200
}
```

说明：

- `rendered-prompt` 用于前端预览实际传给 provider 的最终 prompt。Codex CLI provider 会使用中文优先 wrapper 加 profile prompt 拼装。
- `reset-default-prompt` 会把指定 profile 的 `codexPrompt` 和 `openAiInstructions` 恢复为平台内置默认值，其他 profile 配置保持不变。
- Codex CLI 执行时不会再把完整 prompt 放进命令行参数，而是写入 UTF-8 prompt 文件；进度事件只记录 prompt hash、长度、预览和脱敏后的 command preview。

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
