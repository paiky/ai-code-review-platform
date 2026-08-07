# 开发、部署与验证操作手册

> 本文承接原 README 中的本地环境、后端配置、启动、数据库迁移、Docker 部署和验证步骤。项目入口与最短启动方式见 `README.md`；环境和工具异常先在 `docs/11-agent-environment-pitfalls.md` 中按关键词检索。

## 一、环境要求

- Python 3.12+
- MySQL 8.0+
- Node.js 20+
- Windows 本地开发使用 PowerShell 和仓库 `scripts/` 脚本
- Docker 部署需要 Docker Engine 和 Docker Compose plugin

当前主后端是 `backend-python/`，前端是 `frontend/`。`backend/` Java 后端仅作历史参考，默认不启动、不测试。

## 二、本地配置

后端读取环境变量；仓库脚本还会自动加载 `.local/gitlab.env`。可从示例开始：

```powershell
New-Item -ItemType Directory -Force .local
Copy-Item examples/gitlab.env.example .local/gitlab.env
```

本地优先配置 SQLAlchemy 连接串：

```powershell
$env:DATABASE_URL="mysql+pymysql://root:root@localhost:3306/ai_code_review?charset=utf8mb4"
```

未设置 `DATABASE_URL` 时，后端兼容 `MYSQL_URL`、`MYSQL_USERNAME` 和 `MYSQL_PASSWORD`。

### 核心变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | 空 | SQLAlchemy MySQL 连接串，优先级最高 |
| `MYSQL_URL` | `jdbc:mysql://localhost:3306/ai_code_review?...` | 兼容 JDBC 连接配置 |
| `MYSQL_USERNAME` | `root` | MySQL 用户 |
| `MYSQL_PASSWORD` | `root` | MySQL 密码 |
| `SERVER_PORT` | `8090` | Python 后端监听端口 |
| `PLATFORM_BASE_URL` | `http://localhost:5173` | 钉钉详情链接等外部访问地址 |
| `GITLAB_API_ENABLED` | `false` | 是否通过 GitLab API 补拉 diff |
| `GITLAB_BASE_URL` | 空 | GitLab 可访问 base URL |
| `GITLAB_TOKEN` | 空 | 具备项目读取权限的 access token |
| `GITLAB_DIFF_PER_PAGE` | `100` | MR diff 分页大小 |
| `LOCAL_REPO_CONTEXT_ENABLED` | `false` | 是否启用本地仓库上下文 |
| `LOCAL_REPO_WORKSPACE_ROOT` | `.local/review-workspaces` | mirror / worktree 根目录 |
| `LOCAL_REPO_MAX_FETCH_SECONDS` | `120` | Git clone / fetch / worktree 超时 |
| `LOCAL_REPO_CLEANUP_ENABLED` | `true` | 是否执行 best-effort workspace 清理 |
| `LOCAL_REPO_WORKTREE_RETENTION_HOURS` | `24` | task worktree 保留时间 |
| `LOCAL_REPO_MIRROR_RETENTION_DAYS` | `30` | 项目 mirror 保留时间 |
| `CODE_QUALITY_REVIEW_ENABLED` | `false` | AI Review 首次初始化兼容值；以后以数据库设置为准 |
| `CODE_QUALITY_REVIEW_PROVIDER` | `DEEPSEEK` | 默认 Provider 初始化值 |
| `CODE_QUALITY_REVIEW_PROXY` | 空 | 普通 Review / Provider 测试 / 修复预览专用 HTTP 代理；不影响 GitLab、钉钉和数据库 |
| `OPENAI_API_KEY` | 空 | OpenAI 初始化 Key |
| `OPENAI_RESPONSES_URL` | `https://api.openai.com/v1/responses` | OpenAI Responses API |
| `OPENAI_CODE_REVIEW_MODEL` | `gpt-5.4` | OpenAI 模型 |
| `ANTHROPIC_API_KEY` | 空 | Anthropic 初始化 Key |
| `ANTHROPIC_MESSAGES_URL` | `https://api.anthropic.com/v1/messages` | Anthropic Messages API |
| `ANTHROPIC_CODE_REVIEW_MODEL` | `claude-sonnet-4-5` | Anthropic 模型 |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek 初始化 Key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek base URL |
| `DEEPSEEK_CODE_REVIEW_MODEL` | `deepseek-v4-pro` | DeepSeek 模型 |
| `XIAOMIMO_API_KEY` | 空 | XiaoMIMO 初始化 Key |
| `XIAOMIMO_BASE_URL` | `https://api.xiaomimimo.com/v1` | XiaoMIMO base URL |
| `XIAOMIMO_CODE_REVIEW_MODEL` | `mimo-v2.5-pro` | XiaoMIMO 模型 |
| `GLM_API_KEY` | 空 | GLM 初始化 Key |
| `GLM_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | GLM base URL |
| `GLM_CODE_REVIEW_MODEL` | `glm-5.1` | GLM 模型 |

Provider URL、模型、Key 和超时建议在前端“设置”页维护。真实 Key 不得提交到仓库、文档、测试快照或日志。

## 三、本地启动

### 1. 创建数据库

```sql
CREATE DATABASE ai_code_review
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

