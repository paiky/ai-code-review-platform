# 本地开发避坑记录

> 状态说明：本文按时间累积记录本地开发与调试踩坑，条目编号只增不减。§14 等迁移期条目可能仍提及 Java 对照，默认开发以 `backend-python/` 为准；权威契约见 `docs/03-api-contract.md`，启动验证见 `README.md`。

## 1. Codex 沙箱内 Git 推送凭据问题

在当前 Windows + Codex 桌面环境里，普通沙箱命令执行 `git push origin main` 可能失败：

```text
error: cannot spawn sh: No such file or directory
error: failed to execute prompt script
fatal: could not read Username for 'https://github.com': No such file or directory
```

实际原因不是远端仓库或提交问题，而是 Git Credential Manager 需要调用 Git Bash 的 `sh.exe` 处理凭据提示；Codex 沙箱用户启动 `sh.exe` 时可能遇到 Windows 权限错误，例如：

```text
couldn't create signal pipe, Win32 error 5
```

处理方式：

1. 如果用户已授权沙箱外执行，可以用 escalated `git push`，让 Git Credential Manager 读取本机用户的 GitHub 凭据。
2. 如果仍失败，Codex 只完成 `git commit`，把 commit hash 和 `git push origin <branch>` 命令交给用户手动执行。

本次验证记录：

```text
普通沙箱 git push 失败。
沙箱外 git push origin main 成功。
成功推送提交：a24f593 Add local GitLab test environment
```

## 2. 前端 JSON 解析错误实际可能是后端纯文本错误

现象：

```text
Unexpected token 'I', "Invalid CORS request" is not valid JSON
```

原因：

前端 `fetchApi` 如果无条件执行 `response.json()`，当后端返回纯文本错误时，会把纯文本当 JSON 解析。`Invalid CORS request` 的首字符是 `I`，所以报 `Unexpected token 'I'`。

处理方式：

1. 前端请求工具应先读取 `response.text()`，再尝试 `JSON.parse`。
2. 解析失败时把原始文本作为错误信息展示。
3. 后端如果是本地开发场景，可以临时放开 `/api/**` CORS，避免不同 localhost / 127.0.0.1 / 局域网 IP 导致拦截。

## 3. GitLab Push 没有目标分支，不应展示为 `source -> -`

现象：

```text
master_coolpet -> -
```

原因：

GitLab Push Hook 只有被推送的 `ref`，没有 MR 的 `source_branch` 和 `target_branch`。如果复用 MR 的分支展示模型，就会出现 `branch -> -`。

处理方式：

1. Push 展示应使用“推送分支：branch”或 `Push branch commit`，不要复用 MR 的 `source -> target`。
2. 任务列表、任务详情、Gate 审核区都要保持相同语义：Push 展示 `sourceBranch` 作为推送分支，不展示不存在的 `targetBranch`。
3. 当前 Push AI Review 已通过 Gate 控制自动触发，应优先依赖 Profile 的 `pushBranchPatterns` 过滤分支，例如只允许 `develop`、`feature/*`、`bugfix/*`、`hotfix/*`。

## 4. API Key / Provider 模式没有历史 CLI 的 stdout/stderr 调试链路

现象：

代码质量 Review 使用 API Key / Provider 模式后，执行过程只看到主要 INFO 阶段，看不到历史 CLI 子进程下的 stdout / stderr debug 输出。

原因：

历史 CLI provider 通过本地子进程执行，后端可以读取 stdout / stderr 并记录过程输出。OpenAI、Anthropic、DeepSeek 和自定义 Provider 都是 HTTP 请求，默认没有子进程输出流，因此需要显式记录请求和响应 debug 事件。

处理方式：

1. 非流式模型 Provider 调试应至少记录请求摘要、请求预览、响应摘要、原始响应预览、输出文本预览和解析结果。
2. 不要记录 API Key、Authorization header 等敏感信息。
3. 请求和响应内容需要截断，避免 progress event 过大。
4. 当前 AI Review 保持非流式 HTTP 调用；前端只通过 progress / result 轮询刷新执行状态。

## 5. Agent 不应绕过 `scripts/` 自行拼编译命令

现象：

新对话或新 Agent 容易直接进入 `backend/` 执行 `mvn test`，或进入 `frontend/` 执行 `npm run build`，导致没有复用仓库已有脚本里的环境准备逻辑。

原因：

项目脚本不仅是启动入口，也封装了本地开发约定：

1. `scripts/run-backend.cmd` 默认转发到 Python 后端脚本，并加载 `.local/gitlab.env`。
2. `scripts/run-backend-java.cmd` 保留 JDK 21 选择逻辑，供 legacy Java 行为对照使用。
3. `scripts/run-frontend.cmd` 会检查 Node / npm，并在缺少 `node_modules` 时自动安装依赖。
4. Windows 下优先使用 `.cmd` 入口可以减少 Shell、PATH、命令后缀差异。

处理方式：

1. 新对话先读 `AGENTS.md` 和 `README.md`。
2. 后端启动、测试、编译优先使用：

```powershell
.\scripts\run-backend.cmd dev
.\scripts\run-backend.cmd test
.\scripts\run-backend.cmd lint
.\scripts\run-backend.cmd migrate
```

3. 前端启动、构建优先使用：

```powershell
.\scripts\run-frontend.cmd
.\scripts\run-frontend.cmd build
```

4. 只有脚本缺少所需能力或脚本本身失败需要定位时，才直接执行底层 `mvn.cmd` / `npm.cmd` 命令，并记录原因。
5. 如果确实需要对照历史 Java 后端，再显式使用：

```powershell
.\scripts\run-backend-java.cmd
```

## 6. Docker 离线部署打包脚本找不到 docker 命令

现象：

```text
docker : 无法将“docker”项识别为 cmdlet、函数、脚本文件或可运行程序的名称。
```

原因：

`scripts/package-docker-deploy.cmd` 会调用 Docker CLI 构建并导出镜像。本机如果没有安装 Docker Desktop、Docker Desktop 未启动，或安装后当前终端没有刷新 PATH，就会找不到 `docker` 命令。

处理方式：

1. Windows 本机安装 Docker Desktop。
2. 启动 Docker Desktop，并等待状态变为 running。
3. 重新打开 PowerShell / Cursor，再执行：

```powershell
docker version
.\scripts\package-docker-deploy.cmd
```

4. 如果 `docker version` 仍提示找不到命令，检查 Docker Desktop 安装目录是否已加入 PATH，或重启 Windows 后再试。

## 7. Docker 前端镜像构建时 `npm ci` 提示 lock 不同步

现象：

```text
npm error `npm ci` can only install packages when your package.json and package-lock.json or npm-shrinkwrap.json are in sync.
npm error Missing: @emnapi/core@1.10.0 from lock file
npm error Missing: @emnapi/runtime@1.10.0 from lock file
npm error Missing: @emnapi/wasi-threads@1.2.2 from lock file
```

原因：

前端 `package.json` 如果使用 `latest`，Docker 镜像内执行 `npm ci` 时可能按当前 registry 最新解析依赖，而 `package-lock.json` 仍锁定旧解析结果，导致二者不一致。打包脚本中的 Docker 子命令如果没有显式检查退出码，还可能在镜像构建失败后继续执行 `docker save` 并误报打包成功。

处理方式：

1. 顶层前端依赖应固定明确版本，不要使用 `latest` 或可浮动范围版本。
2. 修改依赖后执行 `npm install --package-lock-only --save-exact ...` 更新 lock。
3. 打包脚本调用 Docker build / save / pull 后必须检查退出码，失败时立即退出，避免生成半成品离线包。
4. 如果本机 npm 与 Dockerfile 使用的 `node:20-alpine` 内置 npm 版本不同，本机 `npm install --package-lock-only` 可能仍不能生成 Docker `npm ci` 需要的 peer 依赖锁定。此时用与 Dockerfile 一致的 Node 镜像更新 lock，例如：

```powershell
docker run --rm -v "${PWD}\frontend:/workspace/frontend" -w /workspace/frontend node:20-alpine sh -c "npm install --package-lock-only --ignore-scripts"
```

5. 不要把仅为满足 peer 解析的 `@emnapi/core` / `@emnapi/runtime` 手写进 `frontend/package.json` 顶层依赖；让 npm 在 `package-lock.json` 中记录 optional peer 即可。

## 8. PowerShell 默认编码可能把中文文档读成乱码

现象：

在 Windows PowerShell 中直接执行：

```powershell
Get-Content -Raw README.md
Get-Content -Raw docs\17-platform-value-roadmap-ppt-outline.md
```

中文内容可能显示为类似 `AI 鍙樻洿椋庨櫓...` 的乱码，导致 Agent 或人工阅读时误判文档含义。

原因：

仓库中的中文 Markdown 文档按 UTF-8 保存，但 Windows PowerShell 的默认读取编码可能与文件编码不一致。

处理方式：

1. 阅读中文 Markdown / 文档时显式指定 UTF-8：

```powershell
Get-Content -Raw -Encoding UTF8 README.md
Get-Content -Raw -Encoding UTF8 docs\17-platform-value-roadmap-ppt-outline.md
```

2. 如果第一次读取出现中文乱码，应立即用 `-Encoding UTF8` 重新读取，不要基于乱码内容做总结或修改。
3. 新对话理解项目时，读取 `AGENTS.md`、`README.md` 和 `docs/` 下中文文档都优先使用 `-Encoding UTF8`。

## 9. Windows PowerShell `Set-Content -Encoding UTF8` 可能写入 BOM

现象：

Java 测试或源码文件经过批量替换后，编译报错：

```text
illegal character: '\ufeff'
class, interface, enum, or record expected
```

原因：

Windows PowerShell 5 的 `Set-Content -Encoding UTF8` 会写入 UTF-8 BOM。Java 源码文件开头如果带 BOM，Maven 编译时可能把它识别成非法字符。

处理方式：

1. 小范围源码修改优先使用 `apply_patch`，不要用 PowerShell 批量重写 Java 文件。
2. 如果必须批量改写并保留 UTF-8 无 BOM，可用 .NET 明确指定：

```powershell
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($path, $content, $utf8NoBom)
```

3. 遇到 `\ufeff` 编译错误时，先检查最近被脚本改写过的 `.java` / `.sql` 文件编码，再重新保存为 UTF-8 无 BOM。

## 10. WindowsApps 的 `python.exe` 占位别名会干扰 Python 后端脚本

现象：

阶段 1 Python 后端验证时，`python` 命令可能先命中：

```text
C:\Users\<user>\AppData\Local\Microsoft\WindowsApps\python.exe
```

沙箱内可能报：

```text
Program 'python.exe' failed to run: A specified logon session does not exist.
```

沙箱外或普通 PowerShell 中也可能因为 WindowsApps 占位别名而无法启动真实 Python。`py` launcher 存在时，还可能返回：

```text
No installed Python found!
```

原因：

WindowsApps 的 `python.exe` 是应用执行别名，不一定是真实 Python 解释器；`py.exe` launcher 也可能没有注册到已安装解释器。

处理方式：

1. `scripts/run-backend-python.ps1` 优先使用 `backend-python/.venv/Scripts/python.exe`。
2. 如果没有 `.venv`，脚本会跳过 WindowsApps 占位别名，寻找真实 `python.exe`。
3. 如果全局 pip 异常，不要直接修全局 Python；优先在仓库内创建隔离环境：

```powershell
C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe -m venv backend-python\.venv
Push-Location backend-python
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Pop-Location
```

## 11. `Start-Process` 可能因 `Path` / `PATH` 环境键冲突失败

现象：

在 Codex / PowerShell 环境里用 `Start-Process` 启动本地服务时，可能报：

```text
Start-Process : 已添加项。字典中的关键字:“Path”所添加的关键字:“PATH”
```

原因：

当前进程环境中同时存在大小写不同的 `Path` / `PATH` 键，Windows 环境变量大小写不敏感，`Start-Process` 合并环境字典时会冲突。

处理方式：

1. 本地烟测需要临时启动服务时，可以改用 `.NET` 的 `System.Diagnostics.ProcessStartInfo`，并设置 `UseShellExecute = $false`、`CreateNoWindow = $true`。
2. 如果当前 PowerShell / .NET 运行时的 `ProcessStartInfo.EnvironmentVariables` 也是空值或不可写，可以先在父进程设置 `$env:DATABASE_URL` 等环境变量，让子进程继承。
3. 启动前先检查目标端口是否已被监听，避免误停已有服务。
4. 烟测完成后只停止本次监听目标端口的进程。

## 12. Python 后端不能把 JDBC 专属参数透传给 PyMySQL

现象：

Python 后端 `/api/health` 正常，但访问需要数据库的接口，例如：

```text
GET /api/review-tasks?pageNo=1&pageSize=20
```

返回 500。直接复现 SQLAlchemy 查询时可能看到：

```text
TypeError: Connection.__init__() got an unexpected keyword argument 'serverTimezone'
```

原因：

