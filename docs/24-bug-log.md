# BUG 记录

> 状态说明：本文记录真实使用中发现的 BUG 与修复状态，供回归对照。新 BUG 继续在本文件追加；当前实现与验证步骤以 `README.md` 为准。

本文从 2026-05-27 开始记录用户在真实使用中发现的 BUG、影响、根因和修复状态。每条记录都应包含可复现线索，便于后续回归验证。

## BUG-20260527-001 非默认项目组未配置钉钉机器人时误推送到默认项目组

状态：已修复

发现时间：2026-05-27

现象：

- 最新任务 `351` 属于 `IOS端` 项目组，项目为 `here/here-ios`，端类型为 `APP_IOS`。
- `IOS端` 项目组没有配置钉钉机器人。
- 任务仍推送到了 `默认通用项目组` 下配置的钉钉机器人。

期望：

- 默认项目组也是普通项目组，只服务归属默认项目组的项目。
- 非默认项目组没有启用钉钉机器人时，通知记录应为 `SKIPPED`。
- 不应回退发送到默认项目组或其它项目组机器人。

根因：

- `enabled_webhooks_for_task()` 在任务所属项目组没有启用机器人时，会主动回退查询默认项目组机器人。
- `_resolve_skipped_result()` 通过该回退逻辑判断存在可用机器人，因此允许继续发送。

修复：

- 任务通知只查询任务所属项目组的启用机器人。
- 任务所属项目组无机器人时直接返回 `DINGTALK_WEBHOOKS_EMPTY` / `SKIPPED`。
- 更新回归测试，确保空项目组不会调用默认项目组机器人。

回归验证：

- 运行 `backend-python/tests/contract/test_gitlab_dingtalk_integration.py::test_dingtalk_delivery_skips_when_project_group_has_no_webhooks`。

## BUG-20260718-001 Agent Review 设置页因未定义处理函数崩溃

状态：已修复

发现时间：2026-07-18

现象：

- 打开设置页后，浏览器控制台报 `ReferenceError: testAgentSettings is not defined`。
- `TemplateConfig` 渲染失败，整个设置页面无法使用。

根因：

- Agent Review 设置卡片引用了 `testAgentSettings`，但没有实现该函数，React 在渲染 `onClick` 属性时立即抛错。
- `saveAgentSettings` 同样未实现，只因位于箭头函数体内而没有在首屏渲染时立即报错。
- 前端将配置测试成功状态误写为 `READY`，与后端 `QUEUED / RUNNING / SUCCESS / FAILED` 契约不一致。
- Agent 设置卡片虽然加入了 `collapseItems`，但没有加入最终的 `orderedCollapseItems` 白名单；即使修复运行时错误，卡片仍不会显示。

修复：

- 实现 Agent 设置保存、保留原 Key、替换 Key 和清除 Key。
- 实现 Worker 配置测试提交及两秒间隔的状态轮询，并支持页面重新打开后恢复轮询。
- 按后端状态展示排队、运行、成功、失败和轮询超时；成功状态统一为 `SUCCESS`。
- Worker 离线或设置尚未保存时，在前端给出明确提示。
- 将 `agent-review-settings` 加入设置页最终渲染顺序。

回归验证：

- 运行 `scripts/run-frontend.cmd build`。
- 打开 `/settings`，确认页面正常渲染；分别验证保存、清除 Key、Worker 离线提示和配置测试状态流转。

## BUG-20260724-001 项目组 Agent Review 引擎选择未保存

状态：已修复

发现时间：2026-07-24

现象：

- 设置页已经提供项目组 `STANDARD / AGENT` 选择和 Agent 源码外发授权，但入口位于“AI Review 配置”，用户容易在“项目组 / 端类型配置”中找不到。
- 即使在“AI Review 配置”完成选择并保存，刷新后仍恢复原值。

根因：

- “保存项目组 AI Review 策略”的请求体遗漏 `reviewEngine` 和 `agentSourceExportAllowed`，界面状态没有持久化到后端。
- Agent 全局配置卡没有说明“启用能力”与“切换项目组主引擎”是两个独立步骤。

修复：

