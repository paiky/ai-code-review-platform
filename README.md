# AI 变更风险审查平台

本仓库当前处于 MVP 原型阶段。设计文档位于 `docs` 目录，后端工程位于 `backend` 目录，前端工程位于 `frontend` 目录。

当前已经具备可本地演示的主链路：

```text
mock GitLab MR webhook / GitLab Push webhook
  -> 创建项目与审查任务
  -> 保存原始 webhook payload
  -> 变更分析
  -> 风险规则引擎
  -> 生成提醒卡片
  -> 审查结果落库
  -> 钉钉推送或 SKIPPED 记录
  -> 前端查看任务与提醒卡片
```

说明：P0 演示链路可以继续使用 mock payload 中的 `changedFiles` / `diffText`。真实 GitLab MR webhook 通常不会携带完整 diff，当前已支持在 payload 缺少 changed files 时按 `projectId + mrIid` 调用 GitLab API 补拉 diff。Push webhook 会优先按 `projectId + beforeSha + afterSha` 调用 GitLab compare API 拉取完整 diff；compare 不可用时回退到 commits 的 `added` / `modified` / `removed` 文件列表，任务不中断。

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
- 同一个 GitLab webhook URL 支持 `Merge Request Hook` 和 `Push Hook` 分发处理。
- mock changed files / diffText 解析。
- API / DB / CACHE / MQ / CONFIG 启发式变更分析。
- 规则引擎与结构化风险卡片生成。
- 审查任务和审查结果落库。
- 钉钉通知器；未配置 webhook 时记录 `SKIPPED`。
- React + Ant Design 最小管理页面。
- 审查模板查看与项目默认模板绑定。
- 手动审查后端接口。
- payload 不带 `changedFiles` 时，可通过 GitLab API 拉取 MR diff。
- Push webhook 支持从 commit 文件列表生成 `GITLAB_PUSH_WEBHOOK` 审查任务。
- Push webhook 支持通过 GitLab compare API 拉取完整 diff，成功时 `changedFilesSummary.source = gitlab_compare_api`，失败时回退 `push_payload` 并记录 `fallbackReason`。
- GitLab 扫描模式下通过 project detail / MR detail 回填真实项目名、MR URL、分支、作者和 commit sha。
- DB 风险第一轮细分识别：`DB_SCHEMA`、`DB_SQL`、`ORM_MAPPING`、`ENTITY_MODEL`、`DATA_MIGRATION`，并保留 `DB` 聚合类型兼容旧模板；实体识别包含 JPA 注解和 MyBatis Plus `@TableField` / `@TableId` 字段映射变更。
- MQ / CACHE 风险第一轮细分识别：`MQ_PRODUCER`、`MQ_CONSUMER`、`MQ_MESSAGE_SCHEMA`、`MQ_TOPIC_CONFIG`、`MQ_RETRY_DLQ`、`CACHE_KEY`、`CACHE_TTL`、`CACHE_INVALIDATION`、`CACHE_READ_WRITE`、`CACHE_SERIALIZATION`，并保留 `MQ` / `CACHE` 聚合类型兼容旧模板。
- RiskCard schema 已对齐当前后端对象；展示层先按“提醒卡片”处理，前端会把 DB / MQ / Redis/缓存 / 配置相关命中分组，点开后查看规则命中原因、关联信号和证据。
- RiskCard 已新增粗粒度关注指标 `focusIndicators`，固定输出 DB 表/字段、MQ 配置、Redis 配置、`@Value` 配置四类指标，任务列表和风险卡片详情会优先展示该字段。
- 代码质量 AI Review 已有第一版闭环：支持本地 `CODEX_CLI`、`OPENAI_API` 和 `ANTHROPIC_API` 三种 provider，支持项目级 profile / prompt 配置，手动接口会创建任务并将结果落库，GitLab MR 风险审查成功后可按 profile 异步触发 AI Review，前端任务详情页可展示 `RUNNING` / `SUCCESS` / `FAILED` 状态和代码质量 Review 结果。
- AI Review 增加了运行期治理：平台提供 MR 自动 AI Review 全局开关，关闭后新的 MR 只做规则风险审查；后端启动时会把超时残留的 `RUNNING` AI Review 标记为失败；任务详情支持重试 AI Review，并展示 Codex CLI / OpenAI / Anthropic 调用过程事件。
- RiskCard schema 校验测试覆盖 DB / MQ / CACHE 细分字段，防止 schema 文档和后端输出脱节。
- 主链路集成测试覆盖 `mock payload` 和 `gitlab_api source`，并验证 `review_results` / `notification_records` 落库与查询。
- 本地 GitLab CE Docker 模拟环境，见 `local-gitlab/README.md`。
- 钉钉通知支持按模板 `focusChangeTypes` 过滤提醒来源；推送内容会按 DB / MQ / Redis/缓存 / 配置聚合同组命中，只输出简洁提醒和平台详情链接。

