# AI 变更提醒与代码质量审查平台

本仓库是一个可接入 GitLab / 钉钉 / 多模型 API 模式 AI Review 的研发质量平台原型。当前主流程围绕代码变更生成结构化“提醒卡片”，再按需触发代码质量 AI Review。

代码目录：

- `backend-python/`：当前主后端，FastAPI 实现，后续功能开发默认在这里落地。
- `frontend/`：React + Ant Design 前端。
- `docs/`：设计、API、schema 与实施计划文档。
- `examples/`：Webhook 与手动审查示例请求。
- `scripts/`：本地启动与 Docker 打包脚本。

常用文档：

- `docs/23-help-gitlab-dingtalk-project-onboarding.md`：接入帮助页文档源，面向首次接入用户，按 GitLab Webhook、钉钉机器人、项目组和模型配置组织。
- `docs/26-gitlab-diff-context-expansion-plan.md`：GitLab 风格 Diff 上下文展开与暗黑语法高亮分阶段实施计划。
- `docs/18-project-integration-user-guide.md`：项目接入使用手册，按 GitLab 接入、项目设置、钉钉推送链路组织。
- `docs/10-local-dev-pitfalls.md`：本地环境与调试避坑（按条目累积，含迁移期记录）。
- `docs/03-api-contract.md`：HTTP API 契约。
- `docs/04-risk-card-schema.md`：提醒卡片 JSON schema。
- `docs/02-domain-model.md` / `docs/06-change-analysis-rules.md`：领域模型与变更分析规则。
- `docs/24-bug-log.md`：已知 BUG 与修复记录。
- `docs/19-python-backend-refactor-plan.md`：Python 迁移计划（**已完成**，保留分阶段 prompt 写法参考）。
- 其它 `docs/1*.md` / `docs/2*.md` 多为计划、历史方案或 PPT 素材；使用前请看文首状态说明。

## Agent / 新对话入口

新对话或自动化 Agent 理解项目时，优先阅读：

1. `AGENTS.md`：项目目标、工作方式、脚本使用约束。
2. `README.md`：本地启动、配置、验证步骤。
3. `docs/10-local-dev-pitfalls.md`：本地环境与调试避坑。
4. 与当前任务相关的 `docs/` 设计文档，例如 API、规则、AI Review provider 计划等。

后续开发以 `backend-python/` 和 `frontend/` 为主。

启动、编译、测试、构建应优先使用 `scripts/` 目录下脚本，不要绕过脚本直接按个人习惯执行底层命令。脚本负责统一本地 env、依赖安装和 Windows 命令兼容。

当前默认后端入口：

- `.\scripts\run-backend.cmd`：默认启动或测试 Python FastAPI 后端；内部会调用 `run-backend.ps1`。
- `.\scripts\run-backend.ps1`：薄包装，最终原样转发参数到 `run-backend-python.ps1`。
- `.\scripts\run-backend-python.ps1`：Python 后端实际 runner，负责加载 `.local/gitlab.env`、设置 `PYTHONPATH`、选择 Python、执行 `dev/test/lint/migrate`。

验证策略按影响范围选择最小集，不要无意义地默认全量扫描：

- 只改前端样式或交互：优先跑 `.\scripts\run-frontend.cmd build`。
- 只改 Python 后端局部逻辑：优先跑相关 pytest 文件或测试类。
- 改到 webhook -> 分析 -> 风险卡片 -> 通知 -> 落库主链路、共享模型、数据库兼容或跨模块边界时，再跑 `.\scripts\run-backend.cmd test` 全量 Python 测试。

搜索代码时排除依赖和构建产物目录，例如 `frontend/node_modules/`、`frontend/dist/`、`backend-python/.venv/`、`__pycache__/`、`.pytest_cache/`。仓库根目录提供 `.rgignore`，优先使用 `rg` 遵守该忽略规则。

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
- Push Hook 可优先调用 GitLab compare API 拉取 `beforeSha -> afterSha` diff；新分支 Push（`before` 全 0）且无 diff 时会直接 `SKIPPED` 不建任务；其它场景 compare 失败时才回退到 payload 文件列表。
- 变更分析识别 API、DB、缓存、MQ、配置等信号；默认 `backend-default` 提醒规则已收敛为 DB 写入/结构、缓存写入删除、MQ 配置、应用配置四类（分析层仍保留更多细粒度 changeType 供扩展）。
- 缓存写入删除提醒只根据 diff 实际新增或删除行判断，未修改上下文中的历史 `set / put / expire / delete / evict` 不会触发提醒。
- `@Value` 配置占位符变更会进入重点变更提醒。
- 提醒卡片在前端按 DB / MQ / Redis/缓存 / 配置分组展示，并为重点提醒生成可复制维护内容：SQL 草稿、Redis 命令、MQ 配置伪代码、Nacos 配置块。
- DB 维护 SQL 会优先使用真实 DDL；没有 SQL 文件时按 Entity / Mapper 和变更类型推断 `CREATE TABLE` 或 `ALTER TABLE`，并标记为 `INFERRED`。
- 提醒项保留原命中证据，并可在详情页直接查看对应文件 diff。
- GitLab MR / Push 任务可按需读取变更文件的完整源码上下文；“查看 Diff”支持 GitLab 风格分段展开，“AI 修复 Patch 预览”保持紧凑展示；两者都支持明亮 / 暗黑主题切换和按文件类型语法高亮。未配置 GitLab API、缺少历史 refs 或手动粘贴 diff 时保持紧凑 diff 展示。
- 钉钉消息按模板 `focusChangeTypes` 过滤提醒来源，并带上项目名称、简洁提醒和平台详情链接。
- 审查任务、变更分析结果、提醒卡片、通知记录均落库。
- 代码质量 AI Review 支持 OpenAI、Anthropic、DeepSeek、XiaoMIMO、GLM 和 OpenAI-compatible 自定义模型 Provider。
- AI Review 支持配置 / prompt 配置、模型端点 URL / 模型名称 / API Key 配置、项目组多模型并行 Review、自动触发、重试、执行过程展示。
- AI Review finding 支持展示上下文状态、置信度、判断依据、缺失上下文和上下文摘要；当模型只能基于 diff 判断时，Prompt 会要求输出“部分 / 不足”上下文状态，避免证据不足时武断判为高风险。
- GitLab MR 自动 AI Review 完成后会向任务所属项目组中已启用的钉钉 webhook 推送“代码质量 Review”结果；项目组未配置机器人时记录为 `SKIPPED`，不会回退推送到默认项目组。
- GitLab Push webhook 会先按项目组 Push 审核策略中的 `pushBranchPatterns` 做入口过滤，只有允许分支会创建审查任务并进入后续流程；Push 自动 AI Review 还需要通过 Push 审核层。该审核层会根据文件数、diff 大小、commit 数、硬上限和 debounce 自动判定是否允许进入 AI Review，并在任务详情页公开展示放行或拦截原因。