旧 Java 后端使用的 `MYSQL_URL` 是 JDBC URL，常带有 `serverTimezone`、`allowPublicKeyRetrieval`、`useSSL` 等 JDBC 参数。Python 阶段把 `MYSQL_URL` 转成 SQLAlchemy URL 时，只有 PyMySQL 支持的参数才能进入 query string；`serverTimezone` 这类 JDBC 专属参数如果透传，会被 PyMySQL 当成连接参数并报错。

处理方式：

1. Python 后端优先使用明确的 `DATABASE_URL`：

```powershell
$env:DATABASE_URL="mysql+pymysql://root:root@localhost:3306/ai_code_review?charset=utf8mb4"
```

2. 如果沿用 `MYSQL_URL`，转换逻辑只保留 `charset=utf8mb4` 等 PyMySQL 支持参数，不透传 `serverTimezone`、`useSSL`、`allowPublicKeyRetrieval`。
3. 健康检查不访问数据库，不能只凭 `/api/health` 判断数据库链路可用；应再访问 `/api/review-tasks` 或 `/api/projects`。

## 13. AI Review retry 不能同步等待真实模型调用

现象：

访问或点击：

```text
POST /api/code-quality-reviews/tasks/{taskId}/retry
```

后，接口长时间无响应；同时 `/api/health`、`/api/review-tasks` 等其它接口也开始超时。

原因：

Python 阶段 4 初版 retry 在 FastAPI `async def` 里同步执行数据库查询和真实模型 HTTP 调用。uvicorn 本地开发默认单 worker，真实 Provider 一慢，就会占住事件循环，导致其它请求也无法处理。

处理方式：

1. retry 接口只负责写入 `RUNNING` 结果和 `QUEUED` progress，然后立即返回。
2. 真实 Provider 调用放到后台线程中执行，执行过程写入 `code_quality_review_progress_events`，结果写入 `code_quality_review_results`。
3. 前端通过 `/api/review-tasks/{taskId}/code-quality-progress` 和 `/api/review-tasks/{taskId}/code-quality-result` 轮询。
4. 如果已经触发旧同步 retry 并导致本地服务整体超时，需要重启 Python 后端进程。

## 14. Python AI Review 阶段 4 通过 mock 不等于已对齐 Java 行为（迁移期记录）

> **迁移期记录。** Python 已是默认主后端；下列“弱于 Java”现象大多已在后续迭代中补齐。只有用户明确要求对照 legacy Java 行为时，才需要按本节去查 `backend/`。

现象：

Python 后端阶段 4 的 AI Review API、Provider mock 测试都能通过，但真实使用时效果仍弱于 Java 后端，例如默认审核规则过短、执行过程缺少请求/响应/解析调试信息、GitLab MR 自动 AI Review 完成后没有按 Java 逻辑发送合并的“变更审查结果”通知。

原因：

阶段 4 的验收重点是 Provider API、settings/profile/provider 接口、结果落库和基础脱敏；这只能证明“能调用模型并保存结果”，不能证明已经完整复刻 Java 后端后续补强过的真实可用性逻辑。

处理方式：

1. 默认以 `backend-python/app/code_quality/` 与 contract 测试为准，不再以 Java 实现为验收标准。
2. 若需对照历史 Java 行为，再核对 Java `codequality` 包中的 auto review、progress、钉钉合并通知等逻辑。
3. 规则提醒主链路需确认模板加载、聚合类型、focus indicator 与钉钉过滤；见 `docs/06-change-analysis-rules.md` 与 `docs/04-risk-card-schema.md`。

## 15. AI Review 已恢复轮询模式，不要再把进度刷新设计成流式链路

现象：

引入 SSE / token streaming 后，前端仍需要轮询兜底，而且真实 Provider 容易卡在首包、网关或协议解析阶段，表现为 AI Review 长时间不完成或必须手动刷新才能看到结果。

当前决定恢复为稳定轮询：Provider 调用非流式 HTTP API，前端不建立 EventSource / WebSocket。

原因：

1. Progress 刷新和模型 token streaming 是两层能力，混在一起会增加前后端状态复杂度。
2. 当前前端没有必要为了 AI Review 结果展示建立 SSE / WebSocket；轮询 `code-quality-progress` 与 `code-quality-result` 已能覆盖执行过程展示。
3. 真实模型网关对 streaming 协议、首包时间、JSON mode 的支持差异较大，容易把一次普通 Review 变成协议排障。

处理方式：

1. 前端任务详情页只保留定时轮询：运行中任务周期性请求 `/api/review-tasks/{taskId}/code-quality-progress` 和 `/api/review-tasks/{taskId}/code-quality-result`。
2. 后端只保留普通 Provider HTTP 调用路径，不再提供 `/code-quality-progress/stream`，也不再维护 delta buffer。
3. Provider 配置接口不暴露 `streamingEnabled`、`capabilities`、`streamingConfig`；页面不再展示流式开关。
4. 如果最后 phase 是 `HTTP_REQUEST_START`，优先检查 endpoint、DNS、网关、API Key、模型名称和普通 HTTP read timeout。
5. 如果最后 phase 是 `JSON_PARSE_FAILED`，说明模型已经返回文本，但不是平台要求的 Review JSON，应检查 prompt、`response_format` / strict schema 支持或模型 JSON mode 能力。
6. 后续如确实要重做 streaming，必须重新设计阶段文档，明确前端连接协议、后端 fan-out、超时策略、回退行为和验收用例，再单独落地。
7. 真实 Provider 联调前不要把 API Key、GitLab token、DingTalk webhook 写入代码、文档、测试快照或 progress detail。

## 16. Python AI Review 配置接口 500 可能是运行库 schema 与 Flyway 迁移不一致

现象：

访问这些接口时返回 500：

```text
GET /api/code-quality-reviews/settings
GET /api/code-quality-review-profiles
GET /api/code-quality-review-providers
```

原因：

Python 后端本身不执行 Java Flyway migration。如果本地 MySQL 还停在较旧的 AI Review 表结构，配置接口会在初始化默认 settings / profile / provider 时遇到缺表或缺列，例如 `code_quality_model_providers`、`default_provider_code`、`provider_code`、`review_instructions`。

本次还定位到一个测试环境里的隐藏坑：运行时补 schema 时如果用 engine 级 inspector，SQLite 单连接测试可能触发额外 ROLLBACK，把同一请求里刚写入的 Provider 配置冲掉。schema 检查应绑定当前 SQLAlchemy Session 的 connection。

处理方式：

1. Python 后端的 AI Review 配置初始化会在当前 Session connection 上补齐必要表和列，避免旧库直接 500。
2. 本地真实 MySQL 如果仍异常，先重启 Python 后端，再确认数据库至少有 `code_quality_review_settings`、`code_quality_review_profiles`、`code_quality_model_providers`。
3. 正式 schema 以 `backend-python/migrations/bootstrap_sql/` 为准；本地可执行 `scripts/run-backend.cmd` 触发的迁移/bootstrap，**不要**再依赖 Java Flyway 作为日常迁移入口。

## 17. Python 后端写 MySQL 时不能依赖数据库默认时间戳

现象：

前端点击“重新审查”或调用：

```text
POST /api/review-tasks/{taskId}/rerun
```

返回 500。离线复现可看到：

```text
Column 'created_at' cannot be null
```

原因：

Java Flyway 表结构里 `review_tasks`、`review_results`、`notification_records`、`gitlab_mr_webhook_events`、`gitlab_push_webhook_events` 等表的 `created_at` / `updated_at` 是 `NOT NULL DEFAULT CURRENT_TIMESTAMP`。但 SQLAlchemy 如果把字段映射出来且对象属性为 `None`，INSERT 时会显式传 `NULL`，MySQL 不会再套用默认值。

处理方式：

1. Python 创建任务、结果、通知、GitLab webhook event、自动创建项目时，显式写入 `created_at` 和 `updated_at`。
2. 标记任务成功或失败时同步更新 `updated_at`。
3. SQLite 测试库对 NULL 更宽松，必须在 contract 测试里至少断言返回的 `createdAt` / `updatedAt` 不为空，避免真实 MySQL 才暴露问题。

## 18. 钉钉发送必须同时遵守环境开关和平台全局开关

现象：

前端“AI Review 全局设置”中关闭钉钉推送后，手动重新触发审阅仍可能发送钉钉消息。

原因：

Python 后端通知发送链路最初只读取环境变量 `DINGTALK_ENABLED` 和 `DINGTALK_WEBHOOK_URL`，没有把数据库里的 `code_quality_review_settings.dingtalk_notification_enabled` 传入规则审查重跑和 AI Review 合并通知。

处理方式：

1. 规则审查通知、AI Review 合并通知和手动审查跳过记录都要读取 `get_settings_record(db).dingtalk_notification_enabled`。
2. 环境变量 `DINGTALK_ENABLED=false` 仍作为更底层的运维总开关。
3. 全局推送关闭时应保存 `SKIPPED` 通知记录，且不能发起钉钉 HTTP 请求。

## 19. AI Review Provider 返回旧字段名时要做归一化

现象：

AI Review 结果里标题、正文和建议正常，但前端“文件 / 行号 / 分类 / 风险等级”显示为 `-`。

原因：

OpenAI Responses strict schema 会强约束 `filePath`、`startLine`、`category`、`severity` 等字段；DeepSeek / OpenAI-compatible JSON mode 不一定严格遵守 schema，可能返回 `file_path`、`line_range`、`type`。如果 Python 后端只读取精确字段名，就会在落库时把这些信息写成 `null`。

处理方式：

1. Prompt 中明确要求返回平台字段：`severity`、`category`、`filePath`、`startLine`、`endLine`、`confidence`。
2. 保存 AI Review 结果时兼容 `file_path`、`line_range`、`type`、`line` 等旧字段名。
3. 读取历史结果时，如果 findings 已经缺字段，但 `rawOutput` 里保留了原始模型响应，可从 `rawOutput` 中重解析并补齐展示字段。

## 20. 不要默认全量跑测试，按改动影响面选择最小验证集

现象：

每轮开发都执行全量测试，例如：

```powershell
.\scripts\run-backend.cmd test
```

随着测试数量和输出增加，会让每轮对话耗时和额度消耗越来越高。对于只改前端交互、文档或单个后端模块的小目标，全量测试常常不是最高性价比的验证方式。

处理方式：

1. 前端样式、交互或展示逻辑改动：优先执行 `.\scripts\run-frontend.cmd build`。
2. Python 后端局部改动：优先执行相关 pytest 文件，例如 `.\backend-python\.venv\Scripts\python.exe -m pytest tests/contract/test_rule_templates_api_contract.py`，或通过脚本能力可达的最小测试集。
3. 通过 `.\scripts\run-backend.cmd test <pytest-path>` 指定文件时，路径要按 `backend-python/` 作为当前目录书写，例如 `tests\contract\test_rule_templates_api_contract.py`；不要写成 `backend-python\tests\...`，否则脚本进入后端目录后 pytest 会找不到文件。
4. 只有改到 webhook -> 分析 -> 风险卡片 -> 通知 -> 落库主链路、共享模型、数据库兼容、通知发送或跨模块边界时，才执行 `.\scripts\run-backend.cmd test` 全量 Python 测试。
5. Java 后端 `backend/` 已停止维护，默认不再执行 Maven 编译或测试；只有用户明确要求对照历史 Java 行为时才读取或运行。
6. 最终结论中说明“为什么选择这组验证”，避免把全量测试当作无脑默认动作。

## 21. 搜索不要扫进依赖目录和构建产物

现象：

使用全仓搜索时如果扫进 `frontend/node_modules/`、`backend/target/`、`frontend/dist/`、`backend-python/.venv/` 等目录，会输出大量无关内容，甚至让搜索命令超时。之前搜索 Ant Design 或通知关键字时就曾被 `node_modules` 和构建产物拖慢。

原因：

依赖目录和构建产物体积大、重复内容多，而且通常不是需要人工修改的源代码。扫这些目录会增加命令耗时、上下文噪声和对话额度消耗。

处理方式：

1. 优先使用 `rg`，并遵守仓库根目录 `.rgignore`。
2. 搜索时显式限定源目录，例如 `backend-python/app`、`backend-python/tests`、`frontend/src`、`docs`。
3. 必要时追加排除参数：

```powershell
rg "focusRuleCodes" backend-python/app frontend/src -g "!**/node_modules/**" -g "!**/target/**" -g "!**/.venv/**"
```

4. 不要把 `node_modules`、`target`、`dist`、`.venv`、`__pycache__`、`.pytest_cache` 的搜索输出贴入分析结论。

## 22. Windows PowerShell 默认写文件编码和换行符可能破坏 Linux 部署脚本

现象：

离线 Docker 打包后，服务器上的 `load-images.sh` 可能报：

```text
/usr/bin/env: ‘bash\r’: No such file or directory
```

`.env.example`、`docker-compose.yml` 里也可能出现 `^M`。

原因：

