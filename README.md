# AI 变更提醒与代码质量审查平台

本仓库是一个可接入 GitLab / 钉钉 / 多模型 API 模式 AI Review 的研发质量平台原型。当前主流程围绕代码变更生成结构化“提醒卡片”，再按需触发代码质量 AI Review。

代码目录：

- `backend/`：Spring Boot 后端。
- `frontend/`：React + Ant Design 前端。
- `docs/`：设计、API、schema 与实施计划文档。
- `examples/`：Webhook 与手动审查示例请求。
- `scripts/`：本地启动、GitLab 验证脚本。

常用文档：

- `docs/18-project-integration-user-guide.md`：项目接入使用手册，按 GitLab 接入、项目设置、钉钉推送链路组织。

## Agent / 新对话入口

新对话或自动化 Agent 理解项目时，优先阅读：

1. `AGENTS.md`：项目目标、工作方式、脚本使用约束。
2. `README.md`：本地启动、配置、验证步骤。
3. `docs/10-local-dev-pitfalls.md`：本地环境与调试避坑。
4. 与当前任务相关的 `docs/` 设计文档，例如 API、规则、AI Review provider 计划等。

启动、编译、测试、构建应优先使用 `scripts/` 目录下脚本，不要绕过脚本直接按个人习惯执行底层 `mvn` / `npm` 命令。脚本负责统一 JDK 21 选择、本地 env 加载、依赖安装和 Windows 命令兼容。

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
- 代码质量 AI Review 支持 OpenAI、Anthropic、DeepSeek 和 OpenAI-compatible 自定义模型 Provider。
- AI Review 支持 profile / prompt 配置、模型端点 URL / 模型名称 / API Key 配置、MR 自动触发开关、重试、执行过程展示。
- GitLab MR 自动 AI Review 完成后会向同一个钉钉 webhook 推送“代码质量 Review”结果。
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
| `PLATFORM_BASE_URL` | `http://localhost:5173` | 钉钉“查看平台详情”链接前缀 |
| `DINGTALK_WEBHOOK_URL` | 空 | 钉钉机器人 webhook，空值时通知记录为 `SKIPPED` |
| `DINGTALK_ENABLED` | `true` | 是否启用钉钉发送 |
| `GITLAB_API_ENABLED` | `false` | 是否启用 GitLab API 补拉 diff |
| `GITLAB_BASE_URL` | 空 | GitLab base URL |
| `GITLAB_TOKEN` | 空 | GitLab access token |
| `GITLAB_DIFF_PER_PAGE` | `100` | MR diff 分页大小 |
| `CODE_QUALITY_REVIEW_ENABLED` | `false` | 是否启用代码质量 Review 能力 |
| `CODE_QUALITY_REVIEW_PROVIDER` | `DEEPSEEK` | 默认模型 Provider，可被数据库配置覆盖 |
| `OPENAI_API_KEY` | 空 | OpenAI API key，首次初始化 Provider 时可作为默认值 |
| `OPENAI_RESPONSES_URL` | `https://api.openai.com/v1/responses` | OpenAI Responses API 地址 |
| `OPENAI_CODE_REVIEW_MODEL` | `gpt-5.4` | OpenAI provider 模型 |
| `OPENAI_CODE_REVIEW_TIMEOUT_SECONDS` | `120` | OpenAI 请求超时时间 |
| `ANTHROPIC_API_KEY` | 空 | Anthropic API key |
| `ANTHROPIC_MESSAGES_URL` | `https://api.anthropic.com/v1/messages` | Anthropic Messages API 地址 |
| `ANTHROPIC_CODE_REVIEW_MODEL` | `claude-sonnet-4-5` | Anthropic provider 模型 |
| `ANTHROPIC_CODE_REVIEW_TIMEOUT_SECONDS` | `120` | Anthropic 请求超时时间 |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek API key，首次初始化 Provider 时可作为默认值 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek OpenAI-compatible base URL |
| `DEEPSEEK_CODE_REVIEW_MODEL` | `deepseek-v4-pro` | DeepSeek provider 模型 |

PowerShell 示例：

```powershell
$env:MYSQL_URL="jdbc:mysql://localhost:3306/ai_code_review?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&useSSL=false"
$env:MYSQL_USERNAME="root"
$env:MYSQL_PASSWORD="root"
$env:DINGTALK_WEBHOOK_URL=""
$env:GITLAB_API_ENABLED="false"
```

## Docker 部署

仓库内置 `deploy/docker-compose.yml`，适合单台远程服务器快速部署：

```text
宿主机 :${PUBLIC_HTTP_PORT}，默认 8080
  -> Nginx frontend 容器 :80
  -> React 静态页面
  -> /api 反向代理到 backend:${BACKEND_PORT}
Spring Boot backend 容器，默认 8080，仅在 Docker 网络内访问
MySQL 8.4 容器 + mysql-data 持久化卷
```

服务器需要先安装 Docker Engine 和 Docker Compose plugin。首次部署：

```bash
git clone <repo-url> ai-code-review-platform
cd ai-code-review-platform/deploy
cp .env.example .env
```

编辑 `deploy/.env`，至少修改：

