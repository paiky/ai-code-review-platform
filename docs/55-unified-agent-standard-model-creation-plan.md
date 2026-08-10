# 统一 Agent / Standard 模型新增与动态 Agent Runtime 计划

## 1. 状态、结论与停止点

- 文档状态：**阶段 55A 至 55H4 已完成并已提交推送；55G 剩余验收已由 55H4 完成接管（2026-08-10）**。
- 可行性结论：**可行，但整体改动量为大**。统一新增弹窗本身属于前端交互调整，真正支持新增多条 Agent Runtime
  还会影响数据库、Backend 公共接口、Worker 能力与 Runner、任务快照、配置测试、历史兼容和安全出站边界，因此必须
  拆分为多个改动量为“中”的独立推进阶段。
- 本文是后续工作的唯一专题推进依据，不再扩写旧布局计划或历史路线文档。
- 当前状态：**阶段 55H4 已完成并提交推送**。未部署，也未发送真实 Provider 请求。

## 2. 目标与产品边界

### 2.1 目标

- 将现有“新增模型连接”弹窗扩展为统一入口，创建时单选归属 `Agent Review` 或 `Standard Review`；
- Standard 继续使用现有 Provider 数据模型和执行契约；
- Agent 从一个固定自定义配置槽升级为可创建、编辑、测试、选择和受保护删除的多 Runtime 模型；
- 新增 Agent 成功后只选中目录记录，不自动设为当前、不自动启用、不自动执行配置测试；
- 将现有自定义 Responses Agent 原样迁移为首条动态 Runtime，保留加密 Key、当前选择和历史兼容；
- 最终支持 OpenAI Responses、OpenAI Chat Completions 和 Anthropic Messages 三类受控 Agent 工具循环。

### 2.2 固定边界

- 一条连接只能归属一个 Review 域；Agent 与 Standard 不共享 Endpoint、模型或 Key；
- 动态 Agent 必须执行真实的受控工具循环，不允许把 Standard 单轮 Review 请求改名为 Agent；
- OpenAI Responses 首先开放；Chat Completions 和 Anthropic Messages 在各自 Runner 验收前只显示禁用选项和固定原因；
- Agent 使用全局执行预算，不增加单 Runtime 超时字段；Standard 继续保留单 Provider 超时；
- 内置 Agent Runtime 不可删除；自定义 Agent 使用受保护硬删除，不建设软删除、归档或恢复能力；
- 历史任务使用入队快照保留展示，不因 Runtime 删除而级联修改或删除；
- 不修改 Java Legacy Backend，不建设 Agent/Standard 共享连接池，不自动迁移 Standard Provider 为 Agent Runtime；
- 不更新旧布局计划、README 或历史路线文档。

## 3. 数据模型与迁移契约

### 3.1 动态 Runtime 表

新增 `code_quality_agent_runtimes`：

| 字段 | 契约 |
| --- | --- |
| `runtime_code` | 主键；`^[A-Z][A-Z0-9_]{0,39}$` |
| `display_name` | 展示名称，最多 64 个字符 |
| `protocol` | `OPENAI_RESPONSES` / `OPENAI_CHAT_COMPLETIONS` / `ANTHROPIC_MESSAGES` |
| `runner_type` | Backend 按协议派生，客户端不得提交 |
| `base_url` | Agent 安全 Base URL；具体请求路径由 Runner 固定追加 |
| `model_name` | 模型或中转站别名 |
| `reasoning_effort` | 仅 Responses 使用；`low` / `medium` / `high` |
| `tls_verify` | 默认 `true`；只影响当前 Runtime transport |
| `enabled` | Runtime 是否允许选择、测试和新任务使用 |
| `built_in` | 内置保护标记 |
| `sort_order` | 稳定目录排序 |
| Key 字段 | 独立密文和不可逆短指纹，不保存明文 |
| 测试字段 | request ID、状态、固定消息、耗时及开始/结束时间 |
| 时间字段 | 创建和更新时间 |

`code_quality_agent_settings` 新增 `selected_runtime_code`，继续保存 Agent 总开关、执行预算和 Worker 兼容摘要。旧固定
字段至少保留一个兼容周期，本文不执行删除旧列的迁移。

### 3.2 V49 迁移

新增 `V49__dynamic_agent_review_runtimes.sql`：

- 插入不可删除的 `CLAUDE_CODE_DEEPSEEK` 内置记录；
- 将旧自定义槽位迁移为 `OPENAI_RESPONSES_CUSTOM`；直接迁移密文和指纹，不解密、不要求重新填写 Key；
- 保持旧环境当前选择；缺失或非法选择回退到 `CLAUDE_CODE_DEEPSEEK`；
- 迁移必须幂等兼容空字段、完整配置、不完整草稿和已有目标记录；
- 两个旧 Runtime 在兼容期双写旧字段；选择其它动态 Runtime 时，旧 `runtime_type` 按默认 Runtime 投影，避免旧 Backend
  将 Chat 或 Anthropic 配置误当成旧 Responses 槽位执行；
- 不修改历史 Run、Result、Progress 或 Scheduler Job。

## 4. 公共接口与内部执行契约

### 4.1 Agent Runtime 公共接口

- `GET /api/code-quality-agent-runtimes`
- `POST /api/code-quality-agent-runtimes`
- `PUT /api/code-quality-agent-runtimes/{runtimeCode}`
- `DELETE /api/code-quality-agent-runtimes/{runtimeCode}`
- `POST /api/code-quality-agent-runtimes/{runtimeCode}/set-current`
- `POST /api/code-quality-agent-runtimes/{runtimeCode}/test`

创建和更新使用明确 Pydantic DTO。写入字段包括 Runtime Code、名称、协议、Base URL、模型、可选推理强度、TLS、Key
和启用状态；`runnerType`、配置完整性、Worker 支持和协议可用状态由 Backend 派生。Key 缺失或 `null` 表示保留，只有
显式 `clearApiKey=true` 才清除。所有响应只返回 Key 已配置状态和掩码。

创建行为：

- 只允许 Backend 已开放且存在 Worker Runner 能力的协议；未开放协议返回稳定错误，不依赖前端禁用；
- 创建不改变当前 Runtime、不改变 Agent 总开关、不执行配置测试；
- Runtime Code 冲突返回稳定 `409`；失败不清除前端内存中的 Key 草稿。

删除行为：