暂未完成：

- Jenkins 入口。
- 前端手动发起审查页面。
- 代码质量 Review GitLab MR comment 回写。
- GitLab token、钉钉 webhook、AI API Key 的生产级密钥托管与加密存储。目前 GitLab / 钉钉主要使用环境变量，AI API Key 已支持前端配置但仍建议接入 KMS/Secret Manager。
- 提醒卡片领域命名仍兼容 `RiskCard` / `riskItems` 历史字段，后续如要彻底改名为 reminder，需要分阶段迁移 JSON schema、API DTO、数据库字段和前端字段。
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
| `PLATFORM_BASE_URL` | `http://localhost:5173` | 平台前端访问地址，用于钉钉消息“查看平台详情”链接 |
| `DINGTALK_WEBHOOK_URL` | 空 | 钉钉机器人 webhook，空值时推送记录为 `SKIPPED` |
| `GITLAB_API_ENABLED` | `false` | payload 不带 `changedFiles` 时是否启用 GitLab API 补拉 diff |
| `GITLAB_BASE_URL` | 空 | GitLab base URL，例如 `https://gitlab.example.com` |
| `GITLAB_TOKEN` | 空 | GitLab access token，通过 `PRIVATE-TOKEN` header 使用 |
| `GITLAB_DIFF_PER_PAGE` | `100` | GitLab MR diff 分页大小 |
| `CODE_QUALITY_REVIEW_ENABLED` | `false` | 是否启用代码质量 Review 手动接口 |
| `CODE_QUALITY_REVIEW_PROVIDER` | `CODEX_CLI` | 代码质量 Review provider，可选 `CODEX_CLI` / `OPENAI_API` / `ANTHROPIC_API` |
| `CODE_QUALITY_WORKSPACE_ROOT` | 空 | Codex CLI 可审查仓库根目录限制，建议生产-like 环境配置 |
| `CODEX_CLI_COMMAND` | 按 OS 推断 | Windows 默认 `codex.cmd`，Linux 默认 `codex` |
| `CODEX_CLI_MODEL` | 空 | Codex CLI model override，空值时使用本机 Codex 配置 |
| `CODEX_CLI_TIMEOUT_SECONDS` | `600` | Codex CLI 审查超时时间 |
| `OPENAI_API_KEY` | 空 | OpenAI API provider 使用的 API key |
| `OPENAI_RESPONSES_URL` | `https://api.openai.com/v1/responses` | OpenAI Responses API 地址 |
| `OPENAI_CODE_REVIEW_MODEL` | `gpt-5.4` | OpenAI API provider 使用的模型 |
| `OPENAI_CODE_REVIEW_TIMEOUT_SECONDS` | `120` | OpenAI API provider 请求超时时间 |
| `ANTHROPIC_API_KEY` | 空 | Anthropic API provider 使用的 API key |
| `ANTHROPIC_MESSAGES_URL` | `https://api.anthropic.com/v1/messages` | Anthropic Messages API 地址 |
| `ANTHROPIC_CODE_REVIEW_MODEL` | `claude-sonnet-4-5` | Anthropic API provider 使用的模型 |
| `ANTHROPIC_CODE_REVIEW_TIMEOUT_SECONDS` | `120` | Anthropic API provider 请求超时时间 |

