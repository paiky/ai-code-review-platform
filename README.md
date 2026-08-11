# AI代码质量审查平台

本仓库是一个可接入 GitLab、钉钉和多模型 Provider 的研发质量平台。平台接收 MR、Push、manual review、commit range 或 branch diff，先通过规则生成结构化提醒卡片，再按项目配置触发代码质量 AI Review。

当前主线包括：

- 规则驱动的变更提醒：识别接口、数据库、缓存、MQ、配置等高价值变更。
- AI 驱动的代码质量审查：关注正确性、数据一致性、安全性、事务、并发、测试和可维护性。
- 质量治理：通过评估样本、回放、规则缺口、验收记录和确定性检查衡量审查质量。
- 可选 Agent Review：使用受控只读 Agent 获取更多源码证据，并与标准 Review 做生产对照。

## 代码目录

- `backend-python/`：当前主后端，Python 3.12+ / FastAPI。
- `frontend/`：React 前端，当前以 Ant Design 为主，并逐步使用 Material Design 3 / MUI。
- `backend/`：已停止维护的 Java 历史后端，仅在明确需要对照旧行为时读取。
- `docs/`：设计、API、schema、路线和操作文档。
- `examples/`：Webhook、manual review 和生产验证示例。
- `scripts/`：本地启动、测试、构建、迁移和部署打包脚本。
- `deploy/`：Dockerfile、Compose 和运行环境示例。

## 文档入口

README 只提供项目入口和最短运行方式。详细配置、部署、验证和功能行为以专题文档为准。

### 开发与接入

- `docs/42-development-deployment-and-validation-guide.md`：本地配置、启动、数据库迁移、Docker 部署、离线打包和验证命令。
- `docs/18-project-integration-user-guide.md`：项目接入使用手册。
- `docs/23-help-gitlab-dingtalk-project-onboarding.md`：GitLab、钉钉和项目组首次接入。
- `docs/03-api-contract.md`：HTTP API 契约。
- `docs/04-risk-card-schema.md`：提醒卡片 JSON schema。
- `docs/02-domain-model.md`：领域模型。
- `docs/06-change-analysis-rules.md`：变更分析规则。

### 产品与路线

- `docs/43-project-phase-acceptance-report.md`：平台能力规划与一期至四期分期验收标准。
- `docs/37-review-platform-target-product-roadmap.md`：长期产品目标和完整验收标准；仅在目标或验收标准变化时更新。
- `docs/38-review-lifecycle-and-frontend-entrypoints.md`：Review 生命周期、任务、质量治理和前端入口。
- `docs/40-review-evidence-pipeline-and-multi-target-roadmap.md`：确定性检查、Planner 多端感知和证据链专项。
- `docs/41-server-side-readonly-agent-review-plan.md`：服务器侧只读 Agent Review、安全边界和生产验收。
- `docs/47-agent-review-multi-worker-pool-and-queue-governance-plan.md`：Agent Worker 池化、并发领取、扩缩容和队列治理。
- `docs/48-review-task-detail-unified-progress-ui-plan.md`：任务详情统一 Review 进度 UI 专项。
- `docs/49-review-progress-animation-style-extension-plan.md`：Review 进度动画风格扩展专项；在 `docs/48` 完成后实施。

### 排障与历史

- `docs/11-agent-environment-pitfalls.md`：环境、脚本、部署、Codex、检索和工具链避坑；遇到问题时按关键词检索。
- `docs/24-bug-log.md`：业务缺陷和修复记录。
- `docs/10-local-dev-pitfalls.md`：历史避坑归档，仅追溯旧问题时读取。
- `docs/36-review-platform-current-roadmap.md`：2026 年 7 月 Review 路线与阶段记录归档，不再作为当前总控或继续更新。
- `docs/19-python-backend-refactor-plan.md`：已完成的 Python 迁移历史。
- `docs/39-review-accuracy-and-material-ui-roadmap.md`：已完成的准确率与前端体验专项记录。