- 内置、当前、存在排队/运行任务或存在排队/运行配置测试的 Runtime 返回稳定 `409`；
- 历史终态任务和历史测试不阻塞删除；历史展示继续读取任务快照；
- 删除事务内重新锁定并核对全部保护条件，前端隐藏不能代替 Backend 防绕过。

### 4.2 任务快照与 reviewKey

新任务快照增加：Runtime Code、协议、Runner、Base URL、模型、推理强度和 TLS 设置，不包含 Key。Claim 根据快照中的
Runtime Code 获取当前凭据，继续保持 Key 轮换即时生效的现有语义；Key 被清除或 Runtime 被停用时，任务记录稳定失败
原因并进入现有 fallback。

- 两个历史 Runtime 继续使用原 reviewKey；
- 新 Runtime 使用 `agent-runtime-<runtime-code>`，Runtime Code 转为小写并将下划线替换为连字符；
- Runtime Code 最大长度保证 reviewKey 不超过现有 64 字符字段；
- 删除 Runtime 不修改历史 reviewKey、结果、进度和展示快照。

### 4.3 Worker 能力

Worker 按 Runner 能力而不是具体 Runtime Code 领取任务：

- `OPENAI_RESPONSES_AGENT`
- `OPENAI_CHAT_AGENT`
- `ANTHROPIC_MESSAGES_AGENT`

旧 capability `OPENAI_RESPONSES_CUSTOM` 映射为 `OPENAI_RESPONSES_AGENT`；未上报新能力的旧 Worker 继续只执行现有
兼容 Runner。协议开放由 Backend 配置和在线 Worker capability 共同决定，接口返回可用状态和固定不可用原因。

## 5. 统一新增弹窗设计

- 弹窗第一项为 Review 类型单选：`Agent Review` / `Standard Review`；切换类型时若已有输入，先确认丢弃，再重置为目标
  类型默认草稿；
- Standard 表单继续使用 Provider Code、名称、协议、Endpoint、模型、超时、Key 和启用状态，并调用现有 Provider
  创建接口；
- Agent 表单使用 Runtime Code、名称、协议、Base URL、模型、Key、TLS 和启用状态；Responses 额外显示推理强度；
- Agent 协议列表始终展示三类协议，未完成的 Chat Completions 和 Anthropic Messages 禁用并显示固定原因；
- 创建成功关闭弹窗、刷新目录并选中新行；Standard 不自动设默认，Agent 不自动设当前；两者都不自动测试；
- 动态 Agent 详情支持原生编辑、测试、清除 Key和受保护删除；顶部 Agent 运行卡负责明确设置当前 Runtime；
- 目录使用稳定 ID `AGENT:<runtimeCode>` / `STANDARD:<providerCode>`，Agent 和 Standard 仍独立保存；
- 修复 `761–767px` 删除入口空档：`>=761px` 使用目录操作列，`<=760px` 使用详情危险操作区；
- 创建、编辑、切换、删除和跨设置路由继续使用统一 dirty 守卫与焦点恢复。

## 6. 推进阶段

### 55A：数据库与兼容读取基础

改动量等级：**中**。只建立新表、迁移和兼容 Repository，不切换任务执行或前端。

实施状态：**已完成（2026-08-10）**。

- 目标：迁移两个现有 Runtime、双 Key和当前选择；
- 范围：模型、V49、兼容读取/双写和迁移测试；
- 非目标：不新增公开 API，不调整 Worker、任务或页面；
- 验收：空库、旧默认、旧自定义完整/不完整、双 Key、非法选择和重复迁移通过；迁移不解密 Key；
- 浏览器：不执行；
- 授权边界与停止点：完成定向迁移及 Repository 测试后停止，等待 55B 授权。

实施结果：

- 新增 `code_quality_agent_runtimes` ORM 模型和 V49 迁移，完整承载 Runtime 身份、协议、Runner、连接配置、独立密文、
  配置测试状态、内置/启用/排序和时间字段；`code_quality_agent_settings` 新增 `selected_runtime_code`；
- V49 将 `CLAUDE_CODE_DEEPSEEK` 和 `OPENAI_RESPONSES_CUSTOM` 迁移为两条兼容记录，密文和指纹直接复制且不解密；当前
  选择保持，缺失或非法旧选择回退到内置 Runtime，已有目标记录通过 `NOT EXISTS` 保留；
- 兼容 Repository 在空库或旧库中补齐两条 Runtime，旧设置保存继续双写两条历史记录；运行时 schema 提前补列时会按旧
  `runtime_type` 回填选择，正式 V49 可识别并跳过兼容列，避免重复迁移冲突；
- 内部 Runtime 读取只暴露 Key 已配置状态和指纹掩码，不返回密文；数据库复制到本地时同步清除新 Runtime 表中的密文、
  指纹和配置测试状态；
- 定向 Ruff 通过；迁移、Repository、数据库复制及完整 Agent Review 契约测试共 `95/95` 通过；未修改任务快照、Worker、
  Runner、公开 API、前端或 Java Backend，未执行真实请求和浏览器验收；
- 55A 完成时未单独提交或推送，并按阶段停止点等待 55B 明确授权。

### 55B：动态 Agent Runtime CRUD 与选择

改动量等级：**中**。新增独立 Backend 接口和保护逻辑，但不接入任务执行。

实施状态：**已完成（2026-08-10）**。

- 目标：完成列表、创建、编辑、设为当前、清除 Key和删除；
- 范围：DTO、API、Service、Repository、错误码及契约测试；
- 非目标：不修改 Worker、不开放前端、不执行真实测试；
- 验收：字段边界、重复冲突、Key 保留/清除、内置/当前/活动引用保护、历史非阻塞和响应脱敏通过；
- 浏览器：不执行；
- 授权边界与停止点：完成 Backend 自动化后停止，等待 55C1 授权。

实施结果：

- 新增独立 Pydantic DTO 和 `GET/POST/PUT/DELETE /api/code-quality-agent-runtimes`、
  `POST /api/code-quality-agent-runtimes/{runtimeCode}/set-current`；客户端不能提交 Runner，Backend 按协议派生；
- 首阶段只开放 `OPENAI_RESPONSES`，创建同时校验 Backend 协议开关和在线 Worker Responses 能力；Chat Completions 与
  Anthropic Messages 返回稳定 `AGENT_RUNTIME_PROTOCOL_UNAVAILABLE`，Responses 缺少 Worker 返回
  `AGENT_RUNTIME_RUNNER_UNAVAILABLE`；