PowerShell 示例：

```powershell
$env:MYSQL_URL="jdbc:mysql://localhost:3306/ai_code_review?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&useSSL=false"
$env:MYSQL_USERNAME="root"
$env:MYSQL_PASSWORD="root"
$env:DINGTALK_WEBHOOK_URL=""
$env:GITLAB_API_ENABLED="false"
```

代码质量 Review 手动验证可选开启。本地 Codex CLI provider 示例：

```powershell
$env:CODE_QUALITY_REVIEW_ENABLED="true"
$env:CODE_QUALITY_REVIEW_PROVIDER="CODEX_CLI"
$env:CODE_QUALITY_WORKSPACE_ROOT="D:\projects"
$env:CODEX_CLI_COMMAND="codex.cmd"
```

OpenAI API provider 示例：

```powershell
$env:CODE_QUALITY_REVIEW_ENABLED="true"
$env:CODE_QUALITY_REVIEW_PROVIDER="OPENAI_API"
$env:OPENAI_API_KEY="sk-..."
```

Anthropic / Claude API provider 示例：

```powershell
$env:CODE_QUALITY_REVIEW_ENABLED="true"
$env:CODE_QUALITY_REVIEW_PROVIDER="ANTHROPIC_API"
$env:ANTHROPIC_API_KEY="sk-ant-..."
```

开启后，GitLab MR webhook 主链路仍会先完成变更风险审查；如果项目绑定的 AI Review profile 启用且 `triggerOnMr=true`，后端会异步触发 AI Code Review，并把结果挂到同一个 `review_tasks.id` 下。AI Review 启动时会先保存 `RUNNING` 结果，Codex / OpenAI / Anthropic 完成后更新为 `SUCCESS` 或 `FAILED`。`CODEX_CLI` 自动触发需要后端能定位本地仓库目录：可以将本地仓库放在 `CODE_QUALITY_WORKSPACE_ROOT` 下，并使用 `gitProjectId`、项目名或仓库名作为目录名；`OPENAI_API` / `ANTHROPIC_API` 自动触发会直接使用 MR diff 文本。

前端“模板配置”页可以在全局设置中切换 AI Review 执行方式：`CODEX_CLI` 表示使用项目所在服务器的本地 CLI agent；`OPENAI_API` / `ANTHROPIC_API` 表示使用平台配置的 API Key。OpenAI 与 Anthropic API Key 支持按供应商保存和清除，接口只返回是否已配置与脱敏后的 key，不返回明文。当前 MVP 会把 key 保存到 `code_quality_review_settings` 表；生产环境建议替换为 KMS/Secret Manager 或数据库字段加密。

