# Python 后端执行版重构计划

> **状态：已完成。** Python FastAPI 后端已是默认主后端（`backend-python/`），Java `backend/` 仅作历史参考。本文保留分阶段 prompt 写法与迁移记录；当前启动、验证与能力范围以 `README.md`、`AGENTS.md` 为准。不要再按本文从头实施迁移。

## 1. 执行结论

当前项目已经形成完整后端主链路：

```text
GitLab MR / Push webhook / 手动审查
  -> 创建 review task
  -> 拉取或解析 changed files / diff
  -> 变更分析
  -> 规则引擎生成提醒卡片
  -> 结果落库
  -> 钉钉推送或 SKIPPED 记录
  -> React 前端查看任务详情
  -> 可选触发代码质量 AI Review
```

重构目标不是“顺手换语言”，而是在保持产品能力和接口兼容的前提下，把 Java Spring Boot 后端替换为 Python 后端。

执行结论：

1. 继续保持前后端分离。
2. 前端 React + Ant Design 暂不重写。
3. Python 后端使用 FastAPI + Pydantic + SQLAlchemy + Alembic + pytest。
4. 数据库表结构第一阶段不重做，继续读写现有 MySQL 表。
5. 对外 URL 尽量不变，尤其是 GitLab webhook 地址。
6. 按“契约冻结 -> Python 骨架 -> 只读 API -> 主链路 -> AI Review 迁移 -> AI Review 稳定化 -> 部署切换 -> 双后端目录治理”迁移。
7. Java 后端长期保留在 `backend/`，作为 legacy/reference backend；Python 后端位于 `backend-python/`，验证完成后成为 primary backend。

## 2. 保持前后端分离

建议继续前后端分离。

原因：

- 当前前端已经围绕 `/api` 契约实现了任务列表、任务详情、提醒卡片、模板配置、AI Review 结果展示，后端重构不需要同时重写 UI。
- GitLab webhook、钉钉推送、模型 Provider、数据库迁移、规则引擎都属于后端职责，前端只消费结构化结果。
- Python 后端可以独立测试、独立部署、独立回滚。
- 部署时仍然可以由 Nginx 对外暴露一个端口，用户和 GitLab 感知不到内部语言变化。

目标部署形态：

```text
浏览器 / GitLab / 钉钉
  -> Nginx frontend 容器或宿主机反代
  -> /             React 静态页面
  -> /api/**       Python backend
  -> /actuator/**  健康检查兼容入口，后续可迁移到 /api/health
```

前端改动原则：

- Python 后端优先兼容 `docs/03-api-contract.md` 和当前 Java Controller 的真实行为。
- `riskCard`、`riskItems`、`riskLevel`、`changeAnalysis` 等历史字段继续保留。
- API 字段、分页结构、错误码不主动改名。
- 只有当接口契约确实需要升级时，才同步修改前端、README 和 API 文档。

## 3. Python 技术栈与工程约定

| 能力 | 选型 | 对应当前 Java 能力 |
| --- | --- | --- |
| Web 框架 | FastAPI | Spring MVC Controller |
| DTO / schema | Pydantic v2 | Java DTO / VO / validation |
| 数据访问 | SQLAlchemy 2.x | Spring JDBC Repository |
| 数据库迁移 | Alembic | Flyway |
| MySQL 驱动 | PyMySQL，后续可评估 mysqlclient | mysql-connector-j |
| HTTP 客户端 | httpx | GitLab / DingTalk / AI Provider HTTP 调用 |
| 后台任务 | 先用应用内 executor | 当前 `CodeQualityAsyncReviewExecutor` |
| 测试 | pytest + pytest-asyncio + respx | JUnit / Spring Boot Test |
| 代码质量 | ruff，mypy 渐进引入 | 编译和测试约束 |
| 本地运行 | uvicorn | spring-boot:run |
| 生产运行 | gunicorn + uvicorn worker | java -jar |

建议 Python 版本：3.12。

第一阶段不要引入 Celery、Redis 队列、复杂依赖注入框架。先让业务边界和测试闭环站稳。

## 4. 目标目录结构

```text
backend-python/
  pyproject.toml
  alembic.ini
  app/
    main.py
    core/
      config.py
      database.py
      response.py
      errors.py
      tracing.py
      logging.py
    project_integration/
      api.py
      service.py
      schemas.py
      models.py
      repository.py
      gitlab_client.py
    review_record/
      api.py
      service.py
      schemas.py
      models.py
      repository.py
    change_analysis/
      service.py
      schemas.py
      rules/
        api_rule.py
        db_rule.py
        cache_rule.py
        mq_rule.py
        config_rule.py
    rule_template/
      api.py
      service.py
      schemas.py
      models.py
      repository.py
    risk_engine/
      service.py
      schemas.py
      rule_repository.py
    notification/
      api.py
      service.py
      schemas.py
      models.py
      repository.py
      dingtalk.py
    code_quality/
      api.py
      service.py
      schemas.py
      models.py
      repository.py
      progress.py
      providers/
        base.py
        openai_provider.py
        anthropic_provider.py
        openai_compatible_provider.py
    knowledge_base/
      __init__.py
  migrations/
    versions/
    bootstrap_sql/
  tests/
    contract/
    integration/
    unit/
```

命名约定：

- Python 包和文件使用 snake_case。
- 对外 JSON 字段继续使用 camelCase，由 Pydantic alias 处理。
- 数据库字段继续使用 snake_case。
- 枚举值保持现有大写字符串，例如 `GITLAB_MR_WEBHOOK`、`DB_SCHEMA`、`HIGH`。
- 所有响应统一通过 `ApiResponse` 包装。

## 5. Java 到 Python 模块映射

| Java 模块 / 类 | Python 目标模块 | 迁移阶段 | 备注 |
| --- | --- | --- | --- |
| `common.response.ApiResponse` | `app.core.response` | 阶段 1 | 统一响应结构必须先实现 |
| `common.response.PageResponse` | `app.core.response` | 阶段 2 | 分页字段保持 `items/pageNo/pageSize/total` |
| `common.exception.*` | `app.core.errors` | 阶段 1 | 错误码和 HTTP status 尽量兼容 |
| `common.web.TraceId*` | `app.core.tracing` | 阶段 1 | 请求级 traceId |
| `health.HealthController` | `app.main` 或 `app.core.health` | 阶段 1 | `/api/health`，临时兼容 `/actuator/health` |
| `projectintegration.controller.*` | `app.project_integration.api` | 阶段 3 | GitLab webhook 和项目配置 |
| `projectintegration.application.*` | `app.project_integration.service` | 阶段 3 | MR / Push 主流程 |
| `projectintegration.infrastructure.GitLabClient` | `app.project_integration.gitlab_client` | 阶段 3 | httpx + 超时 + fallback |
| `reviewrecord.controller.*` | `app.review_record.api` | 阶段 2/3 | 查询先迁，创建后迁 |
| `reviewrecord.application.*` | `app.review_record.service` | 阶段 2/3 | 任务生命周期 |
| `reviewrecord.infrastructure.*` | `app.review_record.repository` | 阶段 2 | SQLAlchemy 查询 |
| `changeanalysis.*` | `app.change_analysis` | 阶段 3 | 规则行为必须有 golden sample |
| `riskengine.*` | `app.risk_engine` | 阶段 3 | RiskCard schema 必须兼容 |
| `ruletemplate.*` | `app.rule_template` | 阶段 2/3 | 只读先迁，规则加载后迁 |
| `notification.*` | `app.notification` | 阶段 3 | 钉钉失败不阻断主任务 |
| `codequality.controller.*` | `app.code_quality.api` | 阶段 4 | 手动、settings、provider、profile |
| `codequality.application.*` | `app.code_quality.service` | 阶段 4 | 自动触发、retry、startup recovery |
| `codequality.infrastructure.*Provider` | `app.code_quality.providers` | 阶段 4 | OpenAI / Anthropic / DeepSeek / Custom |
| `knowledgebase.package-info` | `app.knowledge_base` | 阶段 6 | Java legacy/reference 保留时继续占位 |