### 2. 准备 Python 环境

```powershell
python -m venv backend-python\.venv
Push-Location backend-python
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Pop-Location
```

### 3. 初始化数据库

```powershell
.\scripts\run-backend.cmd migrate
```

### 4. 启动后端

```powershell
.\scripts\run-backend.cmd dev
```

默认地址为 `http://localhost:8090`。临时修改端口：

```powershell
.\scripts\run-backend.cmd dev --port 9090
```

健康检查：

```powershell
curl http://localhost:8090/api/health
curl http://localhost:8090/actuator/health
```

### 5. 启动前端

```powershell
.\scripts\run-frontend.cmd
```

前端默认访问 `http://localhost:5173`，Vite `/api` 默认代理到 `http://localhost:8090`。需要连接其他后端时设置 `VITE_API_PROXY_TARGET`。首次运行脚本会安装依赖。

## 四、数据库迁移

应用当前运行环境的迁移入口：

```powershell
.\scripts\run-backend.cmd migrate
```

- Python 迁移实现位于 `backend-python/app/migrate.py`。
- 历史 bootstrap SQL 位于 `backend-python/migrations/bootstrap_sql/`。
- 空数据库会按版本顺序初始化历史表和内置数据，并在 `schema_migrations` 登记 version/checksum。
- 已存在核心表但尚无迁移账本的数据库不会重放历史 SQL；必须先通过 schema baseline 校验并显式登记 V1～V47。
- 已登记数据库只执行待应用版本；已执行文件的 checksum 变化、版本重复或历史 schema 不完整时拒绝继续。
- Docker backend 启动时会先运行 `python -m app.migrate`。
- 回滚应用镜像不会自动回滚 schema；迁移应优先新增表或列，避免在可回滚窗口删除、重命名旧字段。

迁移后至少检查健康接口和任务列表接口；涉及共享模型或数据库兼容时运行全量 Python 测试。

### 本地库与测试线库目标隔离

本地与测试线连接分别保存在 Git 已忽略的文件中：

```text
.local/database.local.env
.local/database.test.env
```

`database.local.env` 只供本地 Backend 和本地迁移使用；`database.test.env` 保留原测试线 JDBC/SQLAlchemy URL，
不得被本地 Backend 自动加载。可填写 `DATABASE_URL`，或填写 `MYSQL_URL + MYSQL_USERNAME + MYSQL_PASSWORD`；
`DATABASE_URL` 非空时优先。真实连接串和密码不得出现在命令参数、Git、文档或终端输出中。