- 创建默认不启用、不设为当前、不执行配置测试；Runtime Code、连接字段、Responses 推理强度、安全 HTTPS URL、Key 和
  启用完整性均由 DTO/Repository 双层校验，响应只返回 Key 配置状态与掩码；
- 更新支持 Key 缺省或 `null` 保留、显式轮换、`clearApiKey=true` 清除并停用；两个历史 Runtime 继续向旧设置槽双写，
  动态 Runtime 选择通过 `selected_runtime_code` 保持，旧 `runtime_type` 安全投影到默认 Runtime；
- 55C1 前旧设置接口不能启用动态 Runtime 执行，非选择类旧设置保存不会重置动态选择；停用当前 Runtime 会同步关闭 Agent
  总开关；
- 删除事务阻止内置、当前、排队/运行任务和排队/运行配置测试；历史终态任务不阻塞、不级联，重复删除返回 404；旧自定义
  Runtime 删除后不会被空兼容槽自动重建；
- 定向 Ruff 通过；55A+55B 的迁移、Repository、数据库复制、完整旧 Agent 契约和新增 Runtime 契约共 `103/103` 通过；
  未修改任务快照、Worker 领取、Runner、配置测试或前端，未执行真实请求和浏览器验收；
- 当前工作区包含尚未提交或推送的 55A、55B 改动，停止等待阶段 55C1 明确授权。

### 55C1：动态 Responses 任务快照与领取

改动量等级：**中**。复用现有 Responses Runner，调整入队、快照、Claim 和凭据解析。

实施状态：**已完成（2026-08-10）**。

- 目标：任意 Responses Runtime 可成为当前连接并执行 Agent Review；
- 范围：选择解析、任务快照、reviewKey、Scheduler Job、Claim、Worker capability 兼容和 fallback；
- 非目标：不实现其它协议、不修改前端；
- 验收：切换、入队快照、按 Code 取 Key、Key 轮换、旧 Worker、取消、重试、历史任务和 fallback 自动化通过；
- 浏览器：不执行；
- 授权边界与停止点：完成受影响 Backend/Worker 测试后停止，等待 55C2 授权。

实施结果：

- 入队按 `selected_runtime_code` 锁定动态 Runtime，快照新增 Runtime Code、协议、Runner、Base URL、模型、推理强度和 TLS，
  不保存 Key；两个历史 Runtime 保持原 reviewKey，新 Runtime 使用稳定的 `agent-runtime-<runtime-code>`；
- Scheduler Job 与 Agent Run 按快照记录模型、Runner 和独立 reviewKey，旧任务缺失新字段时继续按历史默认 Runtime 解析；
- Claim 按 Runner capability 过滤，不再按具体动态 Code 过滤；旧 `OPENAI_RESPONSES_CUSTOM` capability 与新
  `OPENAI_RESPONSES_AGENT` 双向兼容，当前 Worker 同时上报兼容值和 Runner 能力；
- Worker 按快照 `runnerType` 将任意 Responses Runtime 路由到既有受控 Responses 工具循环，历史自定义快照仍可按旧
  `runtimeType` 路由；
- Claim 按快照 Runtime Code 从动态表读取当前密文并临时解密，验证 Key 轮换对已排队任务即时生效，Run、Scheduler Job、
  输入快照和响应持久化均不保存明文；
- Runtime 在入队后被停用、清除 Key 或删除时，已排队任务不受 Agent 总开关阻断，领取阶段记录稳定失败并进入现有
  Standard fallback；取消、重试、历史任务和普通失败 fallback 继续由既有契约回归覆盖；
- 定向 Ruff 通过；55A 至 55C1 的迁移、Repository、Worker、数据库复制、完整旧 Agent 契约和动态 Runtime 契约共
  `127/127` 通过；未实现逐 Runtime 配置测试、其它协议或前端，未执行真实请求和浏览器验收；
- 当前工作区包含尚未提交或推送的 55A、55B、55C1 改动，停止等待阶段 55C2 明确授权。

### 55C2：逐 Runtime 配置测试

改动量等级：**中**。将原单例配置测试改为指定 Runtime 的异步测试。

实施状态：**已完成（2026-08-10）**。

- 目标：非当前 Runtime 也能先完成无源码 synthetic 测试；
- 范围：Runtime 测试状态、请求、Worker 领取/回调、轮询和稳定错误；
- 非目标：不自动测试、不请求真实 Provider、不开放未实现协议；
- 验收：排队、领取、成功、失败、超时、陈旧回调、并发、Worker 不支持和删除保护通过；
- 浏览器：不执行；
- 授权边界与停止点：完成配置测试自动化后停止，等待 55D 授权。

实施结果：

- 新增 `POST /api/code-quality-agent-runtimes/{runtimeCode}/test`，非当前 Runtime 可在 Agent 总开关关闭时独立请求测试；
  Runtime 必须启用、配置完整、协议已开放且存在支持对应 Runner 的在线 Worker；
- 测试状态完全落在指定 Runtime 的 request ID、状态、固定消息、耗时和起止时间字段，旧设置测试接口继续委托当前
  Runtime 并同步兼容字段；创建 Runtime 仍不自动测试；
- Worker 按 Runner capability 从多条 Runtime 测试队列领取，默认 Worker 不领取 Responses 测试，旧 Responses capability
  与新 Runner capability 均可领取；不同 Runtime 可并行排队，同一 Runtime 的重复活动请求稳定返回 `409`；
- Claim 按 Runtime Code 读取当前 Key，使用仅包含 `healthcheck.txt` 的临时 synthetic 工作区执行既有只读工具循环，不包含
  生产源码；回调按 request ID 锁定 Runtime，终态重复回调幂等，已被新请求替换的旧回调稳定拒绝；
- 排队或运行超过 90 秒会转为固定超时失败；测试期间停用 Runtime 或清除 Key 会立即转为固定失败，删除仍受活动测试保护；
- 定向 Ruff 通过；55A 至 55C2 的迁移、Repository、Worker、数据库复制、完整旧 Agent 契约和动态 Runtime 契约共
  `131/131` 通过；未请求真实 Provider、未实现其它协议或前端，未执行浏览器验收；
- 当前工作区包含尚未提交或推送的 55A、55B、55C1、55C2 改动，停止等待阶段 55D 明确授权。

### 55D：统一新增弹窗与动态目录