## 环境要求

- Python 3.12+
- MySQL 8.0+
- Node.js 20+

## 后端配置

后端默认读取环境变量，也支持通过 `.local/gitlab.env` 配合启动脚本加载本地配置。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | 空 | Python SQLAlchemy 连接串，已设置时优先于旧 JDBC 配置 |
| `MYSQL_URL` | `jdbc:mysql://localhost:3306/ai_code_review?...` | MySQL JDBC URL |
| `MYSQL_USERNAME` | `root` | MySQL 用户 |
| `MYSQL_PASSWORD` | `root` | MySQL 密码 |
| `SERVER_PORT` | `8090` | 本地 Python 后端端口；Docker 部署会显式设置为容器内端口 |
| `PLATFORM_BASE_URL` | `http://localhost:5173` | 钉钉“查看平台详情”链接前缀 |
| `GITLAB_API_ENABLED` | `false` | 是否启用 GitLab API 补拉 diff |
| `GITLAB_BASE_URL` | 空 | GitLab base URL；同时用于把 webhook payload 中的内网 GitLab Web 链接归一化为可访问地址 |
| `GITLAB_TOKEN` | 空 | GitLab access token |
| `GITLAB_DIFF_PER_PAGE` | `100` | MR diff 分页大小 |
| `CODE_QUALITY_REVIEW_ENABLED` | `false` | 代码质量 Review 全局能力的兼容初始化值；推荐在设置页通过 `reviewEnabled` 开关启停 |
| `CODE_QUALITY_REVIEW_PROVIDER` | `DEEPSEEK` | 默认模型 Provider，可被数据库配置覆盖 |
| `OPENAI_API_KEY` | 空 | OpenAI API key，首次初始化 Provider 时可作为默认值 |
| `OPENAI_RESPONSES_URL` | `https://api.openai.com/v1/responses` | OpenAI Responses API 地址 |
| `OPENAI_CODE_REVIEW_MODEL` | `gpt-5.4` | OpenAI provider 模型 |
| `OPENAI_CODE_REVIEW_TIMEOUT_SECONDS` | `1000` | OpenAI 请求超时时间 |
| `ANTHROPIC_API_KEY` | 空 | Anthropic API key |
| `ANTHROPIC_MESSAGES_URL` | `https://api.anthropic.com/v1/messages` | Anthropic Messages API 地址 |
| `ANTHROPIC_CODE_REVIEW_MODEL` | `claude-sonnet-4-5` | Anthropic provider 模型 |
| `ANTHROPIC_CODE_REVIEW_TIMEOUT_SECONDS` | `1000` | Anthropic 请求超时时间 |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek API key，首次初始化 Provider 时可作为默认值 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek OpenAI-compatible base URL |
| `DEEPSEEK_CODE_REVIEW_MODEL` | `deepseek-v4-pro` | DeepSeek provider 模型 |
| `DEEPSEEK_CODE_REVIEW_TIMEOUT_SECONDS` | `1000` | DeepSeek 请求超时时间 |
| `XIAOMIMO_API_KEY` | 空 | XiaoMIMO API key，首次初始化 Provider 时可作为默认值 |
| `XIAOMIMO_BASE_URL` | `https://api.xiaomimimo.com/v1` | XiaoMIMO OpenAI-compatible base URL |
| `XIAOMIMO_CODE_REVIEW_MODEL` | `mimo-v2.5-pro` | XiaoMIMO provider 模型 |
| `XIAOMIMO_CODE_REVIEW_TIMEOUT_SECONDS` | `1000` | XiaoMIMO 请求超时时间 |
| `GLM_API_KEY` | 空 | 智谱 GLM API key，首次初始化 Provider 时可作为默认值 |
| `GLM_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | GLM OpenAI-compatible base URL |
| `GLM_CODE_REVIEW_MODEL` | `glm-5.1` | GLM provider 模型 |
| `GLM_CODE_REVIEW_TIMEOUT_SECONDS` | `1000` | GLM 请求超时时间 |

PowerShell 示例：

```powershell
$env:DATABASE_URL="mysql+pymysql://root:root@localhost:3306/ai_code_review?charset=utf8mb4"
$env:GITLAB_API_ENABLED="false"
```

## Docker 部署

仓库内置 `deploy/docker-compose.yml`，适合单台远程服务器快速部署：

```text
宿主机 :${PUBLIC_HTTP_PORT}，默认 8090
  -> Nginx frontend 容器 :80
  -> React 静态页面
  -> /api 反向代理到 backend:${BACKEND_PORT}
