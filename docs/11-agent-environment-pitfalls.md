# Agent 环境与工具避坑

> 状态：当前有效。本文只记录非业务性质的本地环境、部署、脚本、Codex、检索和工具链踩坑。业务规则、接口语义、AI Review 行为和历史修复记录不要继续追加到本文；需要追溯时再看 `docs/10-local-dev-pitfalls.md` 历史归档。

## 使用原则

1. 新对话默认只读 `AGENTS.md`；遇到环境、脚本、部署、Codex、检索或工具链问题时，先用 `rg` 在本文搜索症状或关键词，只读取命中章节。启动、配置、部署和验证步骤按需检索 `docs/42-development-deployment-and-validation-guide.md`。
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

- `run-backend.cmd lint` 当前固定扫描整个 Python 后端，不会把后续路径参数透传给 Ruff。若本次只需检查新增文件，且全量 lint 被既有无关问题阻塞，可改用同一虚拟环境执行聚焦检查，并在结论中同时说明全量 lint 的阻塞项：

```powershell
.\backend-python\.venv\Scripts\ruff.exe check <本次文件或目录>
```

- Windows 上并行执行 pytest 与 Ruff 时，Ruff 可能因 `.ruff_cache/.../.tmp*` 被占用而报 `Failed to create temporary file / Access is denied`。先不要改源码或删除整个缓存；改为串行执行聚焦检查，并加 `--no-cache` 避免缓存竞争：