Windows PowerShell 5 直接使用 `Set-Content` 写文本时，默认可能写成 UTF-16LE，使用 `-Encoding UTF8` 又可能写入 BOM；如果直接复制 Windows 工作区里的文本文件，还可能把 `CRLF` 行尾带到 Linux。对于 Linux shell 脚本、`.env` 和 `docker-compose.yml`，这些编码或换行符差异会让 shebang、变量解析和命令执行异常。

处理方式：

1. 生成 Linux 侧部署文件时，优先用 .NET 显式写 UTF-8 无 BOM：

```powershell
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($path, $content, $utf8NoBom)
```

2. `scripts/package-docker-deploy.ps1` 输出 `docker-compose.yml`、`.env.example` 和 `load-images.sh` 时，都要显式写成 UTF-8 无 BOM + LF。
3. 如果上传后的文件里出现 `^M`，优先怀疑打包产物换行符不对，不要先误判为 Docker 或 Linux 权限问题。

## 23. 离线 Docker 升级时，`runtime/.env` 会被保留，修改新包里的 `.env.example` 不会自动生效

现象：

服务器上明明重新打了新包，`deploy/.env.example` 里也改成了新的数据库账号密码，但 `docker compose up -d` 后，后端日志仍然报类似：

```text
Access denied for user 'ai_review'@'...'
```

原因：

离线部署脚本 `load-images.sh` 的设计是把固定运行目录放在 `/opt/ai-code-review-platform/runtime/`，并且只在第一次部署时从 `.env.example` 创建 `runtime/.env`。后续升级时脚本只更新 `APP_VERSION`，不会覆盖 `runtime/.env` 里已经存在的 `DATABASE_URL`、GitLab、钉钉或模型配置。

所以如果第一次部署时 `runtime/.env` 里写的是：

```text
DATABASE_URL=mysql+pymysql://ai_review:...
```

后来即使重新打包、重新上传，新包里的 `.env.example` 改成了 `root` 或其他账号，运行中的 compose 仍然会继续使用旧的 `runtime/.env`。

处理方式：

1. 永远以服务器上的 `runtime/.env` 作为最终生效配置，不要只改版本目录里的 `.env.example`。
2. 排查时先执行：

```bash
cd /opt/ai-code-review-platform/runtime
grep '^DATABASE_URL=' .env
docker compose config | grep DATABASE_URL
docker compose exec backend /bin/sh -lc 'echo "$DATABASE_URL"'
```

3. 如果 `runtime/.env` 已改，但容器仍是旧值，执行：

```bash
docker compose up -d --force-recreate backend
```

4. 如果确认想完全重置运行配置，再手工备份并删除 `runtime/.env`，然后重新执行新版本目录下的 `./load-images.sh` 让它按新的 `.env.example` 重建。

## 24. 离线升级会持续累积旧镜像，最好在 `load-images.sh` 中做版本保留策略

现象：

多次上传离线包并执行 `./load-images.sh` 后，服务器上会留下越来越多镜像，例如：

```text
ai-code-review-backend:20260520120046
ai-code-review-backend:20260520210156
ai-code-review-backend:20260521103000
```

原因：

`docker load` 只负责导入新 tag，不会自动删除旧 tag。运行中的 compose 只会使用 `runtime/.env` 中 `APP_VERSION` 指向的版本，但历史镜像会持续占用磁盘。

处理方式：

1. 在离线部署脚本 `load-images.sh` 中加入镜像清理逻辑，按 tag 时间倒序只保留最近几个版本。
2. 默认建议保留最近 `2` 个应用版本，兼顾快速回滚和磁盘占用。
3. 清理时如果旧镜像仍被旧容器占用，应跳过删除而不是让部署失败。
4. 如需临时调整保留数量，可在服务器上执行：

```bash
KEEP_IMAGE_VERSIONS=3 ./load-images.sh
```

## 25. 钉钉 Webhook 已改为设置页数据库配置，修改 `.env` 默认不会影响当前通知目标

现象：

部署完成后已经在服务器上更新了 `.env` 或重新打了包，但钉钉仍然不发，或者还在往旧群里发。

原因：

当前 Python 后端的默认通知目标已经从 `.env` 中的 `DINGTALK_WEBHOOK_URL` 切换到前端“设置”页里维护的 `notification_webhooks` 数据。全局钉钉开关、webhook 启用状态和 webhook 列表都以数据库中的设置为准。

处理方式：

1. 优先检查前端“设置”页中的全局钉钉推送开关是否打开。
2. 确认至少存在一个已启用的 webhook，且 URL 保存成功。
3. 如果页面已经配置但仍不生效，先确认当前容器是否已经升级到包含新 settings 接口响应的版本，再查看 `/api/code-quality-reviews/settings` 返回的 `dingtalkWebhooks`。
4. 只有在数据库完全没有 webhook 配置时，才考虑是否仍命中了旧环境变量 fallback。

## 26. 任务列表不要在排序分页时携带大 JSON 字段

现象：

访问任务列表接口返回 500：

```text
GET /api/review-tasks?pageNo=1&pageSize=20
```

后端直连复现可看到 MySQL 报错：

```text
Out of sort memory, consider increasing server sort buffer size
```

原因：

任务列表查询如果直接 join `review_results` 并取出 `risk_card_json`、`change_analysis_json` 等大字段，再按 `review_tasks.created_at` 排序分页，MySQL 可能把大 JSON/TEXT 行一起放进排序缓冲区。数据多或卡片 JSON 较大时，即使只取 20 条，也可能触发 sort buffer 不足。

处理方式：

1. 列表接口先只基于 `review_tasks` 和必要过滤字段查询本页 `task_id`，完成排序和分页。
2. 再按本页 `task_id` 查询项目、结果和提醒摘要，避免大 JSON 字段参与排序。
3. 详情页和结果页仍可读取完整 JSON；列表页只拿必要摘要字段。

## 27. Push 审查任务 rerun 不能复用 MR-only 入口

现象：

Push 类型任务点击“重新触发审阅”返回 400：

```text
POST /api/review-tasks/{taskId}/rerun
```

原因：

早期 Python rerun 实现只允许 `GITLAB_MR_WEBHOOK`，并直接调用 MR webhook 处理函数。后来产品文档和前端已经把 rerun 定义为支持 GitLab MR / Push，但服务层仍保留 MR-only 判断，导致 Push 任务被错误拒绝。

处理方式：

1. rerun 允许 `GITLAB_MR_WEBHOOK` 和 `GITLAB_PUSH_WEBHOOK`。
2. 基于保存的 `rawPayload.object_kind` 统一分发到 GitLab webhook 处理入口，而不是直接调用 MR-only 方法。
3. 补充 Push rerun contract 测试，确认新任务仍是 `GITLAB_PUSH_WEBHOOK`。

## 28. Push 自动已开但仍提示 AI Review 全局能力未启用

现象：

前端 Profile 中已经打开 `triggerOnPush`，重新触发 Push 审查后，任务详情页仍显示：

```text
代码质量 AI Review 全局能力未启用，Push 不会进入 AI Review。
```

同时访问普通 Push 任务的结果接口可能在后端日志里看到：

```text
GET /api/review-tasks/{taskId}/code-quality-result 404 Not Found
```

原因：

`triggerOnPush` 只是 Profile 级 Push 自动触发开关；旧实现还有一个只能通过环境变量 `CODE_QUALITY_REVIEW_ENABLED` 控制的全局能力开关。用户在页面开启 Push 自动后，这个不可见总开关仍可能是关闭状态。对于被 Gate 拦截或未触发 AI Review 的 Push，前端详情页还会查询 AI Review 结果，旧结果接口用 404 表示“没有结果”，容易被误判成异常。

处理方式：

1. 将 AI Review 全局能力落到 `code_quality_review_settings.review_enabled`，设置页展示并保存 `reviewEnabled`。
2. `CODE_QUALITY_REVIEW_ENABLED` 只作为兼容初始化值；已有数据库以设置页保存的 `reviewEnabled` 为准。
3. `GET /api/review-tasks/{taskId}/code-quality-result` 对“任务存在但没有 AI Review 结果”的场景返回 `200` 且 `data=null`，只在任务本身不存在时返回 404。
4. 已经保存为 `GLOBAL_DISABLED` 的旧 Push Gate 记录不会自动改写；开启全局能力后，需要重新触发一次审阅生成新任务，新的 Gate 才会按当前配置重新判定。

## 29. Push 分支过滤要在任务创建前执行

现象：

GitLab 会把所有 Push 都推到 webhook，例如临时分支、个人分支、主干分支或不需要平台审查的分支。旧实现会先创建审查任务，再由 Push 审核层用 `BRANCH_NOT_MATCHED` 拦截 AI Review，导致任务列表仍被大量无效 Push 记录污染。

原因：

Push 审核层原本只负责“是否自动进入 AI Review”，不负责“是否进入平台审查流程”。如果分支限制放在 Gate 阶段，规则提醒、落库和通知等前置流程已经发生。

处理方式：

1. GitLab Push webhook 入口在创建 `review_tasks` 前读取项目绑定 AI Review 配置的 `pushBranchPatterns`。
2. 分支不匹配时直接返回 `SKIPPED`，`taskId=null`，不创建审查任务、不拉 diff、不生成提醒卡片，也不触发通知或 AI Review。
3. 允许分支进入平台后，Push 审核层继续负责 debounce、diff 可用性、硬上限、风险命中和大变更阈值等 AI Review 自动触发判定。

## 30. Python 后端本地默认端口与前端代理必须同步

现象：

`scripts/run-backend-python.ps1` 改成本地默认 `8090` 后，后端能启动，但前端页面仍然请求旧端口，表现为接口 404 / 代理失败 / 页面数据不刷新。或者相反，前端已经代理到 `8090`，但后端仍跑在其它端口。

原因：

Python 后端本地脚本、`app.core.config` 默认端口、前端 `VITE_API_PROXY_TARGET` 默认值和 README 本地示例需要成组维护。只改其中一个会让开发环境出现“服务是好的，但前端打错端口”的假故障。

处理方式：

1. 本地 Python 后端默认端口使用 `8090`。
2. `scripts/run-frontend.ps1` 默认代理到 `http://localhost:8090`。
3. 如果当前 `8090` 已经有一个 Python 后端监听，重复启动第二个后端仍会端口冲突；先停掉旧进程，或显式传 `--port` 使用其他端口。
4. Docker / 生产部署仍通过 `SERVER_PORT` / `BACKEND_PORT` 显式设置容器内端口，不依赖本地脚本默认值。

## 31. Windows WMI / CIM 查询异常会卡住 Python 后端启动

现象：

```text
.\scripts\run-backend-python.ps1 dev
```

长时间没有继续启动。用 `faulthandler` 诊断时可能看到 Python 卡在：

```text
platform.py -> _wmi_query
platform.machine()
sqlalchemy.util.compat
```

同时 `Get-CimInstance Win32_OperatingSystem` 也可能长期不返回。

原因：

Python 3.12 的 `platform` 模块在 Windows 上会优先调用 WMI 查询系统信息。本机 WMI / CIM 服务异常或查询阻塞时，`platform.system()`、`platform.machine()` 以及依赖它们的 `uvicorn` / `sqlalchemy` 导入链路都会卡住，看起来像是启动脚本没有执行。

处理方式：

1. `scripts/run-backend-python.ps1` 会为后端启动设置 `AI_REVIEW_SKIP_PYTHON_WMI=1`，并把 `backend-python/` 加入子进程 `PYTHONPATH`，确保 Python 启动阶段自动加载本项目的 `sitecustomize.py`。
2. `backend-python/sitecustomize.py` 在该变量开启且当前是 Windows 时，让 Python `platform` 模块跳过 WMI，并使用标准库已有的 registry / env fallback。
3. 这只是本项目本地启动的兼容保护；如果 PowerShell 中 `Get-CimInstance Win32_OperatingSystem` 也会卡住，仍建议后续修复本机 WMI / CIM 服务状态。

## 32. 后台任务的 inline 测试路径不要重新打开 `SessionLocal`

现象：

为后台任务增加 `*_INLINE=true` 测试开关后，contract 测试里明明使用的是测试数据库，但执行到后台任务时却尝试连接本地 MySQL，并可能报：

```text
RuntimeError: 'cryptography' package is required for sha256_password or caching_sha2_password auth methods
```

原因：

测试里的 `db_session` / FastAPI dependency override 指向测试库；如果 inline 模式仍复用生产后台函数并在函数内重新创建 `SessionLocal()`，就会绕过测试注入，回到默认运行库配置，进而误连本地 MySQL。

处理方式：

1. 后台任务的真实异步路径可以继续用 `SessionLocal()`。
2. `*_INLINE=true` 的测试路径应复用当前请求/测试传入的 SQLAlchemy `Session`，不要再新建 session。
3. 如果确实要测试真实后台路径，用 monkeypatch 替换 executor 的 `submit`，只断言任务已提交，避免测试进程里启动不可控的后台数据库连接。

## 33. 调度器 contract 测试不要启动真实后台 worker

现象：