## Agent 文档路由

新对话默认只读取 `AGENTS.md`。不要完整通读 README 或批量加载 `docs/`，先根据任务使用 `rg` 搜索关键词，再局部读取命中章节。

- 启动、配置、部署、迁移和验证：在 `docs/42-development-deployment-and-validation-guide.md` 中搜索。
- 当前阶段和推进顺序：以用户明确指定的专题文档及其中的停止点为准，不再维护全局阶段登记表。
- Review 生命周期和前端入口：在 `docs/38-review-lifecycle-and-frontend-entrypoints.md` 中搜索。
- 证据链和多端能力：在 `docs/40-review-evidence-pipeline-and-multi-target-roadmap.md` 中搜索。
- 服务器侧只读 Agent Review：在 `docs/41-server-side-readonly-agent-review-plan.md` 中搜索。
- Agent Worker 副本数、池化和队列治理：在 `docs/47-agent-review-multi-worker-pool-and-queue-governance-plan.md` 中搜索。
- API、规则和 schema：通过 `rg` 定位对应专题文档。
- 环境和工具问题：在 `docs/11-agent-environment-pitfalls.md` 中搜索具体症状。
- 历史计划和归档：只有明确追溯历史决策时读取。

功能行为、阶段记录、接口语义和验收结果写入对应专题文档，不再默认追加到 README。

## 当前主链路

```text
GitLab MR webhook / GitLab Push webhook / 手动审查
  -> 创建 review task 并保存原始事件
  -> 获取 changed files / diff
  -> 变更分析
  -> 规则引擎生成提醒卡片
  -> 结果与通知记录落库
  -> 钉钉推送或 SKIPPED
  -> 前端任务详情
  -> 可选触发标准 AI Review 或只读 Agent Review
  -> 进度、finding、确定性证据和质量数据可见
```

后端 JSON 仍兼容历史 `riskCard`、`riskItems`、`riskLevel` 等字段；展示层统一使用“提醒卡片 / 提醒项”。字段重命名需要单独迁移 schema、API、数据库和历史数据。

## 当前能力

### 规则提醒

- 接收 GitLab `Merge Request Hook` 和 `Push Hook`，并提供手动审查入口。
- MR payload 缺少 diff 时可通过 GitLab API 补拉；Push 支持 compare API 和 payload fallback。
- 识别 API、DB、缓存、MQ、配置等信号，并通过模板生成结构化提醒卡片。
- 提醒项保留命中证据、文件位置和 diff，可生成 SQL、Redis、MQ、Nacos 等维护草稿。
- 审查任务、分析结果、提醒卡片和通知记录统一落库。
- 钉钉按项目组 webhook 和模板关注类型发送提醒。

### AI Review

- 支持 OpenAI、Anthropic、DeepSeek、XiaoMIMO、GLM 和 OpenAI-compatible 自定义 Provider。
- 支持全局开关、Provider、Profile、Prompt、模型、Key、超时和项目组多模型配置。
- 支持 MR 自动触发、Push 策略触发、manual review、retry 和多模型并行执行。
- finding 包含风险等级、证据、上下文状态、置信度、缺失上下文和安全摘要。
- 支持调度队列、失败通知、finding 级补证据和修复 Patch 预览。
- Provider 调用保持非流式 HTTP；前端通过结果和 progress API 轮询展示过程。

### 证据与准确率

- Context Planner 识别变更信号、端类型、语言和覆盖状态。
- Local Retriever 在受控 worktree 内检索调用关系、DTO 字段、DB/Mapper、缓存、MQ 和配置证据。
- 预算裁剪后通过安全摘要说明未注入证据，避免模型把“未提供”误解为“不存在”。
- `SECRET_SCAN` 在 MR、Push、manual 和 retry 的 Provider 调用前自动运行；同次多模型调度复用一个 run。
- 确定性检查失败默认 fail-open，脱敏失败摘要进入 progress 和 Context Pack。
- 质量治理提供评估样本、回放、质量看板、规则缺口和验收记录。