Python FastAPI backend 容器，默认 8090，仅在 Docker 网络内访问
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
PUBLIC_HTTP_PORT=8090
PLATFORM_BASE_URL=http://你的域名或服务器IP:8090
DATABASE_URL=mysql+pymysql://ai_review:强密码@192.168.100.88:3306/ai_code_review?charset=utf8mb4
```

`PUBLIC_HTTP_PORT` 是前端容器暴露到宿主机的访问端口，浏览器访问和 GitLab webhook 都走这个端口。`PLATFORM_BASE_URL` 是后端生成外链用的基础地址，例如钉钉机器人消息里的“查看平台详情”链接；它不会改变前端容器实际监听或暴露的端口。两者通常应该配置为同一个用户可访问地址，例如：

```text
PUBLIC_HTTP_PORT=15173
PLATFORM_BASE_URL=http://192.168.100.241:15173
```

按需再配置这些可选项：

```text
GITLAB_API_ENABLED=true
GITLAB_BASE_URL=https://你的 GitLab 地址
GITLAB_TOKEN=GitLab access token
LOCAL_REPO_CONTEXT_ENABLED=true
LOCAL_REPO_WORKSPACE_ROOT=/app/.local/review-workspaces
LOCAL_REPO_WORKSPACE_HOST_DIR=./review-workspaces
CODE_QUALITY_REVIEW_ENABLED=true
DEEPSEEK_API_KEY=...
XIAOMIMO_API_KEY=...
GLM_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
```

`LOCAL_REPO_CONTEXT_ENABLED=true` 会启用高准确模式的本地仓库上下文检索。`LOCAL_REPO_WORKSPACE_ROOT` 是 backend 容器内路径，默认挂载到 `/app/.local/review-workspaces`；`LOCAL_REPO_WORKSPACE_HOST_DIR` 是宿主机缓存目录，默认是运行目录下的 `./review-workspaces`，用于持久化 Git mirror 和 task worktree。GitLab token 需要具备 `read_repository` 权限，否则本地 clone / fetch 会失败并在任务详情中显示本地仓库不可用。

默认部署使用外部 MySQL，不会启动 compose 内置的 `mysql` 容器。如果确实要使用内置 MySQL，再在 `.env` 中增加：

```text
COMPOSE_PROFILES=local-mysql
MYSQL_ROOT_PASSWORD=强密码
MYSQL_DATABASE=ai_code_review
MYSQL_USERNAME=ai_review
MYSQL_PASSWORD=强密码
DATABASE_URL=mysql+pymysql://ai_review:强密码@mysql:3306/ai_code_review?charset=utf8mb4
```

启动：

```bash
docker compose up -d --build
```

本地执行 `.\scripts\package-docker-deploy.cmd` 前，需要先启动 Docker Desktop 并等待 Linux Engine 可用。脚本会在 Docker CLI 缺失或 Engine 未启动时直接停止，并输出对应处理建议。

查看状态和日志：

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
```

验证：

```bash
curl http://127.0.0.1:8090/actuator/health
curl http://127.0.0.1:8090/api/health
```

说明：

- backend 容器启动时会先执行 `python -m app.migrate`。空 MySQL 会按 `backend-python/migrations/bootstrap_sql/` 顺序初始化历史表结构和内置数据；已有核心表时会自动跳过 bootstrap。
- 如需单独确认后端 bootstrap / gunicorn 启动过程，可执行 `docker compose logs -f backend`。
- 钉钉 webhook 不再通过 `.env` 默认配置。部署完成后，请进入前端“设置”页，在“全局设置”中手动添加一个或多个钉钉 webhook。
- GitLab webhook 接收能力不依赖 `GITLAB_TOKEN`。如果 webhook payload 已携带 changed files，平台可以直接审查；如果 MR payload 没有 diff、Push 需要 compare 补拉，或任务“重新触发审阅”需要重新拉 GitLab diff，则必须配置 `GITLAB_API_ENABLED=true`、`GITLAB_BASE_URL` 和 `GITLAB_TOKEN`。

平台访问和 GitLab webhook 使用同一个对外端口：`PUBLIC_HTTP_PORT`。默认访问 `http://服务器IP:8090`，GitLab webhook 配 `http://服务器IP:8090/api/webhooks/gitlab/merge-request`。如需改端口，同步修改 `deploy/.env` 中的 `PUBLIC_HTTP_PORT` 与 `PLATFORM_BASE_URL` 即可。`BACKEND_PORT` 为容器内后端监听端口，仅在 Docker 网络内使用，Nginx 反向代理会自动跟随。

升级：

```bash
git pull
cd deploy
docker compose up -d --build
```

GitLab webhook 地址配置为：

```text
http://你的域名或服务器IP:8090/api/webhooks/gitlab/merge-request
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

默认外部 MySQL 部署不需要 MySQL 镜像。如果要启用内置 MySQL，或服务器需要完全离线准备 MySQL 镜像，再把 MySQL 镜像一起打包：

```powershell
.\scripts\package-docker-deploy.cmd -IncludeMysqlImage
```

将 `.local/docker-deploy/{版本号}/` 整个目录上传到服务器固定父目录下，例如：

```bash
scp -r .local/docker-deploy/{版本号} user@server:/opt/ai-code-review-platform/
```

服务器执行：

```bash
cd /opt/ai-code-review-platform/{版本号}
chmod +x load-images.sh
./load-images.sh
vi ../runtime/.env
cd ../runtime
docker compose up -d
```

`load-images.sh` 会把运行用的 `docker-compose.yml` 放到 `/opt/ai-code-review-platform/runtime/`，并且只在第一次部署时创建 `/opt/ai-code-review-platform/runtime/.env`。以后升级时重新上传新版本目录，执行新版本目录里的 `./load-images.sh`，脚本只更新 `APP_VERSION`，不会覆盖你已经配置好的 MySQL、GitLab、钉钉或模型密钥。

如果启用本地仓库上下文检索，请在 `/opt/ai-code-review-platform/runtime/.env` 中保留或补充：

```text
LOCAL_REPO_CONTEXT_ENABLED=true
LOCAL_REPO_WORKSPACE_ROOT=/app/.local/review-workspaces
LOCAL_REPO_WORKSPACE_HOST_DIR=./review-workspaces
LOCAL_REPO_MAX_FETCH_SECONDS=120
LOCAL_REPO_MAX_SEARCH_SECONDS=30
# 规划中：用于本地仓库 workspace 自动清理，落地前可先通过运维脚本清理 worktrees。
# LOCAL_REPO_WORKTREE_RETENTION_HOURS=24
# LOCAL_REPO_MIRROR_RETENTION_DAYS=30
```

运行目录下的 `review-workspaces/` 会被挂载进 backend 容器，用来保留 mirror 缓存和 task worktree；升级镜像不会清空该目录。当前本地仓库检索主链路已支持 mirror / worktree 复用，自动清理策略规划为后续 V2-F-10 落地：优先清理过期 `worktrees/{taskId}`，`mirrors/{projectId}.git` 只按较长闲置周期清理。清理 worktree 不影响后续新 MR，清理 mirror 后同项目下一次审查会重新 clone，正确性不受影响但首次准备耗时会增加。

离线升级时，脚本还会自动清理旧版本应用镜像，默认只保留最近 `2` 个版本的：

- `ai-code-review-backend:{版本号}`
- `ai-code-review-frontend:{版本号}`

如果你想临时多保留几个回滚版本，可以在服务器上这样执行：

```bash
KEEP_IMAGE_VERSIONS=3 ./load-images.sh
```

如果旧镜像仍被旧容器占用，脚本会跳过删除，不会中断本次部署。

升级命令：

```bash
cd /opt/ai-code-review-platform/{新版本号}
./load-images.sh
cd ../runtime
docker compose up -d
```

如果升级后需要回滚到上一个仍保留的旧镜像，不需要重新上传代码包。先在运行目录确认当前版本和本机还保留的镜像：

```bash
cd /opt/ai-code-review-platform/runtime
grep '^APP_VERSION=' .env
docker images | grep ai-code-review
```

假设要回滚到旧版本 `{旧版本号}`，修改 `runtime/.env` 中的 `APP_VERSION`，再按旧镜像重建容器：

```bash
cd /opt/ai-code-review-platform/runtime
sed -i 's/^APP_VERSION=.*/APP_VERSION={旧版本号}/' .env
docker compose up -d --force-recreate
docker compose ps
docker compose logs -f backend
```

这相当于停止当前应用容器并用指定旧镜像重新创建，仍复用当前 `docker-compose.yml`、网络、卷、端口映射和 `.env` 配置。不要优先手写 `docker run`，否则容易漏掉前后端网络、MySQL 连接、Nginx 反向代理、restart policy 等 compose 配置。

注意：镜像回滚不会自动回滚数据库 schema。如果新版本已经执行了不兼容的数据库变更，旧镜像可能无法正常读取新表结构。当前迁移原则应尽量保持向前兼容，优先新增表 / 新增列，避免在可回滚版本内删除或重命名旧字段。

## 本地启动

创建数据库：

```sql
CREATE DATABASE ai_code_review DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

