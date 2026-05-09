# AI Review Prompt 与运行环境排查方案

日期：2026-05-09

## 1. 当前排查结论

### 1.1 当前 AI Review 审核规则来自哪里

代码质量 AI Review 当前由 `code_quality_review_profiles` 驱动，核心字段如下：

- `provider`：选择 `CODEX_CLI` 或 `OPENAI_API`。
- `model`：profile 级模型覆盖；为空时使用环境配置中的默认模型。
- `trigger_on_manual`：是否允许手动触发。
- `trigger_on_mr`：是否允许 GitLab MR webhook 自动触发。
- `trigger_on_push`：当前预留给 push 阶段 AI Review。
- `enabled_categories`：结构化分类白名单，目前用于 profile 描述和后续扩展。
- `ignored_paths`：忽略路径配置，目前需要继续落到 provider 请求过滤。
- `codex_prompt`：给 Codex CLI 的代码质量审核 prompt。
- `openai_instructions`：给 OpenAI API provider 的审核指令。

后端已经有 profile 查询和更新接口：

```http
GET /api/code-quality-review-profiles
GET /api/code-quality-review-profiles/{profileCode}
PUT /api/code-quality-review-profiles/{profileCode}
```

所以“编辑 prompt”在后端能力上已经具备；当前缺口是前端还没有提供专门的 profile/prompt 编辑页面，也没有 prompt 预览、恢复默认、测试运行等辅助能力。

### 1.2 当前 Codex CLI prompt 拼装方式

MR 自动触发时：

1. 系统根据项目绑定的 `default_code_quality_profile_code` 找到 profile。
2. `CODEX_CLI` 使用 `profile.codexPrompt()` 作为 `CodeQualityReviewRequest.instructions`。
3. `CodexCliCommandFactory` 如果发现 `instructions` 不为空，会走：

```text
codex exec --json --ephemeral -o <outputFile> -m <model> <prompt>
```

4. `<prompt>` 由英文 wrapper + profile prompt + 英文尾部约束组成：

```text
Run a code quality review for the current repository.

Scope:
...

Review instructions:
<profile.codexPrompt>

Return concise, actionable findings in Simplified Chinese...
```

当前 profile 的默认 `codexPrompt` 已经是中文；用 Node 直接按 UTF-8 拉接口确认，profile prompt 和进度里的 `CODEX_COMMAND` 记录都能看到正常中文。

### 1.3 Windows 下乱码的初步判断

目前看到两类乱码，需要区分：

- PowerShell 查询 API 时出现的乱码：例如作者名、中文 prompt 在 PowerShell 输出里显示为 `å...`。这主要是 PowerShell/终端输出编码问题，不代表 API 或数据库一定是坏的。
- Codex 执行过程中 `CODEX_OUTPUT` 里的乱码：例如 Codex 内部调用 Windows PowerShell 执行 `Get-ChildItem`、`rg --files`、`Get-Content` 后，中文文件名和中文源码内容在 aggregated output 里变成乱码。这更接近 Windows 子进程编码问题。

Linux 环境下通常默认 UTF-8，第一类和第二类问题出现概率会显著降低。但如果被审查仓库里的某些源码文件本身是 GBK/ANSI 编码，Linux 直接按 UTF-8 读取仍可能乱码。因此 Linux/WSL 可以解决大部分 shell/文件名/管道编码问题，但不能自动修复源码文件原始编码不统一的问题。

### 1.4 最新 MR 首轮仍然英文的原因判断

最新任务 `taskId=35` 的 AI Review 状态是 `SUCCESS`，Codex CLI 被成功调用，最终 raw output 是英文：

```text
**Findings**

1. High: ...
2. High: ...
3. Medium: ...
4. Medium: ...
```

这不是前端单纯误判；前端只是检测到 findings 主要是英文后显示“当前结果包含英文内容”。

目前最可能的原因有三个：

1. Windows `cmd.exe /c codex.cmd` 对长中文参数的实际传递不够可靠。即使 Java 侧记录的 command detail 是正常中文，真正进入 `cmd.exe` / `codex.cmd` 的参数仍可能受代码页影响。
2. 当前 prompt wrapper 以英文开头，尾部中文要求也是英文表述，Codex 容易沿用默认 code review 的英文 `Findings / High / Medium` 格式。
3. 当前没有对输出语言做后置校验。只要 Codex 返回成功，系统就保存结果；即使输出是英文，也不会自动重试或标记为“语言不符合要求”。

结论：这和字符集有关，但不只是字符集。需要同时解决“prompt 传递稳定性”和“输出语言强约束/校验”。

## 2. 目标行为

后续希望达到：