为 AI Review / 修复预览增加统一调度器后，contract 测试里如果没有开启 inline，也没有 monkeypatch 调度器 `submit`，后台 worker 会用生产 `SessionLocal()` 启动，并可能再次误连本地 MySQL，报：

```text
RuntimeError: 'cryptography' package is required for sha256_password or caching_sha2_password auth methods
```

原因：

调度器 worker 属于真实异步路径，它不知道 pytest dependency override 中的测试 Session。即使接口本身使用测试库，后台线程也会回到默认数据库配置。

处理方式：

1. 需要验证同步结果时设置对应 inline 开关，例如 `CODE_QUALITY_REVIEW_INLINE=true` 或 `CODE_QUALITY_FIX_PREVIEW_INLINE=true`。
2. 需要验证“已排队但不执行”时 monkeypatch `service._executor.submit`，只断言 job 类型、优先级、状态和队列接口响应。
3. 不要在 contract 测试中等待真实调度器 worker 消费队列；真实 worker 行为留给集成或手工联调验证。

## 34. 运行时补 schema 不能在多个请求里并发 DDL

现象：

重启后前端一直转圈，多个 `/api/**` 接口没有响应，例如：

```text
GET /api/project-groups
GET /api/projects
GET /api/health
```

端口已经监听，TCP 连接也能建立，但请求一直超时。

原因：

多端项目组能力引入了 `project_groups`、`project_target_configs` 和任务端类型字段。旧库首次访问这些接口时会触发 Python 运行时 schema 补齐。如果前端重启后并发请求 `/api/project-groups`、`/api/projects`、设置页配置接口，多个请求可能同时执行 `CREATE TABLE` / `ALTER TABLE` / 默认数据初始化。由于本地 uvicorn 单 worker 且接口中有同步数据库操作，一旦某个请求卡在 DDL 或 metadata lock，其它 `/api` 请求也会一起转圈。

处理方式：

1. 运行时 schema 补齐必须加进程内锁，同一个 SQLAlchemy engine 只执行一次。
2. 默认项目组这类基础数据初始化要明确提交；不要在 GET 请求里 `flush` 后让 session close 回滚，导致下次请求再次初始化。
3. 如果已经卡住，先单独访问或执行一次 schema 补齐，或重启后端；修复后 `/api/project-groups` 和 `/api/projects` 应快速返回。
4. 长期建议仍通过 migration 正式升级 schema，运行时补齐只作为旧库兼容保护。

## 35. Vite 8 CLI 在 Windows / Rolldown 下可能错误发射绝对路径资源

现象：

执行前端构建时失败：

```powershell
.\scripts\run-frontend.cmd build
```

错误类似：

```text
[plugin vite:build-html]
The "fileName" or "name" properties of emitted chunks and assets must be strings that are neither absolute nor relative paths, received "D:/projects/.../frontend/index.html".
```

原因：

当前前端依赖使用 Vite 8，底层构建器切到 Rolldown。在 Windows 路径下，Vite CLI 的 app builder 可能把 `index.html` 的绝对路径传给 `emitFile`，导致构建失败。相同配置下，调用 Vite programmatic `build()` 可以正常构建。

处理方式：

1. 前端 `npm run build` 通过 `frontend/scripts/vite-build.mjs` 调用 Vite `build()`，避免 CLI app builder 的 Windows 路径问题。
2. 仍然通过仓库入口执行构建：

```powershell
.\scripts\run-frontend.cmd build
```

3. 如果后续升级 Vite 后 CLI 行为恢复正常，可以再评估是否切回 `vite build`。

## 36. 查询接口不要隐式创建项目端类型配置

现象：

访问项目端类型配置接口偶发很慢，甚至超时：

```text
GET /api/projects/{projectId}/target-configs
```

后端日志可能出现：

```text
pymysql.err.OperationalError: (1205, 'Lock wait timeout exceeded; try restarting transaction')
```

原因：

旧实现为了兼容没有 `project_target_configs` 的历史项目，在 GET 接口里调用 `ensure_default_target_configs`。这个函数会插入默认 BACKEND 配置，并更新 `projects.supported_target_types`。如果前端设置页、webhook、保存配置等请求并发访问同一个项目，就可能在 MySQL 上等待行锁，最终触发 1205。

处理方式：

1. `GET /api/projects/{projectId}/target-configs` 必须保持纯读。
2. 历史项目没有端类型配置时，GET 只返回一个 `id=null` 的虚拟默认 BACKEND 配置供前端展示。
3. 只有保存端类型配置、webhook 自动创建项目、手动预创建项目或任务解析主链路才允许真正写入 `project_target_configs`。
4. 以后新增查询接口时，不要为了“顺手补默认值”在 GET 路径里写库。

## 37. 多端 AI Review Profile 恢复默认不能复用后端默认 Prompt

现象：

在设置页切换到 PC / APP 的 AI Review Profile 后点击“恢复默认”，页面返回成功，但对应 Profile 的 `reviewInstructions` 变成后端模板内容，例如出现：

```text
你是资深后端代码质量审核助手
```

原因：

旧的 `POST /api/code-quality-review-profiles/{profileCode}/reset-default-prompt` 虽然接收了当前 `profileCode`，但后端实现固定写入 `DEFAULT_REVIEW_INSTRUCTIONS`。多端接入后，PC / iOS / Android / 跨端都有自己的内置默认 prompt，恢复逻辑必须按 `profileCode` 查默认定义，不能再假设只有后端默认模板。

处理方式：

1. 后端维护内置 Profile 默认定义映射，恢复默认时按 `profileCode` 写回对应 prompt。
2. 加载内置 Profile 时，如果发现 PC / APP Profile 被误覆盖成后端默认 prompt，可以自动修复回端侧默认内容。
3. 前端按钮文案应明确为“恢复当前 Profile 默认 Prompt”，调用时使用当前选中的 `profileCode`。
4. 增加 contract 测试覆盖：PC Profile 恢复默认后必须包含 PC Web / H5 关注点，且不能包含后端默认 prompt。

## 38. Docker 部署端口和平台外链不是同一个变量

现象：

远程服务器 `runtime/.env` 中配置：

```text
PUBLIC_HTTP_PORT=8090
PLATFORM_BASE_URL=192.168.100.241:15173
```

浏览器仍然需要访问 `192.168.100.241:8090`，而不是 `15173`。任务详情页点击“重新触发审阅”还可能报：

```text
GitLab diff is not provided and GitLab API is disabled
```

原因：

`PUBLIC_HTTP_PORT` 是 Docker Compose 暴露前端 Nginx 的宿主机端口，决定用户访问哪个端口。`PLATFORM_BASE_URL` 只由后端用于生成外链，例如钉钉机器人消息里的详情链接，不会改变容器端口映射。并且 `PLATFORM_BASE_URL` 应包含协议，例如 `http://192.168.100.241:15173`。

重新触发审阅会复用原始 webhook payload。如果原始 payload 没有 changed files / diff，后端需要调用 GitLab API 补拉 diff；Docker 环境未配置 `GITLAB_API_ENABLED=true`、`GITLAB_BASE_URL`、`GITLAB_TOKEN` 时，就会报 GitLab API disabled。本地正常通常是因为 `.local/gitlab.env` 已启用 GitLab API，或原始测试 payload 自带 changed files。

处理方式：

1. 希望浏览器访问 `15173`，应配置 `PUBLIC_HTTP_PORT=15173`，并把 `PLATFORM_BASE_URL` 配成同一个可访问地址：`http://192.168.100.241:15173`。
2. GitLab webhook 接收本身不一定需要 token；payload 自带 changed files 时可以直接处理。
3. MR payload 缺少 diff、Push compare 补拉、任务重新触发审阅需要 GitLab API 时，必须在部署 `.env` 中配置：

```text
GITLAB_API_ENABLED=true
GITLAB_BASE_URL=https://你的 GitLab 地址
GITLAB_TOKEN=GitLab access token
```

4. 修改 `runtime/.env` 后执行 `docker compose up -d --force-recreate backend frontend`，确保容器拿到新环境变量。

## 39. 任务列表端类型筛选要兼容历史任务空端类型

现象：

在“项目组 / 端类型配置”里把某个项目手动设置为后端后，任务列表筛选“端类型 = 后端”仍看不到该项目的历史任务。

原因：

项目配置保存的是 `projects.supported_target_types` 和 `project_target_configs`，用于后续 webhook / 手动审查创建新任务时选择端类型。任务列表筛选则查 `review_tasks.target_type` / `review_tasks.target_types_json`，这是任务创建时的快照。多端字段落地前创建的历史任务可能没有写入 `target_types_json`，因此只按任务字段筛选会漏掉这些历史数据。

处理方式：

1. 新任务仍优先使用任务自己的 `target_type` / `target_types_json` 做筛选，保证任务快照语义稳定。
2. 当历史任务的 `target_types_json` 为 `NULL`、空字符串或 `[]` 时，任务列表筛选可回退匹配项目当前 `supported_target_types`。
3. 不要为了列表展示直接批量改写历史任务端类型；如果后续需要正式回填，应单独做可审计的数据迁移或管理脚本。

## 40. AI Review 调度队列不要只按 created_at 判断最近一天

现象：

测试环境和本地连接同一个数据库时，AI Review 调度队列弹窗看到的任务数量不一致，或者最近完成的任务没有出现在队列里。

原因：

调度队列用于展示当前排队 / 运行任务，以及最近完成的 AI Review / 修复预览任务。旧查询对所有状态都使用：

```text
code_quality_scheduler_jobs.created_at >= now - 1 day
```

这会漏掉两类情况：

1. `QUEUED` / `RUNNING` 任务创建时间超过一天，但仍是当前活跃任务。
2. 任务创建时间较早，但最近才完成，`updated_at` / `finished_at` 在一天内。

处理方式：

1. `QUEUED` / `RUNNING` 活跃任务不加时间窗口，避免当前仍在执行的任务被隐藏。
2. `SUCCESS` / `FAILED` / `SKIPPED` 最近任务按 `updated_at >= now - 24 hours` 展示；活跃任务不加时间窗口。
3. 排查环境差异时优先查看 `code_quality_scheduler_jobs.status`、`created_at`、`updated_at`，而不是只看任务表。当前调度队列只展示最近 24 小时已完成 / 失败 / 跳过记录，活跃任务不受时间窗口限制。

## 41. `@Value` 规则不能把 diff 上下文行当成配置变更

现象：

提醒卡片命中 `@Value 配置变更`，并显示类似：

```text
automaticallySubscribe.newPackage
```

但在 GitLab MR diff 中，该 `@Value("${automaticallySubscribe.newPackage:...}")` 行没有 `+` / `-`，只是为了展示附近新增代码而带出的上下文行。

原因：

GitLab API 返回的 unified diff 会包含 hunk 上下文行。旧的 `VALUE_CONFIG_HEURISTIC_RULE` 直接扫描整段 diff 文本，只要上下文中出现 `@Value(` 就会命中；虽然 evidence 的 `addedLines` 里没有该配置行，规则本身仍被错误触发。

处理方式：

1. `@Value` 配置规则只扫描真正变化的 diff 行，也就是 `+` / `-` 行，忽略 `@@`、文件头和上下文行。
2. 排查类似问题时同时看 `changed_files_summary.files[].diffText` 和 `review_results.change_analysis_json.evidences[].addedLines`；如果配置字段只出现在 diffText 上下文、不在 changed lines 中，应视为误报。
3. 前端 Diff 弹窗展示的是 GitLab 原始 diff，上下文行出现配置名不代表配置本身发生了变更。

## 42. 运行时 webhook 归属回填不要挂在普通查询请求上

现象：

访问多个接口都变慢或超时，例如：

```text
GET /api/code-quality-reviews/job-queue
GET /api/code-quality-reviews/settings
GET /api/code-quality-review-providers
```

MySQL `SHOW PROCESSLIST` 里可能看到后端连接长时间卡在：

```sql
UPDATE notification_webhooks
SET project_group_id = ...
WHERE project_group_id IS NULL
```

原因：

项目组级钉钉机器人改造后，旧全局 webhook 需要兼容默认项目组。如果在每次 `ensure_webhook_schema()` 中无条件执行 `UPDATE ... WHERE project_group_id IS NULL`，普通 GET 请求也会反复触发 DML。uvicorn 本地开发通常是单 worker，FastAPI 接口虽然是 `async def`，内部同步数据库调用一旦等待 metadata lock 或行锁，就会拖住同进程里的其它接口。

同时，`code_quality_scheduler_jobs` 如果缺少 `status / updated_at / task_id` 等索引，队列弹窗查询会退化为全表扫描和 filesort。数据量小时不是主因，但会放大后续慢查询。

处理方式：

