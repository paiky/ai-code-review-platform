# 统一 Agent / Standard 模型新增与动态 Agent Runtime 计划

## 1. 状态、结论与停止点

- 文档状态：**规划完成、尚未实施（2026-08-10）**。
- 可行性结论：**可行，但整体改动量为大**。统一新增弹窗本身属于前端交互调整，真正支持新增多条 Agent Runtime
  还会影响数据库、Backend 公共接口、Worker 能力与 Runner、任务快照、配置测试、历史兼容和安全出站边界，因此必须
  拆分为多个改动量为“中”的独立推进阶段。
- 本文是后续工作的唯一专题推进依据，不再扩写旧布局计划或历史路线文档。
- 当前停止点：**只完成本文落地**。等待用户明确授权阶段 55A；不得自动实施代码、迁移数据库、执行真实模型请求、
  提交、推送或部署。

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

- 目标：迁移两个现有 Runtime、双 Key和当前选择；
- 范围：模型、V49、兼容读取/双写和迁移测试；
- 非目标：不新增公开 API，不调整 Worker、任务或页面；
- 验收：空库、旧默认、旧自定义完整/不完整、双 Key、非法选择和重复迁移通过；迁移不解密 Key；
- 浏览器：不执行；
- 授权边界与停止点：完成定向迁移及 Repository 测试后停止，等待 55B 授权。

### 55B：动态 Agent Runtime CRUD 与选择

改动量等级：**中**。新增独立 Backend 接口和保护逻辑，但不接入任务执行。

- 目标：完成列表、创建、编辑、设为当前、清除 Key和删除；
- 范围：DTO、API、Service、Repository、错误码及契约测试；
- 非目标：不修改 Worker、不开放前端、不执行真实测试；
- 验收：字段边界、重复冲突、Key 保留/清除、内置/当前/活动引用保护、历史非阻塞和响应脱敏通过；
- 浏览器：不执行；
- 授权边界与停止点：完成 Backend 自动化后停止，等待 55C1 授权。

### 55C1：动态 Responses 任务快照与领取

改动量等级：**中**。复用现有 Responses Runner，调整入队、快照、Claim 和凭据解析。

- 目标：任意 Responses Runtime 可成为当前连接并执行 Agent Review；
- 范围：选择解析、任务快照、reviewKey、Scheduler Job、Claim、Worker capability 兼容和 fallback；
- 非目标：不实现其它协议、不修改前端；
- 验收：切换、入队快照、按 Code 取 Key、Key 轮换、旧 Worker、取消、重试、历史任务和 fallback 自动化通过；
- 浏览器：不执行；
- 授权边界与停止点：完成受影响 Backend/Worker 测试后停止，等待 55C2 授权。

### 55C2：逐 Runtime 配置测试

改动量等级：**中**。将原单例配置测试改为指定 Runtime 的异步测试。

- 目标：非当前 Runtime 也能先完成无源码 synthetic 测试；
- 范围：Runtime 测试状态、请求、Worker 领取/回调、轮询和稳定错误；
- 非目标：不自动测试、不请求真实 Provider、不开放未实现协议；
- 验收：排队、领取、成功、失败、超时、陈旧回调、并发、Worker 不支持和删除保护通过；
- 浏览器：不执行；
- 授权边界与停止点：完成配置测试自动化后停止，等待 55D 授权。

### 55D：统一新增弹窗与动态目录

改动量等级：**中**。涉及统一弹窗、目录、详情、运行卡和响应式代码，但只开放 Responses Agent。

- 目标：同一弹窗按 Review 类型分别创建 Agent Runtime 或 Standard Provider；
- 范围：React、前端适配模型、目录、详情、运行卡、安全 mock、dirty 和响应式样式；
- 非目标：不实现 Chat/Anthropic Runner，不自动设当前/默认或测试；
- 验收：纯模型、交互、dirty、异常恢复、Key 内存边界、响应式源码契约、全部前端测试和 build 通过；
- 浏览器：不执行，待 55G 与后续协议统一验收；
- 授权边界与停止点：完成自动化和 build 后停止，等待 55E1 授权。

### 55E1：Chat Completions Agent Runner 验证

改动量等级：**中**。在隔离 mock 中实现单协议受控工具循环，不接生产选择。