改动量等级：**中**。涉及统一弹窗、目录、详情、运行卡和响应式代码，但只开放 Responses Agent。

实施状态：**已完成（2026-08-10）**。

- 目标：同一弹窗按 Review 类型分别创建 Agent Runtime 或 Standard Provider；
- 范围：React、前端适配模型、目录、详情、运行卡、安全 mock、dirty 和响应式样式；
- 非目标：不实现 Chat/Anthropic Runner，不自动设当前/默认或测试；
- 验收：纯模型、交互、dirty、异常恢复、Key 内存边界、响应式源码契约、全部前端测试和 build 通过；
- 浏览器：不执行，待 55G 与后续协议统一验收；
- 授权边界与停止点：完成自动化和 build 后停止，等待 55E1 授权。

实施结果：

- 设置页加载独立动态 Runtime 目录，统一目录使用稳定 ID `AGENT:<runtimeCode>` / `STANDARD:<providerCode>`；Agent 行
  完整展示当前、内置、启用、配置完整性、Runner 可用性和逐 Runtime 测试状态，Standard 行保持现有语义；
- “新增模型连接”弹窗首项改为 `Agent Review` / `Standard Review` 单选；切换已输入草稿时二次确认并清空目标域草稿，
  Agent 默认选择 Responses，Chat Completions 与 Anthropic Messages 始终可见但禁用并显示固定未开放原因；
- Agent 创建调用动态 Runtime API，Standard 创建继续调用 Provider API；两者成功后只刷新并选中新目录行，不自动设为
  当前/默认、不自动测试，失败时保留当前内存 Key 草稿且响应状态不保存明文；
- 动态 Agent 详情支持原生名称、Base URL、模型、推理强度、TLS、启用和独立 Key 编辑，可测试非当前 Runtime、清除 Key、
  设为当前以及受保护删除；内置、当前和活动测试 Runtime 的删除入口按服务端契约禁用；
- Agent 运行卡改为动态 Runtime 选择并通过独立 `set-current` 接口保存，Agent 总开关和执行预算继续使用兼容设置接口，
  Standard 默认选择和 Provider 详情保存仍相互独立；
- 目录操作列从 `761px` 起显示，`760px` 及以下隐藏并使用详情危险操作区，补齐原 `761–767px` 删除入口空档；统一 dirty
  守卫继续覆盖目录切换、创建类型切换、设置路由和页面离开；
- 本机安全 mock 新增动态 Runtime 列表、创建、编辑、测试、设为当前和删除场景，不发起真实 Provider 请求；新增纯模型与
  源码契约测试后全部前端测试 `201/201` 通过，`scripts/run-frontend.cmd build` 通过；
- 按计划未执行浏览器验收，未实现或开放 Chat/Anthropic Runner；当前工作区的 55A 至 55D 改动尚未提交或推送，停止等待
  阶段 55E1 明确授权。

### 55E1：Chat Completions Agent Runner 验证

改动量等级：**中**。在隔离 mock 中实现单协议受控工具循环，不接生产选择。

实施状态：**已完成（2026-08-10）**。

- 目标：证明 Chat Completions Compatible 服务可完成五工具白名单、续接、预算、取消和结构化提交；
- 范围：Runner、协议 Adapter、固定 mock 和单元测试；
- 非目标：不开放生产协议、不使用真实模型；
- 验收：工具能力缺失、并行调用、损坏响应、429/5xx、预算耗尽、取消和脱敏通过；
- 浏览器：不执行；
- 授权边界与停止点：隔离验证完成后停止，等待 55E2 授权。

实施结果：

- 新增隔离的 OpenAI-compatible Chat Completions 协议 Adapter 与 Agent Runner，严格限定 HTTPS
  `/chat/completions` 端点、Bearer 认证、单 choice、`tool_calls` 完成原因和五工具白名单；Provider 返回的工具调用先
  规范化再续接，不保存原始响应、推理、源码片段或工具参数；
- Runner 复用现有 Review Workspace、Tool Executor、预算和 Review Card schema，支持同轮多个工具调用的确定性顺序执行、
  assistant/tool 消息续接、超限后提交、无效 schema 反馈以及唯一一次结构化 `submit_review`；
- 复用统一的决策回合、工具次数、证据次数、源码字节数、内联 diff、提交回合和总超时预算，支持执行前取消检查；429 与
  5xx 仅在有界次数内退避重试，认证、协议、模型/端点及网络失败统一映射为不含 Key 和 Provider 原始错误体的安全错误；
- 新增固定本地 Synthetic Transport，两轮完成并行证据工具续接和结构化提交，整个验证不打开网络连接；未注册 Worker
  capability、未修改 Runtime 协议门禁，也未开放前端 Chat Completions 选项；
- Chat Runner 定向测试 `20/20` 通过；与 Responses Runner、共享 Workspace 联合回归 `61 passed, 1 skipped`，新增文件
  定向 Ruff 通过；按计划未执行浏览器或真实 Provider 验收，停止等待阶段 55E2 明确授权。

### 55E2：Chat Completions 生产接入

改动量等级：**中**。将已验证 Runner 接入 Worker、配置测试和协议状态。

实施状态：**已完成（2026-08-10）**。

- 目标：支持 `OPENAI_CHAT_AGENT`，能力满足时解除弹窗禁用；
- 范围：Worker 路由、能力协商、配置测试、任务快照、fallback、Backend/前端协议状态；
- 非目标：不自动修改已有 Runtime 或当前选择；
- 验收：Runner 路由、能力、配置测试、快照、fallback 和前端自动化通过；
- 浏览器：不执行，待 55G；
- 授权边界与停止点：完成自动化和必要 build 后停止，等待 55F1 授权。

实施结果：

- Backend 开放 `OPENAI_CHAT_COMPLETIONS` 协议并继续执行协议开放与在线 Worker capability 双门禁；创建、启用、设为当前和
  配置测试均要求在线 Worker 上报 `OPENAI_CHAT_AGENT`，不可用原因按实际 Runner 返回，旧 Responses capability 映射保持；
- 任务与配置测试领取列表新增 `OPENAI_CHAT_AGENT`，Chat Runtime 入队快照保留 Runtime Code、协议、Runner、Base URL、
  模型和 TLS，非 Responses 协议的 `reasoningEffort` 明确为 `null`；Run 使用独立
  `openai-chat-completions-agent-v1` 版本和既有动态 reviewKey，Claim 仍按 Runtime Code 获取最新 Key；
