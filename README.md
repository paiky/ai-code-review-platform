# AI 变更风险审查平台

本仓库当前处于 MVP 基础工程阶段。设计文档位于 `docs` 目录，后端基础工程位于 `backend` 目录。

## Backend 本地启动

### 1. 环境要求

- JDK 21+
- Maven 3.6+
- MySQL 8.0+

### 2. 创建数据库

先在本地 MySQL 创建数据库：

```sql
CREATE DATABASE ai_code_review DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 3. 配置数据库连接

后端默认读取以下环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MYSQL_URL` | `jdbc:mysql://localhost:3306/ai_code_review?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&useSSL=false` | MySQL JDBC URL |
| `MYSQL_USERNAME` | `root` | MySQL 用户名 |
| `MYSQL_PASSWORD` | `root` | MySQL 密码 |
| `SERVER_PORT` | `8080` | 后端端口 |

PowerShell 示例：

```powershell
$env:MYSQL_URL="jdbc:mysql://localhost:3306/ai_code_review?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&useSSL=false"
$env:MYSQL_USERNAME="root"
$env:MYSQL_PASSWORD="root"
```

### 4. 启动后端

```powershell
cd backend
mvn spring-boot:run
```

首次启动时 Flyway 会自动执行：

```text
src/main/resources/db/migration/V1__init_mvp_schema.sql
```

该 migration 会创建 MVP 所需基础表：

- `projects`
- `review_tasks`
- `review_results`
- `rule_templates`
- `notification_records`
- `notification_webhooks`

同时会初始化 `backend-default` 规则模板。

### 5. 验证启动

健康检查接口：

```powershell
curl http://localhost:8080/api/health
```

预期返回：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "status": "UP",
    "application": "ai-code-review-backend",
    "time": "2026-04-19T13:00:00+08:00"
  },
  "traceId": "..."
}
```

Actuator 健康检查：

```powershell
curl http://localhost:8080/actuator/health
```

## 当前后端范围

已完成基础工程骨架：

- Spring Boot Maven 工程。
- MySQL 数据源配置。
- Flyway 数据库 migration。
- 统一响应结构 `ApiResponse`。
- 统一异常处理 `GlobalExceptionHandler`。
- 请求 traceId 过滤器。
- 健康检查接口 `/api/health`。
- 按 MVP 文档预留核心模块包结构。

暂未实现复杂业务链路：

- GitLab webhook controller。
- diff 拉取与变更分析。
- 风险规则执行。
- 风险卡片生成。
- 钉钉推送。
- Web 管理页面。

推荐下一步先实现核心 DTO / VO / Entity / enum，再实现 GitLab webhook 到 ReviewTask 落库的最小链路。
## GitLab MR Webhook 最小链路

当前已实现 GitLab Merge Request webhook 的最小可用链路：

```text
POST /api/webhooks/gitlab/merge-request
  -> 校验 X-Gitlab-Event 与 object_kind
  -> 解析项目、MR、分支、作者、changedFiles 摘要、eventTime
  -> 自动 upsert projects
  -> 创建 review_tasks
  -> 保存 gitlab_mr_webhook_events.raw_payload
  -> GET /api/review-tasks/{taskId} 查询详情
```

说明：真实 GitLab MR webhook 通常不直接包含完整 changed files。为了本地验证，mock payload 支持传入顶层 `changedFiles` 数组，后续接入 GitLab API 后再由 MR iid 拉取真实 diff / changed files。

### 本地 mock webhook 请求

PowerShell 示例：

```powershell
$payload = @"
{
  "object_kind": "merge_request",
  "event_type": "merge_request",
  "event_time": "2026-04-19T13:30:00+08:00",
  "project": {
    "id": 1001,
    "name": "demo-service",
    "web_url": "https://gitlab.example.com/group/demo-service"
  },
  "object_attributes": {
    "id": 90001,
    "iid": 12,
    "action": "open",
    "source_branch": "feature/risk-demo",
    "target_branch": "main",
    "url": "https://gitlab.example.com/group/demo-service/-/merge_requests/12",
    "updated_at": "2026-04-19T13:30:00+08:00",
    "last_commit": {
      "id": "abcdef123456"
    }
  },
  "user": {
    "name": "Alice",
    "username": "alice"
  },
  "changedFiles": [
    {
      "old_path": "src/main/java/com/demo/order/OrderController.java",
      "new_path": "src/main/java/com/demo/order/OrderController.java",
      "new_file": false,
      "deleted_file": false,
      "renamed_file": false
    },
    {
      "old_path": "src/main/resources/mapper/OrderMapper.xml",
      "new_path": "src/main/resources/mapper/OrderMapper.xml",
      "new_file": false,
      "deleted_file": false,
      "renamed_file": false
    }
  ]
}
"@

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Merge Request Hook" } `
  -Body $payload
```

预期返回：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "taskId": 1,
    "status": "PENDING",
    "projectId": "1001",
    "projectName": "demo-service",
    "mrId": "12"
  },
  "traceId": "..."
}
```

### 查询任务详情

```powershell
curl http://localhost:8080/api/review-tasks/1
```

详情会返回基础任务字段、MR 字段、`changedFilesSummary` 和 `rawPayload`。当前任务状态固定为 `PENDING`，后续接入变更分析与风险引擎后再推进状态流转。
## 前后端联调步骤

### 1. 启动后端

确认 MySQL 已创建数据库：