1. `ensure_webhook_schema()` 只能做进程内加锁、engine 级一次性 schema 检查。
2. 只有首次新增 `project_group_id` 列时才允许执行历史回填；已有列但仍为 `NULL` 的旧 webhook，在查询默认项目组时按默认组兼容读取，不要在普通请求里反复 UPDATE。
3. 为 `notification_webhooks(project_group_id, channel, enabled, status)` 补索引，减少按项目组查机器人时的扫描。
4. 为 `code_quality_scheduler_jobs` 补齐 `status, priority, queued_at`、`task_id, job_type`、`status, updated_at, id`、`status, updated_at, queued_at, id` 索引。
5. 队列接口的活跃任务查询必须有上限，并用单独 `count` 返回活跃总数；最近完成任务优先按 `updated_at` 窗口查询，避免 `updated_at OR created_at` 破坏索引。
6. 如果线上已经有卡住的 UPDATE，先用 `SHOW PROCESSLIST` 确认锁等待；必要时 kill 对应后端连接，再部署修复后的后端。

## 43. MR 页面有变更文件不代表 Webhook payload 带 changedFiles

现象：

GitLab MR 页面能看到变更文件，但新前端项目配置 MR Webhook 后，平台返回 500，任务列表没有记录。后端日志可能出现：

```text
Column 'default_code_quality_profile_code' cannot be null
```

原因：

GitLab Merge Request Hook payload 默认不一定携带 `changedFiles` / diff。平台第一次看到新项目时，如果 payload 没有文件列表，只能先用空文件集做端类型识别，此时会 fallback 到 `GENERAL`。`GENERAL` 不绑定默认 AI Review Profile；如果线上旧 MySQL schema 仍把 `projects.default_code_quality_profile_code` 设为 `NOT NULL`，自动创建项目会在创建任务前失败。

处理方式：

1. `projects.default_code_quality_profile_code` 必须允许为 `NULL`；无法确定 Profile 时先允许项目和审查任务落库。
2. 后续 GitLab API 补拉 diff 后，再按真实 changed files 更新端类型识别和任务端类型。
3. 如果最终仍无法确定 AI Review Profile，规则审查任务保持可见，AI Review 结果记录为 `SKIPPED`，并在任务详情页展示“项目所属项目组未设置 AI Review 模板”等原因。
4. 排查时不要只看 GitLab MR 页面；要看 Webhook delivery 的 Request body 中是否真的有 `changedFiles` / `changed_files`，以及 Response body 是否有 `taskId`。
5. 新前端项目也可以先在设置页手动预创建项目端类型配置为 `WEB_PC`，Profile 选择 `web-pc-default-ai-review`，路径规则可先用 `**/*`。

## 44. 默认项目组钉钉机器人不能作为其它项目组兜底

现象：

任务 `351` 属于 `IOS端` 项目组，项目为 `here/here-ios`，端类型为 `APP_IOS`。`IOS端` 项目组没有配置钉钉机器人，但通知记录显示消息发送到了 `默认通用项目组` 下配置的机器人。

原因：

旧实现把默认项目组机器人当成全局兜底：`enabled_webhooks_for_task()` 先查任务所属项目组，如果为空且所属组不是默认组，就继续查默认项目组机器人。这会让其它项目组的任务误触达默认组群。

处理方式：

1. 默认项目组只是普通项目组，只服务归属默认项目组的项目。
2. 任务通知只查询任务所属项目组的启用机器人。
3. 任务所属项目组无机器人时记录 `DINGTALK_WEBHOOKS_EMPTY` / `SKIPPED`，不回退到默认项目组或其它项目组。
4. 历史 `project_group_id IS NULL` 的 webhook 只按默认项目组兼容读取，不能成为所有项目组的兜底。

## 45. AI Review 执行失败不能只写结果表

现象：

AI Review Provider 调用失败、JSON 解析失败或后台重试失败后，任务详情里的代码质量结果已经是 `FAILED`，但任务列表中的 `review_tasks.status` 仍显示 `SUCCESS`。

原因：

规则提醒主链路会先把任务标记为 `SUCCESS`。如果后续自动 AI Review 或重试 AI Review 只更新 `code_quality_review_results.status=FAILED`，没有同步 `review_tasks.status`，列表页按任务表查询时就会误显示成功。

处理方式：

1. AI Review 执行失败时必须同时保存 `code_quality_review_results.status=FAILED` 并调用 `mark_task_failed`。
2. 自动 MR / Push AI Review、手动 AI Review、重试 AI Review 和后台异常 catch 路径都要覆盖。
3. AI Review 成功不应额外覆盖规则提醒成功状态；只有手动 AI Review 任务或失败任务重试成功时，才把任务恢复为 `SUCCESS`。
4. 右上角失败通知只展示最近 24 小时内 `code_quality_scheduler_jobs.job_type='AI_REVIEW'` 且 `status='FAILED'` 的执行记录，修复预览失败不进入该通知。

## 46. OpenAI-compatible Provider 不要共用过短的 OpenAI 超时

现象：

新接入的 XiaoMIMO / Xiaomi MiMo 模型执行代码质量 Review 时失败：

```text
read_timeout: Provider response timed out after 120 seconds
```

原因：

XiaoMIMO 虽然有独立 `XIAOMIMO_CODE_REVIEW_TIMEOUT_SECONDS`，但默认仍是 `120` 秒；DeepSeek 更隐蔽，之前没有独立超时变量，实际复用了 `OPENAI_CODE_REVIEW_TIMEOUT_SECONDS`，所以默认也是 `120` 秒。较大的 diff 或慢模型很容易超过这个限制。

处理方式：

1. 真实 Review Provider 默认超时统一调大到 `1000` 秒。
2. DeepSeek 使用独立 `DEEPSEEK_CODE_REVIEW_TIMEOUT_SECONDS`，不再隐式复用 OpenAI 超时。
3. XiaoMIMO 使用 `XIAOMIMO_CODE_REVIEW_TIMEOUT_SECONDS`，默认同样为 `1000` 秒。
4. 设置页“模型 Provider 配置”支持为单个 Provider 保存 `timeoutSeconds`；为空时使用环境变量默认值，填值时优先生效。
5. Provider 联通性测试仍可以传 `timeoutSeconds` 做短超时探测；不要把联通性测试的短超时当成真实 Review 的执行上限。

## 47. Push Gate 提示 Profile 未开启时要同时检查前端是否保存了触发开关

现象：

任务详情页的 Push 审核区显示：

```text
当前 AI Review Profile 未开启 Push 自动触发。
```

原因：

早期后端判断依据是 `code_quality_review_profiles.trigger_on_push` 和 `enabled`。内置 Profile 默认 `trigger_on_push=false`，如果设置页只展示 Provider、模型和 Prompt，而没有提交 `triggerOnPush`，用户即使配置了项目组默认 Profile、Provider 和 Push 审核策略，后端仍会按 `PROFILE_DISABLED` 拦截。后续已把自动触发策略收敛到项目组 AI Review 策略，遇到同类提示时应优先检查项目组策略。

处理方式：

1. 设置页的“项目组 AI Review 策略”必须展示并保存 `aiReviewEnabled`、`triggerOnManual`、`triggerOnMr` 和 `triggerOnPush`。
2. 保存项目组策略后，重新触发一次 Push 审阅生成新任务；已经落库的旧 Gate 记录不会自动改写。
3. 如果项目组 `triggerOnPush=true` 后仍未进入 AI Review，再继续检查全局 `reviewEnabled`、Provider API Key、项目组 `pushBranchPatterns`、diff 可用性、硬上限和大变更阈值。

## 48. 自动触发和修复预览策略应跟项目组走，不要绑定到 Profile

现象：

多个项目组复用同一个 AI Review Profile 时，一个项目组希望开启 Push 自动审查或自动修复预览，另一个项目组希望关闭。如果把 `triggerOnPush`、`autoFixPreviewEnabled` 这类策略放在 Profile 上，会迫使团队复制多个几乎相同的 Profile。

原因：

Profile 更适合表达“怎么审”，例如 Prompt、Provider、模型和端类型关注点；项目组策略更适合表达“什么时候审、触发多激进、是否自动生成修复预览”。这些是团队 / 业务线级别的成本和噪音控制，不应污染可复用的审查模板。

处理方式：

1. AI Review 设置页中保留 Profile 模块用于维护 Prompt / Provider / 模型。
2. 新增或维护“项目组 AI Review 策略”，按项目组保存 `aiReviewEnabled`、`triggerOnManual`、`triggerOnMr`、`triggerOnPush`、`autoFixPreviewEnabled`、`autoFixPreviewSeverities` 和 Push 审核阈值。
3. 后端 MR / Push 自动触发和自动修复预览执行时读取任务所属项目组策略；Profile 上的历史触发字段只作为兼容字段，不再作为主要策略入口。

## 49. GitLab compare API 补拉 Push diff 时不能丢失 commit 数

现象：

Push 任务详情里的 raw payload 明明包含：

```text
total_commits_count=1
commits=[...1 条...]
```

但 Push 审核指标显示：

```text
Commit 数：0
```

原因：

Push payload 初始解析会记录 `commitCount`。但当 GitLab webhook payload 不带完整 diff、后端改用 GitLab compare API 补拉 diff 时，新的 `changedFilesSummary` 会覆盖原 summary；旧实现只写入 compare 返回的文件 diff，没有把 payload 里的 `total_commits_count` / `commits.length` 带回 summary 和每个 file。Push Gate 后续只从 changed file 的 `commitCount` 取值，于是变成 0。

处理方式：

1. GitLab compare API 补拉 Push diff 后，继续保留 payload 级 commit 数。
2. `changedFilesSummary.commitCount` 和每个 `files[].commitCount` 都要写入同一个值。
3. commit 数优先读取 `total_commits_count`；没有该字段时回退到 `len(commits)`。

## 50. GitLab 事件时间不能直接去掉时区

现象：

任务详情页“事件时间”显示为 UTC 时间，例如本地北京时间下午 16 点左右的 Push，页面显示：

```text
2026-05-28T08:21:03.692
```

而任务列表“创建时间”显示本地时间，二者相差 8 小时。

原因：

旧的 GitLab 事件时间解析对 `Z` / `+00:00` 这类带时区的时间直接 `replace(tzinfo=None)`，没有先转换到本机本地时区。没有 payload event time 时，fallback 还使用了 `datetime.now(timezone.utc).replace(tzinfo=None)`，同样会把 UTC 时间伪装成本地无时区时间。

处理方式：

1. 解析带时区的 GitLab 时间时，先 `astimezone()` 转成本机本地时区，再去掉 `tzinfo` 存入当前无时区字段。
2. 没有事件时间或解析失败时，使用 `datetime.now()` 本地时间作为 fallback。
3. 后续如果要彻底规范时间字段，应单独设计数据库时区策略；当前展示层先保持任务列表和详情页都按本地时间语义展示。

## 51. Push 是否进 AI Review 不应由提醒卡片开关决定

现象：

iOS / Android / PC 端项目通常关闭提醒卡片，只使用代码质量 AI Review。但如果 Push Gate 仍启用“仅风险命中触发”一类策略，就会依赖规则提醒卡片的 `HIGH/CRITICAL` 或重点提醒项判断是否进入 AI Review，导致端侧项目明明达到了大变更阈值，仍因为“未命中重点风险”被拦截。

原因：

提醒卡片本质是规则提醒和通知展示能力，不应该作为代码质量 AI Review 的前置风险判断来源。尤其端侧项目关闭提醒卡片后，规则风险等级不再适合作为 Push 自动审查的门槛。

处理方式：

1. Push Gate 不再读取 `triggerOnlyWhenRiskMatched` 作为拦截条件。
2. 设置页移除“Push 仅紧急、高风险命中触发”开关；保存项目组策略时兼容字段固定写为 `false`。
3. Push 自动进入 AI Review 的判断保留分支、debounce、diff 可用性、硬上限和大变更阈值；规则风险命中仍可作为放行原因之一，但不再是可配置的唯一门槛。

## 52. 新远程分支 Push 的全 0 before 不能调用 compare API

现象：

GitLab 新建远程分支后触发 Push Hook，平台返回 500：

```text
Failed to fetch GitLab compare diff: HTTP 404
```

Webhook payload 中通常可以看到：

```text
before=0000000000000000000000000000000000000000
after=<真实提交 SHA>
```

原因：

GitLab 新分支 Push 的 `before` 全 0 表示分支之前不存在，不是一个真实 commit。把它作为 `repository/compare?from=000...&to=<after>` 的 `from` 参数时，GitLab 14.x 可能返回 404。这个 404 不是优先指向 token 权限问题，而是 compare 起点无效。

处理方式：

1. Push Hook 检测到 `beforeSha` 为全 0 时，不调用 GitLab compare API。
2. 如果 payload 中有真实 `changedFiles[].diffText`，可以继续按 payload diff 创建审查任务。
3. 如果只有 `commits[].added / modified / removed` 文件列表、没有任何 diff 文本，直接返回 `SKIPPED`，`taskId=null`，不要创建审查任务污染任务列表。
4. Push summary 中保留 `newBranchPush=true`，方便识别这是新远程分支首次 Push。

## 53. 替换项目组多模型配置要先 flush 删除

现象：

编辑项目组只保存单个模型时，后端返回 500，日志里出现：

