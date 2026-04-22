# AI 变更风险审查平台

本仓库当前处于 MVP 原型阶段。设计文档位于 `docs` 目录，后端工程位于 `backend` 目录，前端工程位于 `frontend` 目录。

当前已经具备可本地演示的主链路：

```text
mock GitLab MR webhook
  -> 创建项目与审查任务
  -> 保存原始 webhook payload
  -> 变更分析
  -> 风险规则引擎
  -> 生成风险卡片
  -> 审查结果落库
  -> 钉钉推送或 SKIPPED 记录
  -> 前端查看任务与风险卡片
```

说明：P0 演示链路可以继续使用 mock payload 中的 `changedFiles` / `diffText`。真实 GitLab MR webhook 通常不会携带完整 diff，当前已支持在 payload 缺少 changed files 时按 `projectId + mrIid` 调用 GitLab API 补拉 diff。

## 当前能力

已完成：

- Spring Boot 后端基础工程。
- MySQL 数据源配置。
- Flyway 数据库 migration。
- 统一响应结构 `ApiResponse`。
- 统一异常处理 `GlobalExceptionHandler`。
- 请求 traceId。
- CORS 配置。
- 健康检查接口 `/api/health`。
- GitLab MR webhook controller。
- mock changed files / diffText 解析。
- API / DB / CACHE / MQ / CONFIG 启发式变更分析。
- 规则引擎与结构化风险卡片生成。
- 审查任务和审查结果落库。
- 钉钉通知器；未配置 webhook 时记录 `SKIPPED`。
- React + Ant Design 最小管理页面。
- 审查模板查看与项目默认模板绑定。
- 手动审查后端接口。
- payload 不带 `changedFiles` 时，可通过 GitLab API 拉取 MR diff。
- GitLab 扫描模式下通过 project detail / MR detail 回填真实项目名、MR URL、分支、作者和 commit sha。
- DB 风险第一轮细分识别：`DB_SCHEMA`、`DB_SQL`、`ORM_MAPPING`、`ENTITY_MODEL`、`DATA_MIGRATION`，并保留 `DB` 聚合类型兼容旧模板。
- RiskCard schema 已对齐当前后端对象，前端风险卡片可展示 DB 细分类型、置信度、命中原因、关联信号和证据。

暂未完成：

- 真实 GitLab diff 拉取的项目级凭证配置与生产级重试策略。
- Jenkins 入口。
- 前端手动发起审查页面。
- 项目级钉钉 webhook 配置读取。
- 主链路集成测试。
- RiskCard schema 校验测试和钉钉消息展示增强。
- knowledge-base / 人工反馈闭环。

## 后端本地启动

### 1. 环境要求

- JDK 21+
- Maven 3.6+
- MySQL 8.0+

如果本机默认 Java 不是 21，可以把 JDK 21 解压到仓库内的 `tools/jdk-21` 目录，后续通过项目脚本临时使用该 JDK 启动后端，不需要修改系统级 `JAVA_HOME`。

推荐目录结构：

```text
tools/
  jdk-21/
    bin/
      java.exe
```

说明：`tools/jdk-21*` 已加入 `.gitignore`。不建议把 JDK 二进制提交到仓库，避免仓库体积、平台差异和安全更新问题。

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
| `MYSQL_PASSWORD` | 以 `backend/src/main/resources/application.yml` 为准 | MySQL 密码 |
| `SERVER_PORT` | `8080` | 后端端口 |
| `DINGTALK_WEBHOOK_URL` | 空 | 钉钉机器人 webhook，空值时推送记录为 `SKIPPED` |
| `GITLAB_API_ENABLED` | `false` | payload 不带 `changedFiles` 时是否启用 GitLab API 补拉 diff |
| `GITLAB_BASE_URL` | 空 | GitLab base URL，例如 `https://gitlab.example.com` |
| `GITLAB_TOKEN` | 空 | GitLab access token，通过 `PRIVATE-TOKEN` header 使用 |
| `GITLAB_DIFF_PER_PAGE` | `100` | GitLab MR diff 分页大小 |

PowerShell 示例：

```powershell
$env:MYSQL_URL="jdbc:mysql://localhost:3306/ai_code_review?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&useSSL=false"
$env:MYSQL_USERNAME="root"
$env:MYSQL_PASSWORD="root"
$env:DINGTALK_WEBHOOK_URL=""
$env:GITLAB_API_ENABLED="false"
```

### 4. 启动后端