- Worker 上报 Chat capability，生产任务路由到隔离阶段已验证的 Chat Completions Runner，固定追加
  `/chat/completions`，沿用 TLS、预算、取消、进度审计和安全结果规范化；逐 Runtime 配置测试使用仅含
  `healthcheck.txt` 的 synthetic 工作区走同一 Chat Runner；
- Chat Runtime 的成功领取、Key 不落快照、清 Key 后稳定失败与 Standard fallback、配置测试及 Worker 成功回调均有契约
  覆盖；不自动修改已有 Runtime、不改变当前选择或 Agent 总开关；
- 前端 Chat 协议仅在存在在线、非 draining 且具备 `OPENAI_CHAT_AGENT` capability 的 Worker 时解除新增弹窗禁用；
  Anthropic 继续展示固定禁用原因，本机安全 mock 只模拟 capability 和 CRUD，不发起 Provider 请求；
- 55A 至 55E2 Backend 联合回归 `154/154`、全部前端测试 `202/202`、定向 Ruff 和前端生产 build 通过；按计划未执行真实
  Provider 请求或浏览器验收，停止等待阶段 55F1 明确授权。

### 55F1：Anthropic Messages Agent Runner 验证

改动量等级：**中**。在隔离 mock 中实现 Messages 受控工具循环。

实施状态：**已完成（2026-08-10）**。

- 目标：证明 Messages 工具调用、tool_result 续接、预算和结构化提交闭环；
- 范围：Runner、协议 Adapter、固定 mock 和单元测试；
- 非目标：不改造内置 Claude Code CLI，不使用真实模型；
- 验收：工具循环、认证头、错误映射、取消、预算和脱敏通过；
- 浏览器：不执行；
- 授权边界与停止点：隔离验证完成后停止，等待 55F2 授权。

实施结果：

- 新增隔离的 Anthropic Messages Adapter 与 Agent Runner，严格限定 HTTPS `/messages` 端点，使用 `x-api-key` 与固定
  `anthropic-version: 2023-06-01`，请求只包含 system、消息、模型、固定输出上限和五工具 schema；
- Runner 严格接收单条 assistant Message、`stop_reason=tool_use` 以及 text/tool_use 内容块，Provider 返回内容先规范化，
  未声明的 server tool、损坏结构、重复 ID、非法工具和非法参数均在执行前拒绝；
- 同轮多个 `tool_use` 按确定顺序执行并聚合为紧邻的单条 user `tool_result` 消息，错误结果标记 `is_error=true`；复用共享
  Workspace、Tool Executor、预算、Review Card schema、提交回合、总超时、取消与审计，不保存原始响应、源码或工具参数；
- 401/403、404、400/409/422、429 与 5xx/网络异常映射为固定安全错误，429/5xx 使用有界退避重试，响应和异常结果不包含
  Key 或 Provider 原始错误体；
- 新增固定本地 Synthetic Transport，两轮完成两个证据工具、tool_result 续接和结构化提交，全程不打开网络连接；未注册
  `ANTHROPIC_MESSAGES_AGENT` Worker capability、未修改 Runtime 协议开放集合或前端禁用状态；
- Anthropic Runner 定向测试 `20/20` 通过；三类 Runner 与共享 Workspace 联合回归 `81 passed, 1 skipped`，新增文件定向
  Ruff 通过；按计划未执行真实 Provider 或浏览器验收，停止等待阶段 55F2 明确授权。

### 55F2：Anthropic Messages 生产接入

改动量等级：**中**。接入 Worker、配置测试和协议开放状态。

实施状态：**已完成（2026-08-10）**。

- 目标：支持 `ANTHROPIC_MESSAGES_AGENT`，能力满足时解除弹窗禁用；
- 范围：Worker 路由、能力协商、配置测试、任务快照、fallback、历史展示和前端状态；
- 非目标：不改变内置 Claude Code + DeepSeek Runtime；
- 验收：执行、配置测试、能力协商、fallback、历史展示和前端自动化通过；
- 浏览器：不执行，待 55G；
- 授权边界与停止点：完成自动化和必要 build 后停止，等待 55G 授权。

实施结果：

- Backend 已将 `ANTHROPIC_MESSAGES` 加入动态 Agent Runtime 开放协议集合，同时继续执行协议开放与在线 Worker
  `ANTHROPIC_MESSAGES_AGENT` capability 双门禁；创建、启用、设为当前和配置测试均不会绕过 Worker 可用性检查；
- Worker 上报 Anthropic capability，任务与配置测试按 Runtime 快照路由到安全 Base URL 的 `/messages` 端点，复用 55F1
  Runner、预算、取消、进度审计和 synthetic 临时工作区；成功摘要固定记录 `anthropic-messages-agent-v1` 且不伪造 CLI 版本；
- Anthropic 任务快照保留 Runtime Code、协议、Runner、Base URL、模型和 TLS 约束，不保存 Key 或 reasoning effort；领取时按
  Runtime Code 解析当前 Key，Key 清除后沿用既有稳定失败与 Standard fallback；历史摘要保留 Runner、版本和模型；
- 前端仅在存在在线、非 draining 且上报 `ANTHROPIC_MESSAGES_AGENT` 的 Worker 时开放 Anthropic 创建选项，安全 mock 同步
  上报 capability 并生成对应 Runner 快照；内置 Claude Code + DeepSeek Runtime 未改动；
- Backend 阶段联合回归 `230 passed, 1 skipped`，完整前端自动化 `203/203` 通过，生产 build、定向 Ruff 与差异检查
  均通过；按计划未执行真实 Provider 请求或浏览器验收，停止等待阶段 55G 明确授权。

### 55G：全量回归与唯一浏览器验收

改动量等级：**中**。不新增产品能力，只处理跨阶段兼容验证和必要回归修复。

实施状态：**旧交互桌面档已验收，剩余 1024px / 390px 验收已由 55H4 接管（2026-08-10）**。

- 目标：证明迁移、三类 Runner、统一前端和历史兼容形成完整安全基线；
- 范围：全量回归、安全 mock、三档浏览器验收和本文结果回填；
- 非目标：不使用真实模型、不部署、不处理无关历史缺陷；
- 自动化：执行 `scripts/run-backend.cmd test`、全部 `frontend/tests/*.test.mjs` 和
  `scripts/run-frontend.cmd build`；
