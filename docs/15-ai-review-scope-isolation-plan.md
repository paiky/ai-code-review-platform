# AI Review 审查范围隔离方案

日期：2026-05-10

## 1. 背景

最新 GitLab MR !371 的代码质量 AI Review 出现了范围污染：

AI 输出了一个关于 `RabbitMqBindingConfig.java` 的 MQ 一致性问题：

```text
src/main/java/com/swd/ljdw/client/config/rabbitmq/RabbitMqBindingConfig.java:563-566
把绑定/解绑事件错误地绑定到了 kiteCallbackQueue()/kiteCallbackExchange()
```

但平台规则分析中保存的 GitLab MR changed files 只有 35 个，里面没有：

```text
src/main/java/com/swd/ljdw/client/config/rabbitmq/RabbitMqBindingConfig.java
src/main/java/com/swd/ljdw/client/service/impl/ToClientUserCarBoundServiceImpl.java
src/main/java/com/swd/ljdw/client/listener/rabbitmq/BindEventQueueListener.java
```

这说明 CODEX_CLI provider 实际审查范围与 GitLab MR payload / GitLab API 拉到的 changed files 不一致。

## 2. 追溯证据

任务：

```text
taskId=50
project=client/ljdw-client-internal
triggerType=GITLAB_MR_WEBHOOK
MR=!371
sourceBranch=feat/app-refund
targetBranch=master
provider=CODEX_CLI
```

平台规则分析接口：

```http
GET /api/review-tasks/50/result
```

结果中：

```text
changedFileCount=35
changeAnalysis.changedFiles 不包含 RabbitMqBindingConfig.java
```

AI Review 过程接口：

```http
GET /api/review-tasks/50/code-quality-progress
```

关键日志：

```text
id=814
phase=REQUEST_BUILT
detail=profileCode=backend-default-ai-review, provider=CODEX_CLI, model=null, mode=BASE, baseRef=origin/master, changedFiles=35

id=816
phase=CODEX_REPOSITORY
detail=D:\projects\ljdw-client-internal

id=832
phase=CODEX_OUTPUT
command=git rev-parse --abbrev-ref HEAD
aggregated_output=merge_tmp_241

id=833
phase=CODEX_OUTPUT
command=git diff --name-only origin/master...HEAD
aggregated_output 包含 src/main/java/com/swd/ljdw/client/config/rabbitmq/RabbitMqBindingConfig.java

id=913
phase=CODEX_OUTPUT
读取了 RabbitMqBindingConfig.java:550-570

id=924
phase=CODEX_OUTPUT
读取了 ToClientUserCarBoundServiceImpl.java:418-432

id=928
phase=CODEX_OUTPUT
读取了 BindEventQueueListener.java:37-42

id=931
phase=CODEX_OUTPUT
基于上述文件输出 MQ 一致性问题
```

结论：

```text
Codex 不是基于平台保存的 GitLab MR changed files 审查，
而是在本地仓库 D:\projects\ljdw-client-internal 中自行执行 git diff origin/master...HEAD。
当本地仓库 HEAD 是 merge_tmp_241 时，审查范围扩大到了不属于当前 MR changed files 的内容。
```

## 3. 当前代码原因

### 3.1 GitLab MR 自动 Review 会构造 changedFiles 和 diffText

位置：

```text
backend/src/main/java/com/leaf/codereview/codequality/application/CodeQualityAsyncReviewExecutor.java
```

当前 `buildRequest` 会从 `event.changedFilesSummary()` 中构造：

- `diffText`
- `changedFiles`

但当 provider 是 `CODEX_CLI` 时：

```java
CodeQualityReviewMode mode = provider == CodeQualityReviewProviderType.CODEX_CLI
        ? CodeQualityReviewMode.BASE
        : CodeQualityReviewMode.DIFF_TEXT;
```

也就是说 API provider 使用 `DIFF_TEXT`，而 Codex CLI 使用本地仓库 `BASE` 模式。

### 3.2 Prompt 文件模式下没有传递结构化 git scope 参数

位置：

```text
backend/src/main/java/com/leaf/codereview/codequality/infrastructure/CodexCliCommandFactory.java
```

当前逻辑：

```java
if (promptFile != null) {
    command.add(shortPrompt(promptFile));
    return command;
}

command.add("review");
addReviewScope(command, request);
```

使用 prompt 文件后，命令不会追加：

```text
review --base origin/master
```

最终命令类似：

```text
codex.cmd --sandbox read-only -a never exec --json --ephemeral -o <output> -m gpt-5.4 "Please read the UTF-8 review instructions from <promptFile>..."
```

Codex 读取 prompt 后自行决定执行：

```text
git diff --name-only origin/master...HEAD
```

### 3.3 本地仓库状态未校验

当前只确认 `repositoryPath` 是目录，并在 `workspaceRoot` 下。

没有校验：