推荐使用项目脚本启动。脚本会优先查找 `tools/jdk-21` / `.jdk/jdk-21`，再查找 `JAVA21_HOME` / `JDK21_HOME` / `JAVA_HOME`，并要求 Java 版本至少为 21：

```powershell
.\scripts\run-backend.cmd
```

如果启动失败，`.cmd` 会停留在窗口中，方便查看错误。自动化脚本中如需失败后直接退出，可先设置 `NO_PAUSE=1`。

也可以继续使用本机环境中的 Maven 和 JDK：

```powershell
cd backend
mvn spring-boot:run
```

首次启动时 Flyway 会自动执行：

```text
src/main/resources/db/migration/V1__init_mvp_schema.sql
src/main/resources/db/migration/V2__gitlab_mr_webhook_events.sql
src/main/resources/db/migration/V3__review_templates.sql
src/main/resources/db/migration/V4__db_fine_grained_rule_templates.sql
```

当前 migration 会创建 MVP 所需基础表：

- `projects`
- `review_tasks`
- `review_results`
- `rule_templates`
- `notification_records`
- `notification_webhooks`
- `gitlab_mr_webhook_events`

并初始化三套模板：

- `backend-default`
- `frontend-default`
- `general-default`

其中 `V4` 会将后端和通用模板升级到 DB 细分风险规则，避免仅修改 Mapper XML 或实体字段时被直接误判为数据库结构变更。

### 5. 验证后端

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
    "time": "2026-04-21T22:37:18.434710600+08:00"
  },
  "traceId": "..."
}
```

Actuator 健康检查：

```powershell
curl http://localhost:8080/actuator/health
```

`components.db.status` 应为 `UP`。

## 前端本地启动

推荐使用项目脚本启动。首次运行时如果 `frontend/node_modules` 不存在，脚本会先执行 `npm install`，然后启动 Vite dev server：

```powershell
.\scripts\run-frontend.cmd
```

如果启动失败，`.cmd` 会停留在窗口中，方便查看错误。自动化脚本中如需失败后直接退出，可先设置 `NO_PAUSE=1`。

也可以继续手动启动：

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

## P0 本地演示闭环

本节用于验证当前 MVP 原型是否能在本机跑通：

```text
后端健康检查
  -> 前端页面访问
  -> mock GitLab MR webhook
  -> 审查任务 SUCCESS
  -> 风险卡片生成
  -> 审查结果查询
  -> 钉钉通知记录 SUCCESS 或 SKIPPED
```

### 1. 确认服务状态

```powershell
curl http://localhost:8080/api/health
curl http://localhost:8080/actuator/health
curl http://localhost:5173
```

后端应返回 `UP`，前端应能打开页面。

### 2. 发送 mock GitLab MR webhook

下面的 payload 同时覆盖 API、DB、CACHE、MQ、CONFIG 五类变更，适合用于 P0 演示：

```powershell
$payload = @"
{
  "object_kind": "merge_request",
  "event_type": "merge_request",
  "event_time": "2026-04-21T22:38:00+08:00",
  "project": {
    "id": 1001,
    "name": "demo-service",
    "web_url": "https://gitlab.example.com/group/demo-service"
  },
  "object_attributes": {
    "id": 90021,
    "iid": 21,
    "action": "open",
    "source_branch": "feature/p0-demo-risk-review",
    "target_branch": "main",
    "url": "https://gitlab.example.com/group/demo-service/-/merge_requests/21",
    "updated_at": "2026-04-21T22:38:00+08:00",
    "last_commit": {
      "id": "p0demoabcdef123456"
    }
  },
  "user": {
    "name": "P0 Demo User",
    "username": "p0-demo"
  },
  "changedFiles": [
    {
      "old_path": "src/main/java/com/demo/order/OrderController.java",
      "new_path": "src/main/java/com/demo/order/OrderController.java",
      "new_file": false,
      "deleted_file": false,
      "renamed_file": false,
      "diffText": "+ @PostMapping(\"/api/orders/{id}/confirm\")\n+ public OrderResponse confirm(@PathVariable Long id) { return orderService.confirm(id); }"
    },
    {
      "old_path": "src/main/resources/mapper/OrderMapper.xml",
      "new_path": "src/main/resources/mapper/OrderMapper.xml",
      "new_file": false,
      "deleted_file": false,
      "renamed_file": false,
      "diffText": "+ update orders set status = 'CONFIRMED' where id = #{id}\n+ select id, status from orders where id = #{id}"
    },
    {
      "old_path": "src/main/java/com/demo/order/OrderCacheService.java",
      "new_path": "src/main/java/com/demo/order/OrderCacheService.java",
      "new_file": false,
      "deleted_file": false,
      "renamed_file": false,
      "diffText": "+ redisTemplate.opsForValue().set(\"order:detail:\" + id, value);\n+ redisTemplate.delete(\"order:list\");"
    },
    {
      "old_path": "src/main/java/com/demo/order/OrderEventPublisher.java",
      "new_path": "src/main/java/com/demo/order/OrderEventPublisher.java",
      "new_file": false,
      "deleted_file": false,
      "renamed_file": false,
      "diffText": "+ rabbitTemplate.convertAndSend(\"order.exchange\", \"order.confirmed\", event);"
    },
    {
      "old_path": "src/main/resources/application.yml",
      "new_path": "src/main/resources/application.yml",
      "new_file": false,
      "deleted_file": false,
      "renamed_file": false,
      "diffText": "+ order:\n+   confirm-timeout-seconds: 30\n+   enable-confirm-event: true"
    }
  ]
}
"@