```text
PUBLIC_HTTP_PORT=8080
PLATFORM_BASE_URL=http://你的域名或服务器IP:8080
BACKEND_PORT=8080
MYSQL_ROOT_PASSWORD=强密码
MYSQL_USERNAME=ai_review
MYSQL_PASSWORD=强密码
DINGTALK_WEBHOOK_URL=钉钉机器人 webhook，可为空
GITLAB_API_ENABLED=true
GITLAB_BASE_URL=https://你的 GitLab 地址
GITLAB_TOKEN=GitLab access token
```

启动：

```bash
docker compose up -d --build
```

查看状态和日志：

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
```

验证：

```bash
curl http://127.0.0.1/actuator/health
curl http://127.0.0.1/api/health
```

平台访问和 GitLab webhook 使用同一个对外端口：`PUBLIC_HTTP_PORT`。默认访问 `http://服务器IP:8080`，GitLab webhook 配 `http://服务器IP:8080/api/webhooks/gitlab/merge-request`。如果服务器的 `8080` 已被占用，可以改 `PUBLIC_HTTP_PORT`，例如 `PUBLIC_HTTP_PORT=18080` 后访问 `http://服务器IP:18080`。`BACKEND_PORT` 默认只在 Docker 内部使用，不会额外占用宿主机端口；如需避开容器内的 `8080` 约定，也可以改成 `BACKEND_PORT=18081`，Nginx 反向代理会自动跟随。

升级：

```bash
git pull
cd deploy
docker compose up -d --build
```

GitLab webhook 地址配置为：

```text
http://你的域名或服务器IP:8080/api/webhooks/gitlab/merge-request
```

如果需要 HTTPS，建议在服务器最外层再放一个宿主机 Nginx / Caddy / 云厂商负载均衡做 TLS 终止，再转发到 `PUBLIC_HTTP_PORT`。

### 本地打包后上传服务器

如果服务器不拉源代码，可以在本地先构建并导出 Docker 镜像。要求本地已安装 Docker Desktop：

```powershell
.\scripts\package-docker-deploy.cmd
```

脚本会生成：

```text
.local/docker-deploy/{版本号}/
  ai-code-review-backend-{版本号}.tar
  ai-code-review-frontend-{版本号}.tar
  docker-compose.yml
  .env.example
  load-images.sh
```

如果服务器无法访问 Docker Hub，还需要把 MySQL 镜像一起打包：

```powershell
.\scripts\package-docker-deploy.cmd -IncludeMysqlImage
```

将 `.local/docker-deploy/{版本号}/` 整个目录上传到服务器，例如：

```bash
scp -r .local/docker-deploy/{版本号} user@server:/opt/ai-code-review-platform
```

服务器执行：

```bash
cd /opt/ai-code-review-platform
chmod +x load-images.sh
./load-images.sh
cp .env.example .env
vi .env
docker compose up -d
```

升级时重新在本地执行 `package-docker-deploy.cmd`，上传新的版本目录到服务器，执行 `./load-images.sh` 后再 `docker compose up -d`。数据库数据保存在 Docker volume `mysql-data` 中，升级应用镜像不会删除数据；不要执行 `docker compose down -v`。

## 本地启动

创建数据库：

```sql
CREATE DATABASE ai_code_review DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

启动后端：

```powershell
.\scripts\run-backend.cmd
```

后端脚本默认执行 `spring-boot:run`，也可以透传 Maven 参数，例如 `.\scripts\run-backend.cmd -q test` 或 `.\scripts\run-backend.cmd -q -DskipTests compile`。

启动前端：

```powershell
.\scripts\run-frontend.cmd
```

前端脚本默认执行 `npm run dev`，首次运行会自动 `npm install`。构建时使用 `.\scripts\run-frontend.cmd build`。

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
V17__dingtalk_notification_global_switch.sql
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
```

Provider 说明：

- `OPENAI`：调用 OpenAI Responses API。
- `ANTHROPIC`：调用 Anthropic Messages API。
- `DEEPSEEK`：调用 DeepSeek OpenAI-compatible Chat Completions API，默认 base URL 为 `https://api.deepseek.com`。
- `CUSTOM`：调用自定义 OpenAI-compatible Chat Completions API，需要配置端点 URL、模型名称和 API Key。

前端“模板配置”页可以：

- 控制 GitLab MR 是否自动触发 AI Review。
- 控制是否全局发送钉钉推送；关闭后审查和落库仍正常执行。
- 配置 OpenAI / Anthropic / DeepSeek / 自定义 Provider 的模型端点 URL、模型名称和 API Key。
- 设置全局默认 Provider，以及项目级默认 Provider。
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
    "mode": "DIFF_TEXT",
    "baseRef": "origin/main",
    "title": "Manual review",
    "diffText": "diff --git a/src/main/java/com/demo/OrderService.java b/src/main/java/com/demo/OrderService.java\n+ public void createOrder() {}",
    "changedFiles": ["src/main/java/com/demo/OrderService.java"]
  }'
```

AI Review 设置接口：

```powershell
curl http://localhost:8080/api/code-quality-reviews/settings
curl http://localhost:8080/api/code-quality-review-providers

Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8080/api/code-quality-reviews/settings" `
  -ContentType "application/json" `
  -Body '{"mrAutoReviewEnabled": false, "dingtalkNotificationEnabled": false}'
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
.\scripts\run-backend.cmd -q test
```

快速编译：

```powershell
.\scripts\run-backend.cmd -q -DskipTests compile
```

前端：

```powershell
.\scripts\run-frontend.cmd build
```