- 目标：证明 Chat Completions Compatible 服务可完成五工具白名单、续接、预算、取消和结构化提交；
- 范围：Runner、协议 Adapter、固定 mock 和单元测试；
- 非目标：不开放生产协议、不使用真实模型；
- 验收：工具能力缺失、并行调用、损坏响应、429/5xx、预算耗尽、取消和脱敏通过；
- 浏览器：不执行；
- 授权边界与停止点：隔离验证完成后停止，等待 55E2 授权。

### 55E2：Chat Completions 生产接入

改动量等级：**中**。将已验证 Runner 接入 Worker、配置测试和协议状态。

- 目标：支持 `OPENAI_CHAT_AGENT`，能力满足时解除弹窗禁用；
- 范围：Worker 路由、能力协商、配置测试、任务快照、fallback、Backend/前端协议状态；
- 非目标：不自动修改已有 Runtime 或当前选择；
- 验收：Runner 路由、能力、配置测试、快照、fallback 和前端自动化通过；
- 浏览器：不执行，待 55G；
- 授权边界与停止点：完成自动化和必要 build 后停止，等待 55F1 授权。

### 55F1：Anthropic Messages Agent Runner 验证

改动量等级：**中**。在隔离 mock 中实现 Messages 受控工具循环。

- 目标：证明 Messages 工具调用、tool_result 续接、预算和结构化提交闭环；
- 范围：Runner、协议 Adapter、固定 mock 和单元测试；
- 非目标：不改造内置 Claude Code CLI，不使用真实模型；
- 验收：工具循环、认证头、错误映射、取消、预算和脱敏通过；
- 浏览器：不执行；
- 授权边界与停止点：隔离验证完成后停止，等待 55F2 授权。

### 55F2：Anthropic Messages 生产接入

改动量等级：**中**。接入 Worker、配置测试和协议开放状态。

- 目标：支持 `ANTHROPIC_MESSAGES_AGENT`，能力满足时解除弹窗禁用；
- 范围：Worker 路由、能力协商、配置测试、任务快照、fallback、历史展示和前端状态；
- 非目标：不改变内置 Claude Code + DeepSeek Runtime；
- 验收：执行、配置测试、能力协商、fallback、历史展示和前端自动化通过；
- 浏览器：不执行，待 55G；
- 授权边界与停止点：完成自动化和必要 build 后停止，等待 55G 授权。

### 55G：全量回归与唯一浏览器验收

改动量等级：**中**。不新增产品能力，只处理跨阶段兼容验证和必要回归修复。

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

## 7. 统一验证、开放与安全约束

- 中间阶段必须完成各自自动化测试；涉及前端产物的阶段执行 build，不得因最终统一浏览器验收而推迟已知缺陷；
- 浏览器验收只有 55G 一次；若发现跨阶段问题，修复后重新执行受影响自动化和完整三档矩阵；
- 协议开放由 Backend 配置与 Worker capability 双重门禁；前端禁用不能代替 Backend 拒绝；
- 新配置不影响已排队或运行任务；任务使用入队快照，Claim 按 Runtime Code 获取当前凭据；
- Base URL 继续执行安全 HTTPS、无凭据、无 query/fragment、非 IP 和受控端口约束；
- Key 不进入任务快照、日志、错误正文、Progress、Run、前端状态或 mock 固定数据；
- 所有浏览器验收使用本机安全 mock 和虚构 Key，不执行真实 Provider 测试或 Agent Review；
- 真实密钥、真实请求、模型费用、部署和协议开关变更必须由用户额外明确授权；
- 所有阶段独立授权并完成后停止；合并最终浏览器验收不合并实施授权或停止点。

## 8. 文档落地结果

- 2026-08-10：完成多 Agent Runtime 与统一 Agent/Standard 新增弹窗可行性评估；
- 2026-08-10：确认 Agent/Standard 连接单一归属，新增 Agent 不自动设为当前或启用；
- 2026-08-10：确认三类协议最终均需真实 Agent 工具循环，Responses 先开放，Chat/Anthropic 先显示禁用并分阶段验证；
- 2026-08-10：确认现有自定义 Responses 配置原样迁移，动态 Agent 使用受保护硬删除；
- 2026-08-10：整体大改造已在规划阶段拆分为十个改动量为“中”的阶段；中间阶段只做自动化与必要 build，浏览器
  验收统一在 55G 执行一次；
- 当前只完成计划文档，尚未实施任何 55 代码、数据库迁移、真实请求、提交、推送或部署。