$webhookResponse = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Merge Request Hook" } `
  -Body $payload

$webhookResponse | ConvertTo-Json -Depth 20
$taskId = $webhookResponse.data.taskId
```

预期返回：

```json
{
  "success": true,
  "code": "OK",
  "message": "success",
  "data": {
    "taskId": 2,
    "status": "SUCCESS",
    "projectId": "1001",
    "projectName": "demo-service",
    "mrId": "21"
  },
  "traceId": "..."
}
```

说明：`taskId` 会随本机数据库已有数据递增，不一定等于示例里的 `2`。

### 3. 验证任务列表、详情和风险结果

```powershell
Invoke-RestMethod -Uri "http://localhost:8080/api/review-tasks" -Method Get |
  ConvertTo-Json -Depth 20

Invoke-RestMethod -Uri "http://localhost:8080/api/review-tasks/$taskId" -Method Get |
  ConvertTo-Json -Depth 20

Invoke-RestMethod -Uri "http://localhost:8080/api/review-tasks/$taskId/result" -Method Get |
  ConvertTo-Json -Depth 30
```

预期结果：

- 任务状态为 `SUCCESS`。
- `riskLevel` 为 `HIGH`。
- `riskItemCount` 为 `5`。
- `changeAnalysis.changeTypes` 包含 `API`、`DB`、`CACHE`、`MQ`、`CONFIG`。
- `riskCard` 包含风险项、受影响资源、推荐检查项和建议 review 角色。

### 4. 验证通知记录

如果本机安装了 MySQL CLI，可以查询通知记录：

```powershell
mysql -h localhost -P 3306 -u root -p --default-character-set=utf8mb4 ai_code_review --execute "SELECT id, task_id, result_id, channel, status, target, error_message, sent_at, created_at FROM notification_records WHERE task_id = $taskId ORDER BY id DESC LIMIT 5;"
```

预期结果：

- 配置了 `DINGTALK_WEBHOOK_URL`：`status` 通常为 `SUCCESS` 或 `FAILED`。
- 未配置 `DINGTALK_WEBHOOK_URL`：`status` 为 `SKIPPED`，`error_message` 为 `DingTalk webhook is not configured`。

### 5. 前端查看

打开：

```text
http://localhost:5173
```

验证：

- 任务列表页展示 `demo-service`、MR、分支、状态、风险等级和风险项数量。
- 任务详情页展示风险卡片、分析结果和原始事件摘要。
- 风险卡片展示整体风险、受影响资源、风险项、推荐检查项和建议 review 角色。

### 6. 自动化验证

后端测试：

```powershell
cd backend
mvn -q test
```

前端构建：

```powershell
cd frontend
npm.cmd run build
```

## GitLab MR Webhook 接口

当前接口：

```text
POST /api/webhooks/gitlab/merge-request
```

处理流程：

```text
校验 X-Gitlab-Event 与 object_kind
  -> 解析项目、MR、分支、作者、changedFiles 摘要、eventTime
  -> 自动 upsert projects
  -> 创建 review_tasks
  -> 保存 gitlab_mr_webhook_events.raw_payload
  -> 变更分析
  -> 风险卡片生成
  -> review_results 落库
  -> 钉钉推送或 SKIPPED 记录