首次本地启动建议先准备 Python 虚拟环境：

```powershell
python -m venv backend-python\.venv
Push-Location backend-python
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Pop-Location
```

默认后端入口现在是 `.\scripts\run-backend.cmd`。常用命令：

```powershell
.\scripts\run-backend.cmd dev
.\scripts\run-backend.cmd test
.\scripts\run-backend.cmd lint
```

Python 健康检查：

```powershell
curl http://localhost:8090/api/health
curl http://localhost:8090/actuator/health
```

如果是空数据库，先执行一次 bootstrap migration：

```powershell
.\scripts\run-backend.cmd migrate
```

本地开发优先使用 `DATABASE_URL`；未设置时兼容 `MYSQL_URL`、`MYSQL_USERNAME`、`MYSQL_PASSWORD`：

```powershell
$env:DATABASE_URL="mysql+pymysql://root:root@localhost:3306/ai_code_review?charset=utf8mb4"
.\scripts\run-backend.cmd dev
```

Python 后端本地默认跑在 `8090`；如需临时改端口：

```powershell
.\scripts\run-backend.cmd dev --port 9090
```

### 主要 HTTP API

规则提醒与任务查询：

```text
POST /api/webhooks/gitlab/merge-request
POST /api/review-tasks/manual
POST /api/review-tasks/{taskId}/rerun
POST /api/review-tasks/{taskId}/rerun-in-place
GET  /api/review-tasks
GET  /api/review-tasks/{taskId}
GET  /api/review-tasks/{taskId}/result
GET  /api/review-tasks/{taskId}/notifications
GET  /api/review-tasks/{taskId}/diff-context
GET  /api/projects
GET  /api/project-groups
GET  /api/target-type-path-mappings
GET  /api/projects/{projectId}/target-configs
PUT  /api/projects/{projectId}/target-configs/{targetType}
GET  /api/rule-templates
GET  /api/rule-templates/{templateCode}
```

任务列表支持按 `reviewStatus`、`groupId`、`targetType`、`triggerType` 等筛选；列表项 `riskItemCount` 表示 AI Review finding 总数。完整字段见 `docs/03-api-contract.md`。

反馈池与项目策略：

说明：V2-F-8 起，反馈池和项目策略默认作为暗能力保留；生产前端默认不展示反馈池导航、任务详情提交反馈、生成策略和项目策略管理入口。需要在前端构建环境显式设置 `VITE_REVIEW_LEARNING_UI_ENABLED=true`，并按需设置 `VITE_PROJECT_REVIEW_POLICY_UI_ENABLED=true`，才会恢复对应入口；后端 API 和数据表仍保持兼容。

```text
POST /api/review-tasks/{taskId}/feedback
GET  /api/review-tasks/{taskId}/feedback
GET  /api/risk-feedback
PUT  /api/risk-feedback/{feedbackId}/status
POST /api/risk-feedback/{feedbackId}/convert-to-policy
GET  /api/projects/{projectId}/review-policies
PUT  /api/project-review-policies/{policyId}
PUT  /api/project-review-policies/{policyId}/enabled
```

代码质量 AI Review：

```text
POST /api/code-quality-reviews/manual
GET /api/code-quality-reviews/settings
PUT /api/code-quality-reviews/settings
POST /api/code-quality-reviews/tasks/{taskId}/retry
GET /api/code-quality-reviews/job-queue
GET /api/code-quality-review-profiles
GET /api/code-quality-review-profiles/{profileCode}
PUT /api/code-quality-review-profiles/{profileCode}
GET /api/code-quality-review-profiles/{profileCode}/rendered-prompt
POST /api/code-quality-review-profiles/{profileCode}/reset-default-prompt
GET /api/code-quality-review-providers
PUT /api/code-quality-review-providers/{providerCode}
POST /api/code-quality-review-providers/{providerCode}/test
POST /api/code-quality-review-providers/{providerCode}/set-default
GET /api/review-tasks/{taskId}/code-quality-result
GET /api/review-tasks/{taskId}/code-quality-progress
GET /api/review-tasks/{taskId}/code-quality-gate
GET /api/review-tasks/{taskId}/code-quality-fix-previews
POST /api/review-tasks/{taskId}/code-quality-fix-preview
GET  /api/review-tasks/{taskId}/code-quality-results
```

GitLab API 补拉默认关闭，需要配置 `GITLAB_API_ENABLED=true`、`GITLAB_BASE_URL`、`GITLAB_TOKEN`；全局钉钉开关关闭或未配置任何已启用 webhook 时，通知记录为 `SKIPPED`。