### 服务器侧只读 Agent Review

- 项目组可选择 `STANDARD` 或 `AGENT`，启用 Agent 前必须确认源码外发授权。
- 独立 Worker 使用加密 Key、持久化 Job/Run、只读 workspace 和受限 MCP 工具。
- Agent 失败会显式执行 `STANDARD_FALLBACK`，不会伪装成 Agent 成功。
- 生产观察支持 STANDARD / AGENT 对照、人工标注、脱敏导出和合成 demo。
- 当前停止点、样本门禁和扩大范围条件以 `docs/41-server-side-readonly-agent-review-plan.md` 为准。

## 环境要求

- Python 3.12+
- MySQL 8.0+
- Node.js 20+
- 可选：Docker Engine + Docker Compose plugin

详细环境和依赖安装见 `docs/42-development-deployment-and-validation-guide.md`。

## 最小配置

后端读取环境变量；仓库脚本也会加载 `.local/gitlab.env`。最小本地配置：

```powershell
$env:DATABASE_URL="mysql+pymysql://root:root@localhost:3306/ai_code_review?charset=utf8mb4"
```

需要补拉真实 GitLab diff 时再配置：

```text
GITLAB_API_ENABLED=true
GITLAB_BASE_URL=https://你的GitLab地址
GITLAB_TOKEN=具备项目读取权限的token
```

AI Review 默认关闭。Provider、Profile、模型和 Key 推荐在前端“设置”页维护。完整变量表见 `docs/42-development-deployment-and-validation-guide.md`，部署示例见 `deploy/.env.example`。

## 快速启动

### 1. 创建数据库

```sql
CREATE DATABASE ai_code_review
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### 2. 初始化并启动后端

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-backend.ps1 migrate
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-backend.ps1 dev
```

后端默认地址：`http://localhost:8090`。

```powershell
curl http://localhost:8090/api/health
curl http://localhost:8090/actuator/health
```

### 3. 启动前端

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-frontend.ps1
```

前端默认地址：`http://localhost:5173`，`/api` 默认代理到本地 8090 后端。

首次安装 Python 依赖、修改端口和本地配置文件的步骤见操作手册。

## Docker 快速部署

```bash
cd deploy
cp .env.example .env
```

至少配置：

```text
PUBLIC_HTTP_PORT=8090
PLATFORM_BASE_URL=http://你的域名或服务器IP:8090
DATABASE_URL=mysql+pymysql://ai_review:强密码@数据库地址:3306/ai_code_review?charset=utf8mb4
```