## 6. API 兼容矩阵

Python 后端必须按下表逐个接口复刻。每个接口迁移时都要补一个 contract 测试。

| 接口 | 当前 Java 来源 | 阶段 | Python 模块 | 验收重点 |
| --- | --- | --- | --- | --- |
| `GET /api/health` | `HealthController` | 1 | `core.health` | `data.status=UP`、有 `traceId` |
| `GET /actuator/health` | Spring Actuator | 1 | `core.health` | Docker/Nginx 兼容，可返回简化 UP |
| `POST /api/webhooks/gitlab/merge-request` | `GitLabWebhookController` | 3 | `project_integration.api` | 同 URL 分发 MR Hook / Push Hook |
| `POST /api/review-tasks/manual` | `ReviewTaskController` | 3 | `review_record.api` | 手动 changedFiles / diffText 审查 |
| `POST /api/review-tasks/{taskId}/rerun` | `ReviewTaskController` | 3 | `review_record.api` | 基于 raw payload replay |
| `GET /api/review-tasks` | `ReviewTaskController` | 2 | `review_record.api` | 查询参数、分页、keyword 兼容 |
| `GET /api/review-tasks/{taskId}` | `ReviewTaskController` | 2 | `review_record.api` | 任务详情字段兼容 |
| `GET /api/review-tasks/{taskId}/result` | `ReviewTaskController` | 2 | `review_record.api` | `changeAnalysis`、`riskCard` 字段兼容 |
| `GET /api/review-tasks/{taskId}/code-quality-result` | `ReviewTaskController` | 4 | `review_record.api` | RUNNING/SUCCESS/FAILED 兼容 |
| `GET /api/review-tasks/{taskId}/code-quality-progress` | `ReviewTaskController` | 4 | `review_record.api` | 进度事件列表顺序和脱敏 |
| `GET /api/review-tasks/{taskId}/notifications` | `ReviewTaskController` | 2 | `review_record.api` | 通知记录列表 |
| `GET /api/projects` | `ProjectController` | 2 | `project_integration.api` | 当前只返回 ENABLED 项目分页 |
| `PUT /api/projects/{projectId}/default-template` | `ProjectController` | 3 | `project_integration.api` | 请求 `{templateCode}` |
| `PUT /api/projects/{projectId}/code-quality-profile` | `ProjectController` | 4 | `project_integration.api` | 请求 `{profileCode}` |
| `PUT /api/projects/{projectId}/code-quality-provider` | `ProjectController` | 4 | `project_integration.api` | 请求 `{providerCode}` |
| `GET /api/rule-templates` | `RuleTemplateController` | 2 | `rule_template.api` | 分页包装 |
| `GET /api/rule-templates/{templateCode}` | `RuleTemplateController` | 2 | `rule_template.api` | `config.focusChangeTypes` 兼容 |
| `POST /api/code-quality-reviews/manual` | `CodeQualityReviewController` | 4 | `code_quality.api` | 受 enabled 开关控制 |
| `GET /api/code-quality-reviews/settings` | `CodeQualityReviewController` | 4 | `code_quality.api` | 全局设置 |
| `PUT /api/code-quality-reviews/settings` | `CodeQualityReviewController` | 4 | `code_quality.api` | 请求字段允许部分更新 |
| `POST /api/code-quality-reviews/tasks/{taskId}/retry` | `CodeQualityReviewController` | 4 | `code_quality.api` | 清旧 progress，重新运行 |
| `GET /api/code-quality-review-profiles` | `CodeQualityReviewProfileController` | 4 | `code_quality.api` | 分页包装 |
| `GET /api/code-quality-review-profiles/{profileCode}` | `CodeQualityReviewProfileController` | 4 | `code_quality.api` | profile 详情 |
| `PUT /api/code-quality-review-profiles/{profileCode}` | `CodeQualityReviewProfileController` | 4 | `code_quality.api` | profile 配置更新 |
| `GET /api/code-quality-review-profiles/{profileCode}/rendered-prompt` | `CodeQualityReviewProfileController` | 4 | `code_quality.api` | promptHash/promptLength |
| `POST /api/code-quality-review-profiles/{profileCode}/reset-default-prompt` | `CodeQualityReviewProfileController` | 4 | `code_quality.api` | 恢复内置 prompt |
| `GET /api/code-quality-review-providers` | `CodeQualityModelProviderController` | 4 | `code_quality.api` | API key 只返回 masked |
| `PUT /api/code-quality-review-providers/{providerCode}` | `CodeQualityModelProviderController` | 4 | `code_quality.api` | 支持 `clearApiKey` |
| `POST /api/code-quality-review-providers/{providerCode}/set-default` | `CodeQualityModelProviderController` | 4 | `code_quality.api` | 更新全局默认 provider |

## 7. 请求体兼容清单

### 7.1 手动规则审查

`POST /api/review-tasks/manual`

```json
{
  "projectId": 1,
  "templateCode": "backend-default",
  "sourceBranch": "feature/demo",
  "targetBranch": "main",
  "authorName": "Alice",
  "authorUsername": "alice",
  "changedFiles": [],
  "diffText": "diff --git ..."
}
```

兼容要求：

- `projectId` 必填。
- `changedFiles` 为空时按空列表处理。
- `templateCode` 为空时使用项目默认模板。
- `diffText` 可以作为全局 diff 输入。

### 7.2 项目配置

```json
{ "templateCode": "backend-default" }
```

```json
{ "profileCode": "backend-default-ai-review" }
```

```json
{ "providerCode": "DEEPSEEK" }
```

### 7.3 AI Review 手动触发

`POST /api/code-quality-reviews/manual`

```json
{
  "projectId": 1,
  "profileCode": "backend-default-ai-review",
  "repositoryPath": null,
  "mode": "DIFF_TEXT",
  "baseRef": "origin/main",
  "commitSha": null,
  "title": "Manual review",
  "model": null,
  "instructions": "Only report actionable issues.",
  "diffText": "diff --git ...",
  "changedFiles": ["src/main/java/com/demo/OrderService.java"]
}
```

兼容要求：

- 当前 API Provider 主要支持 `DIFF_TEXT`。
- `changedFiles` 是 finding 输出白名单。
- `CODE_QUALITY_REVIEW_ENABLED=false` 时必须返回可解释失败。

### 7.4 AI Review Settings

`PUT /api/code-quality-reviews/settings`

```json
{
  "mrAutoReviewEnabled": false,
  "dingtalkNotificationEnabled": true,
  "defaultProviderCode": "DEEPSEEK"
}
```

兼容要求：

