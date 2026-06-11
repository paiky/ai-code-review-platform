# API 契约

> 状态说明：本文是平台 HTTP API 的权威契约，默认以 `backend-python/` FastAPI 实现为准。领域对象与表结构见 `02-domain-model.md`；提醒卡片 JSON 见 `04-risk-card-schema.md`。未列出的字段以 contract 测试和实际响应为准。

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

### 2.1 接收 GitLab webhook

```http
POST /api/webhooks/gitlab/merge-request
```

同一 URL 同时接收 `Merge Request Hook` 与 `Push Hook`，通过请求头 `X-Gitlab-Event` 分发。

请求头：

```text
X-Gitlab-Event: Merge Request Hook | Push Hook
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

- 当前 Python 后端在 webhook 接收后同步执行规则提醒主链路，并异步调度 AI Review。
- MR `action` 为 close、merge 等非审查触发动作时可返回 `SKIPPED`。
- Push Hook 会先按项目组 Push 策略与分支规则过滤；不匹配时直接 `SKIPPED`，不会创建任务。

## 3. Review Task API

### 3.1 查询审查任务列表

```http
GET /api/review-tasks
```

查询参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| projectId | Long | 否 | 项目 ID |
| groupId | Long | 否 | 项目组 ID |
| targetType | String | 否 | 端类型，例如 BACKEND / WEB_PC |
| triggerType | String | 否 | GITLAB_MR_WEBHOOK / GITLAB_PUSH_WEBHOOK / MANUAL |
| status | String | 否 | PENDING / RUNNING / SUCCESS / FAILED |
| reviewStatus | String[] | 否 | 可重复传入；NOT_TRIGGERED / REVIEWING / NO_RISK / MINOR / MAJOR / CRITICAL / SKIPPED / REVIEW_FAILED / TASK_FAILED |
| riskLevel | String | 否 | NONE / LOW / MEDIUM / HIGH / CRITICAL |
| keyword | String | 否 | 项目名、分支、MR 关键字 |
| pageNo | Integer | 否 | 默认 1 |
| pageSize | Integer | 否 | 默认 20 |

列表项补充字段：

- `groupId`、`targetType`、`targetTypes`、`codeQualityProfileCode`、`reviewStatus`、`focusIndicators`。
- `riskItemCount` 表示该任务下 AI Review finding 总数（跨模型求和）；无 AI Review 时为 `0`。规则提醒项数量请查看 `/result` 返回的 `riskCard.riskItems`。

响应 data：

```json
{
  "items": [
    {
      "id": 10001,
      "projectId": 1,
      "projectName": "demo-service",
      "groupId": 1,
      "triggerType": "GITLAB_MR_WEBHOOK",
      "targetType": "BACKEND",
      "targetTypes": ["BACKEND"],
      "codeQualityProfileCode": "backend-default-ai-review",
      "externalSourceId": "12",
      "externalUrl": "https://gitlab.example.com/group/demo-service/-/merge_requests/12",
      "sourceBranch": "feature/risk-demo",
      "targetBranch": "main",
      "authorName": "Alice",
      "templateCode": "backend-default",
      "status": "SUCCESS",
      "reviewStatus": "CRITICAL",
      "riskLevel": "HIGH",
      "riskItemCount": 2,
      "focusIndicators": [],
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
  "groupId": 1,
  "gitProjectId": "1001",
  "triggerType": "GITLAB_MR_WEBHOOK",
  "mrId": "12",
  "externalSourceId": "12",
  "externalUrl": "https://gitlab.example.com/group/demo-service/-/merge_requests/12",
  "sourceBranch": "feature/risk-demo",
  "targetBranch": "main",
  "commitSha": "abcdef123456",
  "beforeSha": "111111111111",
  "afterSha": "abcdef123456",
  "authorName": "Alice",
  "authorUsername": "alice",
  "templateCode": "backend-default",
  "targetType": "BACKEND",
  "targetTypes": ["BACKEND"],
  "codeQualityProfileCode": "backend-default-ai-review",
  "status": "SUCCESS",
  "reviewStatus": "CRITICAL",
  "riskLevel": "HIGH",
  "eventAction": "open",
  "eventTime": "2026-04-19T12:00:00+08:00",
  "changedFilesSummary": [],
  "diffContextCapabilities": {
    "diff": true,
    "fixPreview": true
  },
  "rawPayload": {},
  "errorMessage": null,
  "createdAt": "2026-04-19T12:00:00+08:00",
  "updatedAt": "2026-04-19T12:00:08+08:00"
}
```

### 3.2.1 按需查询 Diff 完整上下文

```http
GET /api/review-tasks/{taskId}/diff-context?filePath=src/main/java/example/Foo.java&viewType=DIFF
```

查询参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `filePath` | 是 | 必须是当前任务 `changedFilesSummary.files[]` 中已有的变更文件路径 |
| `viewType` | 否 | `DIFF` 或 `FIX_PREVIEW`，默认 `DIFF` |

响应 data：

```json
{
  "taskId": 509,
  "filePath": "src/main/java/example/Foo.java",
  "viewType": "DIFF",
  "language": "java",
  "left": {
    "path": "src/main/java/example/Foo.java",
    "ref": "base-sha",
    "lines": ["package example;", ""]
  },
  "right": {
    "path": "src/main/java/example/Foo.java",
    "ref": "head-sha",
    "lines": ["package example;", ""]
  }
}
```

说明：

- `DIFF` 使用任务保存的历史 base / head refs。新增文件没有 `left`，删除文件没有 `right`。
- `FIX_PREVIEW` 只返回当前源码作为 `left` 基线，由前端结合模型 patch 构造预览。
- changed file 优先使用 `newFile / deletedFile / renamedFile` 标记；历史任务缺少标记时兼容读取 `changeType=ADDED / DELETED / RENAMED`。
- 只允许读取当前任务已记录的 changed file。单文件限制为 1 MiB、最多 20000 行。
- GitLab API 未启用、Token 缺失、refs 缺失或文件超限时返回明确错误；前端应隐藏不适用的展开入口。

### 3.3 查询审查结果

```http
GET /api/review-tasks/{taskId}/result
```

响应 data：

```json
{
  "taskId": 10001,
  "targetType": "BACKEND",
  "reminderCardEnabled": true,
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

### 3.5 手动发起规则提醒审查

```http
POST /api/review-tasks/manual
```

用于本地调试、无 webhook 权限或粘贴 diff 的场景。请求体支持项目、模板、分支、changed files 与 diff 文本；成功时返回新任务 ID 与执行状态。

### 3.6 原地重跑规则提醒

```http
POST /api/review-tasks/{taskId}/rerun-in-place
```

基于已有任务重新执行规则提醒主链路，不创建新任务 ID。`/rerun` 则会创建新任务，便于对比前后规则结果。

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

## 4.3 项目端类型配置

```http
GET /api/projects/{projectId}/target-configs
PUT /api/projects/{projectId}/target-configs/{targetType}
PUT /api/projects/{projectId}/group
GET /api/target-type-path-mappings
PUT /api/target-type-path-mappings
```

`target-configs` 用于按端类型绑定规则模板、AI Review profile、provider、路径匹配和是否启用提醒卡片。项目默认 AI Review profile 也通过端类型配置维护，不再单独提供 `PUT /api/projects/{projectId}/code-quality-profile`。

## 4.4 项目组 AI Review 模型配置

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
        "DB_DATA_WRITE_CHANGE_CHECK",
        "CACHE_WRITE_DELETE_CHANGE_CHECK",
        "MQ_CONFIG_CHANGE_CHECK",
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
    "DB_DATA_WRITE_CHANGE_CHECK",
    "CACHE_WRITE_DELETE_CHANGE_CHECK",
    "MQ_CONFIG_CHANGE_CHECK",
    "CONFIG_RELEASE_CHECK"
  ],
  "config": {
    "focusChangeTypes": ["DB_DATA_WRITE", "CACHE_WRITE_DELETE", "MQ_CONFIG", "CONFIG"],
    "focusRuleCodes": [
      "DB_DATA_WRITE_CHANGE_CHECK",
      "CACHE_WRITE_DELETE_CHANGE_CHECK",
      "MQ_CONFIG_CHANGE_CHECK",
      "CONFIG_RELEASE_CHECK"
    ],
    "defaultRiskLevel": "LOW"
  }
}
```

说明：模板启用规则以数据库 seed / migration 为准；历史细粒度 ruleCode 仍可能在分析结果中出现，但默认模板已收敛为上述四类提醒规则。

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
- Provider 请求会附带后端构造的 `reviewContext / contextPack`。V0 包含 changed files 摘要、同文件上下文可用性说明、预算内同文件上下文片段、同项目上下文不足反馈统计摘要、Context Planner 的 `contextPlan / plannerSignals / requestedContexts` 和 `unavailableContexts`。同文件上下文片段只读取当前 changed files 的 GitLab raw file，并只注入变更 hunk 附近窗口；Context Planner 只基于当前 changed files、diff text、文件路径和已有上下文不足反馈统计输出缺失证据提示，不做全项目扫描、引用搜索、related files 读取、向量库 / RAG、自动降级或自动忽略 finding。
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
- 注入项目策略时会记录 `PROJECT_POLICIES_INJECTED`，detail 仅包含策略摘要和数量，不包含策略正文。
- 构造 Context Pack 时会记录 `CONTEXT_PACK_BUILT`，detail 仅包含 meta、changed file 数量、同文件上下文可用性、同文件 source snippet 数量、上下文不足反馈数量、planner 命中数量、requested context 类型统计和不可用上下文数量，不记录 diff 正文或源码片段。
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

内置 `GLM` Provider 使用 `OPENAI_CHAT_COMPATIBLE` 协议，默认 `endpointUrl` 为
`https://open.bigmodel.cn/api/paas/v4`，默认 `modelName` 为 `glm-5.1`。

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
```

项目绑定 profile 通过 `PUT /api/projects/{projectId}/target-configs/{targetType}` 维护，见 §4.3。

`GET /api/code-quality-review-profiles/{profileCode}/rendered-prompt` 可追加 `projectId` query，用于预览指定项目会注入的项目策略。

`GET /api/code-quality-review-profiles/{profileCode}/rendered-prompt?projectId=1` 响应 data：

```json
{
  "profileCode": "backend-default-ai-review",
  "provider": "DEEPSEEK",
  "model": "gpt-5.4",
  "projectId": 1,
  "projectPolicyCount": 1,
  "projectReviewPolicies": [
    {
      "id": 11,
      "policyType": "PROJECT_RULE",
      "riskType": "AUTHORIZATION",
      "title": "网关统一鉴权",
      "sourceFeedbackId": 101
    }
  ],
  "prompt": "你是代码质量审核助手...",
  "promptHash": "e3b0c44298fc1c149afbf4c8996fb924...",
  "promptLength": 1200
}
```

说明：

- `rendered-prompt` 用于前端预览实际传给 provider 的最终 instructions。
- 有 `projectId` 时只预览该项目 `enabled=true` 且类型为 `PROJECT_RULE / CONTEXT_FACT` 的策略注入结果；`projectReviewPolicies` 只返回摘要，不返回策略正文。
- `reset-default-prompt` 会把指定 profile 的 `reviewInstructions` 恢复为平台内置默认值，其他 profile 配置保持不变。

### 7.7 Finding 修复预览与调度队列

```http
POST /api/review-tasks/{taskId}/code-quality-fix-preview
GET /api/review-tasks/{taskId}/code-quality-fix-previews
GET /api/code-quality-reviews/job-queue
POST /api/code-quality-reviews/job-queue/{jobId}/cancel
POST /api/code-quality-reviews/tasks/{taskId}/cancel
GET /api/code-quality-reviews/failure-notifications
```

说明：

- fix-preview 按 `findingIndex` 与可选 `reviewKey` 生成 patch 预览。
- 调度队列用于观察 AI Review / fix-preview 异步任务；取消接口仅影响排队或未完成任务。

## 8. Review Feedback 与项目策略 API

### 8.1 提交和查询任务反馈

```http
POST /api/review-tasks/{taskId}/feedback
GET  /api/review-tasks/{taskId}/feedback
```

提交反馈请求：

```json
{
  "sourceType": "AI_FINDING",
  "itemFingerprint": "code-quality:1:TRANSACTION:src/main/java/demo/OrderService.java:42",
  "feedbackType": "FALSE_POSITIVE",
  "reasonType": "PROJECT_ALLOWED",
  "reasonText": "本项目该入口事务由统一切面注入。",
  "missingContextTypes": [],
  "suggestAsProjectRule": true,
  "operatorName": "Alice"
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `sourceType` | `RULE_REMINDER` 或 `AI_FINDING` |
| `itemFingerprint` | 风险项 / finding 的稳定反馈键 |
| `feedbackType` | `USEFUL`、`FALSE_POSITIVE`、`LEVEL_TOO_HIGH`、`DUPLICATE`、`FIXED` |
| `reasonType` | `PROJECT_ALLOWED`、`HAS_EXTERNAL_GUARD`、`CONTEXT_MISSING`、`RULE_NOT_APPLICABLE`、`LEVEL_TOO_HIGH`、`DESCRIPTION_INACCURATE`、`DUPLICATE`、`OTHER` |
| `missingContextTypes` | 当 `reasonType=CONTEXT_MISSING` 时可选，记录缺失上下文类型 |
| `suggestAsProjectRule` | 用户建议沉淀为项目策略；仍需管理员在反馈池确认生成 |

`missingContextTypes` 当前可选值：

```text
SAME_FILE_CONTEXT / SAME_CLASS_METHODS / REFERENCE_SEARCH / CALLER_CONTEXT /
CALLEE_CONTEXT / RELATED_FILE / DB_SCHEMA_CONTEXT / CONFIG_CONTEXT /
PROJECT_POLICY_CONTEXT / TEST_RESULT_CONTEXT / OTHER
```

### 8.2 反馈池

```http
GET /api/risk-feedback
PUT /api/risk-feedback/{feedbackId}/status
POST /api/risk-feedback/{feedbackId}/convert-to-policy
```

`GET /api/risk-feedback` 查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `projectId` | Long | 按项目过滤 |
| `sourceType` | String | `RULE_REMINDER / AI_FINDING` |
| `riskType` | String | 按风险类型过滤 |
| `feedbackType` | String | 按反馈类型过滤 |
| `reasonType` | String | 按反馈原因过滤，例如 `CONTEXT_MISSING` |
| `missingContextType` | String | 按缺失上下文类型过滤 |
| `policyCandidate` | Boolean | `true` 时只返回可沉淀候选 |
| `status` | String | `PENDING / VALID / INSUFFICIENT / IGNORED / CONVERTED` |
| `keyword` | String | 按项目、任务来源和反馈说明模糊搜索 |
| `pageNo` / `pageSize` | Number | 分页 |

`policyCandidate=true` 的候选规则：

- `status=VALID` 或 `suggestAsProjectRule=true`。
- 排除 `INSUFFICIENT / IGNORED / CONVERTED`。
- 排除 `reasonType=CONTEXT_MISSING`，上下文不足反馈进入反馈池统计和 Context Pack backlog。

反馈池响应 data 在分页字段外额外返回上下文不足统计：

```json
{
  "items": [],
  "pageNo": 1,
  "pageSize": 20,
  "total": 0,
  "contextMissingStats": {
    "total": 3,
    "byRiskType": [
      { "riskType": "TRANSACTION", "count": 2 },
      { "riskType": "AUTHORIZATION", "count": 1 }
    ],
    "byMissingContextType": [
      { "missingContextType": "CALLER_CONTEXT", "count": 2 },
      { "missingContextType": "REFERENCE_SEARCH", "count": 1 }
    ]
  }
}
```

`contextMissingStats` 会跟随当前筛选条件变化，用于前端展示上下文不足数量、风险类型分布和缺失上下文类型分布；它只做统计，不自动创建策略、不影响 AI Review Prompt。

更新状态请求：

```json
{
  "status": "VALID",
  "adminComment": "确认可作为项目策略候选。"
}
```

从反馈生成项目策略请求：

```json
{
  "policyType": "PROJECT_RULE",
  "riskType": "TRANSACTION",
  "title": "统一事务边界由框架注入",
  "content": "本项目部分入口方法事务由框架切面注入，Review 时需结合项目策略判断。",
  "enabled": true,
  "createdBy": "alice"
}
```

生成策略限制：

- 仅 `VALID` 或 `suggestAsProjectRule=true` 的反馈可转换。
- `CONTEXT_MISSING`、`INSUFFICIENT`、`IGNORED`、`CONVERTED` 不可转换。
- 首版只允许 `PROJECT_RULE / CONTEXT_FACT`，不开放自动忽略或自动降级策略。
- 转换成功后反馈状态变为 `CONVERTED`。

### 8.3 项目策略管理

```http
GET /api/projects/{projectId}/review-policies
PUT /api/project-review-policies/{policyId}
PUT /api/project-review-policies/{policyId}/enabled
```

`GET /api/projects/{projectId}/review-policies` 查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `enabled` | Boolean | 按启用状态过滤 |
| `policyType` | String | `PROJECT_RULE / CONTEXT_FACT` |
| `riskType` | String | 按风险类型过滤 |

项目策略响应：

```json
{
  "id": 11,
  "projectId": 1,
  "projectName": "demo-service",
  "policyType": "PROJECT_RULE",
  "riskType": "TRANSACTION",
  "title": "统一事务边界由框架注入",
  "content": "本项目部分入口方法事务由框架切面注入，Review 时需结合项目策略判断。",
  "sourceFeedbackId": 101,
  "enabled": true,
  "version": 1,
  "createdBy": "alice",
  "createdAt": "2026-06-10T10:00:00",
  "updatedAt": "2026-06-10T10:00:00"
}
```

后续 AI Review 会读取同 `projectId`、`enabled=true`、`policyType in PROJECT_RULE / CONTEXT_FACT` 的策略注入 Prompt。执行过程会记录 `PROJECT_POLICIES_INJECTED` progress event，只包含策略数量、id、标题、类型、风险类型和来源反馈 id，不记录策略正文。

## 9. DTO / VO 边界

### 9.1 WebhookTriggerCommand

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

### 9.2 ChangeAnalysisResultDTO

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

### 9.3 RiskCardVO

前端直接消费完整 RiskCard JSON；后端不应再拼接不可解析的展示文本作为主要输出。