规则提醒闭环：

```text
mock MR webhook / GitLab MR webhook / GitLab Push webhook / manual review
  -> 变更分析 -> 提醒卡片 -> review_results 落库 -> notification_records
```

Python AI Review 默认关闭；可在设置页直接开启或关闭“代码质量 AI Review 全局能力”。`CODE_QUALITY_REVIEW_ENABLED` 只作为兼容初始化值使用，已有数据库以设置页保存的 `reviewEnabled` 为准。启用后支持 OpenAI Responses、Anthropic Messages、DeepSeek / XiaoMIMO / GLM / Custom OpenAI-compatible Chat Completions。Provider API Key 只返回 masked 形式，进度事件会做敏感字段脱敏。设置页 Provider 配置支持用当前表单里的端点、模型和临时 API Key 发起一次最小请求测试联通性，不会保存该临时 Key。自动化验证使用 respx mock 外部模型 API，真实模型凭据联调需要单独确认。

AI Review 当前保持稳定的非流式 HTTP Provider 调用。前端通过 `GET /api/review-tasks/{taskId}/code-quality-progress`、`GET /api/review-tasks/{taskId}/code-quality-result` 和 `GET /api/review-tasks/{taskId}/code-quality-results` 轮询展示执行过程与结果，不再建立 SSE / WebSocket 连接，也不启用模型 token streaming。项目组配置多个模型时，同一个任务会并行生成多条 Review 结果；任务详情页只在多结果时显示模型子 tab，单模型仍保持原展示。

AI Review 质量问题支持两个辅助查看入口：

- `查看 Diff`：基于任务详情中的 `changedFilesSummary.files[].diffText` 展示当前文件左右对照 diff，并按模型返回的 `startLine/endLine` 高亮定位。
- `生成修复预览`：AI Review 成功后，如果全局“自动修复预览”开关开启，会后台自动为所选风险等级且可匹配 diff 的 finding 生成 unified diff patch 预览并保存到 `code_quality_fix_previews`；默认只处理 `CRITICAL`（紧急），也可在设置页额外允许 `MAJOR`（高风险）或 `MINOR`（中风险）。未被自动选中的 finding 仍可在页面单条手动生成 / 失败后重试。Provider 调用统一进入 `code_quality_scheduler_jobs` 调度队列，默认全局最多 10 个并发，AI Review 优先于修复预览；修复预览先显示 `QUEUED`，真正占用 Provider 资源时才显示 `RUNNING`。该能力仅用于查看，不会修改仓库、不提交 GitLab MR。
- `调度队列`：任务列表页提供队列提示入口，调用 `GET /api/code-quality-reviews/job-queue` 查看当前 AI Review 与 finding 级修复预览的排队、运行和完成明细。活跃任务不受时间窗口限制，已完成 / 失败 / 跳过任务默认展示最近 24 小时内更新的记录。
- `失败通知`：右上角通知图标调用 `GET /api/code-quality-reviews/failure-notifications`，只展示最近 24 小时内 AI Review 执行失败记录，角标显示失败数。AI Review 执行失败会同步把任务状态标记为 `FAILED`，避免任务列表仍显示 `SUCCESS`。

Push webhook 默认只接收项目组 Push 审核策略中 `pushBranchPatterns` 允许的分支。Push 自动 AI Review 默认关闭，需要在 AI Review Profile 中开启 `triggerOnPush`，并通过项目组 Push 审核层后才会自动触发。

Push 审核层默认策略：

- `pushBranchPatterns`：`["master"]`
- `pushMinChangedFiles`：`10`
- `pushMinDiffBytes`：`30000`
- `pushMinCommitCount`：`3`
- `pushMaxChangedFiles`：`-1`，表示不限制最大文件数
- `pushMaxDiffBytes`：`-1`，表示不限制最大 Diff 字节数
- `pushDebounceSeconds`：`300`

允许分支匹配后，放行需要满足 Push 审核策略的六项指标：最小文件数、最小 Diff 字节数、最小 Commit 数、最大文件数、最大 Diff 字节数、Debounce。阈值配置为 `-1` 表示不限制；未放行的 Push 仍会完成规则提醒、通知记录和落库。

已补充非流式 Provider 诊断事件：`PROVIDER_SELECTED`、`REQUEST_VALIDATED`、`HTTP_REQUEST_START`、`HTTP_RESPONSE_HEADERS`、`HTTP_RESPONSE_BODY_PREVIEW`、`OUTPUT_EXTRACTED`、`JSON_PARSE_START`、`JSON_PARSE_FAILED`、`RESULT_SAVED`。这些阶段用于定位 API Key / endpoint / HTTP 状态 / 超时 / 协议响应 / JSON 解析问题；失败会落库为 `FAILED`，不会长期停留在 `RUNNING`。

AI Review 排障建议：

```text
最后 phase = HTTP_REQUEST_START：请求已发出但未收到响应，检查 endpoint、DNS、网关、模型响应耗时。
最后 phase = JSON_PARSE_FAILED：模型已返回完整文本，但不是平台要求的 Review JSON，检查 prompt、response_format 或模型 JSON mode 能力。
最后 phase = *_FAILED：查看 detail 中的 connect_timeout、read_timeout、provider_error、protocol_error 或 parse_error。
```

启动前端：

```powershell
.\scripts\run-frontend.cmd
```

前端脚本默认执行 `npm run dev`，首次运行会自动 `npm install`。脚本会读取 `.local/gitlab.env`，默认把 Vite `/api` 代理到 `http://localhost:8090`；如需临时改到其他后端，可设置 `VITE_API_PROXY_TARGET`。构建时使用 `.\scripts\run-frontend.cmd build`。

访问前端：

```text
http://localhost:5173
```

健康检查：

```powershell
curl http://localhost:8090/api/health
curl http://localhost:8090/actuator/health
```

## 数据库迁移

当前主后端使用 Python bootstrap migration。空库初始化时，后端启动会先执行 `python -m app.migrate`，按 `backend-python/migrations/bootstrap_sql/` 中的 SQL 版本顺序创建历史表结构和内置数据；已有核心表时会自动跳过 bootstrap。