- 字段允许部分更新。
- 未传字段保持原值。

### 7.5 AI Review Provider

`PUT /api/code-quality-review-providers/{providerCode}`

```json
{
  "providerName": "DeepSeek",
  "endpointUrl": "https://api.deepseek.com",
  "modelName": "deepseek-v4-pro",
  "apiKey": "sk-...",
  "clearApiKey": false,
  "enabled": true
}
```

兼容要求：

- `apiKey` 不能出现在日志、progress event、响应明文中。
- `clearApiKey=true` 时清空密钥。
- 响应只返回 `apiKeyConfigured` 和 `apiKeyMasked`。

### 7.6 AI Review Profile

`PUT /api/code-quality-review-profiles/{profileCode}`

```json
{
  "profileName": "后端默认 AI Review",
  "enabled": true,
  "providerCode": "DEEPSEEK",
  "model": "deepseek-v4-pro",
  "triggerOnManual": true,
  "triggerOnMr": true,
  "triggerOnPush": false,
  "severityThreshold": "MAJOR",
  "blockOnSeverities": ["CRITICAL"],
  "enabledCategories": [],
  "ignoredPaths": [],
  "pushBranchPatterns": [],
  "pushMaxChangedFiles": 20,
  "pushMaxDiffBytes": 200000,
  "pushDebounceSeconds": 60,
  "triggerOnlyWhenRiskMatched": false,
  "reviewInstructions": "..."
}
```

兼容要求：

- JSON 列字段保持原样存储。
- prompt 更新后 `rendered-prompt` 必须可预览。

## 8. 数据库迁移执行方案

推荐策略：保留现有 MySQL 表结构和数据，不做清空式重写。

当前历史 migration 到 `V18`，涉及表：

- `notification_webhooks`
- `projects`
- `review_tasks`
- `review_results`
- `rule_templates`
- `notification_records`
- `gitlab_mr_webhook_events`
- `gitlab_push_webhook_events`
- `code_quality_review_profiles`
- `code_quality_review_results`
- `code_quality_review_progress_events`
- `code_quality_review_settings`
- `code_quality_model_providers`

### 8.1 新数据库初始化

执行策略：

1. 将 `backend/src/main/resources/db/migration/*.sql` 复制到 `backend-python/migrations/bootstrap_sql/`。
2. 初始化空库时按文件版本顺序执行 `V1` 到 `V18`。
3. 执行后创建 Alembic baseline revision。
4. 后续新增表或字段只走 Alembic。

验收：

```powershell
.\scripts\run-backend.cmd migrate
```

应完成：

- 空库出现全部核心表。
- `rule_templates` 有内置模板。
- `code_quality_review_settings` 有 id=1 默认设置。
- `code_quality_model_providers` 有内置 Provider。

### 8.2 已有数据库切换

执行策略：

1. Python 后端启动时先检查关键表是否存在。
2. 如果关键表已存在，不重复执行历史 SQL。
3. 执行 Alembic `stamp` 标记 baseline。
4. 只执行 baseline 之后的 Python 新 migration。

验收：

- 老任务可通过 `GET /api/review-tasks` 查询。
- 老 `risk_card_json` 能被原样返回。
- 老 AI Review 结果能被前端展示。

### 8.3 回滚策略

第一阶段不修改表结构，因此回滚简单：

```text
Nginx upstream 指回 Java backend
  -> Java backend 继续读写原表
```

从 Python 开始新增 Alembic migration 后，每个 migration 必须写明：

- 是否兼容 Java 后端。
- 是否可 downgrade。
- 回滚时是否需要停写。

## 9. 配置与环境变量兼容

保留现有变量：

- `SERVER_PORT`
- `PLATFORM_BASE_URL`
- `DINGTALK_ENABLED`
- `DINGTALK_WEBHOOK_URL`
- `GITLAB_API_ENABLED`
- `GITLAB_BASE_URL`
- `GITLAB_TOKEN`
- `GITLAB_DIFF_PER_PAGE`
- `CODE_QUALITY_REVIEW_ENABLED`
- `CODE_QUALITY_REVIEW_PROVIDER`
- `OPENAI_API_KEY`
- `OPENAI_RESPONSES_URL`
- `OPENAI_CODE_REVIEW_MODEL`
- `OPENAI_CODE_REVIEW_TIMEOUT_SECONDS`
- `ANTHROPIC_API_KEY`
- `ANTHROPIC_MESSAGES_URL`
- `ANTHROPIC_CODE_REVIEW_MODEL`
- `ANTHROPIC_CODE_REVIEW_TIMEOUT_SECONDS`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_CODE_REVIEW_MODEL`
- `DEEPSEEK_CODE_REVIEW_TIMEOUT_SECONDS`
- `XIAOMIMO_API_KEY`
- `XIAOMIMO_BASE_URL`
- `XIAOMIMO_CODE_REVIEW_MODEL`
- `XIAOMIMO_CODE_REVIEW_TIMEOUT_SECONDS`

新增推荐变量：

```text
DATABASE_URL=mysql+pymysql://ai_review:password@mysql:3306/ai_code_review?charset=utf8mb4
```

兼容要求：

- 如果设置了 `DATABASE_URL`，优先使用。
- 如果没有 `DATABASE_URL`，从旧 `MYSQL_URL + MYSQL_USERNAME + MYSQL_PASSWORD` 转换。
- `MYSQL_URL` 是 JDBC URL，Python 配置层要解析 host、port、database、query。
- `.local/gitlab.env` 继续由脚本加载。

## 10. 部署变化

### 10.1 本地开发

当前命令保持不变：

```powershell
.\scripts\run-backend.cmd
.\scripts\run-frontend.cmd
```

Python 版 `run-backend.cmd` 建议支持：

```powershell
.\scripts\run-backend.cmd
.\scripts\run-backend.cmd test
.\scripts\run-backend.cmd lint
.\scripts\run-backend.cmd migrate
.\scripts\run-backend.cmd dev --port 18080
```

同时保留 Java 临时入口：

```powershell
.\scripts\run-backend-java.cmd
.\scripts\run-backend-java.cmd -q test
```

### 10.2 Docker

当前后端镜像：

```text
maven:3.9-eclipse-temurin-21 build
  -> eclipse-temurin:21-jre runtime
  -> java -jar /app/app.jar
```

目标后端镜像：

```text
python:3.12-slim
  -> 安装依赖
  -> 拷贝 backend-python/app 和 migrations
  -> gunicorn app.main:app -k uvicorn.workers.UvicornWorker
```

`deploy/docker-compose.yml` 中保留：

- MySQL service
- frontend service
- `PUBLIC_HTTP_PORT`
- Nginx `/api/` 反代
- `mysql-data` volume

只替换：

- backend Dockerfile
- backend healthcheck
- backend environment 中的 database URL 处理

### 10.3 对外访问

保持不变：

```text
平台页面:
http://服务器IP:8080

GitLab webhook:
http://服务器IP:8080/api/webhooks/gitlab/merge-request
```

内部变化：

- Java 进程替换为 Python ASGI 进程。
- `/actuator/health` 由 Python 兼容实现。
- 日志从 Spring Boot 切换为 uvicorn/gunicorn + 应用日志。

## 11. 独立目录开发与长期双后端策略

### 11.1 当前仓库内独立目录开发

Python 后端第一阶段建议在当前仓库内新建独立目录开发：

```text
ai-code-review-platform/
  backend/          # 现有 Java 后端，保留作行为对照和回滚基线
  backend-python/   # 新 Python 后端，独立依赖、独立测试、独立启动
  frontend/         # 现有 React 前端，先不重写
  docs/
  deploy/
  scripts/
  examples/