执行 `run-backend.cmd dev`、`run-backend-python.cmd dev` 或其 `migrate` 动作时，启动脚本先读取通用的
`.local/gitlab.env`，再读取并校验 `database.local.env`，因此本地数据库变量固定覆盖通用文件或父进程中的同名变量。
`database.local.env` 存在时必须声明 `DATABASE_TARGET=LOCAL` 并提供完整连接信息；启动脚本不会读取
`database.test.env`。修改数据库目标后必须停止并重新启动 Backend，Uvicorn reload 不会重新执行 PowerShell 启动脚本。

双目标迁移工具：

```powershell
# 只解析目标、检查本地/测试线不是同一个 schema，并查看迁移状态
.\scripts\run-database-migration.cmd status local
.\scripts\run-database-migration.cmd status test

# 只展示计划，不执行 DDL/DML
.\scripts\run-database-migration.cmd dry-run local

# 历史库首次接入账本；只有 schema 满足 V1～V47 基线才能登记
.\scripts\run-database-migration.cmd baseline local

# 应用待执行版本并校验
.\scripts\run-database-migration.cmd apply local
.\scripts\run-database-migration.cmd verify local
```

测试线的 `baseline` 和 `apply` 额外要求显式确认参数，并且仍需遵守变更前备份和用户授权：

```powershell
.\scripts\run-database-migration.cmd baseline test -ConfirmTest
.\scripts\run-database-migration.cmd apply test -ConfirmTest
```

每次 schema 或登记数据变更使用同一迁移文件，顺序固定为“本地 dry-run/apply/verify → 测试与备份 → 测试线
dry-run/apply/verify → 比对 version/checksum”。这不是业务数据双向同步；任务、Worker、队列和运行状态不得自动在
两套数据库间复制。测试线到本地的一次性脱敏数据迁移属于 `docs/53` 阶段三 B，必须在用户配置变量并再次确认后执行。

历史库 baseline 前若缺少 V1～V47 的命名索引，使用 reconcile 工具先做只读计划：

```powershell
.\scripts\run-database-baseline-reconcile.cmd plan local
.\scripts\run-database-baseline-reconcile.cmd plan test
```

计划会输出表/索引名、唯一性、估算行数、数据/索引字节和唯一索引重复状态，不读取或输出业务行值。实际增加索引是
写操作，本地要求 `-ConfirmWrite`，测试线同时要求 `-ConfirmWrite -ConfirmTest`：

```powershell
.\scripts\run-database-baseline-reconcile.cmd apply local -ConfirmWrite
.\scripts\run-database-baseline-reconcile.cmd apply test -ConfirmWrite -ConfirmTest
```

索引 DDL 固定使用 `ALGORITHM=INPLACE, LOCK=NONE`；任一缺失唯一索引存在重复数据时整次 apply 在首条 DDL 前拒绝。
测试线仍必须另行确认备份和变更窗口。

测试线数据单向复制到空本地库：

```powershell
# 只读检查客户端、源库容量和本地表数量
.\scripts\run-database-data-copy.cmd plan

# 写入本地；读取测试线，不修改测试线
.\scripts\run-database-data-copy.cmd apply -ConfirmCopy -ConfirmSourceData
```

复制工具要求本地库表数量为 `0`，使用 `mysqldump --single-transaction` 流式传给本地 `mysql` 客户端，不生成持久化
dump 文件；连接凭据只写入执行期临时 client option 文件，命令参数和日志不包含密码，结束后立即删除。导入成功后在
本地事务中执行安全清理：

- 清空普通 Provider Key、Agent 双 Key、Webhook、Worker 注册和 Scheduler Job；
- 关闭 Agent Review、普通 AI Review、钉钉通知、项目组自动触发和自动修复预览；
- 清除通知目标/响应、Worker 心跳和配置测试状态；
- 把未完成 Agent Run 标记为本地迁移取消，保留已完成任务、Review 结果和进度用于复现；
- Review/source 历史会复制到本地，因此 apply 额外要求 `-ConfirmSourceData`，本地机器仍须满足源码数据授权。

