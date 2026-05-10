# AI 变更提醒与代码质量审查平台

本仓库是一个可接入 GitLab / 钉钉 / 本地或 API 模式 AI Review 的研发质量平台原型。当前主流程围绕代码变更生成结构化“提醒卡片”，再按需触发代码质量 AI Review。

代码目录：

- `backend/`：Spring Boot 后端。
- `frontend/`：React + Ant Design 前端。
- `docs/`：设计、API、schema 与实施计划文档。
- `examples/`：Webhook 与手动审查示例请求。
- `scripts/`：本地启动、GitLab 验证脚本。

## 当前主链路

```text
GitLab MR webhook / GitLab Push webhook / 手动审查
  -> 创建 review task
  -> 保存原始事件
  -> 解析 changed files / diff
  -> 变更分析
  -> 规则引擎生成提醒卡片
  -> 结果落库
  -> 钉钉推送或 SKIPPED 记录
  -> 前端查看任务详情
  -> 可选触发代码质量 AI Review
```

说明：后端 JSON 字段仍兼容历史命名，例如 `riskCard`、`riskItems`、`riskLevel`。前端和钉钉展示层已按“提醒卡片 / 提醒项”处理，后续如需彻底改字段名，应单独迁移 schema、DTO、数据库和历史数据。

## 当前能力

- GitLab `Merge Request Hook` 与 `Push Hook` 共用 `/api/webhooks/gitlab/merge-request` 入口。
- MR payload 缺少 changed files 时，可调用 GitLab API 拉取 MR diff，并兼容 `/diffs` 与 `/changes`。
- Push Hook 可优先调用 GitLab compare API 拉取 `beforeSha -> afterSha` diff；失败或空 diff 时回退到 push payload 文件列表。
- 变更分析覆盖 API、DB、MQ、Redis/缓存、配置等类型。
- DB 细分识别覆盖 `DB_SCHEMA`、`DB_SQL`、`ORM_MAPPING`、`ENTITY_MODEL`、`DATA_MIGRATION`。
- MQ / 缓存细分识别覆盖 producer、consumer、消息结构、topic 配置、重试死信、cache key、TTL、失效、读写、序列化等场景。
- `@Value` 配置占位符变更会进入重点变更提醒。
- 提醒卡片在前端按 DB / MQ / Redis/缓存 / 配置分组展示。
- 钉钉消息按模板 `focusChangeTypes` 过滤提醒来源，只输出简洁提醒和平台详情链接。
- 审查任务、变更分析结果、提醒卡片、通知记录均落库。
- 代码质量 AI Review 支持 `CODEX_CLI`、`OPENAI_API`、`ANTHROPIC_API` 三种 provider。
- AI Review 支持 profile / prompt 配置、全局执行方式切换、API Key 配置、MR 自动触发开关、重试、执行过程展示。
- 本地 GitLab CE 验证脚本位于 `local-gitlab/` 与 `scripts/verify-gitlab-diff.*`。

## 环境要求

- JDK 21+
- Maven 3.6+
- MySQL 8.0+
- Node.js 18+，推荐 20+

如果本机默认 Java 不是 21，可以将 JDK 21 解压到仓库内 `tools/jdk-21`，项目脚本会优先使用该目录。

## 后端配置

后端默认读取环境变量，也支持通过 `.local/gitlab.env` 配合启动脚本加载本地配置。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MYSQL_URL` | `jdbc:mysql://localhost:3306/ai_code_review?...` | MySQL JDBC URL |
| `MYSQL_USERNAME` | `root` | MySQL 用户 |
| `MYSQL_PASSWORD` | `root` | MySQL 密码 |
| `SERVER_PORT` | `8080` | 后端端口 |
| `FRONTEND_ALLOWED_ORIGINS` | `http://localhost:5173` | CORS 允许来源 |
| `PLATFORM_BASE_URL` | `http://localhost:5173` | 钉钉“查看平台详情”链接前缀 |
| `DINGTALK_WEBHOOK_URL` | 空 | 钉钉机器人 webhook，空值时通知记录为 `SKIPPED` |
| `DINGTALK_ENABLED` | `true` | 是否启用钉钉发送 |
| `GITLAB_API_ENABLED` | `false` | 是否启用 GitLab API 补拉 diff |
| `GITLAB_BASE_URL` | 空 | GitLab base URL |
| `GITLAB_TOKEN` | 空 | GitLab access token |
| `GITLAB_DIFF_PER_PAGE` | `100` | MR diff 分页大小 |
| `CODE_QUALITY_REVIEW_ENABLED` | `false` | 是否启用代码质量 Review 能力 |
| `CODE_QUALITY_REVIEW_PROVIDER` | `CODEX_CLI` | 默认 provider |
| `CODE_QUALITY_WORKSPACE_ROOT` | 空 | 本地 CLI 可访问仓库根目录限制 |
| `CODEX_CLI_COMMAND` | 按 OS 推断 | Windows 默认 `codex.cmd`，Linux 默认 `codex` |
| `CODEX_CLI_MODEL` | 空 | Codex CLI 模型覆盖 |
| `CODEX_CLI_TIMEOUT_SECONDS` | `600` | Codex CLI 超时时间 |
| `OPENAI_API_KEY` | 空 | OpenAI API key |
| `OPENAI_RESPONSES_URL` | `https://api.openai.com/v1/responses` | OpenAI Responses API 地址 |
| `OPENAI_CODE_REVIEW_MODEL` | `gpt-5.4` | OpenAI provider 模型 |
| `OPENAI_CODE_REVIEW_TIMEOUT_SECONDS` | `120` | OpenAI 请求超时时间 |
| `ANTHROPIC_API_KEY` | 空 | Anthropic API key |
| `ANTHROPIC_MESSAGES_URL` | `https://api.anthropic.com/v1/messages` | Anthropic Messages API 地址 |
| `ANTHROPIC_CODE_REVIEW_MODEL` | `claude-sonnet-4-5` | Anthropic provider 模型 |
| `ANTHROPIC_CODE_REVIEW_TIMEOUT_SECONDS` | `120` | Anthropic 请求超时时间 |

