# Code Quality Review Provider Plan

> 状态说明：本文是早期 Provider 设计文档，编写时以 `CODEX_CLI` / `OPENAI_API` 为主。当前 Python 后端已切换为多 API Provider（OpenAI、Anthropic、DeepSeek、XiaoMIMO、GLM、Custom OpenAI-compatible），MR/Push 自动 Review、进度事件、Push Gate、调度队列与 fix preview 均已落地。现行契约与配置见 `README.md`、`docs/03-api-contract.md` 和设置页；**不要再按本文从零实现 Provider**。

## 1. Goal

Add a code quality review capability without coupling it to the existing change-risk review engine.

The first implementation supports two providers:

| Provider | Status | Notes |
| --- | --- | --- |
| API Providers（OpenAI / Anthropic / DeepSeek / XiaoMIMO / GLM / Custom） | **当前默认** | diff-only HTTP 调用，配置在设置页 |
| `CODEX_CLI` | **历史/停用** | 数据库 seed 可能仍见 legacy 字符串；新版本不再执行 CLI |

Current trigger status:

| Trigger | Status | Notes |
| --- | --- | --- |
| Manual | Implemented | `POST /api/code-quality-reviews/manual` 或 `POST /api/review-tasks/manual` |
| GitLab MR | Implemented | 规则提醒成功后按 profile / 项目组策略异步触发 |
| GitLab Push | Implemented | 经 Push 审核 Gate 与分支策略过滤后触发 |

## 2. Architecture

```text
GitLab / manual trigger
  -> CodeQualityReviewService
  -> CodeQualityReviewProvider
      -> CODEX_CLI provider
      -> OPENAI_API provider
  -> review_tasks: CODE_QUALITY_MANUAL / later MR / later push
  -> code_quality_review_results
  -> later: notification, MR comments
```

This module is intentionally separate from `risk-engine`:

- `risk-engine` explains change impact risk: API / DB / cache / MQ / config.
- `codequality` explains implementation quality risk: correctness, maintainability, security, transactions, concurrency, tests.

## 3. Provider Behavior

### 3.1 `CODEX_CLI`

The backend invokes Codex as a local command.

Windows default command:

```text
cmd.exe /c codex.cmd --sandbox read-only -a never exec review --json --ephemeral -o <output-file> ...
```

Linux default command:

```text
codex --sandbox read-only -a never exec review --json --ephemeral -o <output-file> ...
```

Supported scopes:

| Mode | CLI arguments |
| --- | --- |
| `BASE` | `--base <baseRef>` |
| `COMMIT` | `--commit <sha>` |
| `UNCOMMITTED` | `--uncommitted` |
| `DIFF_TEXT` | fallback to `--uncommitted`; use `OPENAI_API` for raw diff-only review |

Operational notes:

- The backend process must run as the same OS user that has completed `codex login`, or must have access to the same `CODEX_HOME`.
- On Windows, call `codex.cmd` instead of `codex.ps1` to avoid PowerShell execution-policy failures.
- Use `workspace-root` in production-like environments to prevent reviewing arbitrary filesystem paths.
- Manual review stores the provider result on a dedicated `CODE_QUALITY_MANUAL` task.
- MR auto review stores the provider result on the existing MR review task. It first upserts a `RUNNING` result, then updates the same row to `SUCCESS` or `FAILED`.
- Codex CLI auto review requires a local repository checkout. The resolver checks `workspace-root/gitProjectId`, `workspace-root/projectName`, and `workspace-root/repositoryName`.
- Codex CLI Markdown output is preserved in `raw_output` and parsed into structured `findings` when it uses review bullets such as `- High:` or `- Medium:`. Older rows with empty `findings_json` are parsed on read as a compatibility fallback.
- A global database-backed setting controls whether GitLab MR webhooks automatically start AI Review. Manual review and retry remain available while the global MR switch is off.
- Backend startup marks stale `RUNNING` results as `FAILED` after the configured Codex timeout, so reviews interrupted by backend shutdown do not stay running forever.
- Review execution progress is persisted in `code_quality_review_progress_events` and exposed via `GET /api/review-tasks/{taskId}/code-quality-progress`. Codex CLI reviews record repository resolution, command startup, process PID, stdout/stderr lines, exit code, parsing, and result persistence stages.

### 3.2 `OPENAI_API`

The backend calls the OpenAI Responses API with `OPENAI_API_KEY`.

The request uses Structured Outputs with a strict JSON schema:

```json
{
  "summary": "string",
  "overallLevel": "LOW | MEDIUM | HIGH | CRITICAL",
  "findings": [
    {
      "severity": "MINOR | MAJOR | CRITICAL",
      "category": "string",
      "filePath": "string",
      "startLine": 1,
      "endLine": 1,
      "title": "string",
      "body": "string",
      "suggestion": "string",
      "confidence": "LOW | MEDIUM | HIGH"
    }
  ]
}
```

This path is better for service deployments because it does not depend on an interactive Codex CLI login.

## 4. Configuration

```yaml
code-quality:
  review:
    enabled: false
    provider: CODEX_CLI
    workspace-root: ""
    codex:
      command: ""
      model: ""
      timeout-seconds: 600
    openai:
      api-key: ""
      responses-url: https://api.openai.com/v1/responses
      model: gpt-5.4
      timeout-seconds: 120
```

Environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `CODE_QUALITY_REVIEW_ENABLED` | `false` | Enables manual code quality review endpoint |
| `CODE_QUALITY_REVIEW_PROVIDER` | `CODEX_CLI` | `CODEX_CLI` or `OPENAI_API` |
| `CODE_QUALITY_WORKSPACE_ROOT` | empty | Optional allowed repository root |
| `CODEX_CLI_COMMAND` | OS default | Windows defaults to `codex.cmd`, Linux defaults to `codex` |
| `CODEX_CLI_MODEL` | empty | Optional model override |
| `CODEX_CLI_TIMEOUT_SECONDS` | `600` | CLI execution timeout |
| `OPENAI_API_KEY` | empty | API key for `OPENAI_API` provider |
| `OPENAI_RESPONSES_URL` | OpenAI Responses API URL | Override for compatible gateways |
| `OPENAI_CODE_REVIEW_MODEL` | `gpt-5.4` | Model used by API provider |
| `OPENAI_CODE_REVIEW_TIMEOUT_SECONDS` | `1000` | OpenAI API request timeout |
| `ANTHROPIC_CODE_REVIEW_TIMEOUT_SECONDS` | `1000` | Anthropic API request timeout |
| `DEEPSEEK_CODE_REVIEW_TIMEOUT_SECONDS` | `1000` | DeepSeek API request timeout |
| `XIAOMIMO_CODE_REVIEW_TIMEOUT_SECONDS` | `1000` | XiaoMIMO API request timeout |
| `GLM_CODE_REVIEW_TIMEOUT_SECONDS` | `1000` | GLM API request timeout |

单个 Provider 可在设置页“模型 Provider 配置”中覆盖 `timeoutSeconds`；为空时使用对应环境变量默认值。

## 5. Manual Verification

Codex CLI provider:

```powershell
$env:CODE_QUALITY_REVIEW_ENABLED="true"
$env:CODE_QUALITY_REVIEW_PROVIDER="CODEX_CLI"
$env:CODE_QUALITY_WORKSPACE_ROOT="D:\projects"
$env:CODEX_CLI_COMMAND="codex.cmd"
```

Request:

```http
POST /api/code-quality-reviews/manual
Content-Type: application/json

{
  "projectId": 1,
  "profileCode": "backend-default-ai-review",
  "repositoryPath": "D:/projects/ai-code-review-platform",
  "mode": "BASE",
  "baseRef": "origin/main",
  "title": "Manual Codex review",
  "instructions": "Only report actionable correctness, data consistency, or security issues."
}
```

OpenAI API provider:

```powershell
$env:CODE_QUALITY_REVIEW_ENABLED="true"
$env:CODE_QUALITY_REVIEW_PROVIDER="OPENAI_API"
$env:OPENAI_API_KEY="sk-..."
```

Request:

```http
POST /api/code-quality-reviews/manual
Content-Type: application/json

{
  "projectId": 1,
  "profileCode": "backend-default-ai-review",
  "mode": "DIFF_TEXT",
  "title": "Diff-only review",
  "diffText": "+ public void createOrder() { ... }",
  "changedFiles": ["src/main/java/com/demo/OrderService.java"]
}
```

## 6. 项目专用 Profile 管理（2026-10-24）

全局配置动态列出全部启用 Profile（含跨端、API 创建及 SQL 导入记录），提供“复制为新 Profile”，项目配置继续通过同一列表按 `profileCode` 绑定。项目端类型保持真实类型；Profile 与端类型不新增匹配字段，也不改现有“项目绑定优先、端类型默认兜底”的解析逻辑。

### 接口与兼容