- 保存项目组策略时一并提交 `reviewEngine` 和 `agentSourceExportAllowed`。
- 前端在选择 `AGENT` 但未确认源码外发授权时直接阻止保存并提示。
- Agent 设置卡和“AI Review 配置”项目组策略区增加明确的切换路径、主引擎和 fallback 说明。
- 项目组策略区按“Review 引擎 → 触发与授权开关 → 修复预览 / Push 策略”重新分组：桌面端开关保持同一行，修复预览与 Push 策略并排，窄屏自动换行。

回归验证：

- 运行 `scripts/run-frontend.cmd build`。
- 打开 `/settings`，在“AI Review 配置”选择项目组，切换为 `AGENT`、确认源码外发授权并保存；刷新后确认两项保持，随后可用该项目的 Manual Review 验证请求引擎为 `AGENT`。

## BUG-20260724-002 Agent Review 设置提示重复且混用本地操作说明

状态：已修复

发现时间：2026-07-24

现象：

- Agent Review 设置卡同时展示固定组合、项目组切换、加密主密钥和历史配置测试成功等多条提示，主要配置区域被挤压。
- Linux Docker 环境缺少加密主密钥时仍提示执行 Windows 本地脚本。
- 历史配置测试成功提示会在刷新后持续显示，即使当前后端缺少加密主密钥，也可能同时出现“配置可用”和“不能保存 Key”。

修复：

- 删除固定组合和项目组切换两条常驻说明，相关状态继续由配置字段、Worker 标签和项目组策略区域表达。
- 配置测试成功仅使用即时消息反馈，不再把历史成功结果渲染为常驻 Alert；进行中、失败和超时仍保留状态提示。
- 缺少加密主密钥时只保留一条阻塞提示，统一说明在后端运行环境配置 `AGENT_REVIEW_CONFIG_ENCRYPTION_KEY` 并重启，不再混用 Windows 专属命令。

回归验证：

- 运行 `scripts/run-frontend.cmd build`。
- 打开 `/settings` 的 Agent Review 配置，确认正常状态没有常驻说明或历史成功 Alert；缺少加密主密钥时仅显示一条环境无关的阻塞提示。

## BUG-20260724-003 Agent fallback 页签重名且工作区失败原因被覆盖

状态：已修复

发现时间：2026-07-24

现象：

- 任务 `1015` 请求 `AGENT` 后降级到 `STANDARD_FALLBACK`，两个普通 Review 结果页签都显示为“Agent → 普通 Review”，无法区分实际执行的 GLM 与 DeepSeek。
- 项目 mirror 已成功 fetch，但事件提交已不在 mirror 中，任务 worktree 无法按精确 SHA 检出，Agent Run 未创建并记录 `AGENT_WORKTREE_UNAVAILABLE`。
- 本地引用搜索缺少 `rg` 时，会把已经准备好的仓库摘要覆盖成 `worktree MISSING`，掩盖真实失败阶段。

根因：

- 页签文案只判断请求引擎与实际引擎，没有在 fallback 后保留实际 Provider 名称。
- 临时分支或 force-push 分支可能在 webhook 到达后继续移动；普通 mirror fetch 只能获得服务器当前可达的 refs，事件 SHA 可能未被带回。
- 本地引用搜索不可用与 worktree 不存在共用同一段摘要覆盖逻辑。

修复：

- fallback 结果页签显示实际 Provider，并附带“Agent 降级”标识。
- 普通 fetch 后若精确 40 位提交 SHA 无法检出，额外按该 SHA 定向 fetch 一次并重试；仍不可达时保持失败，禁止改用分支最新提交代替。
- `rg` 不可执行时使用 `git grep` 作为本地引用搜索后备；Docker 后端镜像同时安装 `ripgrep`。
- 只有本地引用检索明确报告 worktree 不存在时才更新 worktree 摘要，搜索工具异常不再覆盖仓库准备结果。

回归验证：

- 运行 `scripts/run-backend.cmd test tests/unit/test_local_repo_context.py tests/unit/test_local_retriever.py tests/unit/test_review_context_pack.py`。
- 运行 `scripts/run-frontend.cmd build`。
- 对包含两个普通 Provider 的 Agent fallback 任务确认页签分别显示实际 Provider；用可定向获取的精确 SHA 验证 worktree 重试，用不可达 SHA 验证仍安全降级且保留真实原因。