```

这样做的好处：

- 不破坏现有 Java 后端，随时可以回到当前可运行状态。
- 可以复用现有 `frontend/`、`examples/`、`docs/`、`deploy/` 和数据库 migration。
- 可以让 Java 后端跑在 `8080`，Python 后端跑在 `18080`，用同一组请求做行为对比。
- 可以分阶段迁移脚本和 Docker，而不是一开始就把根目录全部重排。

目录隔离要求：

- `backend-python/` 必须有自己的 `pyproject.toml`、测试目录、迁移目录和应用入口。
- Python 代码不要依赖 Java `backend/target` 或 Maven 构建产物。
- 可以读取或复制 Java 历史 SQL migration，但不要在运行时依赖 Java classpath。
- 新增 Python 依赖只写入 `backend-python/pyproject.toml`，不要污染前端或 Java 后端配置。
- 第一阶段不要删除、移动或重命名现有 `backend/`。

### 11.2 并行验证方式

推荐并行运行：

```text
Java backend   : http://localhost:8080
Python backend : http://localhost:18080
Frontend dev   : http://localhost:5173
```

验证顺序：

1. Java 后端保持当前主链路可用。
2. Python 后端先实现健康检查和只读 API。
3. 同一组 mock webhook 分别发送到 Java 和 Python。
4. 对比任务状态、风险等级、风险项数量、细分类型、RiskCard 关键字段。
5. 前端临时切到 Python 后端验证页面展示。
6. Docker 和 Nginx 最后再切换。

### 11.3 长期保留 Java backend 的目标形态

当前决策：不再规划把 Python 后端剥离成新的根目录，也不删除现有 Java `backend/`。仓库长期保留两个后端目录：

```text
ai-code-review-platform/
  backend/          # Java Spring Boot legacy/reference backend
  backend-python/   # Python primary backend
  frontend/
  docs/
  deploy/
  scripts/
  examples/
```

长期定位：

- `backend-python/`：主后端，默认本地启动、Docker 部署和后续功能迭代都以它为准。
- `backend/`：历史实现、学习参考和行为对照，不再作为默认部署目标。
- `frontend/`：继续消费统一 `/api` 契约，不关心后端语言。
- `deploy/`：默认指向 Python backend；如需回看 Java 部署，可保留 legacy Dockerfile 或文档说明。
- `scripts/`：`run-backend.cmd` 默认启动 Python；`run-backend-java.cmd` 保留用于参考验证。

这样做的好处：

- 仓库保留 Spring Boot 后端项目痕迹，便于后续学习 Java 分层、DTO、Repository、测试和迁移脚本设计。
- Python 后端可以持续成为主线，不需要额外做项目剥离和路径大搬家。
- Java 后端可作为规则行为、API 字段、数据库写法的 reference implementation。
- 避免“重构完成后再移动目录”带来的脚本、Docker、文档和路径引用风险。

治理原则：

- 不删除、不移动 `backend/`。
- 不把 `backend-python/` 改名为 `backend/`。
- README 和 AGENTS.md 最终应明确双后端定位：Python 是 primary，Java 是 legacy/reference。
- 新功能默认只进入 `backend-python/`；除非明确需要对照验证，不再给 Java 后端补同等功能。
- 数据库 schema 以 Python 后端后续 Alembic migration 为主；Java Flyway migration 作为历史基线保留。

## 12. 分阶段执行计划

### 阶段 0：契约冻结与 golden sample

目标：在写 Python 代码前，先固定“必须兼容什么”。

任务：

1. 从 Java Controller 导出接口清单。
2. 用当前 Java 后端生成 golden response 样本。
3. 样本存放到：

```text
backend-python/tests/contract/golden/
```

4. 至少固化这些样本：
   - `GET /api/health`
   - `GET /api/projects`
   - `GET /api/rule-templates`
   - `GET /api/review-tasks`
   - `GET /api/review-tasks/{taskId}/result`
   - mock MR webhook 响应和落库结果
   - mock Push webhook 响应
   - manual review 响应
   - code quality settings 响应
   - code quality providers 响应
5. 在本文件维护 API compatibility checklist；未单独创建额外 checklist 文档。

验收：

- 每个 golden sample 都能说明请求、响应、数据库副作用。
- Python 实现完成后可以用同一组样本做对比。

### 阶段 1：Python 后端骨架

目标：跑起可替代 Spring Boot 的最小服务。

任务：

1. 新建 `backend-python/`。
2. 建立 FastAPI 应用入口。
3. 实现 `GET /api/health`。
4. 实现 `GET /actuator/health` 兼容入口。
5. 实现统一响应结构。
6. 接入配置加载、CORS、traceId、统一异常处理。
7. 建立 pytest 基础测试。
8. 新增 Python 后端启动脚本，保留 Java 后端临时脚本。

验收命令：

```powershell
.\scripts\run-backend.cmd test
.\scripts\run-backend.cmd dev --port 18080
curl http://localhost:18080/api/health
curl http://localhost:18080/actuator/health
```

通过标准：

- pytest 通过。
- 两个健康检查都返回 `UP`。
- 响应包含 `success/code/message/data/traceId`。

### 阶段 2：数据库访问与只读 API

目标：先让前端能读取已有数据。

任务：

1. 接入 SQLAlchemy。
2. 实现 `DATABASE_URL` 和旧 `MYSQL_URL` 兼容。
3. 映射核心表。
4. 实现只读接口：
   - `GET /api/projects`
   - `GET /api/review-tasks`
   - `GET /api/review-tasks/{taskId}`
   - `GET /api/review-tasks/{taskId}/result`
   - `GET /api/review-tasks/{taskId}/notifications`
   - `GET /api/rule-templates`
   - `GET /api/rule-templates/{templateCode}`
5. 使用现有数据库验证前端任务列表和详情页。

验收命令：

```powershell
.\scripts\run-backend.cmd test
.\scripts\run-backend.cmd dev --port 18080
curl http://localhost:18080/api/projects
curl http://localhost:18080/api/review-tasks
curl http://localhost:18080/api/rule-templates
```

通过标准：

- 老数据可查询。
- 前端临时指向 `18080` 后任务列表和详情可展示。
- golden response 的关键字段一致。

### 阶段 3：规则审查主链路

目标：打通 webhook -> 分析 -> 提醒卡片 -> 推送 -> 落库。

任务：

1. 实现 GitLab webhook 分发：
   - `Merge Request Hook`
   - `Push Hook`
   - `object_kind` fallback
2. 移植 GitLab Client：
   - project detail
   - MR detail
   - MR diffs
   - MR changes fallback
   - repository compare
3. 移植 changed files / diff 解析。
4. 移植变更分析规则：
   - API
   - DB / DB_SCHEMA / DB_SQL / ORM_MAPPING / ENTITY_MODEL / DATA_MIGRATION
   - CACHE_KEY / CACHE_TTL / CACHE_INVALIDATION / CACHE_READ_WRITE / CACHE_SERIALIZATION
   - MQ_PRODUCER / MQ_CONSUMER / MQ_MESSAGE_SCHEMA / MQ_TOPIC_CONFIG / MQ_RETRY_DLQ
   - CONFIG
5. 移植 rule template 加载。
6. 移植 risk engine 和 RiskCard 生成。
7. 移植 DingTalk notifier。
8. 实现 raw webhook event 保存。
9. 实现 review task 状态流转。
10. 实现 rerun。

验收命令：

```powershell
.\scripts\run-backend.cmd test
.\scripts\run-backend.cmd dev --port 18080

