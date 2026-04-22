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

## 7. DTO / VO 边界

### 7.1 WebhookTriggerCommand

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

### 7.2 ChangeAnalysisResultDTO

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

### 7.3 RiskCardVO

前端直接消费完整 RiskCard JSON；后端不应再拼接不可解析的展示文本作为主要输出。