Codex CLI provider 会把最终 prompt 写入 UTF-8 临时文件，再通过一段短英文命令让 Codex 读取该文件，避免 Windows 长中文命令行参数导致 prompt 丢失或变形。执行过程会记录 `profileCode`、`provider`、`model`、`repositoryPath`、`promptHash`、`promptLength`、`promptPreview`、`runtimeMode` 和脱敏后的 `commandPreview`，便于确认本轮 AI Review 实际使用了哪个 profile 和 prompt。

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
src/main/resources/db/migration/V5__mq_cache_fine_grained_rule_templates.sql
src/main/resources/db/migration/V6__focused_notification_change_types.sql
src/main/resources/db/migration/V7__gitlab_push_webhook_events.sql
src/main/resources/db/migration/V8__code_quality_review_profiles_and_results.sql
src/main/resources/db/migration/V9__code_quality_review_settings.sql
src/main/resources/db/migration/V10__code_quality_review_summary_text.sql
src/main/resources/db/migration/V11__code_quality_review_progress_events.sql
src/main/resources/db/migration/V12__ai_review_default_prompt_chinese_first.sql
src/main/resources/db/migration/V13__code_quality_api_key_settings.sql
src/main/resources/db/migration/V14__code_quality_global_review_provider.sql
src/main/resources/db/migration/V15__remove_api_compatibility_from_backend_templates.sql
```

当前 migration 会创建 MVP 所需基础表：

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

并初始化三套模板：

- `backend-default`
- `frontend-default`
- `general-default`

其中 `V4` 会将后端和通用模板升级到 DB 细分提醒规则，避免仅修改 Mapper XML 或实体字段时被直接误判为数据库结构变更。`V5` 会将后端模板升级到 MQ / CACHE 细分提醒规则。`V6` 会收窄默认钉钉关注标签。`V7` 会新增 Push Hook 原始事件表。`V8` ~ `V14` 会创建代码质量 AI Review profile、结果、过程事件和全局设置；`V15` 会从后端默认模板中移除低信号 API 兼容性提醒。

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
  -> 提醒卡片生成
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

示例数据位于 `examples/gitlab-mr-webhook.mock.json`，统一说明见 `examples/README.md`。

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
- `riskItemCount` 为 `5`，前端展示为提醒项数量。
- `changeAnalysis.changeTypes` 包含聚合类型 `API`、`DB`、`CACHE`、`MQ`、`CONFIG`，并包含对应细分类型，例如 `DB_SQL`、`CACHE_INVALIDATION`、`MQ_PRODUCER`。
- `riskCard` 仍为兼容字段名，展示层会按提醒卡片处理，包含规则命中、受影响资源、推荐检查项和建议 review 角色。

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

- 任务列表页展示 `demo-service`、类型、分支、状态、重点变更和提醒项数量。
- 任务详情页展示代码质量 Review、提醒卡片、分析结果和原始事件摘要。
- 提醒卡片按 DB / MQ / Redis/缓存 / 配置分组展示命中提醒，点开后可查看命中原因、关联信号和证据。

### 6. 自动化验证

后端测试：

```powershell
cd backend
mvn -q test
```

后端测试包含主链路集成测试，会用内存数据库覆盖 `mock payload`、MR `gitlab_api source`、Push `gitlab_compare_api` 与 Push fallback 路径，并断言 `review_tasks`、`review_results`、`notification_records` 可查询。

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
根据 X-Gitlab-Event 分发 Merge Request Hook / Push Hook
  -> 校验 object_kind
  -> 解析项目、MR、分支、作者、changedFiles 摘要、eventTime
  -> 自动 upsert projects
  -> 创建 review_tasks
  -> 保存 gitlab_mr_webhook_events.raw_payload 或 gitlab_push_webhook_events.raw_payload
  -> 变更分析
  -> 提醒卡片生成
  -> review_results 落库
  -> 钉钉推送或 SKIPPED 记录
```

说明：真实 GitLab MR webhook 通常不直接包含完整 changed files。为了本地验证，mock payload 支持传入顶层 `changedFiles` 数组；真实接入时可启用 GitLab API，由后端按 MR iid 拉取真实 diff / changed files。Push Hook 可使用相同 URL；启用 GitLab API 后会优先拉取 compare diff，用于识别代码内容中的 API / DB / CACHE / MQ / CONFIG 风险。

### Push webhook 验证

示例数据位于 `examples/gitlab-push-webhook.mock.json`：

```powershell
$payload = Get-Content -Raw -Path .\examples\gitlab-push-webhook.mock.json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Push Hook" } `
  -Body $payload