PowerShell 示例：

```powershell
$env:MYSQL_URL="jdbc:mysql://localhost:3306/ai_code_review?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&useSSL=false"
$env:MYSQL_USERNAME="root"
$env:MYSQL_PASSWORD="root"
$env:DINGTALK_WEBHOOK_URL=""
$env:GITLAB_API_ENABLED="false"
```

## 本地启动

创建数据库：

```sql
CREATE DATABASE ai_code_review DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

启动后端：

```powershell
.\scripts\run-backend.cmd
```

或手动启动：

```powershell
cd backend
mvn spring-boot:run
```

启动前端：

```powershell
.\scripts\run-frontend.cmd
```

或手动启动：

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

访问前端：

```text
http://localhost:5173
```

健康检查：

```powershell
curl http://localhost:8080/api/health
curl http://localhost:8080/actuator/health
```

## 数据库迁移

Flyway migration 位于 `backend/src/main/resources/db/migration`，当前包含：

```text
V1__init_mvp_schema.sql
V2__gitlab_mr_webhook_events.sql
V3__review_templates.sql
V4__db_fine_grained_rule_templates.sql
V5__mq_cache_fine_grained_rule_templates.sql
V6__focused_notification_change_types.sql
V7__gitlab_push_webhook_events.sql
V8__code_quality_review_profiles_and_results.sql
V9__code_quality_review_settings.sql
V10__code_quality_review_summary_text.sql
V11__code_quality_review_progress_events.sql
V12__ai_review_default_prompt_chinese_first.sql
V13__code_quality_api_key_settings.sql
V14__code_quality_global_review_provider.sql
V15__remove_api_compatibility_from_backend_templates.sql
V16__stronger_default_ai_review_prompt.sql
```

主要表：

- `projects`
- `review_tasks`
- `review_results`
- `rule_templates`
- `notification_records`
- `notification_webhooks`
- `gitlab_mr_webhook_events`
- `gitlab_push_webhook_events`
- `code_quality_review_profiles`
- `code_quality_review_results`
- `code_quality_review_progress_events`
- `code_quality_review_settings`

## 本地演示

### 发送 mock MR webhook

```powershell
$payload = Get-Content -Raw -Path .\examples\gitlab-mr-webhook.mock.json

$webhookResponse = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Merge Request Hook" } `
  -Body $payload

$webhookResponse | ConvertTo-Json -Depth 20
$taskId = $webhookResponse.data.taskId
```

### 发送 mock Push webhook

```powershell
$payload = Get-Content -Raw -Path .\examples\gitlab-push-webhook.mock.json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Push Hook" } `
  -Body $payload
```

### 查询结果

```powershell
curl http://localhost:8080/api/review-tasks
curl http://localhost:8080/api/review-tasks/$taskId
curl http://localhost:8080/api/review-tasks/$taskId/result
curl http://localhost:8080/api/review-tasks/$taskId/code-quality-result
curl http://localhost:8080/api/review-tasks/$taskId/code-quality-progress
```

重新触发已有 GitLab MR / Push 审查任务，会基于数据库中保存的 raw payload 和 changed files 摘要创建一个新任务：

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/review-tasks/$taskId/rerun"
```

前端任务详情页包含：

- 代码质量 Review
- 提醒卡片
- 分析结果
- 原始事件摘要

## 真实 GitLab diff 验证

复制本地配置示例：

```powershell
New-Item -ItemType Directory -Force .local
Copy-Item examples/gitlab.env.example .local/gitlab.env
```

编辑 `.local/gitlab.env`，填入：