- 新增 `POST /api/code-quality-review-profiles`，请求 `{ "sourceProfileCode": "backend-default-ai-review", "profileCode": "project-a-review", "profileName": "项目 A 审查" }`。来源必须存在且启用；编码为字母开头的字母、数字、短横线或下划线，最多 64 字符，名称去首尾空白后为 1–128 字符。复制来源已保存的完整配置，不修改来源，不自动绑定项目；重复编码返回 409 `CONFLICT`，来源不可用返回 400。并发重复由数据库唯一索引保护。
- 继续使用 `PUT /api/code-quality-review-profiles/{profileCode}` 编辑，支持页面更新名称、指令、Provider/模型覆盖。名称和指令不能为空，模型最多 128 字符，Provider 编码最多 64 字符，指令按 UTF-8 编码不得超过 TEXT 的 65535 字节；保留原接口的其它配置字段语义。更新指令同步三个历史指令列。
- 列表、详情、创建、更新响应在现有 Profile VO 上增加 `builtIn: boolean`，由服务端内置定义判断，不增加数据库字段。编码创建后不可编辑；SQL 导入的自定义项同样可编辑。
- 自定义项不展示“恢复默认”，后端维持只有内置定义可恢复的约束。Profile 指令作用于普通和 Agent Review；Provider/模型覆盖沿用普通 Review 原有逻辑，Agent 使用其独立运行配置。
- 不新增数据库迁移、端类型、删除/禁用入口、Prompt 版本管理或分阶段 Prompt；不改通知、触发、队列和执行机制。

### 页面交互与验收

选择 Profile 后可复制，弹窗填写唯一编码和名称，成功后自动选择新项，再编辑并保存 Prompt。复制基于已保存值，存在未保存修改时先提示保存；保存或复制中不允许切换 Profile。复制不影响任何项目，修改共享 Profile 时页面明确提示会影响引用项目的新 Review。普通 Review 的 Prompt 预览仍只预览已保存配置，不表示 Agent 的最终工具指令。

操作入口：设置 → AI Review 配置 → 策略与 Prompt（`/settings/ai-review/policies`）。复制、编辑保存后，前往“项目 / 端类型配置”，重新打开目标项目抽屉并选择新 Profile。原内置 Profile 和既有项目绑定不变；已经通过临时 SQL 创建的 Profile 自动出现在列表中。部署需要同时更新 Backend 和 Frontend，无需执行数据库迁移。

验收按本次约定不新增或运行单元测试，采用 Python 局部 Ruff/语法检查、前端 build、隔离环境接口与页面手动验收。检查动态列表、复制及重名拒绝、编辑名称和 Prompt、内置恢复与自定义隐藏、项目重新打开后可选择新项，以及请求组装保留所选指令。使用已有数据/隔离数据，不在生产库创建验收 Profile，不触发付费 Provider 或真实通知。

实施与验收记录（2026-10-24）：上述接口和 UI 已实现；改动四个 Python 模块的 Ruff/AST 检查、`scripts/run-frontend.ps1 build`、`git diff --check` 通过。手动使用 ASGITransport 与内存 SQLite 验收真实接口：全部配置复制、重名 409、非法编码/空名称/空指令/超长 UTF-8 指令拒绝、三个指令字段同步、原 Profile 不变、自定义/跨端列表可见、内置恢复、自定义恢复拒绝、项目 A 保存并重读新绑定而项目 B 保持原值、普通/Agent Prompt 组装及已保存预览均通过。应用 lifespan、Worker、真实 Provider 和通知未启动，未连接生产库，未新增或运行单元测试。页面已构建，未执行真实浏览器交互复验或付费模型执行。现有 lint 脚本固定附带全目录 `.` 扫描，另报告四处无关历史 unused import/variable，故使用同一 Python 环境对改动文件单独运行 Ruff 并通过，未修改无关文件。

## 7. 后续方向（历史记录）

以下条目在编写本文时为待办；**当前大多已完成**，仅作演进参考：

1. ~~Persist `CodeQualityReviewResult` in a dedicated table.~~ 已完成。
2. ~~Add a task type or sub-result linked to existing `review_tasks`.~~ 已完成。
3. ~~Add a frontend tab for quality findings.~~ 已完成。
4. Publish actionable findings back to GitLab MR discussions. **仍未实现**。
5. ~~Add queue / concurrency control for long-running reviews.~~ 已完成调度队列。
6. ~~Enable Push AI review behind branch, diff size, debounce, and risk-match policies.~~ 已完成 Push Gate。