```

预期会创建 `triggerType = GITLAB_PUSH_WEBHOOK` 的审查任务。启用并正确配置 GitLab API 时，`changedFilesSummary.source = gitlab_compare_api`；未启用、接口失败或 compare 返回空 diff 时，任务仍会成功回退到 `changedFilesSummary.source = push_payload`，并在摘要中记录 `fallbackReason`。

## 真实 GitLab diff 接入

当 MR webhook payload 不包含 `changedFiles`、`changed_files`、`object_attributes.changed_files` 或 `changes.changed_files.current` 时，后端会尝试通过 GitLab API 拉取 MR diff。Push webhook 会在收到事件后优先通过 GitLab compare API 拉取 `beforeSha -> afterSha` 的完整 diff。

如果当前电脑没有可用的公司 GitLab，可以先启动本地 GitLab CE：

```powershell
.\scripts\run-local-gitlab.cmd
```

访问：

```text
http://localhost:8929
```

本地 GitLab 的完整使用说明见：

```text
local-gitlab/README.md
```

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

Push compare 调用接口：

```text
GET {GITLAB_BASE_URL}/api/v4/projects/{projectId}/repository/compare?from={beforeSha}&to={afterSha}
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
- Push Hook 启用 GitLab API 时，优先使用 compare API，`changedFilesSummary.source = gitlab_compare_api`。
- Push Hook compare 失败或返回空 diff 时，回退到 push payload 文件列表，`changedFilesSummary.source = push_payload`，任务继续生成风险卡片。

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

`GET /api/review-tasks/{taskId}/result` 返回的 `riskCard.focusIndicators` 会固定包含：

| code | 展示含义 | 当前来源信号 |
| --- | --- | --- |
| `DB_SCHEMA_CHANGE` | DB 表/字段变更 | `DB_SCHEMA`、`DATA_MIGRATION`、`ENTITY_MODEL`、`ORM_MAPPING` |
| `MQ_CONFIG_CHANGE` | MQ 配置变更 | `MQ_TOPIC_CONFIG` |
| `REDIS_CONFIG_CHANGE` | Redis 配置变更 | `CACHE_KEY`、`CACHE_TTL`、`CACHE_INVALIDATION`、`CACHE_READ_WRITE`、`CACHE_SERIALIZATION` |
| `VALUE_CONFIG_CHANGE` | `@Value` 配置变更 | Java / Kotlin diff 中出现 `@Value("${xxx}")` 或 `@Value("${xxx:default}")` |

## 审查模板能力

系统内置三套 MVP 模板：

| 模板 | 适用场景 | 默认启用规则 |
| --- | --- | --- |
| `backend-default` | 后端服务 | API、DB、CACHE、MQ、CONFIG |
| `frontend-default` | 前端项目 | API、CONFIG |
| `general-default` | 通用项目 | API、DB、CONFIG |

模板配置存储在 `rule_templates` 表中，`enabled_rule_codes` 决定启用哪些风险规则，`config_json.recommendedChecks` 定义模板级推荐检查项。项目表 `projects.default_template_code` 绑定项目默认模板。

`config_json.focusChangeTypes` 用于控制钉钉关注标签。RiskCard 会完整落库，但钉钉只推送 `category` 精确命中关注标签的提醒来源，并按 DB / MQ / Redis/缓存 / 配置聚合展示。`backend-default` 当前默认关注：

```text
DB_SCHEMA
DATA_MIGRATION
ENTITY_MODEL
```

如果本次审查没有命中关注标签，通知记录会保存为 `SKIPPED`，错误信息为 `No focused reminder matched`。

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

示例数据位于 `examples/manual-review-request.json`，统一说明见 `examples/README.md`。

```powershell
$payload = Get-Content -Raw -Path .\examples\manual-review-request.json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/review-tasks/manual" `
  -ContentType "application/json" `
  -Body $payload
```

如果 `templateCode` 为空，系统会使用项目绑定的 `default_template_code`。

### 手动发起代码质量 Review

代码质量 Review provider 设计与配置见 `docs/12-code-quality-review-provider-plan.md`。该能力默认关闭，需先设置 `CODE_QUALITY_REVIEW_ENABLED=true`。

Codex CLI provider 示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/code-quality-reviews/manual" `
  -ContentType "application/json" `
  -Body '{
    "projectId":1,
    "profileCode":"backend-default-ai-review",
    "repositoryPath":"D:/projects/ai-code-review-platform",
    "mode":"BASE",
    "baseRef":"origin/main",
    "title":"Manual Codex review",
    "instructions":"Only report actionable correctness, data consistency, or security issues."
  }'
```