$payload = Get-Content -Raw -Path .\examples\gitlab-mr-webhook.mock.json
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:18080/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Merge Request Hook" } `
  -Body $payload
```

通过标准：

```text
mock webhook
  -> review_tasks SUCCESS
  -> review_results 写入 risk_card_json
  -> notification_records SUCCESS 或 SKIPPED
  -> GET /api/review-tasks/{taskId}/result 可返回
  -> 前端任务详情可展示
```

规则验收样本：

- Mapper XML SQL 变更：输出 `DB_SQL`，不误判 `DB_SCHEMA`。
- entity 字段变更：输出 `ENTITY_MODEL`。
- migration DDL 变更：输出 `DB_SCHEMA`，置信度 HIGH。
- entity + mapper 且无 migration：输出疑似 schema 未同步组合风险。
- MQ listener：输出 `MQ_CONSUMER`。
- 消息 DTO：输出 `MQ_MESSAGE_SCHEMA`。
- cache key 拼接：输出 `CACHE_KEY`。
- cache TTL：输出 `CACHE_TTL`。

### 阶段 4：AI Review Provider 迁移

目标：恢复当前代码质量 Review 能力。

任务：

1. 实现 settings 接口。
2. 实现 profile 接口。
3. 实现 provider 接口。
4. 移植手动 AI Review。
5. 移植 MR 自动触发逻辑。
6. 移植 Provider：
   - OpenAI Responses
   - Anthropic Messages
   - DeepSeek / OpenAI-compatible Chat Completions
   - Custom Provider
7. 移植 progress events。
8. 移植 retry。
9. 启动时恢复 stale RUNNING 任务为 FAILED。
10. 完成敏感信息脱敏。

验收命令：

```powershell
curl http://localhost:18080/api/code-quality-reviews/settings
curl http://localhost:18080/api/code-quality-review-providers
curl http://localhost:18080/api/code-quality-review-profiles
```

手动 Review 验证：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:18080/api/code-quality-reviews/manual" `
  -ContentType "application/json" `
  -Body '{
    "projectId": 1,
    "profileCode": "backend-default-ai-review",
    "mode": "DIFF_TEXT",
    "title": "Manual review",
    "diffText": "diff --git a/src/main/java/com/demo/OrderService.java b/src/main/java/com/demo/OrderService.java\n+ public void createOrder() {}",
    "changedFiles": ["src/main/java/com/demo/OrderService.java"]
  }'
```

通过标准：

- 未配置 API Key 时失败信息可解释。
- 配置 Provider 后能保存 `code_quality_review_results`。
- `code_quality_progress_events` 有过程记录。
- 响应和日志不泄露 API Key。
- 前端 AI Review tab 可展示结果和进度。

### 阶段 4B：AI Review 稳定化与真实可用性收口

目标：在进入 Docker / 默认入口切流前，把 Python AI Review 从“接口迁移和 mock 可测”推进到“真实 Provider 调用时不拖垮后端，前端可稳定观察结果”的状态。

任务：

1. manual review 和 retry 不同步等待真实模型调用，接口只写入 `RUNNING` 结果和 `QUEUED` progress 后立即返回。
2. Provider 调用放入后台执行器，后台任务使用独立数据库 Session。
3. progress event 必须在关键阶段及时提交，前端轮询时能看到 `QUEUED`、`REQUEST_BUILT`、`*_REQUEST`、`*_RESPONSE`、`SAVE_RESULT`、`FINISHED/FAILED`。
4. Provider 超时、HTTP 错误、非 JSON 输出、空 diff、缺 API Key 都要落成可解释 `FAILED`，不能让任务长期卡在 `RUNNING`。
5. 响应、日志、progress、rawOutput 继续保证不泄露 API Key / Authorization / token / secret。
6. 前端页面验证 retry / manual review 后不会导致 `/api/health`、任务列表、progress 查询一起超时。
7. 如果真实 Provider 凭据或网络不可用，至少用 respx 覆盖慢请求、超时、非 JSON、HTTP 失败等场景；真实联调阻塞要明确说明。

验收：

- retry 接口在真实 Provider 执行前快速返回 `RUNNING`。
- manual review 接口在真实 Provider 执行前快速返回 `RUNNING`。
- Provider 调用期间 `/api/health`、`/api/review-tasks`、`/api/review-tasks/{taskId}/code-quality-progress` 可正常响应。
- progress 可看到执行过程，而不是等模型返回后一次性出现。
- Provider 失败时 `code_quality_review_results.status=FAILED`，并有可读 `errorMessage`。
- Python 后端测试和 lint 通过。

### 阶段 5：部署切换

目标：将本地脚本、Docker、README 切到 Python 后端。

任务：

1. 新增 Python backend Dockerfile。
2. 更新 `deploy/docker-compose.yml`。
3. 更新 `deploy/.env.example`。
4. 更新 `scripts/package-docker-deploy.*`。
5. README 改为 Python 后端启动方式。
6. 保留 Java 后端说明到迁移附录或历史文档。
7. 在测试环境并行跑：

```text
Java backend:   8080
Python backend: 18080
```

8. 用同一组 webhook 样本比较结果。
9. 切换 Nginx backend upstream 到 Python。

验收命令：

```powershell
.\scripts\run-backend.cmd test
.\scripts\run-frontend.cmd build

cd deploy
docker compose up -d --build
docker compose ps
```

通过标准：

- `docker compose up -d --build` 后平台可访问。
- `http://服务器IP:8080/api/health` 返回 UP。
- GitLab webhook 地址不变。
- 老数据可以查询，新任务可以创建。

### 阶段 6：双后端目录治理

触发条件：

- Python 后端连续完成主要链路验证。
- mock webhook、真实 GitLab diff、手动审查、钉钉推送、AI Review 至少各有一次成功记录。
- 前端构建通过。
- Docker 部署通过。
- README 和排障文档已更新。

任务：

1. 保留 `backend/` Java 后端目录，不删除、不移动、不改名。
2. 将 `backend-python/` 标记为 primary backend，后续新功能默认进入 Python 后端。
3. 保留 Java 启动入口 `scripts/run-backend-java.cmd`，用于学习、参考和行为对照。
4. `scripts/run-backend.cmd`、Docker backend service、README 默认指向 Python 后端。
5. 更新 README、AGENTS.md 和部署文档，明确：
   - `backend-python/` 是主后端。
   - `backend/` 是 Java legacy/reference backend。
   - Java 后端不再作为默认部署目标。
6. 检查文档、脚本、Dockerfile 中是否还有误导性的“删除 Java”“剥离新项目”“backend-python 改名 backend”描述，并改为长期双后端策略。
7. 更新 `docs/10-local-dev-pitfalls.md`，记录迁移中新增的环境坑。

## 13. 测试策略

### 13.1 测试分层

