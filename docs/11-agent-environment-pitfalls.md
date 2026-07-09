# Agent 环境与工具避坑

> 状态：当前有效。本文只记录非业务性质的本地环境、部署、脚本、Codex、检索和工具链踩坑。业务规则、接口语义、AI Review 行为和历史修复记录不要继续追加到本文；需要追溯时再看 `docs/10-local-dev-pitfalls.md` 历史归档。

## 使用原则

1. 新对话先读 `AGENTS.md`、`README.md` 和本文，再按任务读取相关设计文档。
2. 启动、测试、构建、迁移优先使用 `scripts/` 目录下脚本。
3. 搜索默认使用 `rg`，并遵守仓库 `.rgignore`，不要扫依赖、构建产物、虚拟环境和停止维护的 Java 后端。
4. 新增踩坑时，只有环境、工具、部署、Codex、检索类问题追加到本文；业务缺陷写入 `docs/24-bug-log.md` 或对应设计 / 路线文档。

## PowerShell 与编码

- 阅读中文 Markdown 时使用：

```powershell
Get-Content -Raw -Encoding UTF8 <path>
```

- 如果第一次读取出现乱码，立即用 `-Encoding UTF8` 重新读取，不要基于乱码内容总结或修改。
- 小范围源码和文档修改优先用 `apply_patch`。Windows PowerShell 5 的 `Set-Content -Encoding UTF8` 可能写入 BOM，Java / SQL 等文件可能因此出现 `\ufeff` 编译或解析错误。
- 需要批量写 UTF-8 无 BOM 时，显式使用 `.NET UTF8Encoding($false)`，并在结论中说明原因。

## 脚本入口

- 后端默认入口：

```powershell
.\scripts\run-backend.cmd dev
.\scripts\run-backend.cmd test
.\scripts\run-backend.cmd lint
.\scripts\run-backend.cmd migrate
```

- 排查脚本行为或直连 Python 后端时，再使用：

```powershell
.\scripts\run-backend-python.cmd
```

- 前端入口：

```powershell
.\scripts\run-frontend.cmd
.\scripts\run-frontend.cmd build
```

- Java 后端已经停止维护。只有明确需要对照历史行为时，才使用：

```powershell
.\scripts\run-backend-java.cmd
```

- Agent 执行 `.cmd` 验证脚本时，避免被失败后的 `pause` 阻塞；优先使用脚本已有的非交互参数或从 PowerShell 直接调用能返回退出码的入口。

## Python 环境

- Codex / Windows 沙箱中，PATH 上的 `python.exe` 可能是 WindowsApps 占位别名，或依赖沙箱不可用的登录会话，报错类似：

```text
A specified logon session does not exist.
```

- 日常启动和测试优先走 `.\scripts\run-backend.cmd`。
- 一次性 Python 命令优先使用仓库虚拟环境：

```powershell
backend-python\.venv\Scripts\python.exe
```

- 不要因为 PATH Python 启动失败就改项目依赖或重建虚拟环境；先确认 `.venv` 解释器是否可用。

## 验证范围

- 前端样式或交互改动：优先跑 `.\scripts\run-frontend.cmd build`。
- Python 后端局部逻辑改动：优先跑相关 pytest 文件或测试类。
- 改到 webhook -> 分析 -> 提醒卡片 -> 通知 -> 落库主链路、共享模型、数据库兼容或跨模块边界时，再跑全量：

```powershell
.\scripts\run-backend.cmd test
```

- 不要为了“保险”默认全量验证。先按影响范围选择最小可复现验证，再在需要时扩大。

## Codex 沙箱

- 普通沙箱内 `git push` 可能因为 Git Credential Manager 需要启动 Git Bash / 凭据提示而失败。若用户授权，可在沙箱外重跑 `git push`；仍失败时，只完成 commit，并把 push 命令和 commit hash 告知用户。
- `Start-Process` 在 Codex / PowerShell 环境里可能因 `Path` / `PATH` 环境键冲突失败。临时启动服务可改用 `.NET System.Diagnostics.ProcessStartInfo`，并设置 `UseShellExecute = $false`、`CreateNoWindow = $true`。
- 启动本地服务前先检查目标端口是否已被监听，避免误停用户已有进程；烟测结束只停止本次启动的进程。
- Codex 沙箱映射路径可能导致 Vite / Rolldown 误判 HTML 输出路径，报错中出现真实工作区和 `.codex/.sandbox/cwd/...` 混用时，先在用户批准后用真实工作区路径重跑同一 build。只有沙箱外仍失败，才排查前端源码或 Vite 配置。

## 搜索与 CodeGraph

- 已知接口路径、字段名、错误文案、日志内容或前端请求路径时，优先使用 `rg`。
- 从业务逻辑、异常现象或架构问题排查 Python 后端时，可先用 CodeGraph 获取候选地图，再用 `rg` 和局部源码核验。
- CodeGraph 是静态索引，不是唯一事实来源；动态调用、异步任务、框架 hook、前端语义召回都可能漏报或误报。
- 旧 Java 后端同名符号容易干扰检索。索引应聚焦 `backend-python/` 和 `frontend/`，修改忽略规则后需要强制重建：