1. 用户可以在前端编辑每个 AI Review profile 的 prompt。
2. Codex CLI 在 Windows/Linux 下都能稳定收到中文 prompt。
3. Windows 原生模式可用；如用户配置 WSL2，也可以让 Codex 在 WSL2/Linux 环境中运行。
4. 首轮 MR 自动 AI Review 就应该输出中文结构化结果，不需要用户手动重试。
5. 如果 AI 输出语言不符合要求，系统应能明确展示原因，并可自动按策略重试一次。
6. 过程日志应保留可读信息，但避免泄露 API Key、token、完整密钥等敏感内容。

## 3. 拟定落地方案

### P0：确认和修复 prompt 可观测性

新增或增强以下可观测信息：

- 在 AI Review 过程事件中记录：
  - `profileCode`
  - `provider`
  - `model`
  - `repositoryPath`
  - `promptHash`
  - `promptLength`
  - `promptPreview`，只保留前 200 字并做敏感信息脱敏
  - `runtimeMode`，如 `WINDOWS_NATIVE` / `LINUX_NATIVE` / `WSL`
  - `commandPreview`，避免记录完整超长 prompt
- 前端“执行过程”展示上述信息，让用户知道本轮到底用了哪个 profile/prompt/model/runtime。

预期收益：后续再出现英文输出时，可以快速判断是 profile 没生效、prompt 没传到、还是模型没有遵守。

### P1：支持前端编辑 AI Review prompt

在“模板配置”或新增“AI Review Profile”页面中增加：

- Profile 列表。
- 基础字段展示：provider、model、triggerOnMr、triggerOnManual。
- `codexPrompt` 文本域编辑。
- `openAiInstructions` 文本域编辑。
- 保存按钮，调用现有：

```http
PUT /api/code-quality-review-profiles/{profileCode}
```

- 恢复默认按钮。
- Prompt 预览按钮：展示实际拼装后的最终 prompt。
- 测试运行按钮：对指定任务或简短 diff 发起一次手动 AI Review。

后端可补充：

- `GET /api/code-quality-review-profiles/{profileCode}/rendered-prompt?taskId=...`
- `POST /api/code-quality-review-profiles/{profileCode}/reset-default-prompt`

### P2：改造 Codex prompt 传递方式，避免 Windows 长中文命令行参数

当前将完整 prompt 作为命令行参数传给 `codex exec`。Windows 下这条路径风险较高。

建议改为：

1. 后端把最终 prompt 写入 UTF-8 临时文件，例如：

```text
codex-review-prompt-<taskId>.md
```

2. 命令行只传 ASCII 短 prompt：

```text
Please read the UTF-8 review instructions from <promptFile> and follow them exactly. Return the final review in Simplified Chinese only.
```

3. 过程事件记录 prompt 文件路径、hash、长度，不记录完整 prompt。
4. Codex CLI 输出文件仍使用 `-o <outputFile>`。

该方案的重点是避开 Windows `cmd.exe` 对长中文 argv 的处理，让中文内容通过 UTF-8 文件传递。

### P3：改造 prompt 模板，中文优先并约束格式

将最终 prompt 改成中文优先：

```text
你是代码质量审核助手。请只审查本次变更，不要修改文件。

审查范围：
...

用户自定义审核规则：
...

输出要求：
1. 必须使用简体中文。
2. 每个问题必须以“高风险：”“中风险：”或“低风险：”开头。
3. 每个问题尽量包含文件路径和行号。
4. 不要输出英文标题，例如 Findings、Residual Risks、Assumptions。
5. 不要报告纯代码风格问题。
```

同时保留英文兼容说明可以放到很短的最后一行，而不是作为主语言。

### P4：新增输出语言校验和自动重试策略

后端保存 Codex 结果前做语言检测：

- 如果 structured findings 的标题/body 中英文占比过高，标记 `language=MOSTLY_ENGLISH`。
- 如果 profile 要求中文且结果是英文：
  - 方案 A：保存为 `FAILED`，错误信息说明“输出语言不符合 profile 要求”。
  - 方案 B：自动重试 1 次，追加更强指令：“上一次输出是英文，本次必须全部使用简体中文。”

建议 MVP 采用方案 B，最多自动重试一次，避免额度失控。

前端展示：

- 如果自动重试后仍英文，显示明确原因。
- 不再用“这是旧一轮输出”这种固定描述，因为现在英文也可能来自最新一轮。

### P5：Windows 原生编码治理

Windows native 模式下建议做以下增强：

- `ProcessBuilder.environment()` 设置：
  - `PYTHONUTF8=1`
  - `PYTHONIOENCODING=utf-8`
  - `JAVA_TOOL_OPTIONS=-Dfile.encoding=UTF-8`
  - `LANG=C.UTF-8`
  - `LC_ALL=C.UTF-8`