```text
Duplicate entry '27-deepseek-default' for key 'uk_project_group_ai_review_model_key'
```

原因：

`project_group_ai_review_models` 使用 `(group_id, review_key)` 唯一键。更新项目组模型配置时如果在同一次 flush 里先 `delete` 旧行再 `add` 新行，SQLAlchemy 的 unit of work 不保证一定先发 DELETE 再发 INSERT；MySQL 可能先看到新 INSERT，于是和旧行的唯一键冲突。

处理方式：

1. 替换子表配置时，删除旧行后立即 `db.flush()`，确保数据库先释放唯一键。
2. 再插入新的模型执行项。
3. 对同一次请求中的重复 `providerCode + modelName` 做去重，避免前端重复提交导致同一 `reviewKey` 冲突。

## 54. 多模型 Review 迁移必须删除旧 `uk_task`

现象：

对历史 MR / Push 任务执行“重新触发审阅”后，新任务进入多模型 AI Review，第一条模型结果可以插入，第二条模型结果报：

```text
Duplicate entry '438' for key 'uk_task'
```

原因：

多模型结果已经改为 `(task_id, review_key)` 唯一，但旧库的 `code_quality_review_results` 可能仍保留历史唯一键 `uk_task(task_id)`。只要这个旧唯一键还在，同一个任务就仍然只能保存一条 AI Review 结果。

处理方式：

1. 正式迁移脚本需要执行 `DROP INDEX uk_task`，再创建 `uk_code_quality_result_task_review_key(task_id, review_key)`。
2. Python 运行时 schema 兼容也要检测并删除旧 `uk_task`，避免本地旧库没有完整跑迁移时继续 500。
3. 已经失败的重新触发任务可以再次重新触发；旧失败任务会保留失败状态。

## 55. 新分支 Push 没有 diff 时不要创建审查任务

现象：

GitLab 新分支 Push 的 `before` 为全 0，payload 里可能只有 `commits[].added / modified / removed` 文件列表，没有真实 `diffText`。平台如果继续按文件列表创建任务，端类型识别容易落到项目默认后端类型，任务列表会出现没有可审查 diff 的无效任务。

原因：

新分支 Push 的全 0 `before` 不是有效 commit，不能调用 compare API 补拉 diff；而 GitLab Push Hook 的 commit 文件列表只能说明涉及哪些路径，不等价于可用于规则分析或 AI Review 的 diff。用这个弱信号继续建任务会污染任务列表，并可能误导端类型。

处理方式：

1. Push Hook 检测到 `newBranchPush=true` 且 changed files 中没有任何 `diffText` 时，直接返回 `SKIPPED`，`taskId=null`。
2. 该场景不调用 GitLab compare API、不创建 `review_tasks`、不生成提醒卡片、不触发通知或 AI Review。
3. 如果未来 GitLab payload 明确携带可审查 `diffText`，仍可按正常 Push 审查链路处理。

## 56. AI Review / 修复预览卡在运行中时需要可手动中断

现象：

修复预览或 AI Review 调度任务可能长时间停留在 `RUNNING` / `QUEUED`，页面持续显示“生成中”或“运行中”，例如 Provider 请求超时前、后台线程异常退出前，或用户已经确认本次任务不需要继续等待。

原因：

当前调度器是后端线程池执行 Provider HTTP 调用，Python 线程无法安全强杀正在执行的请求。仅靠启动时 stale recovery 也只能处理服务重启前遗留的 `RUNNING` Review，不能解决当前页面上需要立即释放状态的任务。

处理方式：

1. 提供协作式中断接口：将调度任务、AI Review 结果或修复预览记录标记为 `SKIPPED`，并写入 `JOB_INTERRUPTED` 进度事件。
2. 对排队任务，worker 取出后如果发现状态已不是 `QUEUED`，应直接跳过执行。
3. 对已开始的 Provider 调用，不能强杀线程，但返回后保存结果前必须再次检查记录是否已被标记为 `SKIPPED`，避免覆盖用户手动中断状态。
4. 前端任务详情和 AI Review 调度队列都应暴露中断按钮，便于处理卡住的 Review 或 finding 级修复预览。

## 57. 多模型 AI Review 队列不能只展示首个 Review job

现象：

项目组配置多个 AI Review 模型后，右上角调度队列角标显示多个活跃任务，但打开队列弹窗只看到一条 Review 记录，用户无法判断或中断具体是哪一个模型的 Review。

原因：

后端队列快照按 `taskId` 分组时虽然保留了 `reviewJobs`，但前端弹窗只读取兼容字段 `reviewJob`，也就是每个任务组里的第一条 AI Review job。队列 job 本身如果不补充 `provider/model/displayName`，前端即使遍历多条 job 也难以清楚标识模型。

处理方式：

1. 队列快照应通过 `(task_id, review_key)` 关联 `code_quality_review_results`，给每个 AI Review job 返回 `provider`、`model`、`displayName` 和 `sortOrder`。
2. 前端调度队列弹窗应渲染 `reviewJobs` 多行表格，而不是只展示 `reviewJob`。
3. 中断操作使用具体 scheduler job id；后端再通过该 job 的 `review_key` 只标记对应模型 Review 为 `SKIPPED`，避免影响同一任务下其他模型。

## 58. AI Review 失败或中断后钉钉摘要必须带原因

现象：

AI Review 被手动中断，或 Provider 因 API Key、HTTP 状态、模型输出解析等原因失败后，平台仍会推送“变更审查结果”钉钉消息，但消息正文只显示“代码质量 Review 执行失败，请查看详情”，没有说明失败原因。

原因：

`code_quality_review_results.error_message` 已经保存了失败或中断原因，例如“用户手动中断 AI Review”或 Provider 错误；但钉钉摘要格式化时对所有非 `SUCCESS` 状态使用了固定文案，没有读取 `errorMessage`。

处理方式：

1. 钉钉 Review 摘要遇到 `FAILED`、`SKIPPED`、`RUNNING`、`QUEUED` 等非成功状态时，应输出状态语义。
2. 优先展示 `errorMessage`，没有时再回退 `summary`。
3. 原因文本需要压缩空白并截断，避免 Provider 大错误栈撑爆钉钉消息。

## 59. 多模型修复预览必须删除旧单模型唯一键

现象：

多模型 AI Review 成功后，在某个模型 Tab 下点击“生成修复预览”返回 500，后端日志出现：

```text
Duplicate entry '463-0' for key 'uk_code_quality_fix_preview_task_finding'
```

原因：

旧版 `code_quality_fix_previews` 表只按 `(task_id, finding_index)` 建唯一键。多模型后，不同模型同一任务下都可能有 `finding_index=0`，实际唯一性应按 `(task_id, review_key, finding_index)` 判断。如果旧库没有完整执行多模型迁移，仍保留旧唯一键，就会把不同模型的修复预览误判为重复。

处理方式：

1. `code_quality_fix_previews` 必须包含 `review_key` 列。
2. 删除旧唯一键 `uk_code_quality_fix_preview_task_finding`。
3. 创建新唯一键 `uk_code_quality_fix_preview_task_review_finding(task_id, review_key, finding_index)`。
4. Python 运行时 schema 兼容也要自动执行这组索引修正，避免旧库直接 500。

## 60. 中断后的修复预览重新生成必须强制刷新

现象：

修复预览生成过程中点击“中断”后，按钮变成“重新生成修复预览”。再次点击按钮没有报错，但页面也没有重新进入队列。

原因：

中断会把 `code_quality_fix_previews.status` 标记为 `SKIPPED`。修复预览生成接口为了避免重复调用 Provider，在已有记录且没有 `forceRegenerate=true` 时会直接返回缓存记录。旧前端只在 `FAILED` 状态传 `forceRegenerate=true`，对 `SKIPPED` 没有传，所以后端原样返回旧的 `SKIPPED`，用户看起来像“点击没反应”。

处理方式：

1. 前端“重新生成修复预览”遇到 `FAILED` 或 `SKIPPED` 都要传 `forceRegenerate=true`。
2. 后端保持缓存保护：只有显式强制重生成时才覆盖旧记录并重新排队。
3. 手动中断属于可重试状态，不应和“缺少 diff / 找不到文件”等不可自动恢复的跳过原因混在交互上。

## 61. 重试单个模型 Review 时要清理该模型旧修复预览

现象：

多模型任务中只重试某个模型后，新 Review 结果刚保存，部分 finding 立刻显示“查看修复预览”，而另一些 finding 显示“修复预览生成中”。看起来像模型 Review 结果自带了部分修复预览，或自动生成风险等级配置没有生效。

原因：

Review 结果本身不会携带修复预览。修复预览来自 `code_quality_fix_previews` 表，并按 `task_id + review_key + finding_index` 关联。重试单个模型会覆盖该模型的 findings，但如果不删除该模型旧的修复预览，旧记录会按相同 `finding_index` 挂到新 finding 上。由于重试后 finding 顺序和风险等级可能变化，就会出现高风险 finding 显示旧的“查看修复预览”，而本次自动生成仍只对配置中的风险等级排队。

处理方式：

1. 重试 AI Review 时，先删除当前 `task_id + review_key` 下旧的修复预览。
2. 不带 `reviewKey` 的全量重试应删除该任务所有旧修复预览。
3. 自动生成修复预览仍只按项目组 AI Review 策略的 `autoFixPreviewEnabled` 和 `autoFixPreviewSeverities` 判断，不读取模型输出中的其它修复建议作为预览。

## 62. 多模型重试后的运行计时不要混入旧进度事件

现象：

在某个模型 Tab 下重新触发 AI Review 后，顶部显示：

```text
AI Review 正在执行 HTTP 请求已发起 已执行 816 秒
```

但这是刚刚重新 Review，计时应该从 0 附近重新开始。

原因：

多模型页面过滤进度事件时，如果把 `review_key IS NULL` 的历史事件也混入当前模型 Tab，运行中计时会拿到旧事件时间作为起点。另一个隐患是运行中优先使用旧 `startedAt`，没有按最新一轮 `QUEUED / STARTED / REQUEST_BUILT / HTTP_REQUEST_START` 事件重置计时基准。

处理方式：

1. 多模型 Tab 只展示当前 `reviewKey` 的进度事件；只有单模型 / 旧数据没有 `reviewKey` 时才展示空 `reviewKey` 事件。
2. 运行中计时优先使用当前 Tab 最新一轮运行起点事件，不要从历史第一条事件或旧 `startedAt` 继续累加。

## 63. 修复预览 Diff 对照表中的长代码行应在列内换行

现象：

AI 修复 Patch 预览弹窗中，左右对照 diff 遇到较长的日志、方法调用或字符串时，代码行不会换行，
需要拖动底部横向滚动条才能看完整内容，左右对照也不容易阅读。

原因：

旧样式使用 `max-content` 和 `white-space: pre` 让代码列按内容撑开。虽然可以横向滚动查看完整长行，
但在弹窗中阅读真实业务代码时不够直观。

处理方式：

1. diff 行使用 `minmax(0, 1fr)` 让左右代码列在弹窗宽度内等分展示。
2. 代码单元格使用 `white-space: pre-wrap` 保留缩进，并使用 `overflow-wrap: anywhere` 处理超长字符串。
3. 弹窗 body 和 diff 表格保留纵向滚动；当 patch 本身包含更多上下文行时，可以在弹窗内继续下滑查看。
4. 如果 AI 返回的 unified diff 只有一个很短的 hunk，页面无法凭空展示更多上下文；需要重新生成更大上下文的 patch，或通过问题项旁的“查看 Diff”看原始任务 diff。

## 64. 调试重跑不要默认复制新任务

现象：

任务详情页点击“重新触发审阅”时，每次都会复制一条新的 `review_tasks`。调试规则、AI Review 或修复预览时，任务列表会快速膨胀，旧任务和新任务之间还容易混淆。

原因：

旧接口 `/api/review-tasks/{taskId}/rerun` 的语义是“基于原始 webhook payload 创建一条新任务并重放”。这适合保留审计历史，但不适合作为调试时的默认按钮。

处理方式：

1. 增加原地重跑接口 `/api/review-tasks/{taskId}/rerun-in-place`，复用当前任务记录重新执行规则审查和后续 AI Review 流程。
2. 原地重跑前清理当前任务的旧规则结果、通知记录、AI Review 结果、进度事件、修复预览、调度队列和 Push Gate 记录，避免新旧结果混在一起。
3. 前端主按钮文案改为“重新执行审阅”，默认调用原地重跑接口。
4. 保留“复制为新任务重跑”作为独立次要按钮，继续调用旧 `/rerun` 接口，满足需要保留历史审计或对比新旧结果的场景。

## 65. Agent 执行 `.cmd` 验证脚本时要禁用失败后的 `pause`

现象：

Agent 执行前端构建或后端测试脚本后，命令长时间不返回，或者工具层只提示没有拿到退出状态，无法判断构建 / 测试是否成功。例如：

```text
The shell command returned no exit status
```

原因：