## BUG-20260724-004 普通 Review 未复用可用的 Provider 出站代理

状态：已修复

发现时间：2026-07-24

现象：

- DeepSeek 普通 Review 或 Agent fallback 后的 DeepSeek 结果偶发失败，错误为 `connect_error: [Errno -2] Name or service not known`。
- 同一环境的 Agent 配置测试可用。

根因：

- `AGENT_REVIEW_UPSTREAM_PROXY` 只作用于隔离的 Agent Worker 出站链路。
- 普通 Review 由 Python backend 直接请求 Provider；backend 未配置 Provider 专用代理时仍依赖本机或容器 DNS，因此 Agent 可用不代表普通 DeepSeek 链路可用。

修复：

- 新增 `CODE_QUALITY_REVIEW_PROXY`，只用于普通 Review、Provider 连接测试和修复预览的模型 HTTP 请求。
- 本地未显式配置时兼容复用 `AGENT_REVIEW_UPSTREAM_PROXY`，避免同一台开发机重复填写代理；生产环境可分别配置两条链路。
- Docker Compose 将该变量传给 backend，不设置时保持原有直连行为；GitLab、钉钉和数据库请求不受影响。

回归验证：

- 配置 `CODE_QUALITY_REVIEW_PROXY=http://代理地址:端口` 并重启 backend。
- 在设置页测试 DeepSeek Provider，再重试普通 Review，确认不再出现本机 DNS 的 `Errno -2`。

## BUG-20260727-001 Agent 入队前误读 worktree 准备结果并直接降级

状态：已修复

发现时间：2026-07-27

现象：

- 任务 `1026`、`1027`、`1028` 请求 `AGENT` 后均直接降级为 `STANDARD_FALLBACK`，结果只记录
  `AGENT_WORKTREE_UNAVAILABLE`，没有 Agent Run。
- 同一任务进入普通 Review 后又能成功 fetch mirror 并按同一精确 SHA 检出 worktree，说明 Worker、模型和
  事件提交并非持续不可用。
- Agent 入队前的具体 Git / 路径错误没有写入进度事件，任务详情无法继续区分瞬时检出失败、路径校验失败和
  持续不可达提交。
- 增加重试和失败详情后，任务 `1030`、`1035` 仍显示 `failurePhase=UNKNOWN, attempts=2`；同任务普通 Review
  随后立即记录 `LOCAL_REPO_PREPARED`。

根因：

- `prepare_local_repository_context()` 返回 `{"summary": {"status": ...}, "unavailableContexts": ...}`，
  Agent `_ensure_worktree()` 却从顶层读取 `status / reason / failurePhase`。新任务首次没有现成 worktree 时，
  即使两次准备都成功，顶层 `status` 仍为空，因此被误判为 `AGENT_WORKTREE_UNAVAILABLE`。
- 原回归测试把准备结果错误模拟为顶层 `status`，没有复现生产返回契约，因此未能阻止该问题。
- 自动调度捕获 `AppError` 后只保存 `exception.code`，丢失了经过脱敏的失败消息和准备阶段，无法从任务记录
  还原低层原因。

修复：

- Agent 入队统一从 `outcome.summary` 读取准备状态和失败阶段，从 `unavailableContexts` 读取脱敏失败原因，并兼容
  测试或旧调用返回的扁平结构。
- 仅在真实 `UNAVAILABLE` 或准备成功但目录不可见时执行一次有界重试；不改变精确 SHA，不回退到分支最新提交。
- 两次准备仍失败时，在任务进度中保存 `AGENT_PREFLIGHT_FAILED`，记录脱敏后的错误码、错误消息和重试次数。
- fallback 的 `agentRunSummary` 同时保留 `failureCode` 和脱敏后的 `failureMessage`，前端与通知可展示真实原因。

回归验证：

- 单元测试使用生产一致的嵌套 `summary`，覆盖首次准备成功、第一次真实失败后第二次成功，以及两次真实失败。
- 契约测试覆盖两次准备均失败时仍安全降级，并可从结果摘要和进度事件读取脱敏失败原因。
- 运行 `scripts/run-backend.cmd test tests/unit/test_local_repo_context.py tests/contract/test_agent_review_api_contract.py`。