| 层级 | 目标 | 工具 |
| --- | --- | --- |
| unit | 规则、schema、URL 解析、prompt 渲染 | pytest |
| repository | SQL 查询和 JSON 字段读写 | pytest + 测试库 |
| contract | API 响应与 golden sample 对齐 | pytest + TestClient |
| integration | webhook 主链路落库 | pytest + 测试库 |
| provider mock | GitLab / DingTalk / OpenAI / Anthropic / DeepSeek HTTP 行为 | respx |
| frontend smoke | 前端构建和页面手动烟测 | `scripts/run-frontend.cmd build` |

### 13.2 必补测试清单

- `test_health_contract.py`
- `test_database_url_parser.py`
- `test_projects_api_contract.py`
- `test_review_tasks_api_contract.py`
- `test_rule_templates_api_contract.py`
- `test_gitlab_webhook_dispatch.py`
- `test_gitlab_client_fallback.py`
- `test_change_analysis_db_rules.py`
- `test_change_analysis_mq_cache_rules.py`
- `test_risk_card_schema.py`
- `test_dingtalk_notifier.py`
- `test_manual_review_flow.py`
- `test_code_quality_settings.py`
- `test_code_quality_provider_masking.py`
- `test_code_quality_manual_review.py`
- `test_code_quality_retry.py`

### 13.3 golden sample 规则

golden sample 不要求逐字节完全一致，因为 `traceId`、时间、id 可能变化。

必须一致：

- `success`
- `code`
- `data` 的业务字段
- `riskCard.riskItems[].category`
- `riskCard.riskItems[].riskLevel`
- `riskCard.riskItems[].confidence`
- 数据库副作用表和关键字段

允许不同：

- `traceId`
- `createdAt` / `updatedAt`
- 自增 id
- 文案中不影响语义的时间或排序差异，但必须尽量减少。

## 14. 切流与回滚

### 14.1 并行验证

本地或测试环境：

```text
Java backend   : localhost:8080
Python backend : localhost:18080
Frontend dev   : localhost:5173
```

验证方式：

1. 同一个 mock webhook 发给 Java 和 Python。
2. 对比任务状态、风险等级、风险项数量、细分类型。
3. 前端代理临时指向 Python，检查页面。

### 14.2 切流步骤

1. 停止写入类验证任务。
2. 备份数据库。
3. 启动 Python backend。
4. 检查 `/api/health`。
5. 切换 Nginx backend upstream。
6. 发送 mock webhook。
7. 查询前端详情页。
8. 配置真实 GitLab webhook 保持原 URL，不需要 GitLab 侧改动。

### 14.3 回滚步骤

如果阶段 5 切换后出现问题：

1. 将 Nginx upstream 指回 Java backend。
2. 重启 frontend/Nginx 容器。
3. 确认 Java `/api/health` 正常。
4. 暂停 Python 后端。
5. 导出 Python 后端错误日志和对应 taskId。

第一阶段不改表结构，因此回滚不需要数据库恢复。开始新增 Alembic migration 后，必须按每个 migration 的回滚说明执行。

## 15. 风险与应对

| 风险 | 等级 | 应对 |
| --- | --- | --- |
| 规则行为不一致 | 高 | golden sample + 规则单测 + Java/Python 并行对比 |
| 数据库 migration 双轨 | 高 | 历史 SQL baseline，Python 新增才走 Alembic |
| Python 类型约束弱于 Java | 中 | Pydantic schema + 枚举集中定义 + pytest |
| API 字段不兼容导致前端坏掉 | 高 | 先迁只读 API，用前端真实页面验证 |
| Provider 泄露 API Key | 高 | 响应、日志、progress event 全部脱敏 |
| Docker 切换失败 | 中 | Java backend 保留，Nginx upstream 可回滚 |
| 学习成本过高 | 中 | 不先引入 Celery/Redis/复杂框架，按小目标推进 |

## 16. 推荐第一个开发任务

不要从完整重写开始。

第一轮只做：

```text
新增 backend-python 骨架，实现 /api/health、/actuator/health、统一响应、配置加载、traceId、pytest，并保留 Java 后端入口。
```

完成后再推进只读查询 API。这样每一步都能本地跑通，也符合当前项目“每次只做一个小目标”的工作方式。

## 17. 分阶段落地 Prompt

本节提供可直接复制使用的分阶段 prompt。原则是每个 prompt 只推进一个阶段，完成后必须给出“改了什么、为什么、如何验证、下一阶段建议”。

不要用单个 prompt 一次性重构完整后端。Python 后端重构涉及接口兼容、数据库、规则行为、AI Provider、Docker 切流和回滚，必须阶段验收。

### 17.1 阶段 1：Python 后端骨架

```text
请按 docs/19-python-backend-refactor-plan.md 开始 Python 后端重构的第一阶段，只做一个小目标：在当前仓库内新增 backend-python/ 独立目录，搭建 FastAPI 后端骨架。

要求：
1. 先阅读 AGENTS.md、README.md、docs/19-python-backend-refactor-plan.md、docs/10-local-dev-pitfalls.md。
2. 不要修改或删除现有 Java backend/，它要保留作行为对照和回滚基线。
3. 在 backend-python/ 内创建独立 Python 工程，包含 pyproject.toml、app/main.py、app/core/、tests/ 等基础结构。
4. 实现 GET /api/health，响应必须使用当前平台统一结构：success/code/message/data/traceId，data.status 为 UP。
5. 实现 GET /actuator/health 兼容入口，可返回简化 UP 响应，用于后续 Docker/Nginx 兼容。
6. 实现基础配置加载、traceId、统一异常处理、CORS。
7. 补 pytest 测试，至少覆盖 /api/health、/actuator/health、统一响应结构。
8. 新增或调整脚本时，保留 Java 后端启动入口，例如 scripts/run-backend-java.cmd；Python 后端默认可跑在 18080，避免影响当前 Java 8080。
9. 不要开始迁移业务接口、数据库、GitLab webhook、规则引擎或 AI Review；这些属于后续阶段。
10. 完成后说明：改了什么、为什么、如何验证，并列出下一阶段建议。

验收目标：
- 能运行 Python 后端测试。
- 能启动 Python 后端并访问 http://localhost:18080/api/health。
- 现有 Java backend/ 未被破坏。
```

### 17.2 阶段 2：只读 API 与数据库访问

```text
请按 docs/19-python-backend-refactor-plan.md 推进 Python 后端重构的第二阶段，只做数据库访问与只读 API。

前置条件：
1. backend-python/ 骨架已经存在。
2. /api/health、/actuator/health 和 pytest 已经可用。
3. 不修改或删除现有 Java backend/。

任务范围：
1. 先阅读 AGENTS.md、README.md、docs/19-python-backend-refactor-plan.md、docs/03-api-contract.md、docs/10-local-dev-pitfalls.md。
2. 在 backend-python/ 中接入 SQLAlchemy。
3. 实现 DATABASE_URL 配置，并兼容旧 MYSQL_URL + MYSQL_USERNAME + MYSQL_PASSWORD。
4. 映射只读查询所需核心表，至少覆盖 projects、review_tasks、review_results、rule_templates、notification_records。
5. 实现以下接口，并保持统一响应结构和字段兼容：
   - GET /api/projects
   - GET /api/review-tasks
   - GET /api/review-tasks/{taskId}
   - GET /api/review-tasks/{taskId}/result
   - GET /api/review-tasks/{taskId}/notifications
   - GET /api/rule-templates
   - GET /api/rule-templates/{templateCode}
6. 补 pytest 测试，至少覆盖 DATABASE_URL 解析、projects API、review-tasks API、rule-templates API。
7. 不要实现 webhook、手动审查、规则引擎、钉钉、AI Review；这些属于后续阶段。

验收目标：
- Python 后端测试通过。
- Python 后端跑在 18080 时，curl 能访问上述只读接口。
- 旧数据库中的任务和模板能被查询。
- 前端如临时指向 Python 后端，只读页面具备展示基础。

完成后说明：改了什么、为什么、如何验证，以及下一阶段建议。
```