仓库的 Windows `.cmd` 入口会在子脚本返回非 0 退出码时执行：

```bat
if not defined NO_PAUSE pause
```

这对人工双击脚本有帮助，但在 Agent / 非交互终端里会等待“按任意键继续”，看起来像测试脚本卡住。前端和后端的 `dev` 命令本身也是长驻服务，正常不会退出；验证构建 / 测试时不能误跑默认 `dev`。

处理方式：

1. Agent 执行一次性验证命令时，优先设置 `NO_PAUSE=1`，避免失败后等待输入：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-frontend.cmd build
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\contract\test_rule_templates_api_contract.py
```

2. 如果需要绕过 `.cmd` 的 pause 包装，可直接执行 `.ps1`：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-frontend.ps1 build
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-backend.ps1 test tests\contract\test_rule_templates_api_contract.py
```

3. 手动启动开发服务时仍可使用默认入口，例如 `.\scripts\run-frontend.cmd` 或 `.\scripts\run-backend.cmd dev`；这类命令正常会一直运行，不应作为“一次性验证是否通过”的命令。
4. 如果连 `echo` 这类最小命令都拿不到退出状态，优先怀疑 Cursor / Agent 命令执行桥接异常，而不是项目构建失败。

## 66. CodeGraph MCP 配置后 Cursor 或 Codex App 仍看不到工具

现象：

- 已执行 `codegraph install` 或 `.\scripts\setup-codegraph.cmd`，但 Cursor Agent 或 Codex App 仍像没有 CodeGraph 工具一样全库 grep / Read。

常见原因：

1. 修改 `.cursor/mcp.json` 后未重启 Cursor。
2. 本机 PATH 中没有 `codegraph`；MCP 配置使用 `"command": "codegraph"`，需要全局安装 `@colbymchenry/codegraph` 或把 npm global bin 加入 PATH。
3. 项目还没有 `.codegraph/codegraph.db` 索引；需要先 `codegraph init -i` 或 `.\scripts\setup-codegraph.cmd`。
4. Cursor 项目级 `.cursor/mcp.json` 写入了本机绝对 `--path`；可提交配置应使用 `"${workspaceFolder}"`，避免其他开发者克隆后仍指向原机器目录。
5. Codex App 不读取 Cursor 的 `.cursor/mcp.json`；需要在用户级 `~/.codex/config.toml` 单独增加 CodeGraph MCP 配置并重启 Codex App。
6. Windows PowerShell 直接运行 `codegraph` 时可能优先命中 `codegraph.ps1` 并被执行策略拦截；脚本和 Codex App 配置可显式使用 `codegraph.cmd`。

处理方式：

```powershell
npm install -g @colbymchenry/codegraph
.\scripts\setup-codegraph.cmd
```

Cursor 使用仓库内 `.cursor/mcp.json`。Codex App 还需要在 `~/.codex/config.toml` 增加：

```toml
[mcp_servers.codegraph]
command = "codegraph.cmd"
args = ["serve", "--mcp"]
```

然后重启对应客户端，在 Agent 中先调用 `codegraph_status` 验证索引是否可用。

## 67. 多模型钉钉摘要链接必须携带 Review Key

现象：

项目组配置多个 AI Review 模型后，钉钉 Markdown 能展示某个具体 Provider 的 Review 摘要，但点击“详情”或 finding 链接进入任务详情页时，页面默认展示排序第一的模型子 tab，和消息正文不一致。

原因：

旧链接只包含任务 ID。多模型结果都挂在同一个任务下，前端无法判断用户是从哪一个模型的钉钉摘要进入详情页。只传 `providerCode` 也不够精确，因为同一个 Provider 可能配置多个模型执行项。

处理方式：

1. AI Review 钉钉摘要的详情链接和 finding 深链追加 `?reviewKey={reviewKey}`。
2. 前端任务详情页读取 `reviewKey`，在多模型结果中选中对应子 tab。
3. 规则提醒链接保持任务级跳转，不追加模型参数。

## 68. Docker Engine 未启动时打包脚本不能被 stderr 提前中断

现象：

Docker Desktop 未启动或 Linux Engine 不可用时，执行：

```powershell
.\scripts\package-docker-deploy.cmd
```

直接看到 PowerShell `NativeCommandError`，没有进入脚本预期的 Docker Engine 诊断提示。

原因：

脚本设置了 `$ErrorActionPreference = "Stop"`。PowerShell 5 执行 `docker version 2>&1` 或 `docker info 2>&1` 时，Docker CLI 写入 stderr 会先触发终止错误，导致后续 `$LASTEXITCODE` 判断来不及执行。

处理方式：

1. Docker 探测命令单独在 `Continue` 模式下执行，捕获输出和退出码。
2. 探测失败后恢复原始错误策略，再抛出包含 Docker 原始输出的可操作提示。
3. 本机实际打包前仍需启动 Docker Desktop，并确认 Linux Engine 已进入 running 状态。

## 69. 任务列表不能直接把底层 `SUCCESS` 当成 AI Review 结论

现象：

规则提醒链路完成后，任务列表大量显示 `SUCCESS`，但 AI Review 可能尚未触发、仍在排队，
或多个模型仍在执行。用户无法从列表判断审查是否完成以及最高风险等级。

原因：

`review_tasks.status` 表示底层任务执行状态。规则分析会先将它写为 `SUCCESS`，AI Review
是后续增强链路。多模型执行后，单个 Provider 的失败也不等于整个审查失败。

处理方式：

1. 使用独立的 `review_tasks.review_status` 作为列表审查状态，保留原 `status` 用于排障。
2. 多模型只要仍有 `RUNNING` 就显示 `REVIEWING`；存在成功结果时按成功 findings 的最高
   `MINOR / MAJOR / CRITICAL` 展示；只有全部失败时显示 `REVIEW_FAILED`。
3. 没有触发 AI Review 显示 `NOT_TRIGGERED`，策略拦截或人工中断显示 `SKIPPED`，规则分析
   等基础链路失败显示 `TASK_FAILED`。
4. 列表筛选使用可重复的 `reviewStatus` 查询参数，支持组合查看多个状态。

## 70. CodeGraph 会被停止维护的 Java 后端同名符号干扰

现象：

CodeGraph 已经索引 Python 主线，但查询任务列表、AI Review 或 GitLab webhook 时仍优先返回
`backend/` 下的 Java 类，容易误把历史实现当成当前代码。

原因：

CodeGraph 会索引 Git 可见文件。旧 Java 后端仍保留在仓库中，并且与 Python 主线存在大量同名
模块和领域概念；只排除 `backend/target/` 不会排除 Java 源码。

处理方式：

1. 根 `.gitignore` 排除整个 `backend/`，让 CodeGraph 聚焦 `backend-python/` 和 `frontend/`。
2. 修改忽略规则后执行 `codegraph.cmd index --force`，不能只执行增量 `sync`。
3. 通过 `codegraph.cmd status` 或 MCP `codegraph_files` 检查语言统计，确认 Java 历史源码不再进入索引。
4. Java 历史代码仍留在工作区；需要对照旧行为时直接按路径读取。

## 71. Codex 沙箱内 PATH 中的 `python.exe` 可能无法直接启动

现象：

在 Codex Windows 沙箱中直接执行 `python -` 或 `python --version`，可能报错：

```text
A specified logon session does not exist. It may already have been terminated
```

原因：

PATH 命中的系统 Python 启动器可能依赖当前沙箱不可用的登录会话。项目自己的
`backend-python/.venv/Scripts/python.exe` 不受该问题影响。

处理方式：

1. 日常启动和测试优先使用 `.\scripts\run-backend.cmd`。
2. 排查脚本行为或执行一次性 Python 命令时，优先使用
   `backend-python\.venv\Scripts\python.exe`。
3. 不要因为 PATH Python 启动失败改动项目依赖或重建虚拟环境；先确认 `.venv` 解释器是否可用。

## 72. 缓存提醒不能把 unified diff 上下文当成变更行

现象：

任务提醒卡片出现 Redis/缓存写入提醒，但展开后显示“暂无可维护内容”。实际新增代码只有
`terminalCacheService.getTypeByImei(...)` 等缓存读取，`put()` 位于 unified diff 未修改上下文。

原因：

缓存 matcher 如果使用整个 diff 判断写入信号，会先因缓存客户端名称进入候选，再被上下文中的
旧 `ehcacheService.put(...)` 误判为本次新增缓存写入。维护内容只从新增行提取，因此提醒项为空。

处理方式：

1. 文件路径和缓存客户端名称只用于筛选候选文件。
2. `set / put / expire / delete / evict`、TTL 和序列化变化必须只在实际新增或删除行中判断。
3. 保留删除行分析，避免删除缓存失效逻辑时漏报一致性风险。

## 73. CodeGraph 静态调用图不能替代 `rg` 和局部源码核验

现象：

CodeGraph 可以快速返回 Python 后端候选模块和调用链，但个别 `codegraph_callers` 查询可能漏掉
真实调用者，`codegraph_trace` 也可能无法跨越异步调度边界。前端模糊语义查询还可能优先返回
后端模型。

原因：

CodeGraph 基于静态索引。动态调用、回调、异步任务、框架 hook 和前端语义召回都存在边界。

处理方式：

1. 从业务逻辑或异常现象排查 Python 后端时，先用 `codegraph_context` 获取候选地图。
2. 已知接口路径、字段名、错误文案、日志或前端请求路径时，优先使用 `rg`。
3. CodeGraph 返回结果必须结合 `rg` 命中和局部源码核验，不作为唯一事实来源。
4. 完整协作策略和实测记录见 `docs/25-codegraph-search-guide.md`。

## 74. Diff 完整上下文不能只依赖任务中保存的 unified diff

现象：

任务详情中的 unified diff 只能展示 GitLab 返回的有限上下文。即使前端给 `@@ ... @@` 增加点击事件，
也无法凭空补出 hunk 之外的完整源码。

原因：

GitLab diff 和模型生成的 patch 都只包含局部上下文。真正展开时需要根据任务保存的历史 refs，
再通过 GitLab Repository Files API 拉取对应版本的完整文件内容。

处理方式：

1. Push 任务使用已有 `before_sha / after_sha`。
2. MR API 补拉时把 `diff_refs.base_sha / head_sha` 保存到 `review_tasks.before_sha / after_sha`。
3. 只允许按任务 `changedFilesSummary.files[]` 中已有路径读取源码，避免接口变成任意仓库文件浏览器。
4. 未配置 GitLab API、Token 缺失、历史 MR 缺 base SHA 或文件超限时保持紧凑 diff，前端隐藏展开入口。
5. 单文件读取限制为 1 MiB、最多 20000 行，避免大文件拖慢页面。

## 75. Codex 沙箱映射路径可能导致 Vite / Rolldown 误判 HTML 输出路径

现象：

在 Codex 沙箱中执行 `.\scripts\run-frontend.cmd build` 时，Vite 可能报错：

```text
The "fileName" or "name" properties of emitted chunks and assets must be strings that are neither absolute nor relative paths
```

错误中的路径指向真实工作区 `D:/projects/.../frontend/index.html`，但脚本日志里的本地 env 路径位于
`C:/Users/CodexSandboxOffline/.codex/.sandbox/cwd/...`。

原因：

沙箱把工作区映射到临时目录，Vite / Rolldown 同时观察到映射路径和真实路径时，可能把 HTML asset
误判为绝对输出路径。该报错不一定是前端代码或 Vite 配置回归。

处理方式：

1. 先确认脚本日志中的工作区是否被映射到 `.codex/.sandbox/cwd/...`。
2. 在用户批准后，于沙箱外使用真实工作区路径重跑同一条 `.\scripts\run-frontend.cmd build`。
3. 只有沙箱外仍失败时，才继续排查前端源码或 Vite 配置。

## 76. Patch 预览展开上下文前必须校验当前源码基线

现象：

AI 修复 Patch 预览可以拿到 GitLab head / Push after 的完整源码，但模型生成 patch 的行号或上下文
可能已经与当前源码不一致。直接把两者拼接会展示错误的上下文位置。

原因：

模型 patch 是基于 prompt 中的代码片段生成的 unified diff。任务保存的源码快照、模型输入范围和模型输出
都可能存在偏差，不能只按 hunk 行号假设 patch 一定可应用。

处理方式：

1. Patch 预览按需读取当前源码后，先逐 hunk 校验行号、声明行数和上下文文本。
2. 校验通过后再应用 patch，生成右侧完整上下文和折叠区。
3. 校验失败时显示非阻断提示，保留原有紧凑 patch，不影响用户查看模型输出。
4. 普通 Diff 同样校验保存的 hunk 与左右源码，避免历史 refs 或变更数据异常时展示错误上下文。

## 77. GitLab changed-files 摘要不能丢失新增、删除和重命名标记

现象：

真实 Push compare 任务中，新增文件调用 `diff-context` 时返回 GitLab raw file 404。GitLab compare
已经给出 `new_file=true`，但保存后的 `changedFilesSummary.files[]` 只剩 `changeType=ADDED`。

