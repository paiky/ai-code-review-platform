# Code Quality Review Provider Plan

> 状态说明：本文是早期 Provider 设计文档，编写时以 `CODEX_CLI` / `OPENAI_API` 为主。当前 Python 后端已切换为多 API Provider（OpenAI、Anthropic、DeepSeek、XiaoMIMO、Custom OpenAI-compatible），MR/Push 自动 Review、进度事件、Push Gate、调度队列与 fix preview 均已落地。现行契约与配置见 `README.md`、`docs/03-api-contract.md` 和设置页；**不要再按本文从零实现 Provider**。

## 1. Goal

Add a code quality review capability without coupling it to the existing change-risk review engine.

The first implementation supports two providers:

| Provider | Status | Notes |
| --- | --- | --- |
| API Providers（OpenAI / Anthropic / DeepSeek / XiaoMIMO / Custom） | **当前默认** | diff-only HTTP 调用，配置在设置页 |
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

## 6. 后续方向（历史记录）

以下条目在编写本文时为待办；**当前大多已完成**，仅作演进参考：

1. ~~Persist `CodeQualityReviewResult` in a dedicated table.~~ 已完成。
2. ~~Add a task type or sub-result linked to existing `review_tasks`.~~ 已完成。
3. ~~Add a frontend tab for quality findings.~~ 已完成。
4. Publish actionable findings back to GitLab MR discussions. **仍未实现**。
5. ~~Add queue / concurrency control for long-running reviews.~~ 已完成调度队列。
6. ~~Enable Push AI review behind branch, diff size, debounce, and risk-match policies.~~ 已完成 Push Gate。