当前推荐写入顺序是“流式复制到空本地库 → 本地索引 reconcile → 本地 baseline/verify → 切换本地 Backend 并验证 →
测试线备份与窗口确认 → 测试线索引 reconcile → 测试线 baseline/verify”。任何一步失败都停止，不自动推进下一目标。

## 五、Docker 部署

### 1. 部署结构

`deploy/docker-compose.yml` 的默认拓扑：

```text
宿主机 :${PUBLIC_HTTP_PORT}
  -> frontend Nginx :80
  -> React 静态页面
  -> /api 反向代理到 backend:${BACKEND_PORT}
backend Python FastAPI，仅在 Docker 网络内访问
外部 MySQL；可通过 local-mysql profile 启动内置 MySQL
```

### 2. 首次部署

```bash
git clone <repo-url> ai-code-review-platform
cd ai-code-review-platform/deploy
cp .env.example .env
```

至少配置：

```text
PUBLIC_HTTP_PORT=8090
PLATFORM_BASE_URL=http://你的域名或服务器IP:8090
DATABASE_URL=mysql+pymysql://ai_review:强密码@数据库地址:3306/ai_code_review?charset=utf8mb4
```

`PUBLIC_HTTP_PORT` 是浏览器和 GitLab webhook 的对外端口；`PLATFORM_BASE_URL` 用于生成钉钉详情链接等外链。二者通常应指向同一用户可访问地址。`BACKEND_PORT` 仅为容器内部端口。

按需配置：

```text
GITLAB_API_ENABLED=true
GITLAB_BASE_URL=https://你的GitLab地址
GITLAB_TOKEN=具备read_repository权限的token
LOCAL_REPO_CONTEXT_ENABLED=true
LOCAL_REPO_WORKSPACE_ROOT=/app/.local/review-workspaces
LOCAL_REPO_WORKSPACE_HOST_DIR=./review-workspaces
LOCAL_REPO_WORKTREE_RETENTION_HOURS=72
LOCAL_REPO_MIRROR_RETENTION_DAYS=180
CODE_QUALITY_REVIEW_ENABLED=true
```

模型 Key 可通过部署环境完成首次初始化，之后推荐在设置页维护。钉钉 webhook 不通过 `.env` 默认配置，应在设置页按项目组添加。

启用内置 MySQL：

```text
COMPOSE_PROFILES=local-mysql
MYSQL_ROOT_PASSWORD=强密码
MYSQL_DATABASE=ai_code_review
MYSQL_USERNAME=ai_review
MYSQL_PASSWORD=强密码
DATABASE_URL=mysql+pymysql://ai_review:强密码@mysql:3306/ai_code_review?charset=utf8mb4
```

启动和检查：

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
curl http://127.0.0.1:8090/actuator/health
curl http://127.0.0.1:8090/api/health
```

GitLab webhook 地址：

```text
http://你的域名或服务器IP:${PUBLIC_HTTP_PORT}/api/webhooks/gitlab/merge-request
```

HTTPS 应在宿主机 Nginx、Caddy 或负载均衡终止 TLS，再转发到 `PUBLIC_HTTP_PORT`。

### 3. 本地仓库上下文

启用后，宿主机 `LOCAL_REPO_WORKSPACE_HOST_DIR` 挂载到 backend 容器中的 `LOCAL_REPO_WORKSPACE_ROOT`，持久化项目 mirror 和 task worktree。生产建议 worktree 至少保留 72 小时、mirror 至少保留 180 天。

GitLab token 需要 `read_repository` 权限。若出现 `LOCAL_REPO_PREPARE_FAILED` 且 `failurePhase=CLONE`，检查：

- `GITLAB_BASE_URL` 是否从容器和宿主机可访问。
- 项目 `repositoryUrl` 是否仍使用 webhook payload 中的内网 hostname。
- 企业自签名 CA 是否已加入镜像信任链。
- volume 映射和目录权限是否正确。

不要通过关闭 SSL 校验绕过证书问题。更完整的环境排障见 `docs/11-agent-environment-pitfalls.md`。

### 4. 升级

```bash
git pull
cd deploy
docker compose up -d --build
```

升级后检查 backend 日志、健康接口、前端页面和一个最小 webhook 样本。

## 六、本地打包并上传服务器

本机需要先启动 Docker Desktop，并确认 Linux Engine 可用：

```powershell
.\scripts\package-docker-deploy.cmd
```

如需同时打包内置 MySQL 镜像：

```powershell
.\scripts\package-docker-deploy.cmd -IncludeMysqlImage
```

镜像构建命令默认直接连接当前终端，保留 Docker BuildKit 的蓝色动态进度。脚本会把输出同步记录到
`.local/docker-deploy/logs/`，失败时窗口暂停并给出日志路径。Docker Hub 鉴权、基础镜像元数据、DNS、
TLS 或连接重置失败不会自动重试，请根据日志确认是临时网络问题后手动重新执行。

若本次只修改 Agent Worker，可复用一个已经完整打包成功、且仍存在于本机 Docker 中的旧版本镜像，
只重新构建 Worker：

```powershell
.\scripts\package-docker-deploy.cmd `
  -AgentWorkerOnly `
  -ReuseVersion 20260728183000