## BUG-20260727-002 Agent 租约跨时区误过期且降级任务未创建

状态：已修复

发现时间：2026-07-27

现象：

- 任务 `1042` 刚进入 `AGENT_QUEUED`，执行过程便显示已执行约 `28852` 秒，恰好多出约 8 小时。
- Agent 调度任务 `1267` 只产生一次领取心跳，`turnCount / toolCallCount / sourceBytesReturned` 均为 0，
  随后被标记为 `AGENT_LEASE_EXHAUSTED`。
- 调度任务已经 `FAILED`，但正式结果仍为 `RUNNING`、Agent Run 仍显示 `PENDING`，页面持续停留在“审查中”。

根因：

- Agent 心跳、租约和恢复扫描使用无时区的 `datetime.now()`。连接同一数据库的 Linux UTC Backend 与
  Windows / 东八区 Backend 会把同一个 `DATETIME` 按不同本地时区解释，东八区恢复线程会把刚由 UTC
  Backend 创建的租约误判为已经过期 8 小时。
- API 返回的时间字符串没有 `Z` 或明确偏移，前端 `new Date()` 将 UTC 时间误当成本地时间，运行计时因此多出
  8 小时。
- 恢复扫描准备创建 Standard fallback 时读取不存在的 `AgentReviewRun.project_id`；项目 ID 实际保存在
  `ReviewTask` 和 Agent 调度任务中，异常导致 fallback Job 没有落库，正式结果也无法继续推进。

修复设计：

- Agent 心跳、租约、恢复扫描及 Agent 结果时间统一使用 UTC，无论 Backend 运行在 Windows 还是 Linux，
  数据库比较语义保持一致。
- API 时间序列化统一携带明确时区；前端所有只读时间统一转换为 `Asia/Shanghai`（UTC+8）展示，运行时长基于
  绝对时间戳计算，不再依赖浏览器所在时区。
- Standard fallback 从 `ReviewTask.project_id` 解析项目，不再访问不存在的 Agent Run 字段；增加真实创建
  fallback 调度记录的契约测试，避免只 mock 调度函数而漏掉字段错误。
- 生产环境同一数据库只保留一套 Backend 调度 / 恢复进程；多实例部署时所有实例仍必须遵循同一 UTC 存储约定。

回归验证：

- 覆盖 Agent Worker 心跳与租约时间为 UTC，跨系统时区不会立即过期。
- 覆盖过期 Agent Run 能创建带正确 `projectId` 的 Standard fallback Job。
- 覆盖无时区 UTC、`Z`、显式偏移三类时间输入均按东八区展示，且运行秒数不再多出 8 小时。

## BUG-20260727-003 单个敏感路径导致整个 Agent Review 降级

状态：已修复

发现时间：2026-07-27

现象：

- MR 只要包含一个 `application-prod.properties`、`.env`、证书或密钥类路径，即使其余文件均为普通业务代码，
  整次 Agent Review 仍会在入队前返回 `SENSITIVE_PATH_DENIED`。
- 普通业务文件因此失去 Agent 的源码检索和多轮审查能力，页面也无法区分“全部不可审查”与“仅排除了少量文件”。

根因：

- Agent 入队对 `changedFiles` 使用 fail-fast 列表校验；任意路径命中拒绝策略都会抛出异常，未建立允许文件与排除
  文件的安全分区。
- 即使只过滤 `changedFiles`，原始多文件 diff 仍可能包含敏感文件内容，因此不能仅删除文件名，必须同步过滤 diff
  section。

修复设计：

- 入队前将变更路径分为 `included` 与 `excluded`。`SENSITIVE_PATH_DENIED` 只排除当前文件；越界路径等结构性错误
  仍拒绝整次请求。
- 发送给 Agent 的 `changedFiles` 与 diff 必须来自同一允许集合；优先按标准 unified diff 的 `diff --git`
  section 过滤，无法拆分时只使用允许文件自己的 `diffText` 重建 diff，禁止回退到未过滤原文。
- 仍有允许文件时继续 Agent Review，并记录 `AGENT_SENSITIVE_PATHS_EXCLUDED` 进度事件，页面展示总文件数、审查
  文件数、排除文件数和排除路径。
