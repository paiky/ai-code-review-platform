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

## 4. API Key 模式默认没有 Codex CLI 的 stdout/stderr 调试链路

现象：

代码质量 Review 使用 OpenAI API Key 后，执行过程只看到主要 INFO 阶段，看不到之前 Codex CLI 下的详细 debug 输出。

原因：

`CODEX_CLI` 通过本地子进程执行，后端可以读取 stdout/stderr 并记录 `CODEX_OUTPUT`。`OPENAI_API` 是一次 HTTP 请求，默认没有子进程输出流，因此需要显式记录请求和响应 debug 事件。

处理方式：

1. OpenAI 非流式调试应至少记录请求摘要、请求预览、响应摘要、原始响应预览、输出文本预览和解析结果。
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
