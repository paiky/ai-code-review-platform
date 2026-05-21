# 本地开发避坑记录

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
```

原因：

前端 `package.json` 如果使用 `latest`，Docker 镜像内执行 `npm ci` 时可能按当前 registry 最新解析依赖，而 `package-lock.json` 仍锁定旧解析结果，导致二者不一致。打包脚本中的 Docker 子命令如果没有显式检查退出码，还可能在镜像构建失败后继续执行 `docker save` 并误报打包成功。

处理方式：

1. 顶层前端依赖应固定明确版本，不要使用 `latest`。
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

## 14. Python AI Review 阶段 4 通过 mock 不等于已对齐 Java 行为

现象：

Python 后端阶段 4 的 AI Review API、Provider mock 测试都能通过，但真实使用时效果仍弱于 Java 后端，例如默认审核规则过短、执行过程缺少请求/响应/解析调试信息、GitLab MR 自动 AI Review 完成后没有按 Java 逻辑发送合并的“变更审查结果”通知。

原因：

阶段 4 的验收重点是 Provider API、settings/profile/provider 接口、结果落库和基础脱敏；这只能证明“能调用模型并保存结果”，不能证明已经完整复刻 Java 后端后续补强过的真实可用性逻辑。

处理方式：

1. 对照 Java `codequality` 包时，不只看 Controller/API，还要同时核对 `CodeQualityAutoReviewService`、`CodeQualityAsyncReviewExecutor`、Provider progress debug、默认 prompt migration 和 `DingTalkNotifier.sendReviewSummary`。
2. Python AI Review 至少应覆盖：强默认 prompt、请求/响应/输出预览 progress、Provider 失败落成 `FAILED`、MR 自动触发后的合并通知记录。
3. 规则提醒主链路也不能只看样例测试通过；需要确认风险规则来源、模板加载、聚合类型匹配、focus indicator 和钉钉过滤是否与 Java 保持一致。

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
3. 长期仍建议通过 Java 后端启动一次 Flyway，让正式 schema 迁移记录保持完整；Python 的运行时补齐只作为本地重构期兼容保护。

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
3. 只有改到 webhook -> 分析 -> 风险卡片 -> 通知 -> 落库主链路、共享模型、数据库兼容、通知发送或跨模块边界时，才执行 `.\scripts\run-backend.cmd test` 全量 Python 测试。
4. Java 后端 `backend/` 已停止维护，默认不再执行 Maven 编译或测试；只有用户明确要求对照历史 Java 行为时才读取或运行。
5. 最终结论中说明“为什么选择这组验证”，避免把全量测试当作无脑默认动作。

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

`scripts/run-backend-python.ps1` 改成本地默认 `18080` 后，后端能启动，但前端页面仍然请求 `8080`，表现为接口 404 / 代理失败 / 页面数据不刷新。或者相反，前端已经代理到 `18080`，但后端仍跑在 `8080`。

原因：

Python 后端本地脚本、`app.core.config` 默认端口、前端 `VITE_API_PROXY_TARGET` 默认值和 README 本地示例需要成组维护。只改其中一个会让开发环境出现“服务是好的，但前端打错端口”的假故障。

处理方式：

1. 本地 Python 后端默认端口使用 `18080`，避免常见的 `8080` 占用。
2. `scripts/run-frontend.ps1` 默认代理到 `http://localhost:18080`。
3. 如果当前 `18080` 已经有一个 Python 后端监听，重复启动第二个后端仍会端口冲突；先停掉旧进程，或显式传 `--port` 使用其他端口。
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