```

说明：真实 GitLab MR webhook 通常不直接包含完整 changed files。为了本地验证，mock payload 支持传入顶层 `changedFiles` 数组；真实接入时可启用 GitLab API，由后端按 MR iid 拉取真实 diff / changed files。

## 真实 GitLab diff 接入

当 webhook payload 不包含 `changedFiles`、`changed_files`、`object_attributes.changed_files` 或 `changes.changed_files.current` 时，后端会尝试通过 GitLab API 拉取 MR diff。

推荐使用本地忽略文件保存联调配置。先复制示例：

```powershell
New-Item -ItemType Directory -Force .local
Copy-Item examples/gitlab.env.example .local/gitlab.env
```

然后编辑 `.local/gitlab.env`，填入真实的 `GITLAB_BASE_URL`、`GITLAB_TOKEN`、`GITLAB_PROJECT_ID`、`GITLAB_MR_IID` 和 MySQL 密码。`.local/` 已加入 `.gitignore`，不要提交 token。

使用项目脚本重启后端时，会自动加载 `.local/gitlab.env`：

```powershell
.\scripts\run-backend.cmd
```

后端启动成功后，可以一键验证 GitLab diff 拉取链路：

```powershell
.\scripts\verify-gitlab-diff.cmd
```

验证脚本会先读取 GitLab project detail 和 MR detail，再发送一个不携带 `changedFiles` 的模拟 webhook。后端会使用 GitLab API 回填真实项目名称、MR URL、source/target branch、作者和 commit sha，避免验证模式下前端显示占位项目名或占位分支名。

启用方式：

```powershell
$env:GITLAB_API_ENABLED="true"
$env:GITLAB_BASE_URL="https://gitlab.example.com"
$env:GITLAB_TOKEN="your_access_token"
$env:GITLAB_DIFF_PER_PAGE="100"
```

后端调用接口：

```text
GET {GITLAB_BASE_URL}/api/v4/projects/{projectId}/merge_requests/{mrIid}/diffs?page=1&per_page=100
PRIVATE-TOKEN: {GITLAB_TOKEN}
```

兼容说明：部分 GitLab 版本（例如 14.x）可能不支持 MR `diffs` 接口并返回 404。当前后端和验证脚本会自动 fallback 到：

```text
GET {GITLAB_BASE_URL}/api/v4/projects/{projectId}/merge_requests/{mrIid}/changes
PRIVATE-TOKEN: {GITLAB_TOKEN}
```

处理规则：

- payload 自带 `changedFiles` 时，优先使用 payload，`changedFilesSummary.source = payload`。
- payload 不带 `changedFiles` 时，使用 GitLab API 补拉，`changedFilesSummary.source = gitlab_api`。
- GitLab API 未启用、`GITLAB_BASE_URL` 缺失、`GITLAB_TOKEN` 缺失、接口失败或返回空 diff 时，任务会标记为 `FAILED`。

可以先手动验证 GitLab token：

```powershell
curl `
  --header "PRIVATE-TOKEN: $env:GITLAB_TOKEN" `
  "$env:GITLAB_BASE_URL/api/v4/projects/<projectId>/merge_requests/<mrIid>/diffs?page=1&per_page=20"
```

真实 webhook 验证步骤：

1. 启动后端时配置 `GITLAB_API_ENABLED=true`、`GITLAB_BASE_URL`、`GITLAB_TOKEN`。
2. 发送不带 `changedFiles` 的 GitLab MR webhook payload。
3. 查询 `GET /api/review-tasks/{taskId}`，确认 `changedFilesSummary.source` 为 `gitlab_api`。
4. 查询 `GET /api/review-tasks/{taskId}/result`，确认风险卡片正常生成。

## 查询接口

```powershell
curl http://localhost:8080/api/review-tasks
curl http://localhost:8080/api/review-tasks/{taskId}
curl http://localhost:8080/api/review-tasks/{taskId}/result
```

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

## 下一步建议

推荐按以下顺序继续推进：

1. 新增 `examples/`，保存 mock GitLab webhook 和 manual review 请求示例。
2. 补主链路集成测试，覆盖 `webhook -> review_results -> notification_records`。
3. 完善 GitLab diff 接入的真实环境联调、项目级凭证和失败重试。
4. 补 RiskCard schema 校验测试，并增强钉钉消息中的 DB 细分展示。
5. 将 GitLab token 和钉钉 webhook 从环境变量升级为项目级数据库配置。