- 对 Codex CLI stdout/stderr 继续按 UTF-8 读取。
- 过程日志中对 Codex 内部 `command_execution.aggregated_output` 做截断和脱敏。
- 如果仍需经过 `cmd.exe /c`，使用 `/d /s /c`，并评估是否可改为直接执行 `codex.cmd`。

注意：这能改善一部分输出，但 Codex 内部调用 Windows PowerShell 时的中文输出仍可能受 PowerShell 版本、控制台代码页、被读文件编码影响。

### P6：支持 WSL2 / Linux-like Codex 运行环境

新增配置：

```properties
CODEX_CLI_RUNTIME=NATIVE
CODEX_CLI_WSL_DISTRO=Ubuntu
CODEX_CLI_WSL_WORKSPACE_ROOT=/mnt/d/projects
CODEX_CLI_WSL_CODEX_COMMAND=codex
```

运行模式：

- `NATIVE`：当前系统原生运行。
  - Windows：`cmd.exe /c codex.cmd ...`
  - Linux：`codex ...`
- `WSL`：Windows 后端通过 `wsl.exe` 启动 Linux 环境中的 Codex。
  - 命令形态：

```text
wsl.exe -d Ubuntu -- bash -lc 'cd /mnt/d/projects/<repo> && codex ...'
```

需要新增路径映射：

- Windows repo path：`D:\projects\ljdw-client-internal`
- WSL repo path：`/mnt/d/projects/ljdw-client-internal`
- Windows temp prompt/output 文件也需要映射到 WSL 可访问路径，或直接创建在 workspace 下的 `.ai-review/tmp`。

使用 WSL 的前置条件：

- WSL 内已安装 Codex CLI。
- WSL 内已完成 `codex login`，或者配置了可用的 API key。
- WSL 能访问对应仓库和 git refs。

WSL 的收益：

- 默认 UTF-8 环境，中文文件名和 shell 输出更稳定。
- 行为更接近 Linux CI/服务器环境。
- 后续迁移到 Linux 部署时更平滑。

### P7：敏感信息脱敏

最新 AI Review 已经指出仓库中存在明文密钥。后续过程日志如果记录 `rg` 输出，可能会把密钥写进平台数据库。

需要增加脱敏：

- 对 `password`
- `accessKeyId`
- `accessKeySecret`
- `token`
- `secret`
- `apiKey`
- `Authorization`

做统一 masking，例如：

```text
accessKeySecret: ****
token: ****
```

脱敏应作用于：

- progress event detail
- rawOutput 展示
- command preview
- error message

## 4. 建议实施顺序

1. P0：先增强 prompt/runtime 可观测性，避免继续盲查。
2. P2 + P3：把 prompt 改为 UTF-8 文件传递，并改为中文优先模板。
3. P4：增加输出语言校验和最多一次自动重试。
4. P1：补前端 profile/prompt 编辑页面。
5. P5：优化 Windows native 环境变量和命令启动。
6. P6：新增 WSL runtime。
7. P7：补全脱敏策略。

## 5. 对四个问题的直接回答

### Q1：现在的 AI Review 审核规则是怎样的？是否支持编辑 prompt？

规则来自 profile 表，当前默认 profile 关注线上缺陷、数据一致性、安全、事务、SQL 性能、缓存一致性、MQ 一致性、异常处理和测试缺口，不报告纯风格问题。后端已经支持通过 `PUT /api/code-quality-review-profiles/{profileCode}` 编辑 prompt；前端“模板配置”页已经提供 profile / prompt 编辑入口，并把执行方式作为全局设置切换 `CODEX_CLI`、`OPENAI_API`、`ANTHROPIC_API`。

### Q2：Windows PowerShell 乱码在 Linux 上是否不会存在？

Linux/WSL 默认 UTF-8，通常不会出现 Windows PowerShell 这类输出乱码。但如果仓库文件本身是 GBK/ANSI 编码，Linux 仍可能读出乱码。也就是说，Linux 能解决大部分运行环境编码问题，但不能保证修复所有源码文件编码问题。

### Q3：Windows 下能否让 Codex 子进程运行在类似 Linux 的 WSL2？

可以。需要后端支持 `CODEX_CLI_RUNTIME=WSL`，通过 `wsl.exe -d <distro> -- bash -lc ...` 启动 WSL 内的 Codex，并实现 Windows/WSL 路径映射。WSL 内需要单独安装 Codex CLI 并完成登录授权或配置 API key。

### Q4：为什么最新 MR 首轮还是英文？和字符集有关吗？

最新结果确实是 Codex 返回了英文，不是前端单纯误判。当前 profile prompt 在 API 层是中文，但 Windows 原生命令行参数、Codex 默认英文 review 习惯、以及当前英文 wrapper 都可能导致中文约束没有稳定生效。因此它和字符集有关，但不是唯一原因。后续应通过 UTF-8 prompt 文件、中文优先模板、输出语言校验和自动重试来闭环。