```

`-ReuseVersion` 必须显式指定且不能等于新版本。脚本会校验旧版 Backend、Frontend 和 Agent 出站代理
镜像均存在，将它们重新标记为本次新版本，再和新 Worker 一起生成结构不变的完整离线包；缺少任一旧镜像
立即失败，不会静默改用其它版本。该模式不能用于同时包含 Backend、Frontend、Compose 或出站代理改动的发布。

产物目录：

```text
.local/docker-deploy/{版本号}/
  ai-code-review-backend-{版本号}.tar
  ai-code-review-frontend-{版本号}.tar
  ai-code-review-agent-worker-{版本号}.tar
  ai-code-review-agent-egress-{版本号}.tar
  docker-compose.yml
  .env.example
  load-images.sh
  deploy-stage3.sh
```

上传并加载：

```bash
scp -r .local/docker-deploy/{版本号} user@server:/opt/ai-code-review-platform/
cd /opt/ai-code-review-platform/{版本号}
chmod +x load-images.sh
./load-images.sh
cd ../runtime
./deploy-stage3.sh upgrade --workers 2
```

`load-images.sh` 是每次离线部署和升级的必执行步骤：它会加载 backend、frontend、Agent Worker 和 Agent 出站代理镜像，并自动将当前版本的 `docker-compose.yml` 复制到 `runtime`，不需要手工替换。脚本只在首次部署创建 `runtime/.env`，升级时只更新 `APP_VERSION`，不覆盖已有连接和密钥。默认保留最近两个应用镜像版本；可用 `KEEP_IMAGE_VERSIONS=3 ./load-images.sh` 临时增加保留数。

`deploy-stage3.sh upgrade` 会先更新 Backend，再通过现有 Agent Settings GET/PUT 等待零队列并自动短暂暂停
Agent，随后更新指定数量的 Worker、等待容量恢复、更新 Frontend，最后仅在健康检查通过后恢复原启用状态。
完整升级成功后，脚本会清理当前 Compose 项目中处于 `created / exited / dead` 状态的旧容器，其中包括
同项目已经停止的 orphan。清理通过运行中 Backend 的 Compose project 标签限定范围，逐个使用
非强制删除；不会删除运行中容器、其它 Compose 项目、镜像、网络、Volume 或数据库数据。部署失败时不执行
清理，以保留故障现场；清理自身失败只输出告警，不改变已经通过的部署结果。

脚本不会读取或打印 Agent Key；失败时若已暂停 Agent，会保持禁用并要求人工检查。常用命令：

```bash
./deploy-stage3.sh status
./deploy-stage3.sh preflight
./deploy-stage3.sh upgrade --workers 2 --dry-run
./deploy-stage3.sh scale --workers 3
```

首次从不支持 DRAINING 的旧 Worker 升级时必须使用默认安全模式，不要绕过队列闸门。`scale` 只执行用户
明确指定的人工 Compose 副本变更，不会根据指标自动扩缩容；容量收敛后同样清理当前项目的已停止旧容器。
如果历史容器来自其它目录或其它 `COMPOSE_PROJECT_NAME`，脚本会按安全边界保留，需先核对标签后人工处理，
不要使用无项目过滤的 `docker system prune`。

回滚时修改 `runtime/.env` 中的 `APP_VERSION`，再执行：

```bash
docker compose up -d --force-recreate
docker compose ps
docker compose logs -f backend
```

镜像回滚不会回滚数据库 schema。

## 七、服务器侧只读 Agent Review

完整设计、安全边界、当前停止点和生产验收见 `docs/41-server-side-readonly-agent-review-plan.md`。部署至少需要：

```text
AGENT_REVIEW_CONFIG_ENCRYPTION_KEY=Fernet URL-safe base64 key
AGENT_REVIEW_WORKER_TOKEN=后端与Worker共用的高强度随机Token
AGENT_REVIEW_BACKEND_URL=http://backend:8090
AGENT_REVIEW_WORKER_ID=agent-worker-1
```

自定义 OpenAI Responses Agent 的目标地址以设置页保存的 Base URL 为准，不再需要额外环境白名单。Backend 仍只接受
HTTPS 默认 443 的 DNS hostname，拒绝 IP、通配符、userinfo、query、fragment 和自定义端口；Worker 代理仅允许
CONNECT 443 和本地 Backend 8090，不开放其它端口或普通 HTTP 外联。默认 `Claude Code + DeepSeek` 行为不变。

生成密钥：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Windows 本地开发可直接初始化这两个基础密钥（不会生成或读取 DeepSeek API Key）：

```powershell
.\scripts\init-agent-review-secrets.cmd
```

命令将缺失或空白的 `AGENT_REVIEW_CONFIG_ENCRYPTION_KEY`、`AGENT_REVIEW_WORKER_TOKEN` 写入 `.local/gitlab.env`，已有非空值保持不变，且不会把生成值打印到终端。随后必须停止并重新执行 `.\scripts\run-backend.cmd dev`；仅刷新前端不会让已运行的后端进程重新加载环境变量。设置页不再显示“禁止保存 Agent Key”后，才可输入并保存独立 DeepSeek Key。

### Windows + Docker Desktop 启动 Worker

本地后端和前端仍使用仓库脚本启动。`run-backend.cmd dev` 会在后台等待后端健康并自动确保 Windows 专用 Agent Worker/代理运行，不启动容器 backend，也不要求手工维护 volume 路径。因此日常只需两个终端：

```powershell
.\scripts\run-backend.cmd dev
.\scripts\run-frontend.cmd dev
```

自动启动日志写入 `.local/agent-worker-startup-*.out.log` 和 `.local/agent-worker-startup-*.err.log`。如需关闭自动启动，在 `.local/gitlab.env` 设置 `AGENT_REVIEW_AUTO_START_WORKER=false`。手动管理命令仍保留：

```powershell
.\scripts\run-agent-worker.cmd status
.\scripts\run-agent-worker.cmd logs
.\scripts\run-agent-worker.cmd stop
```

Windows 专用代理只允许 Worker 访问 `host.docker.internal:8090` 和 HTTPS `443`；实际模型目标由当前任务中固化的
设置页 Base URL 决定，Worker 自身仍只加入 internal 网络。若后端使用非 `8090` 端口，当前代理不会放行，应先统一回
默认端口，而不是扩大代理端口范围。

需要通过局域网 HTTP 代理访问 DeepSeek 时，在本机 `.local/gitlab.env` 设置：

```text
AGENT_REVIEW_UPSTREAM_PROXY=http://192.168.100.133:7897
CODE_QUALITY_REVIEW_PROXY=http://192.168.100.133:7897
```

重新执行 `.\scripts\run-agent-worker.cmd start` 后，Windows 启动脚本会生成本机专用 Squid 配置。`AGENT_REVIEW_UPSTREAM_PROXY` 供 Agent Worker 使用，`CODE_QUALITY_REVIEW_PROXY` 供 Python backend 的普通 Provider 请求使用；本地未显式配置后者时会兼容复用前者。上游代理只承接模型请求，Linux 生产不会自动继承该本机设置。

自定义 Responses Agent 的安全启用顺序：

1. 在设置页确认至少一个在线 Worker 上报 `OPENAI_RESPONSES_CUSTOM`；
2. 保存符合安全 URL 约束的自定义 Base URL、模型和 Key，先保持 Agent Review 关闭；
3. 确认“URL 安全校验通过 / 配置完整”后再启用并执行 synthetic 配置测试。

修改页面 Base URL 不需要重启 Backend、代理或 Worker。配置测试只发送平台生成的 synthetic 文件，不读取生产任务、
仓库或历史 diff。Base URL、模型和运行时会固化到新任务快照，Key 按凭据槽位在 Worker Claim 时瞬时解密，因此后续
修改设置不会改变已排队任务的地址和模型，Key 轮换则立即作用于同一槽位。

Agent Job 领取兼容现有 MySQL 5.7 数据库：后端会使用普通 `FOR UPDATE` 串行领取；MySQL 8.0+ 自动使用 `FOR UPDATE SKIP LOCKED`，多 Worker 并发更好。新建和生产数据库仍按环境要求使用 MySQL 8.0+，无需为 Windows 本地兼容模式修改 Compose。

### Linux 生产启动 Worker

生产 runtime 继续使用完整 Compose，无需叠加 Windows 配置。确认 `runtime/.env` 已配置加密主密钥、Worker Token 和 workspace 宿主机目录后执行：

```bash
cd /opt/ai-code-review-platform/runtime
mkdir -p review-workspaces
docker compose up -d
docker compose ps
docker compose logs --tail=100 agent-worker
```

默认目录映射：宿主机 `runtime/review-workspaces`，backend 容器 `/app/.local/review-workspaces`，Worker 容器 `/workspaces:ro`。`docker compose ps` 中 Worker 健康且设置页显示 `Worker ONLINE` 后，才执行真实配置测试。

Windows 自动启动配置不会进入远程 runtime，也不会改变原离线部署步骤。`scripts/package-docker-deploy.cmd` 仍会打包 backend、frontend、Agent Worker、出站代理和 Linux `docker-compose.runtime.yml`；服务器仍按“加载镜像 -> 维护 runtime/.env -> docker compose up -d”部署。

安全约束：

- Worker 不持有数据库或 GitLab 凭据，只读挂载 review workspace。
- Agent 仅使用仓库提供的只读 MCP 工具，不开放 Bash、文件编辑、Web 或子 Agent。
- 项目组必须选择 `AGENT` 并确认源码外发授权，自动任务才进入 Agent 队列。
- Worker 使用受限出站网络，只允许访问已批准模型端点。
- 脱敏导出不包含源码、完整 diff、Key、Prompt、模型思维过程或 MCP 源码。
- 样本不足门禁、STANDARD 对照、fallback 和生产扩大条件以 `docs/41` 为准。

无真实 Provider Key 时，可使用阶段 3A 合成观察接口验证：

```powershell
Invoke-RestMethod "http://localhost:8090/api/review-quality/agent-observation?syntheticDemo=true" |
  ConvertTo-Json -Depth 20