```powershell
codegraph.cmd index --force
```

- Codex App 或 Cursor 看不到 CodeGraph MCP 工具时，优先检查 MCP 配置、索引状态和当前应用是否已重载。完整搜索策略见 `docs/25-codegraph-search-guide.md`。

## Docker 与部署

- Codex / Windows 沙箱中执行 `npm install` 可能因为 npm 默认 cache 位于用户目录而失败，例如：

```text
EPERM: operation not permitted, open 'C:\Users\<user>\AppData\Local\npm-cache\_cacache\tmp\...'
```

  这通常不是 `package.json` 或 lockfile 本身损坏，而是命令需要写入沙箱外 npm cache 或访问 registry。若本次任务确实需要新增依赖，应按权限规则请求用户授权后重跑同一条 `npm.cmd install ...`；不要手工改 lockfile 伪造安装结果。

- `scripts/package-docker-deploy.cmd` 依赖 Docker CLI 和 Docker Engine。执行前先启动 Docker Desktop，并确认：

```powershell
docker version
```

- Docker Engine 未启动、CLI 不在 PATH 或 Windows 终端未刷新 PATH 时，先修本机 Docker 环境，不要改项目打包脚本。
- Docker 前端镜像构建使用 `npm ci`，要求 `frontend/package.json` 和 `frontend/package-lock.json` 同步。不要使用 `latest` 或浮动顶层依赖；更新依赖后同步 lock。
- 如果本机 npm 与 Dockerfile 的 Node / npm 版本差异导致 lock 不一致，用与 Dockerfile 一致的 Node 镜像更新 lock。
- 离线部署升级时，`runtime/.env` 会保留。修改新包里的 `.env.example` 不会自动影响线上配置，需要同步修改运行目录的 `.env`。
- 离线升级会累积旧镜像和旧版本目录；清理前先确认当前 `APP_VERSION`、容器状态和回滚需求。

## 端口与外链

- 本地 Python 后端默认端口与前端代理必须同步，常用后端端口为 `8090`，前端开发端口为 `5173`。
- Docker 部署中：

```text
PUBLIC_HTTP_PORT = 用户浏览器和 GitLab webhook 访问的宿主机端口
PLATFORM_BASE_URL = 后端生成外链时使用的公开地址
BACKEND_PORT = 容器内后端监听端口，只在 Docker 网络内使用
```

- `PUBLIC_HTTP_PORT` 和 `PLATFORM_BASE_URL` 通常应指向同一个用户可访问地址；`BACKEND_PORT` 不应暴露给用户配置 webhook。

## 数据库与迁移

- Python 后端优先使用 `DATABASE_URL`：

```powershell
$env:DATABASE_URL="mysql+pymysql://root:root@localhost:3306/ai_code_review?charset=utf8mb4"
```

- 如果沿用旧 `MYSQL_URL`，不要把 JDBC 专属参数如 `serverTimezone`、`useSSL`、`allowPublicKeyRetrieval` 透传给 PyMySQL。
- `/api/health` 不访问数据库，不能仅凭 health 判断数据库链路可用；还应访问 `/api/review-tasks` 或 `/api/projects`。
- Python 后端以 `backend-python/migrations/bootstrap_sql/` 为 schema 基准，日常不要依赖 legacy Java Flyway 迁移。

## GitLab 本地仓库上下文

- `GITLAB_TOKEN` 能访问 REST API，不代表 Git HTTP clone / fetch 一定成功。部分 GitLab 实例需要 Basic Auth 语义，例如用户名 `oauth2`、密码为 token。
- Git 命令不要把 token 拼进 clone URL，避免日志、命令行和 progress 泄露凭据；应使用临时 Git env config 注入认证头，并保持 `GIT_TERMINAL_PROMPT=0`。
- `projects.repository_url` 必须归一化为运行环境可访问的 `GITLAB_BASE_URL` 地址。Webhook payload 中的容器内 hostname 可能导致 clone 失败。
- Windows 本地 worktree 会被仓库里的非法文件名阻断，例如路径包含 `?`。mirror fetch 可以成功，但 `git worktree add` checkout 会失败。此类仓库建议在 Linux / WSL / Linux Docker volume 上运行高准确模式，或先清理非法文件名。
- `LOCAL_REPO_PREPARED` 是历史 progress 状态，不代表当前 task worktree 仍存在。删除 `.local/review-workspaces` 后，需要重新触发 AI Review 才会重新准备 workspace。
- `review-workspaces` 为空不一定是清理任务导致。先检查 `LOCAL_REPO_CONTEXT_ENABLED`、GitLab token 权限、仓库 URL、commit / branch ref、Docker volume 映射和任务详情里的工作区诊断。

## 追加规则

- 环境、脚本、部署、Codex、检索、工具链的新坑追加到本文。
- 业务规则误判、接口语义、前端展示逻辑、AI Review 产品行为写入对应设计文档或 `docs/24-bug-log.md`。
- 如果一个问题同时包含业务和环境因素，只在本文记录可复用的环境判断方法，把业务结论放到业务文档。
