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
- 项目组主引擎固定为 Agent Review。响应中的 `reviewEngine=AGENT`、`agentSourceExportAllowed=true`、`aiReviewEnabled=true`、`triggerOnManual=true` 是兼容字段，设置页不再提供对应选项；创建或更新请求传入相反值不会关闭这些能力。
- `triggerOnMr`、`triggerOnPush`、自动修复预览和 Push 审核阈值仍按项目组配置。

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

GitLab MR 自动 AI Review 完成后，也会向同一个钉钉 webhook 推送“代码质量 Review”消息，包含 provider / 模型名称、状态、等级、问题数、摘要、最多 5 条主要 finding 和平台详情链接。“AI 模型”优先展示 `Provider / model`，例如 `DeepSeek / deepseek-v4-pro[1m]`；历史结果缺少 model 时回退为 Provider，Provider 也缺失时才展示 `-`。多模型任务（包括 Agent Review）中的 AI Review 摘要链接会追加持久化结果的 `?reviewKey={reviewKey}`，任务详情页据此直接选中消息对应的模型 Review 子 tab；finding 深链也保留同一个 `reviewKey`。

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

## 9. Evaluation Case API

Evaluation Case 用于沉淀 Review 质量评估样本，服务于后续误判 / 漏报 / 等级偏差治理。它不修改原 AI Review 结果，不创建反馈池记录，不生成项目策略，也不会触发模型回放。

前端最小入口：

- 任务详情页的 AI finding 操作区可调用 `POST /api/evaluation-cases` 标注评估样本。
- “评估样本”列表页调用 `GET /api/evaluation-cases`，支持按 `projectId / provider / profile / riskType / verdict` 查询。
- M2 仅提供标注和基础列表，不提供模型回放、项目策略生成或反馈池转换。

### 9.1 创建评估样本

```http
POST /api/evaluation-cases
```

从已有 AI finding 沉淀样本：

```json
{
  "source": "AI_FINDING",
  "taskId": 10001,
  "reviewKey": "deepseek-main",
  "fingerprint": "finding-feedback-key",
  "verdict": "FALSE_POSITIVE",
  "humanComment": "本项目该入口事务由统一切面注入。"
}
```

人工补充漏报样本：