启动并验证：

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8090/api/health
```

### Agent Worker 副本数

每个 `agent-worker` 容器同时只执行一个 Agent Review。生产首次池化推荐使用 2 个 Worker，
Worker 数量由 Docker Compose 的 `--scale` 参数显式控制，不在设置页中配置：

```bash
WORKER_COUNT=2
docker compose up -d --scale agent-worker=$WORKER_COUNT
```

升级时只重建 Worker 和受限出站代理：

```bash
WORKER_COUNT=2
docker compose up -d --scale agent-worker=$WORKER_COUNT agent-egress-proxy agent-worker
```

Worker 相关配置：

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `--scale agent-worker=N` | 未指定时单副本 | Worker 容器数量；当前远程验收值为 `2` |
| `AGENT_REVIEW_WORKER_ID_PREFIX` | `agent-worker` | Worker ID 前缀；Linux 容器自动追加 hostname，通常无需修改 |
| `AGENT_REVIEW_WORKER_TOKEN` | 无 | Backend 与 Worker 共用的内部鉴权密钥，必须配置且不得写入仓库 |
| `LOCAL_REPO_WORKSPACE_HOST_DIR` | 部署配置决定 | 挂载到 Worker 的只读仓库工作区宿主机目录 |

注意：

- 普通 `docker compose up -d` 不应作为保持多副本数量的部署命令；升级、执行 `down` 后重建或调整数量时，
  应重新显式传入 `--scale agent-worker=N`。
- `docker compose restart` 和服务器基于 `restart: unless-stopped` 的重启通常会保留现有容器数量。
- 当前只验收 2 个 Worker，不建议在完成容量与队列治理前扩大到更多副本。
- 阶段三优雅排空落地前，缩容必须先禁用 Agent Review 并等待运行任务结束。
- 生产多 Worker 要求 MySQL 8；MySQL 5.7 只保留串行领取兼容。

GitLab webhook：

```text
http://你的域名或服务器IP:8090/api/webhooks/gitlab/merge-request
```

外部 MySQL、内置 MySQL profile、本地仓库 volume、离线镜像包、升级、回滚和 Agent Worker 部署见 `docs/42-development-deployment-and-validation-guide.md`。

## 最小验证

发送 Mock MR webhook：

```powershell
$payload = Get-Content -Raw .\examples\gitlab-mr-webhook.mock.json
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Merge Request Hook" } `
  -Body $payload
```

查询任务：

```powershell
curl http://localhost:8090/api/review-tasks
```

完整 Mock Push、manual review、真实 GitLab diff、确定性检查和 Agent Review 验证见操作手册与 `examples/`。

## 常用验证命令

按影响范围选择最小集，不要默认执行全量测试。

```powershell
# Python 后端全量测试
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-backend.ps1 test

# Python lint
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-backend.ps1 lint

# 前端生产构建
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-frontend.ps1 build
```

- 前端样式或交互改动：优先只跑前端 build。
- Python 局部逻辑：优先跑相关 pytest 文件或测试类。
- webhook 主链路、共享模型、通知、数据库兼容或跨模块改动：运行全量 Python 测试。

## 主要接口入口

规则提醒与任务：

```text
POST /api/webhooks/gitlab/merge-request
POST /api/review-tasks/manual
POST /api/review-tasks/{taskId}/rerun
GET  /api/review-tasks
GET  /api/review-tasks/{taskId}
GET  /api/review-tasks/{taskId}/result
GET  /api/review-tasks/{taskId}/diff-context
```

代码质量 Review：

```text
POST /api/code-quality-reviews/manual
POST /api/code-quality-reviews/tasks/{taskId}/retry
GET  /api/review-tasks/{taskId}/code-quality-results
GET  /api/review-tasks/{taskId}/code-quality-progress
GET  /api/code-quality-review-profiles
GET  /api/code-quality-review-providers
```

完整字段、请求体和管理接口见 `docs/03-api-contract.md`。

## 前端入口

- `任务`：任务列表、详情、提醒卡片、分析、AI Review、执行过程和调度队列。
- `质量治理`：质量看板、评估样本、规则缺口、验收记录和回放记录。
- `设置`：全局开关、Provider、Profile、Prompt、项目组、端类型和 Push 策略。
- `版本更新`：近期功能变化、部署注意和验证提示。
- `反馈池`：默认隐藏，仅在对应前端 feature flag 开启后显示。

详细页面职责、生命周期和高级入口见 `docs/38-review-lifecycle-and-frontend-entrypoints.md`。

## 文档维护规则

- README 只维护项目入口、最短启动方式和专题文档路由。
- 环境、部署、迁移和验证步骤写入 `docs/42-development-deployment-and-validation-guide.md`。
- 新环境或工具踩坑写入 `docs/11-agent-environment-pitfalls.md`。
- 接口语义和 schema 写入对应 API 或设计文档。
- 阶段目标、落地记录和验收结果写入对应路线或专项文档。
- 业务缺陷和规则误判写入对应设计文档或 `docs/24-bug-log.md`。