```powershell
.\backend-python\.venv\Scripts\ruff.exe check --no-cache <本次文件或目录>
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
- Windows/Codex 环境若 pytest 在用户临时目录 `pytest-of-*` 或仓库 `.pytest_cache` 报 `PermissionError [WinError 5]`，可为本次验证使用工作区内唯一 `--basetemp=../.local/pytest-<唯一值>`，并加 `-p no:cacheprovider`。这属于临时目录 ACL，不要因此修改业务测试或降低断言。

## Codex 沙箱

- 普通沙箱内 `git push` 可能因为 Git Credential Manager 需要启动 Git Bash / 凭据提示而失败。若用户授权，可在沙箱外重跑 `git push`；仍失败时，只完成 commit，并把 push 命令和 commit hash 告知用户。
- `Start-Process` 在 Codex / PowerShell 环境里可能因 `Path` / `PATH` 环境键冲突失败。
  `.NET System.Diagnostics.ProcessStartInfo` 配合 `UseShellExecute = $false`、`CreateNoWindow = $true`
  可以绕过部分启动或窗口问题，但不能据此认定长驻服务已经脱离 Codex 的进程树、Job Object 或继承句柄。
- 启动本地服务前先检查目标端口是否已被监听，避免误停用户已有进程；烟测结束只停止本次启动的进程。
- Codex 沙箱映射路径可能导致 Vite / Rolldown 误判 HTML 输出路径，报错中出现真实工作区和 `.codex/.sandbox/cwd/...` 混用时，先在用户批准后用真实工作区路径重跑同一 build。只有沙箱外仍失败，才排查前端源码或 Vite 配置。

### 长驻 dev / mock 服务被误当作一次性命令

症状：

- 运行 Vite dev server、HTTP mock server、uvicorn、watcher 或 Worker 启动命令后，工具长期显示 Running，
  Agent 一直等待命令完成，无法进入端口检查或浏览器验收。
- 日志可能已经出现 ready，页面也可能可以访问，但启动工具仍不返回。

原因：

- 一次性命令以“进程退出并返回 exit code”为完成条件；dev server 和 mock server 依靠事件循环持续监听端口，
  正常运行时本来就不会退出。
- 直接调用 `scripts/run-frontend.cmd` 的 dev 模式或 `node mock-server.mjs` 会把服务作为前台子进程附着在
  当前 shell。仅做日志重定向并不会自动分离进程，shell / Codex 工具仍会等待子进程退出。
- 如果看到工具仍为 Running 就再次执行启动命令，可能产生端口冲突或多个服务实例；如果直接按进程名结束，
  又可能误伤用户原有服务。

正确处理：

1. 启动前先检查目标端口和 HTTP endpoint；已经 ready 时直接复用。
2. 未 ready 时用后台 / 分离方式启动，记录 PID，并把 stdout / stderr 写入工作区临时日志。
3. 使用有界循环分别核对进程、端口和 HTTP 响应；三者形成 ready 证据后立即进入下一步，不等待服务退出。
4. 若误以前台方式启动，先终止当前工具的等待，再重新检查端口与 HTTP。服务已经 ready 时不要重启；
   没有 ready 才按后台方式重启。
5. 浏览器验收前优先确认前端和依赖的 mock / Backend 都已 ready。验收结束只停止本次记录的 PID，或明确
   保留服务供用户继续人工检查。

这类命令的状态模型应固定理解为：

```text
一次性命令：STARTING -> EXITED(success/failure)
长驻服务：STARTING -> READY -> SERVING -> STOPPED
```

长驻服务进入 `READY / SERVING` 就可以继续 Agent 流程；`STOPPED` 不是启动步骤需要等待的成功状态。

### docs/50 acceptance launcher ready 后仍显示 Running

问题记录：

- docs/50 阶段二验收需要自动启动 Vite 和本地安全 mock。实际运行中，frontend 与 mock 已取得 PID，
  目标端口已经监听，mock 直连 health 与 Vite 代理 health 均返回 `docs50-safe-mock`，但调用
  `run-docs50-acceptance.cmd` 的 Codex tool 仍长时间显示 Running。
- 直接前台运行 Vite 或 mock 不退出属于长驻服务的正常行为。异常点不在服务没有 ready，而在启动器的
  command lifecycle 没有与 service lifecycle 可靠分离。
- 本次先后尝试过 `Start-Process`、`.NET ProcessStartInfo`、隐藏窗口、stdout / stderr 文件重定向，
  以及 Node `child_process.spawn()` 的 `detached + unref`。最小 Node helper 可以快速返回，但完整
  launcher 在 Codex 执行链中仍可能不返回。

根因边界：

- `unref()` 只把子进程从 Node 父进程的事件循环引用计数中移除；`windowsHide` 和 `CreateNoWindow`
  只控制窗口；日志重定向只解决标准流管道。这些机制都不保证进程逃离外部宿主的 Job Object 或后代进程跟踪。
- Windows 中，进程处于 Job Object 时，其通过普通 `CreateProcess` 创建的后代默认仍进入同一 Job。
  即使中间的 `cmd`、PowerShell 或 Node helper 已经退出，Codex 执行器仍可能因为后代进程或继承句柄而
  继续把整次 tool 调用视为 Running。
- 当前证据不能确认 Codex 内部具体使用的是 Job Object、句柄 EOF 等待还是额外的后代进程跟踪，因此
  “Job Object”属于符合 Windows 行为的高可信解释，而不是已经通过宿主源码或句柄审计证明的唯一原因。
- 原有最小测试在 helper 返回后、测试进程退出前主动终止了子进程。它只证明 helper 可以返回，没有证明
  “最外层 Codex command 已退出，同时长驻服务继续存活”，因此不能作为完整 launcher 验收。
- 多加一层 `cmd -> PowerShell -> Node -> PowerShell -> npm`、重复调用 `Start-Process` 或继续调整
  `unref`，都不能消除外部宿主仍持有整棵进程树的可能性。

固定状态模型：

```text
service lifecycle: STARTING -> READY -> SERVING -> STOPPED
command lifecycle: STARTED -> RETURNED(success/failure)
```

- `READY` 不代表 command 已返回；command 返回也不代表服务 ready。
- 自动启动器需要两个独立断言：最外层命令在有界时间内返回 exit code 0；命令返回后服务仍通过
  PID / port owner / HTTP identity 检查。

推荐解决架构：

1. 启动器只做有限生命周期的 `start / status / stop` 请求、状态记录和有界 ready 检查，不直接持有
   Vite 或 mock 的长期生命周期。
2. 长驻服务由独立于当前 Codex 命令进程树的 owner 持有。Windows 可选择用户终端、预先运行的 supervisor、
   `Win32_Process.Create` / Task Scheduler，或已经存在的 Docker 等外部守护进程。
3. stdout / stderr 写入工作区 `.local/` 日志，stdin 与 Codex tool 断开；状态文件记录 owner、launcher PID、
   实际端口 owner、端口、health identity 和日志路径。
4. 状态文件只是所有权记录，不是 ready 事实来源。每次复用和停止前仍须重新检查 PID、端口 owner 与 HTTP。
5. 对真实自动启动链做集成验证：最外层 command 返回后至少继续观察一段有界时间，确认服务仍存活且 health
   正常；随后只按状态文件精确清理由本次启动的 PID。

推荐规避方案：

- 若当前 Codex 环境无法可靠建立外部 owner，不再继续叠加 detached wrapper。由用户或独立 runner 启动
  Vite 与安全 mock，Agent 仅核对端口、页面、直连 health 和代理 health，ready 后继续浏览器验收。
- 工具仍显示 Running 时，不以此判断服务失败，也不重复启动；先终止当前等待包装命令，再检查实际服务状态。
- 端口已被占用时，只有页面和专用 health identity 都符合预期才允许复用。未知服务或真实 Backend 不得用于
  安全合成验收，也不得由 Agent 擅自停止。
- 浏览器验收与环境生命周期分开管理：环境任务负责 `START -> READY -> SERVING -> STOP`，验收任务只负责
  `CHECK_READY -> ACCEPTANCE -> REPORT`。

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

- 打包脚本会把完整输出保存到 `.local/docker-deploy/logs/`。Docker build 默认直接连接当前终端，
  以保留 BuildKit 的蓝色 TTY 动态进度；不要为了同时打印和收集输出而把 build 命令接入
  PowerShell 管道，否则 BuildKit 会退化成逐行 plain 输出。优先双击或执行
  `scripts/package-docker-deploy.cmd`，失败时窗口会暂停；若直接运行 `.ps1`，从资源管理器启动时会
  自动暂停，也可显式传入 `-PauseOnError`。自动化调用可设置 `NO_PAUSE=1` 避免等待输入。
- Docker Engine 未启动、CLI 不在 PATH 或 Windows 终端未刷新 PATH 时，先修本机 Docker 环境，不要改项目打包脚本。
- Codex Windows 沙箱内执行 `docker build` 若出现 `open C:\Users\<user>\.docker\buildx\.lock: Access is denied`，说明 buildx 需要写用户目录；在任务确实要求构建镜像时按权限规则授权重跑，不要改 Dockerfile 绕过。
- `failed to fetch oauth token`、`auth.docker.io/token: EOF`、TLS timeout、DNS temporary failure 和
  `ECONNRESET` 属于 Docker Hub / 构建依赖网络错误，不是 Dockerfile 语法错误。为保留 BuildKit 动态进度，
  打包脚本不捕获构建输出，也不自动重试；失败详情从完整日志确认后手动重跑。PowerShell 或
  `.local/gitlab.env` 中的 Agent/Provider 代理不能代理 BuildKit 拉取 `FROM`，应在 Docker Desktop 中配置代理。
- 只修改 Agent Worker 时可使用
  `scripts/package-docker-deploy.cmd -AgentWorkerOnly -ReuseVersion <上一个完整版本>`。增量模式仍输出四个
  应用镜像的完整离线包，但 Backend、Frontend 和出站代理复用指定旧版本；不得用它掩盖这些组件本身的改动。
- 非 root Squid 容器若启动后立即退出，先检查是否仍尝试写默认 PID 文件；只读代理镜像可配置 `pid_filename none`，并关闭 cache/access log，再用 `squid -k parse -f /etc/squid/squid.conf` 验证。仅设置 `read_only` 不能限制外网，必须结合 internal network 与域名白名单代理或等效防火墙。
- Docker 前端镜像构建使用 `npm ci`，要求 `frontend/package.json` 和 `frontend/package-lock.json` 同步。不要使用 `latest` 或浮动顶层依赖；更新依赖后同步 lock。
- 如果本机 npm 与 Dockerfile 的 Node / npm 版本差异导致 lock 不一致，用与 Dockerfile 一致的 Node 镜像更新 lock。
- 离线部署升级时，`runtime/.env` 会保留。修改新包里的 `.env.example` 不会自动影响线上配置，需要同步修改运行目录的 `.env`。
- 离线升级会累积旧镜像和旧版本目录；清理前先确认当前 `APP_VERSION`、容器状态和回滚需求。
- `deploy-stage3.sh upgrade/scale` 只在最终健康检查通过后清理当前 Compose 项目的
  `created / exited / dead` 容器，使用运行中 Backend 的 `com.docker.compose.project` 标签限定范围且
  不强制删除。不同版本目录或不同 `COMPOSE_PROJECT_NAME` 留下的容器不会自动跨项目清理；先用
  `docker ps -a` 核对 Compose project/service 标签，再人工处理，禁止直接使用无项目过滤的
  `docker system prune`。
- 离线包上传后必须在版本目录执行 `./load-images.sh`，不能只执行 `chmod` 后直接进入 `runtime`。加载脚本会加载本版本全部镜像、自动更新 `runtime/docker-compose.yml` 和 `APP_VERSION`，无需手工复制 Compose。
- Windows 的 `bash.exe` 可能只是未安装 Linux 发行版的 WSL 启动器，执行 `bash -n` 会报
  `CreateProcessCommon ... /bin/bash: No such file or directory`，不能据此判断部署脚本语法错误。若本机已有
  `python:3.12-slim-bookworm` 等可信 Debian 镜像，可用禁网、只读挂载的临时容器执行
  `bash -n /workspace/deploy/deploy-stage3.sh`；不要为语法检查联网拉取未知镜像，也不要把真实 `.env` 挂入容器。
- 远程 Docker Compose 若提示 `services.backend.env_file.0 must be a string`，说明运行文件使用了当前 Compose 不支持的 `env_file.path/required` 长语法。当前 Compose 已逐项声明容器环境变量，并由运行目录 `.env` 完成插值，因此应移除该 `env_file` 块；不需要升级 Docker 或删除现有 `.env`。

## 端口与外链

- 本地 Python 后端默认端口与前端代理必须同步，常用后端端口为 `8090`，前端开发端口为 `5173`。
- Docker 部署中：

```text
PUBLIC_HTTP_PORT = 用户浏览器和 GitLab webhook 访问的宿主机端口
PLATFORM_BASE_URL = 后端生成外链时使用的公开地址
BACKEND_PORT = 容器内后端监听端口，只在 Docker 网络内使用
```

- `PUBLIC_HTTP_PORT` 和 `PLATFORM_BASE_URL` 通常应指向同一个用户可访问地址；`BACKEND_PORT` 不应暴露给用户配置 webhook。

## Agent Review 本地密钥

- 设置页填写 DeepSeek Key 后“保存”仍为禁用，且页面显示 `未配置 AGENT_REVIEW_CONFIG_ENCRYPTION_KEY`，说明缺少的是后端加密主密钥，不是输入框或保存接口失效。不得删除该门禁或降级为明文落库。
- 执行 `.\scripts\init-agent-review-secrets.cmd` 可安全补齐 `.local/gitlab.env` 中缺失或空白的加密主密钥与 Worker Token；脚本不覆盖非空值、不接触 DeepSeek Key，也不回显生成的秘密。
- `.local/gitlab.env` 只在后端进程启动时加载。生成后必须重启 `scripts/run-backend.cmd dev`，浏览器刷新和 uvicorn 源码热重载都不能替代进程重启。
- 如果数据库里已有加密的 Agent Key，不要随意轮换或丢失 `AGENT_REVIEW_CONFIG_ENCRYPTION_KEY`；旧密文无法用新主密钥解密。需要轮换时应先设计显式迁移流程。
- Windows 本地后端不要直接执行生产完整 Compose 来“补一个 Worker”，否则可能额外启动连接同一数据库的 backend 并形成重复调度。使用 `.\scripts\run-agent-worker.cmd start`，它只启动 Windows 专用 Worker 和代理。
- Docker internal 网络不能假设可直接解析或访问 `host.docker.internal`。Windows 专用方案通过双网卡代理严格放行 `host.docker.internal:8090`；不要把 Worker 直接加入普通网络来绕过连接问题。
- Docker Desktop 可能同时返回 IPv6/IPv4，而 Squid 5 已移除 `dns_v4_first`。Windows 一键脚本会查询实际 IPv4 host-gateway，并生成 `.local/agent-review-squid-hosts` 只读挂载给代理；不要硬编码 Docker Desktop 网段。
- Worker 容器有 `HTTP_PROXY/HTTPS_PROXY` 但配置测试恰好在 90 秒返回 `AGENT_TIMEOUT` 时，检查 Claude Code 子进程是否丢失了代理变量。子进程只能选择性继承代理变量，不能复制包含数据库、GitLab 等凭据的整个 Worker 环境。局域网上游代理应配置到白名单 Squid 的 `AGENT_REVIEW_UPSTREAM_PROXY`，不得让 Worker 绕过 Squid 直连。
- `connect_error: [Errno -2] Name or service not known` 是发起请求一侧的 DNS / 出站链路错误，不是模型业务错误。Agent 可用但普通 DeepSeek 失败时，通常是只配置了 `AGENT_REVIEW_UPSTREAM_PROXY`；普通 Provider 应配置 `CODE_QUALITY_REVIEW_PROXY`，该变量只代理模型请求，不要用全局 `HTTP_PROXY` 误伤 GitLab、钉钉和内网请求。
- Linux 生产不使用 Windows 专用 Compose。生产 Worker 通过 internal 网络访问 Compose backend，并与 backend 只读挂载同一个 `LOCAL_REPO_WORKSPACE_HOST_DIR`。
- Windows 的 `run-backend.cmd dev` 会异步启动 Worker，不能在 uvicorn 启动前同步等待 Worker 心跳，否则会形成启动死锁。失败详情查看 `.local/agent-worker-startup.*.log`；设置 `AGENT_REVIEW_AUTO_START_WORKER=false` 可排除 Docker 启动因素。
- Worker 镜像存在时，`run-agent-worker.cmd ensure` 会复用镜像；若宿主 Backend/Worker 心跳契约已更新，可能表现为容器
  长期 `health: starting` 且本地池无节点。先比较宿主与容器内 `worker.py` 摘要，确认过期后使用
  `run-agent-worker.cmd start` 强制重建，不要把问题误判为远程 Worker 竞争。
- 只读 Squid 镜像的入口若要在 `/tmp` 生成运行期配置，Compose 必须提供受限 tmpfs；否则代理会因
  `cannot create /tmp/...: Read-only file system` 重启。Windows 专用代理还必须显式使用启动脚本生成并挂载的
  `/etc/squid/squid.conf`，否则通用代理配置不包含本地 Backend 的 HTTP 8090 例外，Worker 心跳表现为 Squid 403。
- 自动启动只作用于 Windows `dev`，不得影响 `test`、`lint`、`migrate` 或 Linux runtime。远程离线包继续使用 `docker-compose.runtime.yml`，不要把 `docker-compose.windows-agent.yml` 上传叠加到生产环境。
- 不要让 Windows 本地 Backend 与 Linux 生产 Backend 同时连接同一生产数据库。旧版本使用无时区 `DATETIME` 和
  `datetime.now()` 判断 Worker 心跳、租约，UTC 与东八区进程并存会把刚领取的任务误判为超时 8 小时。修复后
  Agent 租约统一存 UTC，Compose 也显式设置 `TZ=UTC`；页面统一转换为 `UTC+8` 展示。
- Worker `healthy` 必须同时满足 `workerStatus=ONLINE` 和设置页返回的 `workerId` 等于容器自己的
  `AGENT_REVIEW_WORKER_ID`。只检查全局 ONLINE 会被另一台 Worker 的心跳误导，出现“Linux 容器健康，但实际由
  Windows Worker 领取任务”的假健康状态。

## 数据库与迁移

- Python 后端优先使用 `DATABASE_URL`：

```powershell
$env:DATABASE_URL="mysql+pymysql://root:root@localhost:3306/ai_code_review?charset=utf8mb4"
```

- 如果沿用旧 `MYSQL_URL`，不要把 JDBC 专属参数如 `serverTimezone`、`useSSL`、`allowPublicKeyRetrieval` 透传给 PyMySQL。
- `/api/health` 不访问数据库，不能仅凭 health 判断数据库链路可用；还应访问 `/api/review-tasks` 或 `/api/projects`。
- Python 后端以 `backend-python/migrations/bootstrap_sql/` 为 schema 基准，日常不要依赖 legacy Java Flyway 迁移。
- Agent Worker 上线后若出现 `1064 ... near 'SKIP LOCKED'`，通常是后端连接到了 MySQL 5.7。Agent Job claim 在 MySQL 5.7 下必须使用带行锁的普通 `FOR UPDATE` 串行领取，在 MySQL 8.0+ 才使用 `FOR UPDATE SKIP LOCKED`；不要通过移除行锁来规避语法错误。生产仍推荐 MySQL 8.0+。

## GitLab 本地仓库上下文

- `GITLAB_TOKEN` 能访问 REST API，不代表 Git HTTP clone / fetch 一定成功。部分 GitLab 实例需要 Basic Auth 语义，例如用户名 `oauth2`、密码为 token。
- Git 命令不要把 token 拼进 clone URL，避免日志、命令行和 progress 泄露凭据；应使用临时 Git env config 注入认证头，并保持 `GIT_TERMINAL_PROMPT=0`。
- `projects.repository_url` 必须归一化为运行环境可访问的 `GITLAB_BASE_URL` 地址。Webhook payload 中的容器内 hostname 可能导致 clone 失败。
- Windows 本地 worktree 会被仓库里的非法文件名阻断，例如路径包含 `?`。mirror fetch 可以成功，但 `git worktree add` checkout 会失败。此类仓库建议在 Linux / WSL / Linux Docker volume 上运行高准确模式，或先清理非法文件名。
- Push webhook 的事件 SHA 与分支当前 SHA 不一定相同，临时分支或 force-push 后尤其常见。普通 mirror fetch 后若事件 SHA 不可检出，应先按精确 SHA 定向 fetch 并重试；服务端仍不允许获取时必须明确降级，不能改用分支最新提交冒充事件版本。
- 本地引用搜索优先使用 `rg`；后端 Docker 镜像应包含 `ripgrep`，Windows 等环境找不到 `rg` 时可回退到仓库自带的 `git grep`，避免仅因搜索工具 PATH 不同而中断上下文准备。
- `LOCAL_REPO_PREPARED` 是历史 progress 状态，不代表当前 task worktree 仍存在。删除 `.local/review-workspaces` 后，需要重新触发 AI Review 才会重新准备 workspace。
- `review-workspaces` 为空不一定是清理任务导致。先检查 `LOCAL_REPO_CONTEXT_ENABLED`、GitLab token 权限、仓库 URL、commit / branch ref、Docker volume 映射和任务详情里的工作区诊断。

## 追加规则

- 环境、脚本、部署、Codex、检索、工具链的新坑追加到本文。
- 业务规则误判、接口语义、前端展示逻辑、AI Review 产品行为写入对应设计文档或 `docs/24-bug-log.md`。
- 如果一个问题同时包含业务和环境因素，只在本文记录可复用的环境判断方法，把业务结论放到业务文档。