```json
{
  "source": "MANUAL",
  "projectId": 1,
  "provider": "DEEPSEEK",
  "profile": "backend-default-ai-review",
  "riskType": "SECURITY",
  "severity": "MAJOR",
  "contextStatus": "CONTEXT_MISSING",
  "verdict": "MISSING_FINDING",
  "humanComment": "人工发现接口缺少鉴权，但本次 AI Review 未报告。",
  "itemSnapshot": {
    "title": "接口缺少鉴权",
    "filePath": "src/main/java/demo/OrderController.java"
  }
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `source` | `AI_FINDING` 或 `MANUAL` |
| `taskId` | 来源任务 ID；`AI_FINDING` 必填，`MANUAL` 可选 |
| `reviewKey` | 多模型结果键；用于定位某个模型的 finding |
| `findingId` | finding JSON 中的 `findingId` 或 `id` |
| `fingerprint` | AI finding 的稳定反馈键；可从 `/code-quality-results` 返回的 `fingerprint` 读取 |
| `projectId` | 项目 ID；`MANUAL` 必填，`AI_FINDING` 可由任务 / 结果推导 |
| `provider` | 模型 Provider，例如 `DEEPSEEK` |
| `profile` | AI Review Profile code，对应现有 `profileCode` |
| `riskType` | 风险类型，例如 `TRANSACTION` |
| `severity` | 风险等级，例如 `CRITICAL / MAJOR / MINOR` |
| `contextStatus` | finding 上下文状态，例如 `FULL / PARTIAL / INSUFFICIENT / CONTEXT_MISSING` |
| `verdict` | 人工裁决 |
| `humanComment` | 人工说明 |

`verdict` 可选值：

```text
TRUE_POSITIVE / FALSE_POSITIVE / LEVEL_TOO_HIGH / LEVEL_TOO_LOW /
CONTEXT_MISSING / DUPLICATE / MISSING_FINDING / UNKNOWN
```

响应 data：

```json
{
  "id": 1,
  "taskId": 10001,
  "reviewKey": "deepseek-main",
  "findingId": "finding-1",
  "fingerprint": "finding-feedback-key",
  "projectId": 1,
  "provider": "DEEPSEEK",
  "profile": "backend-default-ai-review",
  "riskType": "TRANSACTION",
  "severity": "MAJOR",
  "contextStatus": "PARTIAL",
  "verdict": "FALSE_POSITIVE",
  "humanComment": "本项目该入口事务由统一切面注入。",
  "source": "AI_FINDING",
  "itemSnapshot": {},
  "createdAt": "2026-07-01T10:00:00",
  "updatedAt": "2026-07-01T10:00:00"
}
```

### 9.2 查询和更新评估样本

```http
GET /api/evaluation-cases
GET /api/evaluation-cases/{caseId}
PUT /api/evaluation-cases/{caseId}
```

`GET /api/evaluation-cases` 查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `projectId` | Long | 按项目过滤 |
| `provider` | String | 按 Provider 过滤 |
| `profile` | String | 按 AI Review Profile 过滤 |
| `riskType` | String | 按风险类型过滤 |
| `verdict` | String | 按人工裁决过滤 |
| `pageNo` / `pageSize` | Number | 分页 |

更新请求示例：

```json
{
  "verdict": "CONTEXT_MISSING",
  "humanComment": "需要调用方上下文才能判断。",
  "riskType": "TRANSACTION",
  "contextStatus": "PARTIAL"
}
```

可更新字段：`verdict / humanComment / riskType / severity / contextStatus / provider / profile / findingId / fingerprint / source`。

## 10. Finding Refinement API

Finding Refinement 用于对高影响且上下文不足的 AI finding 做一次后端定向补证据。它只保存显式覆盖层，不修改原 AI Review finding，不自动降级、不自动忽略，也不会调用模型回放或生成项目策略。

### 10.1 触发补证据

```http
POST /api/review-tasks/{taskId}/code-quality-refinements
```

请求示例：

```json
{
  "reviewKey": "deepseek-main",
  "findingIndex": 0,
  "fingerprint": "finding-feedback-key",
  "forceRegenerate": false
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `reviewKey` | 多模型结果键；建议传入 |
| `findingIndex` | finding 在该模型结果中的下标；可与 `fingerprint` 二选一 |
| `fingerprint` | AI finding 稳定反馈键；可与 `findingIndex` 二选一 |
| `forceRegenerate` | 已存在 refinement 时是否强制重新检索 |

候选限制：

```text
severity in CRITICAL / MAJOR / HIGH
contextStatus in PARTIAL / INSUFFICIENT
```

不符合候选条件时返回 `VALIDATION_ERROR`，不会创建 refinement。

响应 data：

```json
{
  "id": 1,
  "taskId": 10001,
  "reviewKey": "deepseek-main",
  "findingIndex": 0,
  "fingerprint": "finding-feedback-key",
  "findingId": "finding-1",
  "projectId": 1,
  "status": "COMPLETED",
  "triggerReason": "HIGH_IMPACT_CONTEXT_INSUFFICIENT",
  "triggerConditions": {
    "severity": "MAJOR",
    "contextStatus": "PARTIAL"
  },
  "retrievalPlan": {
    "contextPackVersion": "context-pack-v0",
    "plannerSignalCount": 1,
    "requestedContextCount": 1
  },
  "evidenceSummary": {
    "localRepository": {
      "status": "PREPARED"
    },
    "localReferenceSearch": {
      "queryCount": 1,
      "matchedFileCount": 2,
      "includedSnippetCount": 2
    }
  },
  "missingContext": [],
  "failureReason": null,
  "startedAt": "2026-07-01T10:00:00",
  "finishedAt": "2026-07-01T10:00:01"
}
```

`status` 可选值：

```text
COMPLETED / FAILED
```

安全边界：

- 返回内容只包含检索计划、统计和相对路径摘要。
- 不返回 token、认证头、本地绝对路径、大段源码、provider raw output、raw promptText。
- worktree 未启用、不可用或检索异常时记录 `FAILED` refinement，不影响原 AI Review 结果。

### 10.2 查询补证据记录

```http
GET /api/review-tasks/{taskId}/code-quality-refinements
GET /api/review-tasks/{taskId}/code-quality-refinements?reviewKey=deepseek-main
```

`GET /api/review-tasks/{taskId}/code-quality-results` 会在对应 finding 上附加可选 `refinementOverlay` 字段，作为显式覆盖层返回；原 finding 的 `severity / contextStatus / confidence / evidence` 不会被覆盖。

前端最小入口：

- 任务详情页只在候选 AI finding 上展示“补证据”操作：`severity=CRITICAL / MAJOR / HIGH` 且 `contextStatus=PARTIAL / INSUFFICIENT`。
- 展开 finding 后展示 `refinementOverlay` 的状态、触发条件、检索计划摘要、补到的证据摘要、仍缺失上下文和失败原因。
- “高准确模式流转”会汇总当前 Review 的 finding 级补证据完成 / 失败数量；不展示源码片段、provider raw output、token、认证头或本地绝对路径。

## 11. Evaluation Run API

Evaluation Run 用于记录一次离线评估或 Review 回放的版本元信息和样本结果摘要。它只服务于质量治理和后续回放接入，不会自动调用真实模型，不会修改 Prompt、AI Review 结果、finding 等级、项目策略或忽略状态。

### 11.1 创建回放 / 评估运行

```http
POST /api/evaluation-runs
```

请求示例：

```json
{
  "name": "backend prompt candidate replay",
  "runType": "REVIEW_REPLAY",
  "sampleSetName": "backend-security-regression",
  "caseIds": [1, 2, 3],
  "projectId": 1,
  "provider": "DEEPSEEK",
  "profile": "backend-default-ai-review",
  "model": "deepseek-v4-pro",
  "promptHash": "sha256-new",
  "contextPackVersion": "context-pack-v0",
  "retrieverVersion": "local-retriever-v0",
  "ruleGapVersion": "rule-gap-v0",
  "baseline": {
    "label": "current-prod",
    "provider": "DEEPSEEK",
    "profile": "backend-default-ai-review",
    "model": "deepseek-v4-pro",
    "promptHash": "sha256-old"
  },
  "candidate": {
    "label": "m5-candidate",
    "provider": "DEEPSEEK",
    "profile": "backend-default-ai-review",
    "model": "deepseek-v4-pro",
    "promptHash": "sha256-new"
  },
  "notes": "M5 manual replay placeholder"
}
```

创建行为：

- `caseIds` 必填且至少 1 个；只从已有 `evaluation_cases` 初始化 run item。
- run 初始 `status=PENDING`，item 初始 `status=PENDING`。
- `sampleSet` 只保存 `{caseIds, count, filters?}` 摘要，不复制源码、大段 diff 或 provider raw output。
- 响应返回 run 详情和初始化后的 `items`。

`runType` 可选值：

```text
EVALUATION / REVIEW_REPLAY
```

`status` 可选值：

```text
PENDING / RUNNING / COMPLETED / FAILED / CANCELED
```

响应 data 关键字段：

```json
{
  "id": 1,
  "name": "backend prompt candidate replay",
  "runType": "REVIEW_REPLAY",
  "sampleSetName": "backend-security-regression",
  "sampleSet": {
    "caseIds": [1, 2, 3],
    "count": 3
  },
  "projectId": 1,
  "projectName": "demo-service",
  "provider": "DEEPSEEK",
  "profile": "backend-default-ai-review",
  "model": "deepseek-v4-pro",
  "promptHash": "sha256-new",
  "contextPackVersion": "context-pack-v0",
  "retrieverVersion": "local-retriever-v0",
  "ruleGapVersion": "rule-gap-v0",
  "baseline": {},
  "candidate": {},
  "status": "PENDING",
  "totalCount": 3,
  "completedCount": 0,
  "failedCount": 0,
  "resultSummary": {
    "totalCount": 3,
    "statusCounts": {
      "PENDING": 3
    }
  },
  "durationMs": null,
  "items": []
}
```

### 11.2 查询回放记录

```http
GET /api/evaluation-runs
GET /api/evaluation-runs/{runId}
```

`GET /api/evaluation-runs` 查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `projectId` | Long | 按项目过滤 |
| `provider` | String | 按 Provider 过滤 |
| `profile` | String | 按 AI Review Profile 过滤 |
| `runType` | String | `EVALUATION / REVIEW_REPLAY` |
| `status` | String | `PENDING / RUNNING / COMPLETED / FAILED / CANCELED` |
| `pageNo` / `pageSize` | Number | 分页 |

详情接口返回 run 元信息和 `items`。列表接口不返回 `items`。

### 11.3 记录或更新样本运行结果

```http
PUT /api/evaluation-runs/{runId}/items/{itemId}
```

请求示例：

```json
{
  "status": "COMPLETED",
  "durationMs": 1234,
  "baselineSummary": {
    "findingCount": 2,
    "falsePositiveCount": 1,
    "contextMissingCount": 1,
    "overallLevel": "MAJOR"
  },
  "candidateSummary": {
    "findingCount": 1,
    "falsePositiveCount": 0,
    "contextMissingCount": 0,
    "overallLevel": "MINOR"
  },
  "resultSummary": {
    "matchedVerdict": true,
    "notes": "candidate reduced false positive on this sample"
  }
}
```

更新行为：

- 只能更新当前 `runId` 下的 item；跨 run item 返回 `RESOURCE_NOT_FOUND`。
- 自动刷新 run 的 `completedCount / failedCount / resultSummary / durationMs / status`。
- 不写回 `evaluation_cases`、`code_quality_review_results`、反馈池、项目策略或 Prompt。

前端最小入口：

- 顶部导航“回放记录”查看 run 列表。
- 回放详情页展示 baseline / candidate、sample set、聚合结果和 item 摘要。
- 首版不提供模型执行按钮、质量看板或胜出版本选择。

## 12. Deterministic Check API

Deterministic Check 用于把确定性检查结果作为结构化证据进入 Review 平台。M6 仅支持敏感信息扫描 MVP：只扫描当前任务 changed files / diff 的新增行，不做全仓扫描，不执行外部命令，不自动阻塞合并，不修改 AI Review 结果、Prompt、finding 等级或项目策略。

### 12.1 查询任务确定性检查结果

```http
GET /api/review-tasks/{taskId}/deterministic-checks
```

无记录响应 data：

```json
{
  "taskId": 10001,
  "status": "NOT_RUN",
  "latestRun": null,
  "runs": [],
  "explanation": "No deterministic check run has been recorded for this task."
}
```

有记录响应 data：

```json
{
  "taskId": 10001,
  "status": "COMPLETED",
  "latestRun": {
    "id": 1,
    "taskId": 10001,
    "projectId": 1,
    "checkType": "SECRET_SCAN",
    "status": "COMPLETED",
    "configSnapshot": {
      "configSource": "BUILTIN",
      "checkType": "SECRET_SCAN",
      "rulesetVersion": "secret-scan-mvp-v1",
      "scope": "DIFF_ADDED_LINES",
      "timeoutMs": 0,
      "maxFindings": 50
    },
    "resultSummary": {
      "scannedFileCount": 2,
      "addedLineCount": 4,
      "findingCount": 1,
      "ruleTypeCounts": {
        "API_TOKEN_ASSIGNMENT": 1
      },
      "truncated": false,
      "scope": "DIFF_ADDED_LINES"
    },
    "findings": [
      {
        "ruleType": "API_TOKEN_ASSIGNMENT",
        "filePath": "src/main/resources/application.yml",
        "lineNumber": 12,
        "hunkPosition": 3,
        "evidence": "apiKey: ****"
      }
    ],
    "durationMs": 3,
    "failureReason": null
  },
  "runs": []
}
```

`status` 可选值：

```text
NOT_RUN / COMPLETED / FAILED / NOT_APPLICABLE
```

安全边界：

- 只返回相对路径或脱敏后的路径摘要。
- `findings[].evidence` 必须脱敏，不返回真实 secret、token、认证头、大段源码、本地绝对路径或 provider raw output。
- 删除行、上下文行和 diff header 不参与扫描。

### 12.2 手动触发或重跑确定性检查

```http
POST /api/review-tasks/{taskId}/deterministic-checks/run
Content-Type: application/json
```

请求：

```json
{
  "checkType": "SECRET_SCAN"
}
```

说明：

- `checkType` 为空时默认 `SECRET_SCAN`。
- 每次触发都会新增一条 run，查询接口返回最新 run。
- 无 diff 或无新增行时返回 `NOT_APPLICABLE`，不影响规则提醒和 AI Review 主链路。
- 扫描失败时记录 `FAILED` 和 `failureReason`，不阻断原任务。

### 12.3 Context Pack 集成

构造 AI Review Context Pack 时，后端会读取当前任务最新确定性检查 run，并注入安全摘要：

```json
{
  "contextPack": {
    "deterministicChecks": {
      "securitySummary": {
        "status": "COMPLETED",
        "checkType": "SECRET_SCAN",
        "rulesetVersion": "secret-scan-mvp-v1",
        "scope": "DIFF_ADDED_LINES",
        "durationMs": 3,
        "findingCount": 1,
        "ruleTypeCounts": {
          "API_TOKEN_ASSIGNMENT": 1
        },
        "truncated": false,
        "failureReason": null,
        "findings": []
      }
    }
  }
}
```

`CONTEXT_PACK_BUILT` progress event 只展示同样的安全统计摘要，不展示源码、真实 secret、token、认证头、本地绝对路径或 provider raw output。

### 12.4 M10 缓存 Retriever 集成

M10 将 `CACHE_WRITE_DELETE_CHANGED` 纳入 Local Retriever 支持范围。构造 Context Pack 时：

- Planner 从 diff 新增 / 删除行提取安全摘要：`cacheKeys / cacheNames / keyExpressions / cacheOperations`。
- Retriever 在当前 task worktree 内用 bounded `rg --fixed-strings` 检索缓存 key、cache name、key expression 和必要操作 token 的读写 / 删除 / 过期使用点。
- 命中 snippets 后，`requestedContexts` 中的 `CACHE_USAGE_CONTEXT` 标记为 `available=true`，`availableSource=LOCAL_CACHE_USAGE_CONTEXT`。
- `summary.retrieverSupportedSignalTypes` 包含 `CACHE_WRITE_DELETE_CHANGED`；新任务不再为该 signal 生成 `UNSUPPORTED_PLANNER_SIGNAL` rule gap。
- 该能力不连接运行期 Redis / Caffeine / 其它缓存实例，不执行 AST / LSP / RAG，不修改 AI Review result、finding、Prompt 或项目策略。

安全边界：

- `localReferenceContext.searches[]` 只返回 bounded snippet、相对路径、行号和安全元数据：`cacheKeys / cacheNames / cacheOperations`。
- 请求或 diff 中的源码大段片段、provider raw output、真实 token、认证头和本地绝对路径不得进入 progress summary 或前端可观测摘要。

## 13. Review Quality Dashboard API

Review Quality Dashboard 用于把 M1-M6 已沉淀的评估样本、回放记录、finding 补证据和确定性检查结果聚合成最小质量治理看板。M7 只做统计与诊断，不自动修改 Prompt、不自动选择胜出版本、不生成项目策略、不自动降级或忽略 finding。

### 13.1 查询质量看板

```http
GET /api/review-quality/dashboard
```

查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `projectId` | Long | 按项目过滤 |
| `provider` | String | 按 Provider 过滤 |
| `profile` | String | 按 AI Review Profile 过滤 |
| `riskType` | String | 按风险类型过滤 |
| `verdict` | String | 按人工裁决过滤 |

核心统计口径：

- `summary.sampleCount` 来自匹配的 `evaluation_cases` 数量。
- `falsePositiveCount / contextMissingCount / levelTooHighCount / levelTooLowCount / duplicateFindingCount / missingFindingCount` 均按 `evaluation_cases.verdict` 计数。
- `falsePositiveRate` 和 `contextMissingRate` 以 `sampleCount` 为分母；空样本返回 `0`。
- `dimensions.projects / providers / profiles / riskTypes` 返回 top 聚合行，每行包含同样的样本数、verdict 计数和核心率。
- `replaySummary`、`refinementSummary`、`deterministicCheckSummary` 只作为辅助诊断摘要，不计入主样本数。

响应 data 示例：

```json
{
  "filters": {
    "projectId": 1,
    "provider": "DEEPSEEK",
    "profile": "backend-default-ai-review",
    "riskType": "SECURITY",
    "verdict": null
  },
  "summary": {
    "sampleCount": 6,
    "verdictCounts": {
      "FALSE_POSITIVE": 1,
      "CONTEXT_MISSING": 1,
      "LEVEL_TOO_HIGH": 1,
      "LEVEL_TOO_LOW": 1,
      "DUPLICATE": 1,
      "MISSING_FINDING": 1
    },
    "falsePositiveCount": 1,
    "contextMissingCount": 1,
    "levelTooHighCount": 1,
    "levelTooLowCount": 1,
    "duplicateFindingCount": 1,
    "missingFindingCount": 1,
    "falsePositiveRate": 0.1667,
    "contextMissingRate": 0.1667
  },
  "verdictDistribution": [
    { "verdict": "FALSE_POSITIVE", "count": 1 }
  ],
  "dimensions": {
    "projects": [
      {
        "key": "1",
        "label": "demo-service",
        "projectId": 1,
        "sampleCount": 6,
        "falsePositiveRate": 0.1667,
        "contextMissingRate": 0.1667
      }
    ],
    "providers": [],
    "profiles": [],
    "riskTypes": []
  },
  "replaySummary": {
    "itemCount": 2,
    "statusCounts": { "COMPLETED": 1, "FAILED": 1 },
    "completedCount": 1,
    "failedCount": 1,
    "durationMsTotal": 1234,
    "durationMsAvg": 617,
    "baselineTotals": {},
    "candidateTotals": {},
    "resultTotals": {}
  },
  "refinementSummary": {
    "recordCount": 2,
    "statusCounts": { "COMPLETED": 1, "FAILED": 1 },
    "completedCount": 1,
    "failedCount": 1,
    "failureReasons": [],
    "scopeNote": "Refinements are linked by filtered evaluation case task ids."
  },
  "deterministicCheckSummary": {
    "runCount": 1,
    "statusCounts": { "COMPLETED": 1 },
    "findingCount": 2,
    "ruleTypeCounts": { "API_TOKEN_ASSIGNMENT": 2 },
    "scopeNote": "Deterministic checks are project-scoped auxiliary diagnostics."
  },
  "ruleGapAttributionSummary": {
    "attributedCaseCount": 2,
    "unattributedCaseCount": 4,
    "causedOrRelatedCount": 1,
    "attributionTypeCounts": {
      "RULE_GAP_CAUSED": 1,
      "PROMPT_ISSUE": 1
    },
    "verdictCounts": {
      "FALSE_POSITIVE": 1,
      "CONTEXT_MISSING": 1
    }
  }
}
```

安全边界：

- 看板不返回源码片段、大段 diff、provider raw output、真实 secret、token、认证头或本地绝对路径。
- `deterministicCheckSummary` 只能按项目范围精确过滤；当请求包含 `provider / profile / riskType / verdict` 时，响应通过 `scopeNote` 明确该辅助摘要不能直接应用这些过滤。
- `ruleGapAttributionSummary` 来自匹配的 `evaluation_cases`，只统计人工归因结果，不自动推断因果。

## 14. Rule Gap Attribution API

Rule Gap Attribution 用于在 evaluation case 上记录某个 finding 与规则缺口之间的人工归因。M8 只做诊断，不自动补 Retriever、不自动修改 Prompt、不生成项目策略、不降级或忽略 finding。

### 14.1 查询评估样本规则缺口归因

```http
GET /api/evaluation-cases/{caseId}/rule-gap-attribution
```

未归因响应：

```json
{
  "caseId": 1,
  "attributionType": null,
  "ruleGapSummary": [],
  "comment": null,
  "attributedBy": null,
  "attributedAt": null,
  "explanation": "Rule gap attribution has not been recorded for this evaluation case."
}
```

已归因响应：

```json
{
  "caseId": 1,
  "attributionType": "RULE_GAP_CAUSED",
  "ruleGapSummary": [
    {
      "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
      "signal": "CACHE_WRITE_DELETE_CHANGED",
      "requestedContext": "CACHE_USAGE_CONTEXT",
      "suggestedCapability": "Add cache retriever.",
      "taskId": 10001,
      "reviewKey": "deepseek-main",
      "progressEventId": 123,
      "summaryKey": "UNSUPPORTED_PLANNER_SIGNAL|CACHE_WRITE_DELETE_CHANGED"
    }
  ],
  "comment": "人工确认该误判与缓存调用链上下文缺失相关。",
  "attributedBy": "admin",
  "attributedAt": "2026-07-02T10:00:00"
}
```

`attributionType` 可选值：

```text
RULE_GAP_CAUSED / RULE_GAP_RELATED / NOT_RULE_GAP / PROMPT_ISSUE /
MODEL_REASONING_ISSUE / PROJECT_POLICY_MISSING / INSUFFICIENT_LABEL
```

### 14.2 更新评估样本规则缺口归因

```http
PUT /api/evaluation-cases/{caseId}/rule-gap-attribution
Content-Type: application/json
```

请求：

```json
{
  "attributionType": "RULE_GAP_RELATED",
  "ruleGapSummary": [
    {
      "gapType": "UNAVAILABLE_REQUESTED_CONTEXT",
      "signal": "CONFIG_FILE_CHANGED",
      "requestedContext": "CONFIG_CONTEXT",
      "suggestedCapability": "Add config usage retrieval.",
      "taskId": 10001,
      "reviewKey": "deepseek-main",
      "progressEventId": 123
    }
  ],
  "comment": "缺少配置读取点上下文，导致模型只能按 diff 猜测。",
  "attributedBy": "alice"
}
```

说明：

- 创建 `source=AI_FINDING` 的 evaluation case 时，如果同任务 / reviewKey 存在最新 `CONTEXT_PACK_BUILT` progress event，后端会自动带入最多 5 条安全 rule gap 摘要。
- `GET /api/evaluation-cases` 和 `GET /api/evaluation-cases/{caseId}` 会在 `ruleGapAttribution` 字段返回同样的最小摘要。
- 规则缺口看板的推荐项会返回 `recommendationBasis`：`FREQUENCY_ONLY / PROVEN_BY_EVALUATION_CASES / MIXED`，并在 `attributionSignals` 中返回已归因样本数、归因类型分布和关联 verdict 分布。

安全边界：

- `ruleGapSummary` 只保存 `gapType / signal / requestedContext / suggestedCapability / taskId / reviewKey / progressEventId / summaryKey`。
- 不保存或返回源码片段、大段 diff、provider raw output、真实 token、认证头、本地绝对路径。
- 归因不会修改原 AI Review 结果、finding 等级、`contextStatus`、`confidence`、Prompt 或项目策略。

## 15. Review Quality Acceptance Gate API

Review Quality Acceptance Gate 用于记录规则、Retriever、Prompt、Context Pack、确定性检查或 Provider 改动的人工准入和退出验收。M9 只做治理记录和可观测，不做 CI / 合并阻塞，不做线上 Review runtime gate，不自动修改 Prompt、项目策略、AI Review 结果、finding 等级、`contextStatus` 或 `confidence`。

### 15.1 创建验收记录

```http
POST /api/review-quality/acceptance-gates
Content-Type: application/json
```

请求示例：

```json
{
  "projectId": 1,
  "title": "补缓存 Retriever 准入",
  "changeType": "RETRIEVER",
  "status": "ADMITTED",
  "provider": "DEEPSEEK",
  "profile": "backend-default-ai-review",
  "riskType": "CACHE_CONSISTENCY",
  "evaluationCaseIds": [101, 102],
  "evaluationRunIds": [201],
  "ruleGapSummary": [
    {
      "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
      "signal": "CACHE_WRITE_DELETE_CHANGED",
      "requestedContext": "CACHE_USAGE_CONTEXT",
      "suggestedCapability": "Add cache retriever.",
      "summaryKey": "UNSUPPORTED_PLANNER_SIGNAL|CACHE_WRITE_DELETE_CHANGED"
    }
  ],
  "admission": {
    "problemStatement": "缓存类误判集中在缺少调用方和 key 使用上下文。",
    "expectedBenefit": "降低缓存一致性误判。",
    "riskAssessment": "可能增加检索耗时和 Context Pack 预算。",
    "costEstimate": "低到中等。",
    "decisionBy": "admin",
    "decisionAt": "2026-07-02T10:00:00+08:00"
  }
}
```

响应 data 关键字段：

```json
{
  "id": 1,
  "projectId": 1,
  "projectName": "demo-service",
  "title": "补缓存 Retriever 准入",
  "changeType": "RETRIEVER",
  "status": "ADMITTED",
  "provider": "DEEPSEEK",
  "profile": "backend-default-ai-review",
  "riskType": "CACHE_CONSISTENCY",
  "evaluationCaseIds": [101, 102],
  "evaluationRunIds": [201],
  "evaluationCaseCount": 2,
  "evaluationRunCount": 1,
  "ruleGapSummary": [],
  "admission": {},
  "exit": {},
  "coreDelta": {},
  "createdAt": "2026-07-02T10:00:00",
  "updatedAt": "2026-07-02T10:00:00"
}
```

`changeType` 可选值：

```text
RULE / RETRIEVER / PROMPT / CONTEXT_PACK / DETERMINISTIC_CHECK / PROVIDER / OTHER
```

`status` 可选值：

```text
DRAFT / ADMITTED / RUNNING_VALIDATION / PASSED / FAILED / CANCELED
```

### 15.2 查询验收记录

```http
GET /api/review-quality/acceptance-gates
GET /api/review-quality/acceptance-gates/{gateId}
```

列表查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `projectId` | Long | 按项目过滤 |
| `changeType` | String | 按改动类型过滤 |
| `status` | String | 按验收状态过滤 |
| `provider` | String | 按 Provider 过滤 |
| `profile` | String | 按 AI Review Profile 过滤 |
| `riskType` | String | 按风险类型过滤 |
| `pageNo` / `pageSize` | Number | 分页 |

空列表返回标准分页结构，并包含可解释 `explanation`：

```json
{
  "items": [],
  "pageNo": 1,
  "pageSize": 20,
  "total": 0,
  "explanation": "No review quality acceptance gate record matches the current filters."
}
```

列表项不返回完整 `ruleGapSummary / admission / exit`，只返回 `evaluationCaseCount / evaluationRunCount / coreDelta`。详情接口返回完整治理记录。

### 15.3 更新准入信息与退出结果

```http
PUT /api/review-quality/acceptance-gates/{gateId}
Content-Type: application/json
```

请求示例：

```json
{
  "status": "PASSED",
  "exit": {
    "resultStatus": "IMPROVED",
    "falsePositiveDelta": -2,
    "contextMissingDelta": -1,
    "missingFindingDelta": 0,
    "findingCountDelta": -3,
    "durationDeltaMs": 120,
    "tokenCostDelta": 12.5,
    "notes": "目标样本误判下降，耗时略增。",
    "decidedBy": "admin",
    "decidedAt": "2026-07-02T11:00:00+08:00"
  }
}
```

`resultStatus` 可选值：

```text
IMPROVED / NEUTRAL / REGRESSED / INCONCLUSIVE
```

安全边界：

- `ruleGapSummary` 只保存 `gapType / signal / requestedContext / suggestedCapability / summaryKey`。
- 请求中携带的源码片段、大段 diff、provider raw output、Prompt 原文、真实 token、认证头或本地绝对路径会被忽略或脱敏。
- 关联 evaluation case / evaluation run 只保存 ID 列表，不复制样本源码、diff 或 provider 输出。
- 验收记录不会写回 evaluation case、evaluation run、AI Review result、finding、Prompt、项目策略或通知记录。

### 15.4 质量看板摘要

`GET /api/review-quality/dashboard` 会返回 `acceptanceGateSummary`：

```json
{
  "recordCount": 1,
  "statusCounts": {
    "PASSED": 1
  },
  "changeTypeCounts": {
    "RETRIEVER": 1
  },
  "latestStatus": "PASSED",
  "latestGateId": 1,
  "latestTitle": "补缓存 Retriever 准入",
  "latestUpdatedAt": "2026-07-02T11:00:00",
  "scopeNote": "Acceptance gates are manual governance records and do not block runtime review or code merges."
}
```

## 16. DTO / VO 边界

### 16.1 WebhookTriggerCommand

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

### 16.2 ChangeAnalysisResultDTO

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

### 16.3 RiskCardVO

前端直接消费完整 RiskCard JSON；后端不应再拼接不可解析的展示文本作为主要输出。