- 当前分支是否等于 MR source branch。
- 当前 HEAD 是否等于 MR commitSha。
- 当前仓库是否有未提交变更。
- 当前 `origin/master...HEAD` 是否与 GitLab changed files 一致。
- 本地仓库是否处在临时 merge 分支，例如 `merge_tmp_241`。

## 4. 目标行为

后续 CODEX_CLI 自动 Review 必须满足：

1. AI Review 的有效审查范围必须与平台任务保存的 GitLab changed files / diff 一致。
2. 本地仓库状态不可信时，不允许静默扩大范围。
3. 如果需要读取上下文文件，允许读取，但不能把非 changed files 中的历史问题作为本轮 finding 输出。
4. 过程日志必须明确展示：
   - 平台 changed files 数量。
   - Codex 实际 git diff 文件数量。
   - 两者是否一致。
   - 当前本地分支。
   - 当前 HEAD。
   - MR commitSha。
5. 如果范围不一致，默认应失败或降级到 API diff 模式，而不是保存污染结果。

## 5. 推荐方案

### 5.1 短期优先方案：范围预检 + Prompt 强约束

在 CODEX_CLI 调用前增加本地仓库 scope preflight：

```text
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git diff --name-only <baseRef>...HEAD
```

与平台保存的 `request.changedFiles` 对比。

如果不一致：

- 记录 `SCOPE_MISMATCH` progress event。
- 默认将本轮 AI Review 标记为 `FAILED`。
- 错误信息说明：

```text
CODEX_CLI local git diff scope does not match GitLab changed files.
```

同时 prompt 中加入 changed files 白名单：

```text
本轮 GitLab 变更文件白名单：
...

输出限制：
你可以读取相关上下文文件辅助理解，但最终只能报告白名单文件中的变更引入的问题。
如果问题需要引用上下文文件，必须说明它如何由白名单文件的 diff 触发。
不要报告只存在于上下文文件或本地其它分支中的历史问题。
```

适合先落地，因为改动较小，可快速阻断范围污染。

### 5.2 中期方案：Codex CLI 使用平台 diff 文件

将 `request.diffText` 写入 UTF-8 临时文件：

```text
codex-review-diff-<taskId>.patch
```

Prompt 中明确要求：

```text
本轮审查的唯一变更来源是 diff 文件：<diffFile>
只能审查 diff 文件中的新增和修改内容。
```

Codex 可在本地仓库中读取上下文，但不再自行决定 `origin/master...HEAD` 范围。

优点：

- 和 GitLab API 拉到的 diff 保持一致。
- 不依赖本地仓库分支是否正确。
- 仍可让 Codex 读取项目上下文。

风险：

- 如果 diff 很大，prompt / 文件读取成本较高。
- Codex 是否严格只看 diff 文件，仍需靠 prompt 和结果校验兜底。

### 5.3 长期方案：临时 worktree / checkout 到 MR commit

为每次 AI Review 创建独立 worktree：

```text
git fetch origin <sourceBranch>
git worktree add <tmp-dir> <commitSha>
```

在独立 worktree 中执行 Codex。

要求：

- HEAD 必须等于 MR commitSha。
- baseRef 必须存在并已 fetch。
- Review 结束后清理 worktree。

优点：

- 隔离本地开发分支、临时 merge 分支和未提交文件。
- 最接近 CI 环境。

风险：

- 实现复杂度更高。
- 需要处理 fetch 权限、磁盘清理、并发任务、Windows 路径和锁文件。

## 6. 分阶段改动点

### Phase 1：增加 CODEX_CLI 范围预检

目标：发现范围污染并阻断保存污染结果。

后端新增：

- `CodeQualityGitScope`
- `CodeQualityGitScopePreflight`
- `CodeQualityScopeMismatchException`

预检逻辑：

```text
1. 在 repositoryPath 中执行 git rev-parse --abbrev-ref HEAD。
2. 执行 git rev-parse HEAD。
3. 执行 git diff --name-only <baseRef>...HEAD。
4. 将本地 diff 文件列表与 request.changedFiles 比较。
5. 如果本地多出或缺少文件，返回 mismatch。
```

匹配规则：

- 路径统一 `/`。
- 去掉首尾空白。
- 大小写敏感，除非后续明确支持 Windows case-insensitive。
- 排除空路径。

允许配置：

```yaml
code-quality:
  review:
    codex:
      scope-check-enabled: true
      fail-on-scope-mismatch: true
      allow-context-files: true
```

默认建议：

```text
scope-check-enabled=true
fail-on-scope-mismatch=true
```

progress event：

```text
CODEX_SCOPE_CHECK
detail=branch=merge_tmp_241, head=<sha>, baseRef=origin/master, platformChangedFiles=35, localChangedFiles=120

CODEX_SCOPE_MISMATCH
detail=extra=[RabbitMqBindingConfig.java,...], missing=[...]
```

验收：