- 浏览器只在本阶段执行一次：
  - `1440px`：统一弹窗、Agent/Standard 分流、目录/详情双栏、三协议状态、设为当前和删除；
  - `1024px`：图标栏浮层、目录/详情上下排列、Modal、dirty 和错误恢复；
  - `390px`：嵌套 Drawer、单列表单、精简目录、危险操作区、Code 确认和无横向溢出；
- 联合覆盖 55D、55E2、55F2 的浏览器待验项，不为中间阶段重复启动浏览器；
- 授权边界与停止点：只允许修复本文引入的回归；完成后回填结果并停止，不自动提交、推送或部署。

当前验收记录：

- 完整前端自动化 `203/203` 与生产 build 通过；受影响 Backend 联合回归 `230 passed, 1 skipped`；
- 全量 Backend 共 `601` 项，结果为 `596 passed, 1 skipped, 4 failed`。4 项失败可单独稳定复现，位于既有 Standard
  Review、Push Gate 和项目策略契约，并伴随本机 MySQL `root` 鉴权告警；均不在本专题修改文件或 Agent Runtime 链路，
  当前未越权修改；
- `1440px` 已在本机 `docs54-settings-safe-mock` 完成统一 Agent / Standard 弹窗、双栏目录详情、三类 Agent 协议开放、
  Runtime 选择控件和 Code 删除确认保护验收；未发出真实 Provider 请求；
- 切换 `1024px` 时应用内浏览器连接超时并重置，恢复后浏览器列表仍为空；按 Browser 技能约束未改用独立 Playwright
  或其它浏览器工具替代。`1024px` 与 `390px` 尚未验收，安全 mock 与本次前端服务已停止。

### 55H1：供应商预设目录与可见性基础

改动量等级：**中**。新增 Backend 预设接口、Standard Provider 字段和 V50 兼容迁移，但不切换任务执行或前端。

实施状态：**已完成（2026-08-10）**。

- 目标：由 Backend 统一提供 Agent / Standard 供应商、协议、Base URL、模型和推理强度预设，并持久化 Standard
  Provider 是否进入统一目录；
- 范围：`GET /api/review-model-presets?reviewType=AGENT|STANDARD`、响应 schema、Provider `catalogVisible` / 可选
  `reasoningEffort`、V50、运行时兼容补列、迁移与 API 契约测试；
- 数据回填：已有 Key 的 Provider 与用户自建 Provider 可见；从未配置的内置预置占位项隐藏；清 Key 不清除可见标记；
- 非目标：不新增统一创建接口，不修改 Worker、Runner、任务执行或前端；
- 验收：预设契约、Review 类型过滤、迁移幂等、旧数据回填、清 Key 可见性保持、旧接口兼容和 Key 脱敏通过；
- 浏览器：不执行；
- 授权边界与停止点：完成 Backend 自动化后停止，等待 55H2 授权。

实施结果：

- 新增 Backend 预设目录，Standard 返回 OpenAI、Anthropic、DeepSeek、XiaoMIMO、GLM、自定义，Agent 返回
  Claude Code + DeepSeek、OpenAI 双协议、Anthropic、自定义；默认 URL / 模型取当前 Backend 配置或既有 Runtime
  默认值，响应不包含 Key；
- Standard Provider 新增 `catalogVisible` 与 `reasoningEffort`，用户自建连接立即可见，内置占位项只有存在 Key 才可见；
  首次保存 Key 后可见标记永久保持，清 Key 不回退；推理强度仅允许 OpenAI Responses 使用；
- 新增 V50 正式迁移和启动期兼容补列；正式迁移可识别兼容层已创建的同构列，旧数据按 Key / 用户自建属性回填，
  OpenAI Responses 旧记录回填 `high`；
- 精确契约与迁移回归 `27 passed`，Provider 相关扩展回归 `30 passed`，数据库复制回归 `3 passed`，受影响文件 Ruff
  通过；项目固定全量 Ruff 仍报告 5 个既有无关文件错误，本阶段未越权修改；
- 未修改 Worker、Runner 或前端，未发出真实 Provider 请求，未提交、推送或部署；现停止等待 55H2 明确授权。

### 55H2：Agent 供应商连接创建与 Claude Code 多实例

改动量等级：**中**。扩展 Agent 创建服务、Claude Code Runtime 参数化和 Worker 路由，不开放前端。

实施状态：**已完成（2026-08-10）**。

- 目标：统一创建接口支持 Agent 预设、多条 Claude Code + DeepSeek、OpenAI、Anthropic 和自定义连接；
- 范围：服务端隐藏 Code/名称生成、必填 Key、安全连接校验、Runner 映射、Claude Code 多实例、快照、配置测试与 fallback；
- 非目标：不修改 Standard 创建和前端；
- 验收：多实例独立 Key、能力门禁、参数化 Base URL/模型、历史展示和删除保护通过；
- 浏览器：不执行；
- 授权边界与停止点：完成 Agent Backend/Worker 自动化后停止，等待 55H3 授权。

实施结果：

- 新增 `POST /api/review-model-connections` 的 Agent 分支；请求不接受 Code、显示名、启停或选中状态，Backend 根据
  预设生成唯一 Runtime Code 和“供应商 · 模型”显示名，重名追加全角序号；Key 必填，新连接固定启用且不自动设为当前；
- Agent 预设支持 Claude Code + DeepSeek、OpenAI Responses / Chat、Anthropic Messages 和自定义；允许修改预填 URL、
  模型和适用推理强度，同时执行预设协议归属、安全 HTTPS、非 IP、模型长度、推理强度及在线 Worker capability 门禁；
- `ANTHROPIC_COMPATIBLE` 映射 `runnerType=CLAUDE_CODE`，支持多条普通动态 Runtime；内置
  `CLAUDE_CODE_DEEPSEEK` 继续不可删除，预设创建实例沿用动态 Runtime 的受保护删除；
- Claude Worker 改为按 `runnerType=CLAUDE_CODE` 路由；`run_agent_candidate` 的 Runtime 配置新增 Base URL、模型、
  推理强度和 TLS 校验并写入受控 Claude CLI 参数/环境，损坏快照在执行前拒绝；任务快照不保存 Key，Claim 按 Runtime
  Code 解密当前 Key；
- 动态 Claude 配置测试、设为当前、任务领取、最新 Key、清 Key fallback、历史摘要和删除保护通过；旧动态 Runtime
  Provider 语义保持兼容，新预设 Runtime 按供应商记录历史 Provider；