```sql
CREATE DATABASE ai_code_review DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

PowerShell 示例：

```powershell
$env:MYSQL_USERNAME="root"
$env:MYSQL_PASSWORD="root"
$env:DINGTALK_WEBHOOK_URL=""
cd backend
mvn spring-boot:run
```

说明：

- `DINGTALK_WEBHOOK_URL` 为空时，系统仍会生成风险卡片并保存推送记录，推送状态为 `SKIPPED`。
- 配置真实钉钉机器人 webhook 后，任务分析完成会自动推送 IM 消息。

### 2. 启动前端

首次运行需要安装依赖：

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

访问：

```text
http://localhost:5173
```

前端 Vite dev server 已配置 `/api` 代理到 `http://localhost:8080`。

### 3. 发送 mock GitLab MR webhook

```powershell
$payload = @"
{
  "object_kind": "merge_request",
  "event_type": "merge_request",
  "event_time": "2026-04-19T13:30:00+08:00",
  "project": {
    "id": 1001,
    "name": "demo-service",
    "web_url": "https://gitlab.example.com/group/demo-service"
  },
  "object_attributes": {
    "id": 90001,
    "iid": 12,
    "action": "open",
    "source_branch": "feature/risk-demo",
    "target_branch": "main",
    "url": "https://gitlab.example.com/group/demo-service/-/merge_requests/12",
    "updated_at": "2026-04-19T13:30:00+08:00",
    "last_commit": {
      "id": "abcdef123456"
    }
  },
  "user": {
    "name": "Alice",
    "username": "alice"
  },
  "changedFiles": [
    {
      "old_path": "src/main/java/com/demo/order/OrderController.java",
      "new_path": "src/main/java/com/demo/order/OrderController.java",
      "diffText": "+ @GetMapping(\"/api/orders/{id}\")\n+ public OrderResponse detail(@PathVariable Long id) { return service.detail(id); }"
    },
    {
      "old_path": "src/main/resources/mapper/OrderMapper.xml",
      "new_path": "src/main/resources/mapper/OrderMapper.xml",
      "diffText": "+ select id, status from orders where id = #{id}"
    },
    {
      "old_path": "src/main/java/com/demo/order/OrderCacheService.java",
      "new_path": "src/main/java/com/demo/order/OrderCacheService.java",
      "diffText": "+ redisTemplate.opsForValue().set(\"order:detail\" + id, value);"
    }
  ]
}
"@

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Merge Request Hook" } `
  -Body $payload
```

成功后，后端会同步完成：

```text
webhook -> 任务落库 -> 变更分析 -> 风险卡片 -> review_results 落库 -> 钉钉推送/跳过记录
```

### 4. 验证接口

```powershell
curl http://localhost:8080/api/review-tasks
curl http://localhost:8080/api/review-tasks/1
curl http://localhost:8080/api/review-tasks/1/result
```

### 5. 前端查看

打开 `http://localhost:5173`：

- 任务列表页展示项目、MR、分支、状态、风险等级和风险项数量。
- 任务详情页展示风险卡片、分析结果和原始事件摘要。
- 风险卡片展示整体风险、受影响资源、风险项、推荐检查项和建议 review 角色。
## 审查模板能力

系统内置三套 MVP 模板：

| 模板 | 适用场景 | 默认启用规则 |
| --- | --- | --- |
| `backend-default` | 后端服务 | API、DB、CACHE、MQ、CONFIG |
| `frontend-default` | 前端项目 | API、CONFIG |
| `general-default` | 通用项目 | API、DB、CONFIG |

模板配置存储在 `rule_templates` 表中，`enabled_rule_codes` 决定启用哪些风险规则，`config_json.recommendedChecks` 定义模板级推荐检查项。项目表 `projects.default_template_code` 绑定项目默认模板。

### 模板接口

```powershell
curl http://localhost:8080/api/rule-templates
curl http://localhost:8080/api/rule-templates/backend-default
```

### 项目默认模板绑定

```powershell
Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8080/api/projects/1/default-template" `
  -ContentType "application/json" `
  -Body '{"templateCode":"frontend-default"}'
```

### 手动发起审查并指定模板

```powershell
$payload = @"
{
  "projectId": 1,
  "templateCode": "general-default",
  "sourceBranch": "feature/manual-review",
  "targetBranch": "main",
  "authorName": "Manual Tester",
  "changedFiles": [
    {
      "path": "src/main/java/com/demo/order/OrderController.java",
      "oldPath": "src/main/java/com/demo/order/OrderController.java",
      "newPath": "src/main/java/com/demo/order/OrderController.java",
      "changeType": "MODIFIED",
      "diffText": "+ @PostMapping(\"/api/orders\")"
    },
    {
      "path": "src/main/resources/application.yml",
      "oldPath": "src/main/resources/application.yml",
      "newPath": "src/main/resources/application.yml",
      "changeType": "MODIFIED",
      "diffText": "+ order:\n+   feature-enabled: true"
    }
  ]
}
"@

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/review-tasks/manual" `
  -ContentType "application/json" `
  -Body $payload
```

如果 `templateCode` 为空，系统会使用项目绑定的 `default_template_code`。

### 前端配置页面

启动前端后访问：

```text
http://localhost:5173
```

点击顶部“模板配置”：

- 查看 `backend-default` / `frontend-default` / `general-default`。
- 查看每个模板启用的规则和推荐检查项。
- 修改项目默认模板绑定。