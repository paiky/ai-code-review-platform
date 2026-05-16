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
2. 当前阶段已先跳过 `GITLAB_PUSH_WEBHOOK` 审查，避免 MR 合并后目标分支 push 造成重复审查。
3. 后续若重新启用 Push 审查，应优先做项目级分支过滤，例如跳过 `main`、`master`、`release/*`、受保护分支等。

## 4. API Key / Provider 模式没有历史 CLI 的 stdout/stderr 调试链路

现象：

代码质量 Review 使用 API Key / Provider 模式后，执行过程只看到主要 INFO 阶段，看不到历史 CLI 子进程下的 stdout / stderr debug 输出。

原因：

历史 CLI provider 通过本地子进程执行，后端可以读取 stdout / stderr 并记录过程输出。OpenAI、Anthropic、DeepSeek 和自定义 Provider 都是 HTTP 请求，默认没有子进程输出流，因此需要显式记录请求和响应 debug 事件。

处理方式：

1. 非流式模型 Provider 调试应至少记录请求摘要、请求预览、响应摘要、原始响应预览、输出文本预览和解析结果。
2. 不要记录 API Key、Authorization header 等敏感信息。
3. 请求和响应内容需要截断，避免 progress event 过大。
4. 这不是流式输出；流式输出需要单独实现 SSE/event stream 解析。

## 5. Agent 不应绕过 `scripts/` 自行拼编译命令

现象：

新对话或新 Agent 容易直接进入 `backend/` 执行 `mvn test`，或进入 `frontend/` 执行 `npm run build`，导致没有复用仓库已有脚本里的环境准备逻辑。

原因：

项目脚本不仅是启动入口，也封装了本地开发约定：

1. `scripts/run-backend.cmd` 会调用 PowerShell 脚本选择 JDK 21，并加载 `.local/gitlab.env`。
2. `scripts/run-frontend.cmd` 会检查 Node / npm，并在缺少 `node_modules` 时自动安装依赖。
3. Windows 下优先使用 `.cmd` 入口可以减少 Shell、PATH、命令后缀差异。

处理方式：

1. 新对话先读 `AGENTS.md` 和 `README.md`。
2. 后端启动、测试、编译优先使用：

```powershell
.\scripts\run-backend.cmd
.\scripts\run-backend.cmd -q test
.\scripts\run-backend.cmd -q -DskipTests compile
```

3. 前端启动、构建优先使用：

```powershell
.\scripts\run-frontend.cmd
.\scripts\run-frontend.cmd build
```

4. 只有脚本缺少所需能力或脚本本身失败需要定位时，才直接执行底层 `mvn.cmd` / `npm.cmd` 命令，并记录原因。

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