- `GITLAB_BASE_URL`
- `GITLAB_TOKEN`
- `GITLAB_PROJECT_ID`
- `GITLAB_MR_IID`
- MySQL 连接信息

然后重启后端：

```powershell
.\scripts\run-backend.cmd
```

执行验证脚本：

```powershell
.\scripts\verify-gitlab-diff.cmd
```

MR diff 调用：

```text
GET {GITLAB_BASE_URL}/api/v4/projects/{projectId}/merge_requests/{mrIid}/diffs?page=1&per_page=100
PRIVATE-TOKEN: {GITLAB_TOKEN}
```

兼容 fallback：

```text
GET {GITLAB_BASE_URL}/api/v4/projects/{projectId}/merge_requests/{mrIid}/changes
PRIVATE-TOKEN: {GITLAB_TOKEN}
```

Push compare 调用：

```text
GET {GITLAB_BASE_URL}/api/v4/projects/{projectId}/repository/compare?from={beforeSha}&to={afterSha}
PRIVATE-TOKEN: {GITLAB_TOKEN}
```

## 审查模板

内置模板：

| 模板 | 适用场景 |
| --- | --- |
| `backend-default` | 后端服务 |
| `frontend-default` | 前端项目 |
| `general-default` | 通用项目 |

模板接口：

```powershell
curl http://localhost:8080/api/rule-templates
curl http://localhost:8080/api/rule-templates/backend-default
```

项目默认模板绑定：

```powershell
Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8080/api/projects/1/default-template" `
  -ContentType "application/json" `
  -Body '{"templateCode":"frontend-default"}'
```

钉钉推送会按模板 `focusChangeTypes` 过滤提醒来源。后端默认模板当前不再推送低信号 API 兼容性提醒。

## 手动规则审查

示例请求位于 `examples/manual-review-request.json` 和 `examples/manual-review-value-config-request.json`。

```powershell
$payload = Get-Content -Raw -Path .\examples\manual-review-request.json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/review-tasks/manual" `
  -ContentType "application/json" `
  -Body $payload
```

如果请求中的 `templateCode` 为空，会使用项目绑定的 `default_template_code`。

## 代码质量 AI Review

代码质量 Review 默认关闭。启用示例：

```powershell
$env:CODE_QUALITY_REVIEW_ENABLED="true"
$env:CODE_QUALITY_REVIEW_PROVIDER="CODEX_CLI"
$env:CODE_QUALITY_WORKSPACE_ROOT="D:\projects"
$env:CODEX_CLI_COMMAND="codex.cmd"
```

Provider 说明：

- `CODEX_CLI`：调用项目服务器本地 Codex CLI。Linux 默认命令为 `codex`，Windows 默认命令为 `codex.cmd`。
- `OPENAI_API`：调用 OpenAI Responses API。
- `ANTHROPIC_API`：调用 Anthropic Messages API。

前端“模板配置”页可以：

- 控制 GitLab MR 是否自动触发 AI Review。
- 切换执行方式：本地 CLI 或 API Key。
- 按供应商配置 OpenAI / Anthropic API Key。
- 查看、编辑、预览、恢复 AI Review Profile prompt。

手动触发代码质量 Review：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/code-quality-reviews/manual" `
  -ContentType "application/json" `
  -Body '{
    "projectId": 1,
    "profileCode": "backend-default-ai-review",
    "repositoryPath": "D:/projects/ai-code-review-platform",
    "mode": "BASE",
    "baseRef": "origin/main",
    "title": "Manual review"
  }'
```

AI Review 设置接口：

```powershell
curl http://localhost:8080/api/code-quality-reviews/settings

Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8080/api/code-quality-reviews/settings" `
  -ContentType "application/json" `
  -Body '{"mrAutoReviewEnabled": false}'
```

AI Review Profile 接口：

```powershell
curl http://localhost:8080/api/code-quality-review-profiles
curl http://localhost:8080/api/code-quality-review-profiles/backend-default-ai-review
curl http://localhost:8080/api/code-quality-review-profiles/backend-default-ai-review/rendered-prompt
```

重试某个任务：

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/code-quality-reviews/tasks/{taskId}/retry"
```

## 前端页面

启动前端后访问 `http://localhost:5173`。

顶部导航：

- `审查任务`：任务列表、任务详情、提醒卡片、分析结果、AI Review 结果与执行过程。
- `模板配置`：项目默认模板、AI Review 全局设置、API Key、Profile prompt。

任务详情页的“重新触发审阅”会从当前任务复制出一条新的审查任务，适合调试规则、钉钉模板和前端展示，不需要再次真实 push 或更新 MR。

详情页支持 `?taskId={taskId}` 直达，例如：

```text
http://localhost:5173/?taskId=47
```

## 自动化验证

后端：

```powershell
cd backend
mvn.cmd -q test
```

快速编译：

```powershell
cd backend
mvn.cmd -q -DskipTests compile
```

前端：

```powershell
cd frontend
npm.cmd run build
```