```

## 八、Mock webhook 与任务验证

### MR webhook

```powershell
$payload = Get-Content -Raw -Path .\examples\gitlab-mr-webhook.mock.json
$response = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Merge Request Hook" } `
  -Body $payload
$taskId = $response.data.taskId
$response | ConvertTo-Json -Depth 20
```

### Push webhook

```powershell
$payload = Get-Content -Raw -Path .\examples\gitlab-push-webhook.mock.json
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/webhooks/gitlab/merge-request" `
  -ContentType "application/json" `
  -Headers @{ "X-Gitlab-Event" = "Push Hook" } `
  -Body $payload
```

### 查询和重跑

```powershell
curl http://localhost:8090/api/review-tasks
curl http://localhost:8090/api/review-tasks/$taskId
curl http://localhost:8090/api/review-tasks/$taskId/result
curl http://localhost:8090/api/review-tasks/$taskId/code-quality-result
curl http://localhost:8090/api/review-tasks/$taskId/code-quality-progress
Invoke-RestMethod -Method Post -Uri "http://localhost:8090/api/review-tasks/$taskId/rerun"
```

手动规则审查和 AI Review 请求结构见 `examples/` 与 `docs/03-api-contract.md`。

## 九、真实 GitLab diff 验证

在 `.local/gitlab.env` 配置：

```text
GITLAB_API_ENABLED=true
GITLAB_BASE_URL=https://你的GitLab地址
GITLAB_TOKEN=具备项目读取权限的token
GITLAB_PROJECT_ID=项目ID
GITLAB_MR_IID=MR IID
```

启动后端并发送真实 MR webhook。后端使用：

```text
GET /api/v4/projects/{projectId}/merge_requests/{mrIid}/diffs?page=1&per_page=100
GET /api/v4/projects/{projectId}/merge_requests/{mrIid}/changes
GET /api/v4/projects/{projectId}/repository/compare?from={beforeSha}&to={afterSha}
GET /api/v4/projects/{projectId}/repository/files/{filePath}/raw?ref={commitSha}
```

`/changes` 是 MR diff fallback。源码 raw 接口只在用户请求展开当前任务变更文件时使用。普通 diff 上下文可验证：

```powershell
Invoke-RestMethod "http://localhost:8090/api/review-tasks/{taskId}/diff-context?viewType=DIFF&filePath={urlEncodedFilePath}"
```

## 十、确定性检查验证

查询和手动运行 `SECRET_SCAN`：

```powershell
Invoke-RestMethod "http://localhost:8090/api/review-tasks/{taskId}/deterministic-checks" |
  ConvertTo-Json -Depth 20

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8090/api/review-tasks/{taskId}/deterministic-checks/run" `
  -ContentType "application/json" `
  -Body '{"checkType":"SECRET_SCAN"}' |
  ConvertTo-Json -Depth 20
```