当前 Python bootstrap SQL 包含：

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
V18__code_quality_model_providers.sql
V19__push_ai_review_gate.sql
V20__code_quality_review_global_switch.sql
V21__code_quality_fix_previews.sql
V22__code_quality_scheduler_jobs.sql
V23__consolidated_card_reminder_rules.sql
V24__multi_target_project_configs.sql
V25__project_group_push_review_policy.sql
V26__code_quality_auto_fix_preview_switch.sql
V27__project_group_profile_and_target_type_path_mappings.sql
V28__nullable_project_default_ai_review_profile.sql
V29__provider_timeout_seconds.sql
V30__project_group_ai_review_policy.sql
V31__multi_model_ai_review.sql
V32__review_task_review_status.sql
V33__glm_model_provider.sql
V34__review_item_feedbacks.sql
V35__project_review_policies.sql
V36__review_feedback_missing_context.sql
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
- `code_quality_fix_previews`
- `code_quality_scheduler_jobs`
- `review_item_feedbacks`
- `project_review_policies`
- `code_quality_push_review_gate_decisions`
- `project_groups`
- `project_target_configs`

## 本地演示

### 发送 mock MR webhook

```powershell
$payload = Get-Content -Raw -Path .\examples\gitlab-mr-webhook.mock.json

$webhookResponse = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/webhooks/gitlab/merge-request" `
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
  -Uri "http://localhost:8090/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Push Hook" } `
  -Body $payload
```

### 查询结果

```powershell
curl http://localhost:8090/api/review-tasks
curl http://localhost:8090/api/review-tasks/$taskId
curl http://localhost:8090/api/review-tasks/$taskId/result
curl http://localhost:8090/api/review-tasks/$taskId/code-quality-result
curl http://localhost:8090/api/review-tasks/$taskId/code-quality-progress
```

重新触发已有 GitLab MR / Push 审查任务，会基于数据库中保存的 raw payload 和 changed files 摘要创建一个新任务：

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8090/api/review-tasks/$taskId/rerun"
```

前端任务详情页包含：

- 代码质量 Review
- 提醒卡片：按提醒类型展示可复制维护内容、命中证据和 Diff 查看入口
- 分析结果
- 原始事件摘要

任务列表中的“状态”展示代码质量 AI Review 业务状态，不再直接展示底层规则流水线的
`review_tasks.status`。支持按多个状态筛选：未触发审查、审查中、无风险、中风险、高风险、
紧急、已跳过、审查失败、任务失败。多模型并行时，只要仍有模型运行就显示“审查中”；
至少一个模型成功后按成功 findings 的最高等级展示；只有全部模型失败时才显示“审查失败”。
底层任务执行状态仍保留在任务详情中，便于区分规则分析失败和 AI Review 失败。

## 真实 GitLab diff 验证

复制本地配置示例：

```powershell
New-Item -ItemType Directory -Force .local
Copy-Item examples/gitlab.env.example .local/gitlab.env
```

编辑 `.local/gitlab.env`，填入：

- `GITLAB_API_ENABLED=true`
- `GITLAB_BASE_URL`
- `GITLAB_TOKEN`
- `GITLAB_PROJECT_ID`
- `GITLAB_MR_IID`
- MySQL 连接信息（最简单保留 `MYSQL_USERNAME`、`MYSQL_PASSWORD`；如本地库不在默认 `localhost:3306/ai_code_review`，改用 `DATABASE_URL`）

启动 Python 后端：

```powershell
.\scripts\run-backend.cmd dev
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

按需读取 Diff 展开上下文：

```text
GET {GITLAB_BASE_URL}/api/v4/projects/{projectId}/repository/files/{filePath}/raw?ref={commitSha}
PRIVATE-TOKEN: {GITLAB_TOKEN}
```

平台只在用户点击展开入口后代理读取当前任务中的变更文件。可用本地接口验证：

```powershell
# 普通 Diff：修改文件返回 left / right；新增文件仅返回 right；删除文件仅返回 left。
Invoke-RestMethod "http://localhost:8090/api/review-tasks/{taskId}/diff-context?viewType=DIFF&filePath={urlEncodedFilePath}"

# AI 修复 Patch 调试接口：返回 head / after 源码作为 left 基线。
Invoke-RestMethod "http://localhost:8090/api/review-tasks/{taskId}/diff-context?viewType=FIX_PREVIEW&filePath={urlEncodedFilePath}"
```

前端任务详情中的“查看 Diff”和“AI 修复 Patch 预览”默认保持紧凑展示。“查看 Diff”具备源码能力时，
点击“展开上下文”后才拉取源码，并在隐藏区提供“向上展开 20 行”、“向下展开 20 行”和
“展开全部”。AI 修复 Patch 由模型生成，可能与当前源码基线不一致，因此只保留紧凑预览，
不展示上下文展开入口。两个弹窗默认使用明亮主题，顶部都提供太阳 / 月亮图标，可在明亮和暗黑代码主题之间切换。
旧 MR 缺少历史 base SHA 时隐藏普通 Diff 展开入口。
如果 GitLab MR 详情暂未返回 `diff_refs`，平台会回退读取最新 MR diff version 中保存的
`base_commit_sha / head_commit_sha`；原地重跑 MR 时也会刷新这组 refs 和 changed files 摘要。

## 审查模板

内置模板：

| 模板 | 适用场景 |
| --- | --- |
| `backend-default` | 后端服务 |
| `frontend-default` | 前端项目 |
| `general-default` | 通用项目 |

多端接入第一阶段已经引入项目组和端类型配置。当前产品默认按“单仓单端”使用：一个 GitLab 项目通常归属一个端类型；底层 `supported_target_types` 和 `project_target_configs` 仍保留多端扩展能力，混合仓库拆分审查属于后续阶段。当前主要可配置端类型：

```text
BACKEND / WEB_PC / APP_IOS / APP_ANDROID / GENERAL
```

历史跨端类型数据仍保持兼容，但前端下拉框、AI Review Profile 下拉框和全局端类型路径映射不再展示跨端应用。

后端项目默认仍使用 `backend-default` 和 `backend-default-ai-review`，并展示“提醒卡片”。PC / APP 端默认以代码质量 AI Review 为主，后端维护类提醒卡片默认关闭；如确实需要，也可以在项目端类型配置中开启 `reminderCardEnabled`。