- 当本地 `git diff --name-only origin/master...HEAD` 与平台 changed files 不一致时，AI Review 结果为 `FAILED`。
- 页面能看到失败原因。
- 不再保存 Codex 输出的污染 finding。

### Phase 2：Prompt 注入 changed files 白名单

目标：即使范围一致，也让 Codex 明确知道最终输出边界。

改动：

- `CodeQualityReviewRequest` 增加或复用 `changedFiles`。
- `CodexCliCommandFactory.renderPrompt` 增加“本轮变更文件白名单”。
- API provider instructions 也增加同样约束。

示例：

```text
本轮变更文件白名单：
1. src/main/java/...
2. src/main/resources/...

输出限制：
你可以读取上下文文件辅助理解，但最终只能报告由白名单文件 diff 引入的问题。
不要报告只存在于上下文文件、历史代码或本地其它分支中的问题。
```

验收：

- prompt metadata preview 中能看到 changed files 白名单摘要。
- Codex 输出非白名单文件时，后端能识别并标记为疑似越界。

### Phase 3：结果后置校验

目标：防止模型仍然输出越界 finding。

做法：

- 解析 finding 中的文件路径。
- 如果 finding 只引用非 changed files，标记为 `OUT_OF_SCOPE`。
- 默认不计入有效 finding。
- 前端可展示“疑似越界结果”折叠区。

第一阶段可用简单正则提取：

```text
`src/...`
src/main/java/...
```

后续再做结构化 finding 字段增强。

验收：

- 像 `RabbitMqBindingConfig.java` 这种非平台 changed files 的 finding 不再作为有效质量问题展示。
- 原始输出仍可追溯。

### Phase 4：支持平台 diff 文件输入

目标：让 CODEX_CLI 不再依赖本地 `origin/master...HEAD` 来确定变更。

改动：

- `CodexCliCodeQualityReviewProvider` 写入 `diffText` 到临时 diff 文件。
- Prompt 中加入 diff 文件路径。
- 过程事件记录：
  - `diffFile`
  - `diffHash`
  - `diffLength`
  - `changedFiles`

验收：

- 本地仓库分支不匹配时，仍可选择使用平台 diff 文件审查。
- 审查结果不包含 diff 文件之外的历史问题。

### Phase 5：临时 worktree 隔离

目标：从根上隔离本地仓库状态。

改动：

- 新增 `CODEX_CLI_WORKTREE_MODE=DISABLED|TEMP_WORKTREE`。
- 自动 fetch MR source commit。
- 创建临时 worktree。
- 在 worktree 中执行 Codex。
- 任务结束清理。

验收：

- 多个 AI Review 并发运行互不影响。
- 当前开发者工作区未提交变更不会进入 AI Review。

## 7. API 和前端展示改动

### 7.1 Progress 展示

执行过程建议展示新阶段：

- `范围预检`
- `范围一致`
- `范围不一致`
- `平台变更文件数`
- `本地 diff 文件数`

范围不一致时展示：

```text
本地 Codex 审查范围与 GitLab MR changed files 不一致，本轮已阻断。
本地分支：merge_tmp_241
平台文件数：35
本地文件数：120
多出的文件：RabbitMqBindingConfig.java ...
```

### 7.2 Code Quality Result 展示

如果状态为 `FAILED` 且错误类型是 scope mismatch：

```text
AI Review 未执行：本地 Codex 仓库范围与 GitLab MR 不一致。
请同步本地仓库到 MR commit，或切换为 API Key 模式。
```

如果后续实现 `OUT_OF_SCOPE`：

- 有效问题列表不展示。
- 折叠到“疑似越界输出”。

## 8. 测试计划

### 单元测试

- 路径归一化。
- changed files set 对比。
- 多出文件、缺少文件、完全一致三种场景。
- scope mismatch 错误信息截断，避免超长列表。

### 集成测试

- 构造 request.changedFiles 为 A/B。
- mock 本地 git diff 返回 A/B/C。
- 验证 provider 不调用 Codex 或结果保存为 FAILED。
- mock 完全一致时，验证继续执行 Codex。

### 前端验证

- scope mismatch 的 progress event 可读。
- 失败状态展示清楚。
- 不出现污染 finding。

## 9. 推荐推进顺序

建议下一次先做：

```text
Phase 1 + Phase 2
```

原因：

- Phase 1 可以立刻阻断错误范围。
- Phase 2 可以显著降低模型输出越界问题。
- 改动集中在 codequality 模块，不需要重构 GitLab webhook 链路。

暂时不要一开始就做 worktree。worktree 是正确的长期方向，但会牵涉 fetch、凭证、并发清理和 Windows 文件锁，适合在范围预检稳定后推进。

## 10. 一句话结论

这次问题的根因不是 prompt 粗糙，而是 `CODEX_CLI` 使用了本地仓库当前 `HEAD` 的 diff，导致 AI Review 范围大于 GitLab MR 保存的 changed files。后续必须先做审查范围隔离，再继续优化 prompt 和误判反馈闭环。