OpenAI API provider 示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/code-quality-reviews/manual" `
  -ContentType "application/json" `
  -Body '{
    "projectId":1,
    "profileCode":"backend-default-ai-review",
    "mode":"DIFF_TEXT",
    "title":"Diff-only review",
    "diffText":"+ public void createOrder() { }",
    "changedFiles":["src/main/java/com/demo/OrderService.java"]
  }'
```

接口会创建一条 `triggerType = CODE_QUALITY_MANUAL` 的审查任务，并把结果保存到 `code_quality_review_results`。查询结果：

```powershell
curl http://localhost:8080/api/review-tasks/{taskId}/code-quality-result
```

`CODEX_CLI` provider 会保留 Codex 原始 Markdown 输出，同时会把 `- High:` / `- Medium:` 等 findings 解析为结构化 `findings`，供前端折叠面板展示。历史记录如果只有 `rawOutput` 且 `findings_json` 为空，查询时也会做同样的兜底解析。

查询执行过程：

```powershell
curl http://localhost:8080/api/review-tasks/{taskId}/code-quality-progress
```

过程事件会记录 `QUEUED`、`REQUEST_BUILT`、`PROMPT_METADATA`、`CODEX_COMMAND`、`CODEX_PROCESS_STARTED`、`CODEX_OUTPUT`、`CODEX_PROCESS_EXIT`、`CODEX_PARSED`、`SAVE_RESULT` 等阶段。前端任务详情页会在“代码质量 Review”页签展示“执行过程”，`RUNNING` 时自动轮询刷新。

AI Review 运维接口：

```powershell
# 查看全局开关
curl http://localhost:8080/api/code-quality-reviews/settings

# 控制 GitLab MR 是否自动触发 AI Review
Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8080/api/code-quality-reviews/settings" `
  -ContentType "application/json" `
  -Body '{"mrAutoReviewEnabled":false}'

# 重试某个任务的 AI Review
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/code-quality-reviews/tasks/{taskId}/retry"
```

AI Review Profile / Prompt 接口：

```powershell
# 查看 profile
curl http://localhost:8080/api/code-quality-review-profiles
curl http://localhost:8080/api/code-quality-review-profiles/backend-default-ai-review

# 预览最终拼装后的 Codex / OpenAI prompt
curl http://localhost:8080/api/code-quality-review-profiles/backend-default-ai-review/rendered-prompt

# 更新 prompt
Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8080/api/code-quality-review-profiles/backend-default-ai-review" `
  -ContentType "application/json" `
  -Body '{"codexPrompt":"只报告会影响线上正确性、数据一致性或安全的问题。","openAiInstructions":"Review only the supplied diff and return strict JSON."}'

# 恢复内置默认 prompt
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/code-quality-review-profiles/backend-default-ai-review/reset-default-prompt"
```

### 前端配置页面

启动前端后访问：

```text
http://localhost:5173
```

点击顶部“模板配置”：

- 查看 `backend-default` / `frontend-default` / `general-default`。
- 查看每个模板启用的规则和推荐检查项。
- 修改项目默认模板绑定。
- 查看并编辑 AI Review Profile 的 Codex prompt / OpenAI instructions。
- 预览最终拼装后的 AI Review prompt，并可一键恢复内置默认 prompt。

## 下一步建议

推荐按以下顺序继续推进：

1. 做代码质量 Review 的 GitLab MR comment 回写，把 AI Review 高价值问题回写到 MR 讨论区。
2. 做生产级密钥治理：GitLab token、钉钉 webhook、AI API Key 接入 KMS/Secret Manager 或数据库字段加密，并补充权限控制。
3. 将提醒卡片领域命名从 `RiskCard` / `riskItems` 分阶段迁移到 reminder 语义，保持历史数据兼容。
4. 补前端手动发起审查页面，减少依赖 curl / PowerShell 示例。
5. 接入 Jenkins 入口和 knowledge-base / 人工反馈闭环。