项目组用于项目归类、任务列表筛选、默认 AI Review Profile、默认 Provider、钉钉机器人和 Push 审核策略控制。可以在前端“设置 -> 项目组 / 端类型配置”中新增项目组、编辑名称 / 编码 / AI Review 模板 / 默认 Provider、停用非默认项目组，并把已有项目绑定到指定项目组；在“设置 -> AI Review 设置 -> Push 审核策略”中按项目组维护允许分支、大小阈值、硬上限和 debounce。第一阶段项目组不代表权限边界；未绑定或 webhook 新进入的项目会自动归入“默认通用项目组”。默认项目组只是普通项目组的一种，不作为其它项目组的钉钉机器人兜底来源。

首次接入新的 GitLab 项目时，平台只使用“设置 -> 项目组 / 端类型配置 -> 端类型路径映射”中的全局路径规则匹配 changed files。系统会初始化一组可见、可编辑、可停用的默认路径映射：

```text
ios/**、**/*.swift、Podfile -> APP_IOS
android/**、**/*.kt、build.gradle、settings.gradle -> APP_ANDROID
frontend/**、web/**、src/**/*.tsx、src/**/*.jsx、package.json -> WEB_PC
src/main/java/**、src/main/resources/**、src/*.java、pom.xml、backend-python/** -> BACKEND
```

端类型路径规则按仓库根目录原样匹配，不会自动在规则前补 `**/`。例如 `src/main/java/**` 只匹配根目录下的后端源码，不会匹配 Android 项目里的 `app/src/main/java/**`；如确实需要任意层级匹配，请在设置页显式配置 `**/src/main/java/**`。

如果新项目只命中一个端类型，平台会自动创建该端类型配置，并默认使用 `**/*` 作为项目内路径匹配，适合“单端单仓库”。如果没有命中任何端类型，会设置为 `GENERAL`。`GENERAL` 不再兜底到后端 AI Review 模板，如果项目组也未设置 AI Review 模板，AI Review 会落为 `FAILED` 并提示“项目所属项目组未设置 AI Review 模板”。如果同一次变更命中多个端类型，平台会创建一条失败任务，提示调整全局端类型路径映射或项目端类型配置。已有项目的人工端类型配置不会被自动覆盖。

模板接口：

```powershell
curl http://localhost:8090/api/rule-templates
curl http://localhost:8090/api/rule-templates/backend-default
curl http://localhost:8090/api/project-groups
curl http://localhost:8090/api/target-type-path-mappings
curl "http://localhost:8090/api/projects?includeDisabled=true"
curl http://localhost:8090/api/projects/1/target-configs
```

项目模板与 AI Review Profile 通过端类型配置维护：

```powershell
Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8090/api/projects/1/target-configs/BACKEND" `
  -ContentType "application/json" `
  -Body '{"templateCode":"backend-default","codeQualityProfileCode":"backend-default-ai-review","pathPatterns":["**/*"],"reminderCardEnabled":true,"enabled":true}'
```

端类型配置示例（Web 端）：

```powershell
Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8090/api/projects/1/target-configs/WEB_PC" `
  -ContentType "application/json" `
  -Body '{"templateCode":"frontend-default","codeQualityProfileCode":"web-pc-default-ai-review","pathPatterns":["frontend/**","web/**"],"reminderCardEnabled":false,"enabled":true}'
```

钉钉推送会按模板 `focusChangeTypes` 过滤提醒来源。后端默认模板当前不再推送低信号 API 兼容性提醒。

## 手动规则审查

示例请求位于 `examples/manual-review-request.json` 和 `examples/manual-review-value-config-request.json`。

```powershell
$payload = Get-Content -Raw -Path .\examples\manual-review-request.json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/review-tasks/manual" `
  -ContentType "application/json" `
  -Body $payload
```

如果请求中的 `templateCode` 为空，会使用项目绑定的 `default_template_code`。

## 反馈池与项目策略

反馈池支持把人工确认过的反馈沉淀为项目策略。项目策略只影响同一个 `projectId` 的后续 AI Review，并会作为项目上下文注入 Prompt；它不会自动修改当前 Review 结果、不会自动忽略 finding，也不会自动降低风险等级。

注意：V2-F-8 后，这组能力默认不在生产前端展示；开启 `VITE_REVIEW_LEARNING_UI_ENABLED=true` 后才展示反馈入口，继续开启 `VITE_PROJECT_REVIEW_POLICY_UI_ENABLED=true` 后才展示“建议沉淀”、生成策略和项目策略管理入口。不开启这些前端开关时，可以继续通过下面的 API 做后台验证。

开启上述前端开关后的验证路径：

```text
任务详情 -> 对风险项或 AI finding 提交反馈
反馈池 -> 反馈记录 -> 将反馈标记为“有效”或筛选“建议沉淀”
反馈池 -> 点击“生成策略”
反馈池 -> 项目策略 -> 查看、编辑、启用或停用策略
设置 -> AI Review 设置 -> Prompt 预览，选择同项目后确认策略被注入
任务详情 -> AI Review 执行过程，查看 PROJECT_POLICIES_INJECTED 事件
```

生成策略按钮只有在反馈 `status=VALID` 或提交反馈时勾选了“建议沉淀”时可点击。`CONTEXT_MISSING`、`INSUFFICIENT`、`IGNORED`、`CONVERTED` 反馈不会生成项目策略；上下文不足反馈会进入反馈池统计和 Context Pack 规划。

当反馈原因选择“上下文不足”时，反馈弹窗会显示“缺失上下文”多选框，可记录同文件上下文、引用搜索、调用方、被调用方、表结构、配置、项目规则、测试结果等缺失类型。反馈池支持按“反馈原因”和“缺失上下文”筛选，并在列表上方展示上下文不足总数、风险类型分布和缺失上下文类型分布。该统计只作为后续 Context Pack 优先级输入，不会自动创建策略，也不会自动影响后续 Review。

命令行验证示例：