### 17.3 阶段 3：规则审查主链路

```text
请按 docs/19-python-backend-refactor-plan.md 推进 Python 后端重构的第三阶段，只做规则审查主链路：webhook/manual -> analysis -> risk card -> notification record -> 落库。

前置条件：
1. backend-python/ 骨架、配置、统一响应、数据库访问、只读 API 已完成。
2. Java backend/ 仍保留，作为行为对照。
3. 不做 AI Review Provider，不做 Docker 切流。

任务范围：
1. 先阅读 AGENTS.md、README.md、docs/19-python-backend-refactor-plan.md、docs/03-api-contract.md、docs/04-risk-card-schema.md、docs/06-change-analysis-rules.md、docs/10-local-dev-pitfalls.md。
2. 实现 POST /api/webhooks/gitlab/merge-request，同一 URL 支持 Merge Request Hook 和 Push Hook 分发，兼容 object_kind fallback。
3. 实现 POST /api/review-tasks/manual。
4. 实现 POST /api/review-tasks/{taskId}/rerun。
5. 移植 GitLab payload 解析、changedFiles/diffText 解析、raw webhook event 保存。
6. 移植 change-analysis 规则，至少覆盖 API、DB 细分、CACHE 细分、MQ 细分、CONFIG。
7. 移植 rule-template 加载逻辑。
8. 移植 risk-engine 和 RiskCard 生成，RiskCard 必须对齐 docs/04-risk-card-schema.md。
9. 移植 DingTalk notifier 的最小行为：DINGTALK_WEBHOOK_URL 为空时写 notification_records SKIPPED，不阻断主链路。
10. 补 pytest 测试，至少覆盖 webhook 分发、manual review、DB 细分规则、MQ/CACHE 细分规则、risk card schema、notification SKIPPED。

验收目标：
- mock MR webhook 能创建 SUCCESS 任务。
- review_results 写入 change_analysis_json 和 risk_card_json。
- notification_records 写入 SUCCESS 或 SKIPPED。
- GET /api/review-tasks/{taskId}/result 能返回 riskCard。
- 典型规则样本输出的细分 category 与 Java 行为对齐。

完成后说明：改了什么、为什么、如何验证、与 Java 行为是否存在差异，以及下一阶段建议。
```

### 17.4 阶段 3B：真实 GitLab diff 与钉钉联调增强

```text
请按 docs/19-python-backend-refactor-plan.md 推进 Python 后端重构的阶段 3B，只做真实 GitLab diff 拉取与钉钉推送增强。

前置条件：
1. Python 规则审查主链路已能跑通 mock webhook。
2. 不做 AI Review Provider，不做 Docker 切流。
3. 如需要真实 GitLab token 或 DingTalk webhook，请使用现有 .local/gitlab.env 或提示我提供，不要把敏感信息写入代码、日志或文档。

任务范围：
1. 先阅读 AGENTS.md、README.md、docs/19-python-backend-refactor-plan.md、docs/18-project-integration-user-guide.md、docs/10-local-dev-pitfalls.md。
2. 移植 GitLab Client：
   - project detail
   - MR detail
   - MR diffs
   - MR changes fallback
   - repository compare
3. 支持 GITLAB_API_ENABLED、GITLAB_BASE_URL、GITLAB_TOKEN、GITLAB_DIFF_PER_PAGE。
4. payload 缺少 changedFiles 时，通过 GitLab API 补拉 diff。
5. GitLab API 失败时任务进入 FAILED，并记录清晰 errorMessage。
6. 增强 DingTalk notifier，保持现有“变更提醒”语义和 PLATFORM_BASE_URL + ?taskId={taskId} 链接。
7. 补 pytest/respx 测试，覆盖 /diffs 成功、/diffs 失败 fallback /changes、GitLab API 失败、DingTalk SKIPPED/SUCCESS。

验收目标：
- mock payload 仍然不依赖 GitLab API。
- payload 无 changedFiles 且 GitLab API 配置可用时，可以补拉真实 diff。
- GitLab API 失败时失败可解释。
- DingTalk webhook 为空时 SKIPPED，不影响任务成功。
- DingTalk webhook 配置可用时能发送并记录 SUCCESS。

完成后说明：改了什么、为什么、如何验证、真实外部联调是否受凭据或网络限制，以及下一阶段建议。
```

### 17.5 阶段 4：AI Review Provider

```text
请按 docs/19-python-backend-refactor-plan.md 推进 Python 后端重构的第四阶段，只做代码质量 AI Review 能力迁移。

前置条件：
1. Python 规则审查主链路已可用。
2. 不做 Docker 切流，不删除 Java backend/。
3. 如需要模型 API Key，请读取环境变量或提示我提供，不要把密钥写入代码、日志、progress event 或文档。

任务范围：
1. 先阅读 AGENTS.md、README.md、docs/19-python-backend-refactor-plan.md、docs/12-code-quality-review-provider-plan.md、docs/03-api-contract.md、docs/10-local-dev-pitfalls.md。
2. 实现以下接口：
   - POST /api/code-quality-reviews/manual
   - GET /api/code-quality-reviews/settings
   - PUT /api/code-quality-reviews/settings
   - POST /api/code-quality-reviews/tasks/{taskId}/retry
   - GET /api/code-quality-review-profiles
   - GET /api/code-quality-review-profiles/{profileCode}
   - PUT /api/code-quality-review-profiles/{profileCode}
   - GET /api/code-quality-review-profiles/{profileCode}/rendered-prompt
   - POST /api/code-quality-review-profiles/{profileCode}/reset-default-prompt
   - GET /api/code-quality-review-providers
   - PUT /api/code-quality-review-providers/{providerCode}
   - POST /api/code-quality-review-providers/{providerCode}/set-default
   - GET /api/review-tasks/{taskId}/code-quality-result
   - GET /api/review-tasks/{taskId}/code-quality-progress
3. 移植 settings/profile/provider repository。
4. 移植 Provider：
   - OpenAI Responses
   - Anthropic Messages
   - DeepSeek/OpenAI-compatible Chat Completions
   - Custom OpenAI-compatible Provider
5. 移植 MR 自动触发、manual review、retry、progress events、startup stale RUNNING recovery。
6. 所有 API Key、Authorization header、密钥字段必须脱敏。
7. 补 pytest/respx 测试，覆盖 settings、profile、provider masking、manual review、retry、progress events、provider API mock。

验收目标：
- 未启用 CODE_QUALITY_REVIEW_ENABLED 时返回可解释失败。
- 未配置 API Key 时失败可解释。
- 配置 Provider 后，手动 AI Review 能保存 code_quality_review_results。
- code_quality_review_progress_events 有过程事件。
- 前端 AI Review tab 能读取结果和进度。
- 响应和日志不泄露 API Key。

完成后说明：改了什么、为什么、如何验证、哪些 Provider 已 mock 验证、哪些需要真实凭据联调，以及下一阶段建议。
```