MR、Push、manual 和 retry 会在 Provider 调用前运行一次自动 Preflight。同一次多模型调度应复用同一个 `AUTO_PREFLIGHT` run；失败默认 fail-open，并在 progress 和 Context Pack 中记录脱敏摘要。详细设计和阶段记录见 `docs/40-review-evidence-pipeline-and-multi-target-roadmap.md`。

## 十一、自动化验证

按影响范围选择最小测试集。

Python 后端全量测试：

```powershell
.\scripts\run-backend.cmd test
```

Python lint：

```powershell
.\scripts\run-backend.cmd lint
```

前端生产构建：

```powershell
.\scripts\run-frontend.cmd build
```

局部后端改动优先运行相关 pytest 文件；只有修改 webhook 主链路、共享模型、通知、数据库兼容或跨模块契约时才跑全量。前端样式和交互改动优先只跑 production build。

## 十二、相关文档

- 接入手册：`docs/18-project-integration-user-guide.md`
- GitLab / 钉钉 / 项目组接入：`docs/23-help-gitlab-dingtalk-project-onboarding.md`
- HTTP API：`docs/03-api-contract.md`
- Review 生命周期与前端入口：`docs/38-review-lifecycle-and-frontend-entrypoints.md`
- 当前路线和阶段记录：`docs/36-review-platform-current-roadmap.md`
- Review 证据链和多端专项：`docs/40-review-evidence-pipeline-and-multi-target-roadmap.md`
- 服务器侧只读 Agent Review：`docs/41-server-side-readonly-agent-review-plan.md`
- 环境与工具避坑：`docs/11-agent-environment-pitfalls.md`