- Agent Backend/Worker 联合回归 `143 passed`，统一连接/预设/旧 Standard Provider 兼容回归 `37 passed`，受影响文件
  Ruff 与差异检查通过；未执行真实 Provider 请求、前端修改、提交、推送或部署；现停止等待 55H3 明确授权。

### 55H3：Standard 供应商创建与推理强度

改动量等级：**中**。扩展 Standard 统一创建和 Responses 推理参数，保留旧 Provider API。

实施状态：**已完成（2026-08-10）**。

- 目标：支持同供应商多连接、服务端身份生成、必填 Key、默认启用且不自动设为默认；
- 范围：统一创建接口 Standard 分支、重复显示名序号、`reasoningEffort` 保存与 Responses 执行透传、Standard TLS 配置
  持久化与 transport 透传、清 Key 停用；
- 非目标：不切换前端；
- 验收：多供应商、多模型、重复创建、推理参数适用性、旧接口兼容和清 Key 状态通过；
- 浏览器：不执行；
- 授权边界与停止点：完成 Standard Backend 自动化后停止，等待 55H4 授权。

实施结果：

- `POST /api/review-model-connections` 已开放 Standard 分支；Backend 校验预设/协议归属、安全 HTTPS、模型、Key 长度和
  reasoning 适用范围，生成唯一 Provider Code 与“供应商 · 模型”递增显示名；
- OpenAI Responses、Anthropic Messages、OpenAI-compatible 三类 Standard 连接均可按预设或自定义创建；新连接固定启用、
  目录可见且不改变默认 Provider，响应只返回 Key 配置状态和掩码；
- Standard Provider 新增 `tls_verify` 与 V51 兼容迁移，旧库运行时补列和正式迁移可幂等衔接；Review、修复预览和配置测试
  均按连接 TLS 设置创建 transport；
- OpenAI Responses 的 `reasoningEffort` 已保存并透传 Review、修复预览和配置测试请求体，非支持协议继续明确拒绝；
- 清 Key 会保留 `catalogVisible` 和默认 Provider 指针，同时强制停用；即使请求同时携带 `enabled=true` 也不能覆盖停用；
  旧 `POST /api/code-quality-review-providers` 保持可用并默认启用 TLS 校验；
- Agent/Standard/Worker/迁移组合回归 `176 passed`，Standard Provider 其余回归 `89 passed, 3 deselected`，数据复制
  `3 passed`，受影响 Ruff（无缓存）和 `git diff --check` 通过；Standard 全文件中另有 3 个与本轮无关且可独立复现的
  既有失败（缺失任务 404、项目 Provider 二次切换、Push Gate 首次决策），本阶段未越界修改；
- 未发送真实 Provider 请求、未修改前端、未提交、推送或部署；现停止等待 55H4 明确授权。

### 55H4：供应商优先弹窗、目录精简与最终验收

改动量等级：**中**。前端消费稳定接口并执行完整响应式回归，不再改变 Backend 主契约。

实施状态：**已完成（2026-08-10）**。

- 目标：按参考图将供应商设为新增弹窗第一选择，移除 Code、名称、启停和顶部 Alert，API Key 必填；
- 范围：预置联动、自定义手填、模型可搜索/可输入、目录过滤、移除 Endpoint 列、清 Key 不可用状态和安全 mock；
- 自动化：完整 Backend、Frontend、Ruff、生产 build、迁移和数据复制验证；
- 浏览器：`1440px`、`1024px`、`390px` 使用本机安全 mock 完成唯一最终验收；
- 授权边界与停止点：完成后回填结果并停止，不自动提交、推送或部署。

实施结果：

- 统一新增弹窗已切换为 Review 类型、供应商优先、协议/Base URL/模型/推理强度、必填 API Key 和 TLS 风险项；移除
  Code、配置名称、启停开关与顶部说明 Alert，预设值来自 Backend，模型支持搜索和自定义输入；
- Agent 与 Standard 均通过统一创建接口落地，创建后默认启用但不改变当前 Runtime 或默认 Provider；重复连接由 Backend
  生成唯一隐藏身份和“（2）”序号名称；Worker capability 在规范化后保留并用于前端禁用提示，Backend 门禁继续兜底；
- 目录移除 Endpoint 列，隐藏从未配置的 Standard 占位项；清 Key 后保留历史可见行并显示“不可用”，不改变当前/默认指针；
- 本机安全 mock 覆盖全部供应商、重复创建、清 Key、无 Worker capability 和失败恢复，固定使用虚构 Key，不调用真实模型；
- 自动化：前端 `208/208`、迁移与数据复制 `24/24`、受影响 Ruff（无缓存）、生产 build 与 `git diff --check` 均通过；
  完整 Backend 为 `622 passed, 1 skipped, 4 failed`，4 个失败均可独立复现且与本阶段无关（缺失任务 404、项目 Provider
  二次切换、Push Gate 首次决策、无匹配 Profile 的 GENERAL 任务状态），未越界修改；
- 浏览器：`1440px` 完成供应商联动、Agent/Standard 创建、API Key 必填、重复命名、目录过滤和当前/默认不自动切换；
  `1024px` 完成双列弹窗及页面上下布局；`390px` 完成单列表单、模型可搜索输入、TLS 风险项、44px 操作按钮与精简目录；
  三档均无横向溢出，仅观察到既有 Ant Design 弃用告警；
- 未提交、推送、部署或发送真实 Provider 请求；现按 55H4 停止点停止。

## 7. 统一验证、开放与安全约束

- 中间阶段必须完成各自自动化测试；涉及前端产物的阶段执行 build，不得因最终统一浏览器验收而推迟已知缺陷；
- 旧交互 55G 的剩余浏览器验收由 55H4 接管；新交互只在 55H4 执行一次完整三档矩阵；
- 协议开放由 Backend 配置与 Worker capability 双重门禁；前端禁用不能代替 Backend 拒绝；
- 新配置不影响已排队或运行任务；任务使用入队快照，Claim 按 Runtime Code 获取当前凭据；
- Base URL 继续执行安全 HTTPS、无凭据、无 query/fragment、非 IP 和受控端口约束；
- Key 不进入任务快照、日志、错误正文、Progress、Run、前端状态或 mock 固定数据；
- 所有浏览器验收使用本机安全 mock 和虚构 Key，不执行真实 Provider 测试或 Agent Review；
- 真实密钥、真实请求、模型费用、部署和协议开关变更必须由用户额外明确授权；
- 所有阶段独立授权并完成后停止；合并最终浏览器验收不合并实施授权或停止点。