### 17.6 阶段 5：Docker、脚本与部署切流

```text
请按 docs/19-python-backend-refactor-plan.md 推进 Python 后端重构的第五阶段，只做部署、脚本和切流准备。

前置条件：
1. Python 后端规则审查主链路和 AI Review 能力已完成基础验证，且阶段 4B 的 AI Review 稳定化已完成。
2. Java backend/ 仍保留，不能删除。
3. 如果需要启动 Docker 或执行网络依赖安装，按当前环境权限要求请求授权。

任务范围：
1. 先阅读 AGENTS.md、README.md、docs/19-python-backend-refactor-plan.md、deploy/ 下现有文件、scripts/ 下现有脚本、docs/10-local-dev-pitfalls.md。
2. 调整 scripts/run-backend.cmd，使其默认启动 Python 后端。
3. 保留 Java 临时入口，例如 scripts/run-backend-java.cmd。
4. Python run-backend 支持 test、lint、migrate、dev --port 18080 等最小命令。
5. 新增或调整 Python backend Dockerfile。
6. 更新 deploy/docker-compose.yml、deploy/.env.example，使 backend 指向 Python 后端。
7. 更新 Nginx 反代和健康检查兼容 /api/health、/actuator/health。
8. 更新 package-docker-deploy 脚本，适配 Python 后端镜像构建与导出。
9. 更新 README 的本地启动、Docker 部署、验证步骤。
10. 不删除 Java backend/，不做独立项目剥离。

验收目标：
- Python 后端测试通过。
- 前端构建通过。
- docker compose up -d --build 能启动 MySQL、backend、frontend。
- http://localhost:${PUBLIC_HTTP_PORT}/api/health 返回 UP。
- GitLab webhook URL 语义不变。
- 如果 Docker 不可用或网络受限，记录明确阻塞原因和替代验证结果。

完成后说明：改了什么、为什么、如何验证、切流风险、回滚方式，以及下一阶段建议。
```

### 17.7 阶段 6：双后端目录治理

```text
请按 docs/19-python-backend-refactor-plan.md 推进 Python 后端重构的第六阶段，只做双后端目录治理：Python 后端成为主后端，Java 后端保留为 legacy/reference。

前置条件：
1. Python 后端已通过总体 Definition of Done。
2. Docker 部署已切到 Python 后端。
3. 前端已确认只依赖 Python 后端 API。
4. 不要删除、移动、改名 Java backend/。
5. 不要把 backend-python/ 改名为 backend/，也不要剥离为独立新根目录。

任务范围：
1. 先阅读 AGENTS.md、README.md、docs/19-python-backend-refactor-plan.md、docs/10-local-dev-pitfalls.md。
2. 检查 Python 后端是否已满足总体 Definition of Done。
3. 更新 README、AGENTS.md 和相关部署文档，明确：
   - backend-python/ 是 primary backend。
   - backend/ 是 Java legacy/reference backend。
   - scripts/run-backend.cmd 默认启动 Python。
   - scripts/run-backend-java.cmd 用于启动 Java 参考后端。
4. 检查 scripts/、deploy/、docs/ 中是否还有“删除 Java”“剥离新项目”“backend-python 改名 backend”的误导描述，并改为长期双后端策略。
5. 确认 Docker 和默认部署入口指向 Python 后端。
6. 更新 docs/10-local-dev-pitfalls.md，记录迁移中新增的环境坑、误判根因、调试结论。

验收目标：
- backend-python/ 是默认主后端。
- backend/ 仍完整保留，作为 legacy/reference backend。
- README、AGENTS.md、部署文档和脚本描述不再暗示要删除 Java 或剥离新项目。
- Python 后端测试、前端构建和 Docker 验证仍然通过。

完成后说明：改了什么、为什么、如何验证、Java reference backend 如何启动、后续新功能应进入哪个后端。
```

### 17.8 总控 Prompt：按阶段自主推进

如果希望 Agent 尽量自主推进，可以使用下面的总控 prompt。它要求 Agent 按阶段推进，但每个阶段完成后必须停止、汇报验证结果并等待确认，避免因为范围过大导致方向偏移。遇到外部凭据、真实服务、Docker/network 权限、切换部署入口等事项必须停下来请求确认。

```text
请阅读 AGENTS.md、README.md、docs/19-python-backend-refactor-plan.md、docs/10-local-dev-pitfalls.md，然后按文档第 17 节的阶段 prompt 顺序推进 Python 后端重构。

授权范围：
1. 可以在当前仓库内新增和修改 backend-python/、docs/、scripts/、deploy/ 中与当前阶段相关的文件。
2. 可以为当前阶段补充测试、示例和文档。
3. 可以自主运行本地非破坏性验证命令。
4. 每个阶段必须先说明本阶段目标，再实施，再验证，再总结。

硬性边界：
1. 不要删除、移动或改名现有 Java backend/。
2. 不要把 backend-python/ 剥离成新根目录，也不要改名为 backend/。
3. 不要提交、推送、切换生产部署或修改真实 webhook 配置，除非我明确确认。
4. 不要把 API Key、GitLab token、DingTalk webhook 写入代码、日志、测试快照或文档。
5. 遇到需要真实 GitLab、钉钉、模型 Provider、Docker 网络下载、数据库密码、生产配置的步骤，先使用 mock 或本地配置；无法继续时停下来说明需要什么。
6. 每个阶段结束后必须给出：改了什么、为什么、如何验证、剩余风险、是否建议进入下一阶段。
7. 每个阶段完成后停止，等待我确认“继续下一阶段”后再推进。

推进顺序：
1. 阶段 1：Python 后端骨架。
2. 阶段 2：只读 API 与数据库访问。
3. 阶段 3：规则审查主链路。
4. 阶段 3B：真实 GitLab diff 与钉钉联调增强。
5. 阶段 4：AI Review Provider。
6. 阶段 4B：AI Review 稳定化与真实可用性收口。
7. 阶段 5：Docker、脚本与部署切流。
8. 阶段 6：双后端目录治理。

先从阶段 1 开始。不要跳阶段。每完成一个阶段后停止，汇报验证结果、剩余风险和下一阶段建议，等待我确认后再继续。
```

## 18. 总体 Definition of Done

Python 后端重构完成标准：

- 本地能通过脚本启动 Python 后端和 React 前端。
- Docker 部署能通过一个对外端口访问平台。
- GitLab webhook 地址不变。
- 至少一个 mock webhook 完成：

```text
webhook -> 分析 -> 提醒卡片 -> 推送或 SKIPPED -> 落库 -> 前端展示
```

- 至少一个真实 GitLab diff 样本能创建审查任务。
- 手动规则审查可用。
- AI Review 手动触发至少跑通一个 Provider，或在未配置 API Key 时有清晰失败记录。
- 老数据库数据可查询。
- RiskCard schema 与 `docs/04-risk-card-schema.md` 对齐。
- README 写清启动、部署、验证步骤。
- `docs/10-local-dev-pitfalls.md` 记录迁移中新增的环境坑。