- 所有文件均被排除时不创建 Agent Run，也不把敏感 diff 发送给外部模型；保存明确的 `SKIPPED` 结果并完成任务
  状态同步。

回归验证：

- 覆盖一个普通 Java 文件加一个 `application-prod.properties` 时，Agent Job 正常创建，输入中只包含 Java 文件，
  diff 中不出现敏感路径或内容。
- 覆盖所有文件均为敏感路径时不创建 Agent Job、不进入普通 Provider，并产生可见的安全跳过结果。
- 覆盖路径越界等非敏感路径错误仍拒绝整次 Agent 入队。

## BUG-20260728-004 Agent 达到 turn 上限后被笼统记录为 AGENT_CLI_FAILED

状态：已修复

发现时间：2026-07-28

现象：

- 任务 `1062` 的 Agent Run 实际执行约 150 秒，完成 17 次工具调用并返回约 40 KB 源码，但最终降级为
  `STANDARD_FALLBACK`，失败码只有 `AGENT_CLI_FAILED`。
- Run 记录的 `turnCount=9`，超过当前 `maxTurns=8`；Claude CLI 在提交 Review Card 前以非零状态退出。
- Worker 丢弃 CLI stderr，失败回传统一使用“未产生有效 Review Card”，页面无法区分 turn 预算耗尽与其它 CLI
  异常。

根因与修复设计：

- 首版固定 8 turns 对 20 个以上文件、需要多次检索调用链的真实 MR 偏紧；模型完成上下文读取后没有剩余 turn
  调用 `submit_review`。
- Runner 应读取 Claude stream-json 的安全结果元数据；当 result subtype 表示 max turns，或非零退出时
  `numTurns` 已达到预算，将失败稳定分类为 `AGENT_MAX_TURNS_EXCEEDED`，不保存 stderr、模型原文或源码。
- 受控生产预算从 8 提升为 12 turns，保持 40 次工具调用、200 KB 源码返回和 600 秒超时不变；Prompt 明确要求
  在核心证据足够后立即提交，不为穷尽检索消耗最终提交预算。
- Worker 根据稳定错误码回传明确但不含敏感内容的失败消息；其它非零退出继续使用 `AGENT_CLI_FAILED`。

回归验证：

- 单元测试覆盖 Claude result subtype / turn 统计解析、达到预算时的稳定错误码和普通非零退出兼容。
- 校验设置接口与 Worker claim 均返回 `maxTurns=12`，配置测试仍维持独立的 4 turns 小预算。
- 运行 Agent Runner 单元测试与 Agent Review 契约测试最小集。

## BUG-20260729-005 真实 Agent 成功提交后被标记为 AGENT_WORKER_ERROR

状态：已修复

发现时间：2026-07-29

现象：

- 任务 `1107` 的 Run 31 已完成 7 次证据调用并成功调用一次 `submit_review`，随后仍被标记为
  `AGENT_WORKER_ERROR` 并进入普通 Review 降级。
- 安全审计保留了 8 次工具事件和约 14 KB 源码返回，但 `turnCount=0`、`durationMs=null`。

根因与修复设计：

- 生产任务不包含离线评测专用的 `targetFinding`；Runner 在成功结果统计阶段无条件读取该字段，
  触发未分类 `KeyError`。
- `targetFinding` 保持为可选评测字段。真实任务缺少该字段时跳过目标命中率计算，不影响 Review Card 成功。
- Worker 未分类异常日志只记录异常类型和代码位置，禁止记录异常消息、Prompt、源码、查询和模型原文。
- 增加无 `targetFinding` 的真实成功路径和脱敏异常日志回归测试。

回归验证：

- Runner 在生产输入不含 `targetFinding`、Review Card 为合法空结果时返回 `SUCCESS`。
- Worker 收到成功摘要后调用完成接口，不再回传 `AGENT_WORKER_ERROR`。
- 未分类异常日志可定位异常类型和代码位置，且不包含异常消息中的敏感哨兵。
- Agent Review 定向测试结果为 `51 passed, 1 skipped`；相关 Python Ruff 与 `git diff --check`
  均通过。