原因：

GitLab client 已把 `new_file / deleted_file / renamed_file` 转成 camelCase 布尔标记，但摘要归一化时
没有继续保存这些标记。上下文接口只按布尔标记判断左右侧，导致历史新增文件错误读取 base ref，
历史删除文件错误读取 head ref。

处理方式：

1. 新建 GitLab 摘要时保留值为 `true` 的 `newFile / deletedFile / renamedFile`。
2. 上下文读取兼容历史任务：布尔标记缺失时回退读取 `changeType=ADDED / DELETED / RENAMED`。
3. contract 测试同时覆盖新摘要保留标记和历史摘要仅有 `changeType` 两种格式。
4. 真实联调至少分别调用新增、删除、重命名文件，确认响应为仅右侧、仅左侧、old/new 双侧。

## 78. MR 详情缺少 diff_refs 时要回退读取 diff versions

现象：

真实 GitLab MR 任务可以查看紧凑 Diff，Patch 预览也能按 head commit 拉取源码，但普通 Diff 顶部
没有“展开上下文”。任务详情中 `commitSha` 有值，`beforeSha / afterSha` 仍为空。

原因：

部分 GitLab 实例的 MR 详情接口没有及时返回 `diff_refs`。普通 Diff 展开必须同时知道历史 base 和
head，不能只拿当前 head 猜测左侧基线。原地重跑如果只重算已保存 diff，也不会自动补齐 refs。

处理方式：

1. MR 详情缺少 `diff_refs.base_sha / head_sha` 时，回退调用
   `GET /projects/:id/merge_requests/:iid/versions`。
2. 使用最新 diff version 保存的 `base_commit_sha / head_commit_sha / start_commit_sha`，不要临时读取
   当前目标分支 SHA 冒充历史快照。
3. MR 原地重跑时刷新 refs 和 changed-files 摘要，让旧任务也能获得完整上下文能力。
4. 前端 Diff 双栏代码设置明确的 `tab-size`，避免深层 tab 缩进在窄列中被浏览器默认宽度放大后频繁折行。

## 79. 修复预览 Patch 不应暴露不稳定的上下文展开入口

现象：

普通“查看 Diff”可以展开完整上下文，但 AI 修复 Patch 预览点击“展开上下文”后提示：

```text
Patch 上下文与当前源码不匹配：@@ ...
```

原因：

模型生成 unified diff 时可能给出有偏移的 hunk 行号，或者 Patch 原始上下文本身已经与当前
GitLab head 源码不一致。普通 Diff 可以按保存的历史 refs 展开，但模型 Patch 无法保证能够安全应用。

处理方式：

1. 普通“查看 Diff”继续按需读取 GitLab raw file，并提供上下文展开入口。
2. AI 修复 Patch 预览保持模型返回的紧凑 unified diff，不再展示“展开上下文”按钮。
3. 后端 `viewType=FIX_PREVIEW` 调试接口可以保留，供后续重新设计 Patch 应用策略时使用。
4. 不要为了展示更多行对模型 Patch 做模糊拼接，避免把修改错误贴到相似代码段。

## 80. Diff 主题切换应放在共用代码视图组件

现象：

“查看 Diff”和“AI 修复 Patch 预览”都使用暗黑代码视图，但部分用户需要明亮背景阅读或截图。

处理方式：

1. 主题状态放在前端共用 `ExpandableDiffTable`，避免两个弹窗分别维护样式和交互。
2. 默认使用明亮主题。顶部工具栏始终展示主题按钮：暗黑主题显示太阳图标，明亮主题显示月亮图标。
3. 明亮主题同时覆盖背景、行号、增删行、命中高亮、折叠区和 Prism token 配色。
4. 普通 Diff 的“展开上下文”按钮与主题按钮并排；Patch 预览只展示主题按钮。工具栏按钮本身保持白底、
   蓝色描边和浅蓝 hover，不跟随暗黑代码区使用深色背景。

## 81. GitLab API token 可用不代表 Git HTTP clone 接受 PRIVATE-TOKEN header

现象：

高准确模式已开启 `LOCAL_REPO_CONTEXT_ENABLED=true`，任务 progress 出现 `CONTEXT_PACK_BUILT`，
但本地仓库准备仍失败：

```text
LOCAL_REPO_PREPARE_FAILED
failurePhase=CLONE
localRepositoryStatus=UNAVAILABLE
```

即使 `GITLAB_TOKEN` 已勾选 `api / read_api / read_repository`，用 Git 命令验证时仍可能看到：

```text
remote: The project you were looking for could not be found or you don't have permission to view it.
fatal: repository 'http://.../group/project.git/' not found
```

原因：

GitLab REST API 可以通过 `PRIVATE-TOKEN` header 访问，但部分 GitLab 实例的 Git HTTP clone / fetch
不接受 `PRIVATE-TOKEN` header。Git HTTP 需要使用 Basic Auth 语义，例如用户名 `oauth2`、密码为
access token。只验证 `/api/v4/...` 成功，不能证明 `git clone` 成功。

处理方式：

1. 本地仓库检索的 Git 命令不要把 token 拼进 clone URL，避免命令行、日志和 progress 泄露凭据。
2. 通过 Git 临时 env config 注入：

```text
http.extraHeader = Authorization: Basic base64("oauth2:<token>")
```

3. `GIT_TERMINAL_PROMPT=0` 保持关闭交互式凭据提示，clone / fetch 失败时快速进入
   `LOCAL_REPO_PREPARE_FAILED`。
4. 失败原因需要同时脱敏明文 token、Basic Auth base64、`PRIVATE-TOKEN`、`Authorization` 和 URL 中的凭据。
5. 真实验证优先用同样认证方式执行只读命令：

```powershell
git ls-remote http://gitlab.example.com/group/project.git
```

能列出 refs 后，再重跑任务确认出现 `LOCAL_REPO_PREPARED` 和 `LOCAL_CONTEXT_RETRIEVED`。

## 82. Push 项目仓库 URL 也必须按 GITLAB_BASE_URL 归一化

现象：

高准确模式已启用，任务 progress 出现：

```text
LOCAL_REPO_PREPARE_FAILED
failurePhase=CLONE
localRepositoryStatus=UNAVAILABLE
```

`git ls-remote http://<GITLAB_BASE_URL>/<group>/<project>.git` 使用当前 token 可以成功，
但任务对应项目表里的 `projects.repository_url` 仍是 GitLab webhook payload 中的内部 host，
例如：

```text
http://dc8191653c5a/ljdw/ljdw-ios
```

本机或容器无法解析该 host 时，本地 mirror clone 会失败。

原因：

后端已经有 `_normalize_gitlab_web_url`，会把 webhook payload 中的内部 GitLab Web URL
替换为 `GITLAB_BASE_URL` 的 scheme / host / port。MR 路径使用了归一化后的
`event["repositoryUrl"]` 入库，也有 contract 测试覆盖。但 Push 路径曾经在
`_parse_push_event` 中算出了归一化 URL，随后调用 `upsert_gitlab_project` 时又传回了原始
`repository_url`，导致 `projects.repository_url` 被内部 host 覆盖。后续 AI Review retry
会读取项目表里的旧 URL，所以继续 clone 失败。

处理方式：

1. Push webhook 入库项目时必须传 `event["repositoryUrl"]`，不要传原始 payload URL。
2. Contract 测试需要同时覆盖 MR 和 Push 的 GitLab Web URL 归一化。
3. 排查 `failurePhase=CLONE` 时，先查 `projects.repository_url` 是否已经是可访问的
   `GITLAB_BASE_URL` 地址，再排查 token、权限和 commit 是否可 fetch。
4. 旧任务或旧项目数据不会因为代码修复自动改写；需要下一次同项目 webhook 覆盖，或手动把项目
   `repository_url` 修成可 clone 的公开 / 内网可达地址。

## 83. Windows 本地 worktree 会被仓库中的非法文件名阻断

现象：

高准确模式已启用，项目 `repository_url` 已经正确归一化到可访问的 `GITLAB_BASE_URL`，
mirror remote 也是正确地址，且目标 commit 已存在于 mirror 中，但任务 progress 仍显示：

```text
LOCAL_REPO_PREPARE_FAILED
failurePhase=WORKTREE
localRepositoryStatus=UNAVAILABLE
```

手动复现同一个 worktree checkout 时可能看到：

```text
error: invalid path 'Assets.xcassets/指令/command_?.imageset/Contents.json'
fatal: Could not reset index file to revision 'HEAD'.
```

原因：

Windows 文件系统不允许路径中出现 `?` 等字符。Git mirror 可以正常 clone / fetch，因为对象存储不需要把
每个仓库文件落到工作区；但 `git worktree add` 需要 checkout 完整文件树，只要仓库历史或当前 commit
中存在 Windows 非法文件名，checkout 就会失败。本地仓库上下文检索随后降级为 diff-only，因此前端只会看到
“仓库准备状态 不可用”。

处理方式：

1. 先确认 `projects.repository_url` / mirror remote 是否已是 `GITLAB_BASE_URL` 地址，再区分 URL 问题和
   worktree checkout 问题。
2. 在 Windows 本机直接运行后端时，含非法文件名的仓库无法使用完整 worktree 模式；建议把高准确模式后端运行在
   Linux / WSL / Linux Docker volume 上，或先清理仓库中的非法文件名。
3. 如果必须支持这类仓库，后续应单独设计 sparse checkout、bare repo `git grep` 或按 changed files 的受限
   checkout 方案；不要简单扩大异常忽略范围，因为 `rg` Retriever 依赖可搜索的 task worktree。
4. 当前 progress 摘要出于脱敏和不泄露源码路径考虑，不展示 Git 原始错误；排查时可在受控环境中对同一 mirror
   执行 `git worktree add --detach --force <worktree> <commit>` 获取 Git 原始错误。

## 84. 历史 `LOCAL_REPO_PREPARED` 不代表当前 task worktree 仍存在

现象：

手工删除 `.local/review-workspaces` 后，旧任务详情里的高准确模式仍可能看到历史
`LOCAL_REPO_PREPARED` / `localRepositoryStatus=PREPARED`，但 Retriever 步骤提示不可用或失败。

原因：

仓库准备状态来自当次 AI Review 写入数据库的 progress 摘要；它表示“当时准备成功”。如果任务完成后手工删除
workspace，历史 progress 不会自动回写。Retriever 在执行时会校验当前 task worktree 是否存在，缺失时会降级为
`UNAVAILABLE`，因此同一任务可能出现“历史准备成功”和“当前检索不可用”的表象差异。

处理方式：

1. 新执行的 Context Pack 在 Retriever 校验发现 task worktree 缺失时，会把本地仓库摘要降级为
   `UNAVAILABLE`，`worktreeStatus=MISSING`，避免继续展示为单纯“已准备”。
2. 前端遇到历史 `PREPARED` 但最新 `LOCAL_CONTEXT_RETRIEVE_FAILED` 时，展示为“工作区缺失 / 检索不可用”，不要把它解释为无风险或无引用。
3. 删除 `.local/review-workspaces` 后需要重新触发 AI Review，平台会重新 clone / fetch / checkout；旧任务的历史 progress 只作为排障记录。

## 85. `review-workspaces` 目录为空不一定是清理任务导致

现象：

本地 `.local/review-workspaces/worktrees` 为空，或 Docker 远程部署目录
`/opt/ai-code-review-platform/runtime/review-workspaces/mirrors` 为空，容易误判为后台定时任务把源码缓存清掉。

原因：

当前没有常驻定时清理任务。清理只在准备本地仓库上下文时 best-effort 执行，并且默认只清理过期
`worktrees/{taskId}` 和长期闲置 `mirrors/{projectId}.git`。目录为空更常见的原因是：

1. `LOCAL_REPO_CONTEXT_ENABLED=false`，高准确模式本地仓库上下文未启用。
2. 还没有触发过需要本地仓库上下文的 AI Review。
3. GitLab token、`projects.repository_url`、commit / branch ref 或网络导致 clone / fetch 失败。
4. Docker `LOCAL_REPO_WORKSPACE_HOST_DIR` 指向了另一个宿主机目录。
5. task worktree 已按 `LOCAL_REPO_WORKTREE_RETENTION_HOURS` 清理。

处理方式：

1. 先看任务详情“高准确模式流转”的源码工作区诊断，不要只看宿主机目录。
2. 确认 `LOCAL_REPO_CONTEXT_ENABLED=true`、`GITLAB_TOKEN` 有 `read_repository` 权限，且 `repository_url` 是容器可访问的 `GITLAB_BASE_URL` 地址。
3. 推荐生产配置把 worktree 至少保留 72 小时，把 mirror 至少保留 180 天：

```text
LOCAL_REPO_WORKTREE_RETENTION_HOURS=72
LOCAL_REPO_MIRROR_RETENTION_DAYS=180
```

4. mirror 是项目级源码缓存，建议长期保留；worktree 是 task 级临时 checkout，不建议永久保留。