## 8. 文档落地结果

- 2026-08-10：完成多 Agent Runtime 与统一 Agent/Standard 新增弹窗可行性评估；
- 2026-08-10：确认 Agent/Standard 连接单一归属；55H 新交互约定新增连接默认启用，但不自动设为当前 Runtime 或默认
  Provider；
- 2026-08-10：确认三类协议最终均需真实 Agent 工具循环，Responses 先开放，Chat/Anthropic 先显示禁用并分阶段验证；
- 2026-08-10：确认现有自定义 Responses 配置原样迁移，动态 Agent 使用受保护硬删除；
- 2026-08-10：整体大改造已在规划阶段拆分为十个改动量为“中”的阶段；中间阶段只做自动化与必要 build，浏览器
  验收统一在 55G 执行一次；
- 2026-08-10：阶段 55A 已完成。新增动态 Runtime 表、V49、选择字段、两条历史 Runtime 的无解密迁移、旧设置兼容双写
  和本地数据库复制脱敏；定向 Ruff 与 `95/95` 自动化通过；
- 2026-08-10：阶段 55B 已完成。新增动态 Runtime DTO、CRUD、设为当前、Key 生命周期、协议/Worker 双门禁、兼容投影
  和事务删除保护；55A+55B 联合定向 Ruff 与 `103/103` 自动化通过；
- 2026-08-10：阶段 55C1 已完成。动态 Responses Runtime 已接入任务快照、独立 reviewKey、Runner capability 领取、
  按 Code 解析最新凭据、Worker 路由和凭据失效 fallback；55A 至 55C1 联合定向 Ruff 与 `127/127` 自动化通过；
- 2026-08-10：阶段 55C2 已完成。新增逐 Runtime 异步配置测试、Runner capability 领取、synthetic 临时工作区、超时、
  并发、幂等与陈旧回调保护；55A 至 55C2 联合定向 Ruff 与 `131/131` 自动化通过；
- 2026-08-10：阶段 55D 已完成。统一新增弹窗已支持 Agent/Standard 分流，动态 Agent 目录、详情、运行卡、测试、删除、
  dirty、响应式和本地安全 mock 已接入；全部前端测试 `201/201` 与生产 build 通过；
- 2026-08-10：阶段 55E1 已完成。隔离 Chat Completions Adapter、五工具受控 Runner、固定 Synthetic Transport、并行续接、
  预算/取消、协议损坏、429/5xx 和脱敏验证已通过；未接生产 Worker、Runtime 门禁或前端协议选择；
- 2026-08-10：阶段 55E2 已完成。Chat 协议双门禁、Worker capability、任务与配置测试路由、快照、最新 Key、fallback 和
  前端按在线 capability 解禁已接入，未修改已有 Runtime 或当前选择；
- 2026-08-10：阶段 55F1 已完成。隔离 Anthropic Messages Adapter、五工具 Runner、tool_use/tool_result 续接、认证头、
  预算/取消、错误映射、脱敏和固定 Synthetic Transport 验证已通过；未接生产 Worker、Runtime 门禁或前端协议选择；
- 2026-08-10：阶段 55F2 已完成。Anthropic 协议双门禁、Worker capability、任务与配置测试路由、快照、最新 Key、fallback、
  历史摘要和前端按在线 capability 解禁已接入，内置 Runtime 保持不变；
- 2026-08-10：确认供应商优先新增交互、Backend 预设目录、服务端隐藏身份、多连接、配置过即保留和清 Key 不可用语义；
- 2026-08-10：阶段 55H1 已完成。新增 Agent / Standard 供应商预设目录、Standard Provider 目录可见性与可选推理强度、
  V50 和旧数据兼容回填；精确契约与迁移 `27/27`、Provider 回归 `30/30`、数据复制 `3/3` 及受影响 Ruff 通过；
- 2026-08-10：阶段 55A 至 55H1 已以 `e8c16c9` 提交并推送到 `origin/main`；
- 2026-08-10：阶段 55H2 已完成。统一连接 Agent 分支、服务端身份、多供应商映射、Claude Code 多实例、参数化
  Runner、配置测试、快照、fallback、历史和删除保护已落地；联合回归 `143/143`、兼容回归 `37/37` 及受影响 Ruff 通过；
- 2026-08-10：阶段 55H3 已完成。统一连接 Standard 分支、服务端身份、多供应商映射、Responses reasoning、Standard TLS
  与 V51、清 Key 强制停用和旧 Provider API 兼容已落地；联合回归 `176/176`、其余 Standard Provider 回归 `89/89`、
  数据复制 `3/3` 及受影响 Ruff 通过；
- 2026-08-10：阶段 55H4 已完成。供应商优先统一弹窗、Backend 预设联动、必填 Key、目录过滤与不可用状态已落地；前端
  `208/208`、迁移与数据复制 `24/24`、受影响 Ruff、生产 build、差异检查和三档安全 mock 浏览器验收通过；完整 Backend
  的 4 个无关既有失败已记录且未越界修改；
- 2026-08-10：阶段 55H2 至 55H4 与联调收尾修复已整体提交推送；未执行真实 Provider 请求或部署。
- 2026-08-10：55H4 页面联调后修复 Provider 列表 GET 的只读性缺陷。旧实现会在读取内补写缺失的 Responses
  `reasoning_effort` 与目录可见性，并发请求可能触发 MySQL 1205 锁等待；现改为响应与执行层兼容默认值，不在 GET
  中回写该状态。精确契约 `3/3`、Provider 代理 `3/3`、受影响 Ruff 通过，本地 8090 Provider 接口恢复 `200`。
- 2026-08-10：55H4 交互收尾将上方 Agent / Standard 运行卡改为只读当前连接摘要，Agent 总开关、Agent 当前 Runtime
  与 Standard 当前 Provider 切换统一下沉到连接详情；新建连接继续不自动切换，保存非当前 Standard 连接时给出明确引导。
  同时替换 Ant Design 已弃用的 InputNumber addon、Modal `maskClosable` 与 Card `bordered` 属性；前端 `210/210`、
  生产 build 和实际页面控制台验收通过，控制台无应用 warning/error。