```powershell
# 1. 查看可沉淀候选反馈
Invoke-RestMethod "http://localhost:8090/api/risk-feedback?policyCandidate=true" |
  ConvertTo-Json -Depth 20

# 查看上下文不足反馈和统计
Invoke-RestMethod "http://localhost:8090/api/risk-feedback?reasonType=CONTEXT_MISSING" |
  ConvertTo-Json -Depth 20

# 按缺失上下文类型筛选
Invoke-RestMethod "http://localhost:8090/api/risk-feedback?reasonType=CONTEXT_MISSING&missingContextType=CALLER_CONTEXT" |
  ConvertTo-Json -Depth 20

# 2. 如反馈仍是 PENDING，先标记为有效
Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8090/api/risk-feedback/{feedbackId}/status" `
  -ContentType "application/json" `
  -Body '{"status":"VALID","adminComment":"确认可作为项目策略候选。"}'

# 3. 从反馈生成项目策略
$payload = Get-Content -Raw -Path .\examples\project-review-policy-convert-request.json
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/risk-feedback/{feedbackId}/convert-to-policy" `
  -ContentType "application/json" `
  -Body $payload

# 4. 查询项目策略
Invoke-RestMethod "http://localhost:8090/api/projects/{projectId}/review-policies" |
  ConvertTo-Json -Depth 20

# 5. 预览策略注入后的 Prompt
Invoke-RestMethod "http://localhost:8090/api/code-quality-review-profiles/backend-default-ai-review/rendered-prompt?projectId={projectId}" |
  ConvertTo-Json -Depth 20
```

## 代码质量 AI Review

代码质量 Review 默认关闭。兼容环境变量仍可作为初始化默认值：

```powershell
$env:CODE_QUALITY_REVIEW_ENABLED="true"
```

服务启动后，也可以在前端“设置 -> 全局设置”打开“代码质量 AI Review 全局能力”，无需重启后端。

Provider 说明：

- `OPENAI`：调用 OpenAI Responses API。
- `ANTHROPIC`：调用 Anthropic Messages API。
- `DEEPSEEK`：调用 DeepSeek OpenAI-compatible Chat Completions API，默认 base URL 为 `https://api.deepseek.com`。
- `XIAOMIMO`：调用 XiaoMIMO / Xiaomi MiMo OpenAI-compatible Chat Completions API，默认 base URL 为 `https://api.xiaomimimo.com/v1`，默认模型为 `mimo-v2.5-pro`。
- `GLM`：调用智谱 GLM OpenAI-compatible Chat Completions API，默认 base URL 为 `https://open.bigmodel.cn/api/paas/v4`，默认模型为 `glm-5.1`。
- `CUSTOM`：调用自定义 OpenAI-compatible Chat Completions API，需要配置端点 URL、模型名称和 API Key。

前端“设置”页可以：

- 控制代码质量 AI Review 全局能力；关闭后手动触发、MR 和 Push 自动流程都不会调用模型。
- 控制是否全局发送钉钉推送；关闭后审查和落库仍正常执行。
- 按项目组配置多个钉钉 webhook；开启钉钉推送后，只会向任务所属项目组内已启用 webhook 群发同一条通知。
- 配置 OpenAI / Anthropic / DeepSeek / XiaoMIMO / GLM / 自定义 Provider 的模型端点 URL、模型名称、API Key 和 Review 超时秒数，并测试当前配置联通性。
- 设置全局默认 Provider，以及项目组多个 AI Review 模型执行项；旧的项目级 / 端类型 Provider 覆盖仍作为单模型覆盖优先级保留。
- 按项目组绑定默认 AI Review Profile，通过全局端类型路径映射识别新项目端类型，并在项目端类型配置中维护 Provider 覆盖、提醒卡片展示和端类型启停策略。
- 查看、编辑、预览、恢复 AI Review Profile 的 Review Instructions。
- 按项目组配置 Push 审核策略，控制该项目组下的 Push 是否允许自动进入 AI Review。

手动触发代码质量 Review：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/code-quality-reviews/manual" `
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
curl http://localhost:8090/api/code-quality-reviews/settings
curl http://localhost:8090/api/code-quality-review-providers

Invoke-RestMethod `
  -Method Put `
  -Uri "http://localhost:8090/api/code-quality-reviews/settings" `
  -ContentType "application/json" `
  -Body '{"reviewEnabled": true, "dingtalkNotificationEnabled": false}'
```

AI Review 配置接口：

```powershell
curl http://localhost:8090/api/code-quality-review-profiles
curl http://localhost:8090/api/code-quality-review-profiles/backend-default-ai-review
curl http://localhost:8090/api/code-quality-review-profiles/backend-default-ai-review/rendered-prompt
curl "http://localhost:8090/api/code-quality-review-profiles/backend-default-ai-review/rendered-prompt?projectId=1"
```

重试某个任务：

```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8090/api/code-quality-reviews/tasks/{taskId}/retry"
```

## 前端页面

启动前端后访问 `http://localhost:5173`。

顶部导航：

- `任务`：任务列表、任务详情、提醒卡片、分析结果、AI Review 结果与执行过程、AI Review 调度队列入口。
- `反馈池`：默认隐藏；前端构建时启用 `VITE_REVIEW_LEARNING_UI_ENABLED=true` 后可查看风险项 / finding 反馈，继续启用 `VITE_PROJECT_REVIEW_POLICY_UI_ENABLED=true` 后可筛选建议沉淀反馈并管理项目策略。
- 右上角通知图标：查看最近 24 小时内 AI Review 执行失败记录，并可跳转任务详情。
- `设置`：全局设置、模型 Provider 配置、AI Review 设置、项目组 / 端类型配置、启用的卡片提醒类型；Push 审核策略在 AI Review 设置中按项目组维护。
- `版本更新`：查看近期功能变化、部署注意和验证提示。

任务详情页的“重新触发审阅”会从当前任务复制出一条新的审查任务，适合调试规则、钉钉模板和前端展示，不需要再次真实 push 或更新 MR。

详情页支持 `/tasks/{taskId}` 直达；历史 `?taskId={taskId}` 链接仍会自动跳转。多模型 AI Review 的钉钉摘要会追加 `?reviewKey={reviewKey}`，打开详情页时直接选中消息对应的模型 Review，例如：

```text
http://localhost:5173/tasks/47?reviewKey=deepseek-main
```

## 自动化验证

Python 后端：

```powershell
.\scripts\run-backend.cmd test
```

前端：

```powershell
.\scripts\run-frontend.cmd build
```
