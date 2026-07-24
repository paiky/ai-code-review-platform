# AI代码质量审查平台后续价值落地 PPT 大纲

> 状态说明：本文是 PPT / 汇报大纲素材，§2 起包含大量后续规划内容。涉及“当前能力”的描述以 `README.md` 为准；不要将其中的规划项当作已实现功能。

日期：2026-05-12

## 1. 文档目的

本文用于沉淀当前系统已完成能力与后续产品规划，作为后续制作 PPT、阶段汇报或路线介绍的目录大纲。文档既包含“当前项目从 0 到 1 已打通的能力”，也包含“后续价值落地路线”，可直接作为 Gemini / PPT 生成工具的输入素材。

当前平台已经具备从 GitLab MR / Push webhook / 手动审查接入，到 changed files / diff 获取、规则扫描、AI Code Review、钉钉推送、任务落库、通知记录查询和前端查看的基础闭环。下一阶段的核心目标不是继续堆叠更多审查入口，而是让平台从“审查通知工具”演进为“研发变更质量决策辅助系统”。

后续重点围绕五个方向推进：

1. AI Review 结果可标记，并沉淀为 review memory。
2. 将 AI Code Review 从 MR 阶段提前到 commit push 阶段，并通过规则闸门控制触发。
3. 钉钉推送支持 @ 作者修复紧急问题，并跳转到具体 file change。
4. 模型 Provider 支持 OpenAI / Anthropic / DeepSeek / 自定义 OpenAI-compatible 配置，前端可配置端点、模型和 API Key。
5. 增加 Dashboard 仪表盘，用数据展示平台价值。

建议 PPT 生成时采用“当前能力 60% + 后续规划 40%”的结构：前半部分讲清楚系统为什么做、现在能做什么、端到端如何运转；后半部分再讲反馈闭环、Push 前置、精准通知、模型通用化和 Dashboard。

### 1.1 与当前实现对齐（截至 2026-06）

以下能力**已实现**，做 PPT 时应归入“当前能力基线”，不要仍写成规划：

- GitLab MR / Push webhook、手动审查、规则提醒、AI Review、钉钉推送、任务落库与前端查看
- Push 审核 Gate 与 Push 自动 AI Review 策略
- 多模型 Provider 与项目组级配置（OpenAI / Anthropic / DeepSeek / XiaoMIMO / Custom）
- 项目组、端类型、端类型自动识别与按组钉钉隔离

以下能力**仍未实现**，可保留在“后续规划”章节：

- AI Review finding 反馈与 review memory（见 `docs/14-ai-review-feedback-loop-plan.md`）
- 钉钉 @ 作者、跳转到具体 file change 的增强通知
- Dashboard 仪表盘与审查价值度量

## 2. PPT 总体叙事建议

### 2.1 推荐标题

```text
AI代码质量审查平台：从自动提醒到研发质量闭环
```

### 2.2 推荐主线

```text
当前已打通从 GitLab / 手动输入到审查结果展示的闭环
  -> 用规则识别 DB / MQ / 缓存 / 配置等高价值变更
  -> 用 AI Review 增强代码质量审查
  -> 通过钉钉和前端把结果触达给研发团队
  -> 下一步提升审查结果可信度
  -> 将审查提前到更早的 commit push 阶段
  -> 把高风险问题精准触达责任人
  -> 支持更多模型和部署环境
  -> 通过 dashboard 衡量审查价值
```

### 2.3 推荐章节目录

1. 项目背景与当前进展
2. 当前系统能力基线
3. 当前端到端演示链路
4. 后续价值落地总览
5. 方向一：AI Review 反馈闭环与 Review Memory
6. 方向二：Push 阶段智能触发 AI Code Review
7. 方向三：钉钉精准触达与 File Change 深链
8. 方向四：模型 Provider 通用化配置
9. 方向五：Dashboard 价值度量
10. 分阶段路线图
11. 预期收益与验收标准

## 3. 项目背景与当前进展

### 3.1 章节目标

说明平台为什么要做，以及当前已经完成到什么程度。

### 3.2 可展开目录

#### 3.2.1 背景：传统 Code Review 的问题

- Reviewer 需要人工从大量 diff 中识别高风险改动。
- DB / MQ / 缓存 / 配置等稳定性风险容易被普通代码 diff 淹没。
- 风险提醒依赖个人经验，难以结构化沉淀。
- 钉钉、GitLab、代码审查和质量数据之间缺少统一闭环。

#### 3.2.2 产品定位

- 平台围绕“代码变更”进行风险识别。
- 先用规则识别高价值变更，再用 AI 进行代码质量增强审查。
- 输出结构化提醒卡片，而不是只输出一段自然语言评论。
- 目标是帮助 reviewer、开发、测试和发布负责人更早聚焦风险。

#### 3.2.3 当前主链路

```text
GitLab MR webhook / 手动审查 / 手动重跑
  -> 创建 review task
  -> 保存 raw payload / changed files 摘要
  -> 获取 changed files / diff（payload 或 GitLab API）
  -> 变更分析
  -> 规则引擎生成提醒卡片
  -> 结果落库
  -> 钉钉推送或 SKIPPED 通知记录
  -> 可选触发 / 自动触发 AI Code Review
  -> 保存 AI Review 结果和执行进度
  -> AI Review 完成后合并推送规则提醒与 AI 结果摘要
  -> 前端查看任务列表、任务详情、提醒卡片、分析结果、AI Review 结果和通知记录
```

#### 3.2.4 当前已完成能力

接入与任务：

- GitLab `Merge Request Hook` 接入，支持 MR open/update 等事件进入审查链路。
- GitLab `Push Hook` 入口已保留并能解析 payload；当前默认返回 `SKIPPED`，避免目标分支 push 造成重复审查，后续通过 Push AI Review gate 再启用。
- 支持手动规则审查，适合本地验证规则、模板和钉钉消息。
- 支持基于已保存 raw payload 和 changed files 摘要重新触发已有 GitLab 审查任务。
- 审查任务统一落库，包含触发类型、项目、分支、commit、作者、状态、风险等级等信息。

Diff 与变更分析：

- MR payload 缺少 changed files 时，可通过 GitLab API 补拉 MR diff，并兼容 `/diffs` 与 `/changes`。
- 变更分析覆盖 API、DB、MQ、Redis/缓存、配置等类型。
- DB 细分识别覆盖 `DB_SCHEMA`、`DB_SQL`、`ORM_MAPPING`、`ENTITY_MODEL`、`DATA_MIGRATION`。
- MQ 细分识别覆盖 producer、consumer、消息结构、topic 配置、重试死信等场景。
- 缓存细分识别覆盖 cache key、TTL、失效逻辑、读写、序列化等场景。
- 配置识别覆盖配置文件、环境变量、开关项和 `@Value` 占位符变更。

规则与提醒卡片：

- 规则引擎基于变更分析结果生成结构化提醒卡片。
- 提醒卡片包含风险等级、影响资源、重点指标、提醒项、推荐检查项和建议 review 角色。
- 模板支持 `focusChangeTypes`，钉钉消息可只推送 DB / MQ / Redis / 配置等重点提醒，降低噪音。
- 提醒卡片支持前端展示、JSON 落库和钉钉 Markdown 推送。

AI Review：

- AI Review 支持 OpenAI、Anthropic、DeepSeek 和自定义 OpenAI-compatible Provider。
- AI Review 已切换到 diff-only 审查范围，只审查平台保存的 diffText 和 changedFiles，避免读取本地仓库导致范围污染。
- 支持 MR 自动触发 AI Review，也支持在任务详情页手动重试 AI Review。
- 支持 Review Profile：模型、Prompt、OpenAI instructions / Codex prompt 可配置、预览和恢复默认。
- 支持模型端点 URL、模型名称、API Key 配置和脱敏展示，支持在前端切换默认模型 Provider。
- 支持 AI Review 执行进度事件展示，包括 queued、request built、provider start、save result、finished / failed 等阶段。

通知与设置：

- 钉钉支持规则提醒、AI Review 结果、规则 + AI 合并摘要三类消息形态。
- 钉钉消息包含作者、变更标题、分支、维护提醒、AI 主要问题和平台详情链接。
- 已支持钉钉推送全局开关；关闭后审查和落库正常执行，通知记录为跳过或不实际发送。
- 通知记录落库，可在任务详情页查询每次推送的 channel、target、status、digest、error message 等。

前端页面：

- `审查任务`：任务列表、搜索过滤、任务详情。
- 任务详情页：代码质量 Review、提醒卡片、分析结果、原始事件摘要。
- AI Review 面板：状态、Provider、模型、等级、问题数、主要 finding、原始输出、执行进度。
- `模板配置`：项目默认模板、AI Review 全局设置、API Key、Profile Prompt 编辑和预览。
- 全局设置包含 MR 自动 AI Review 开关、钉钉推送开关、执行方式切换和供应商选择。

#### 3.2.5 当前系统模块关系

```text
GitLab / 手动请求
  -> project-integration：解析 webhook、补拉 diff、保存原始事件
  -> change-analysis：识别 API / DB / MQ / CACHE / CONFIG 等变更类型
  -> risk-engine + rule-template：按模板生成结构化提醒卡片
  -> code-quality：按 profile 和 provider 执行 AI Review
  -> notification：生成钉钉 Markdown，保存通知记录
  -> review-record：统一查询任务、规则结果、AI 结果、进度、通知记录
  -> frontend：任务查看、配置管理、AI Review 结果展示
  -> MySQL：保存项目、任务、结果、配置、通知、进度事件
```

#### 3.2.6 推荐演示链路

PPT 中可以用一页“端到端 Demo”展示：

```text
1. GitLab MR 打开或手动导入 diff
2. 平台创建审查任务，保存 raw payload 和 changedFiles
3. 规则扫描识别 DB / MQ / Redis / 配置等重点变更
4. 生成提醒卡片并落库
5. 根据全局配置触发 AI Review
6. AI Review 输出结构化 finding 和整体等级
7. 钉钉推送合并摘要，包含维护提醒和 AI 问题
8. 用户点击平台链接查看任务详情、进度、原始事件和通知记录
```

### 3.3 本章结论

当前系统已经完成从“GitLab / 手动变更进入平台”到“规则扫描、AI Review、钉钉触达、结果落库和前端查看”的基础闭环。下一阶段重点是让 AI 结果更可信、Push 触发更前置、通知更可处理、模型配置更通用、平台价值更可衡量。

## 4. 后续价值落地总览

### 4.1 章节目标

用一页总览说明后续五个方向之间的关系。

### 4.2 可展开目录

#### 4.2.1 从通知链路到质量闭环

```text
发现问题
  -> 判断是否有效
  -> 触达责任人
  -> 跟踪处理状态
  -> 沉淀团队经验
  -> 反向优化后续审查
```

#### 4.2.2 五个建设方向

| 方向 | 核心价值 | 优先级 |
| --- | --- | --- |
| AI Review 结果可标记与 review memory | 降低误判，沉淀团队审查偏好 | P0 |
| Push 阶段智能触发 AI Review | 更早发现问题，减少 MR 后期返工 | P1 |
| 钉钉 @ 作者与 file change 深链 | 让高风险问题真正被处理 | P1 |
| 模型 Provider 通用化配置 | 支持 DeepSeek、更多模型和私有化部署 | P2 |
| Dashboard 仪表盘 | 量化平台效果和质量趋势 | P2 |

#### 4.2.3 推荐推进顺序

```text
Phase 1：AI finding feedback
Phase 2：review memory 注入
Phase 3：Push AI Review gate
Phase 4：钉钉精准触达与 file change 深链
Phase 5：模型端点与模型配置通用化
Phase 6：Dashboard 仪表盘
```

### 4.3 本章结论

后续建设不应简单扩大 AI Review 触发范围，而应先建立反馈机制和噪音控制能力，再逐步前置触发时机和扩展模型接入。

## 5. 方向一：AI Review 结果可标记与 Review Memory

### 5.1 章节目标

说明为什么 AI Review 必须支持人工反馈，以及如何从反馈沉淀为后续审查记忆。

### 5.2 可展开目录

#### 5.2.1 当前问题

- AI Review 输出是候选问题，不一定全部准确。
- 误判如果不能标记，会持续影响有效问题数。
- 相同误判可能在后续任务中重复出现。
- 团队上下文、历史约定和项目特殊规则没有沉淀入口。

#### 5.2.2 建设目标

- 每条 AI finding 都有稳定 fingerprint。
- 用户可以标记 `FALSE_POSITIVE`、`NOT_ACTIONABLE`、`ACCEPTED`、`FIXED` 等状态。
- 被取消的 finding 不计入有效问题数。
- 反馈原因结构化保存。
- 高频反馈可沉淀为 review memory。
- 后续 AI Review 自动参考相关 review memory，降低重复误报。

#### 5.2.3 最小闭环

```text
AI 输出候选 finding
  -> 用户标记误判 / 不采纳 / 确认
  -> 后端保存 finding feedback
  -> 当前任务有效问题数更新
  -> 后续生成 review memory
  -> 下次 Review prompt 注入历史参考
```

#### 5.2.4 页面交互目录

- AI Review 结果卡片增加操作按钮：
  - 误判
  - 不采纳
  - 确认
  - 已修复
- 标记弹窗字段：
  - 处理类型
  - 原因分类
  - 详细原因
  - 是否沉淀为 review memory
  - 适用范围：当前文件、当前目录、当前项目
- 结果统计展示：
  - 候选问题数
  - 有效问题数
  - 已取消问题数
  - 已确认问题数

#### 5.2.5 后端能力目录

- 新增 finding fingerprint 生成逻辑。
- 新增 `code_quality_finding_feedbacks` 表。
- AI Review result response 返回 finding feedback。
- 当前任务有效 finding count 排除误判和不采纳项。
- 后续新增 `code_quality_review_memories` 表。
- Review 执行前按项目、文件、目录检索 memory。
- Prompt 中注入“历史误判参考”。

#### 5.2.6 分阶段落地

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| Phase 1 | finding fingerprint + feedback API | finding 可标记，刷新后状态保留 |
| Phase 2 | review memory 表与生成逻辑 | 反馈可沉淀为 memory |
| Phase 3 | prompt 注入 memory | 下次 Review 可参考历史反馈 |
| Phase 4 | memory 管理页 | 可启用、禁用、编辑、归档 memory |

#### 5.2.7 预期价值

- 降低 AI Review 噪音。
- 让团队审查偏好可以沉淀。
- 为后续 dashboard 提供误判率、确认率等指标。
- 为扩大到 push 阶段触发 AI Review 提供质量控制基础。

### 5.3 本章结论

AI Review 不应被当作最终裁决，而应被当作候选问题来源。人工反馈闭环是平台从“AI 输出结果”走向“团队审查知识沉淀”的关键一步。

## 6. 方向二：Push 阶段智能触发 AI Code Review

### 6.1 章节目标

说明为什么要把 Code Review 从 MR 阶段前移到 commit push 阶段，以及如何避免触发过多 AI Review。

### 6.2 可展开目录

#### 6.2.1 当前问题

- 当前 AI Code Review 主要在 MR 阶段触发。
- 许多问题到 MR 阶段才暴露，开发返工成本较高。
- Push hook 已有入口和解析能力，但当前默认跳过审查，避免目标分支 push 或合并后 push 造成重复任务。
- 如果每次 push 都直接触发 AI Review，会带来成本、耗时和通知噪音。

#### 6.2.2 建设目标

- Commit push 后也能进入审查链路。
- AI Review 触发前先经过规则识别闸门。
- 只有命中高价值变更或高风险信号时才触发 AI Review。
- Push 阶段发现的问题可以在 MR 前被开发者修复。
- MR 阶段继续保留完整审查，作为合并前确认。

#### 6.2.3 推荐链路

```text
GitLab Push webhook
  -> 拉取 beforeSha..afterSha diff
  -> 规则扫描
  -> 判断是否满足 AI Review 触发条件
  -> 满足条件则创建 AI Review 任务
  -> 保存结果
  -> 必要时钉钉通知作者
```

#### 6.2.4 AI Review 触发闸门

建议第一阶段命中以下信号才触发 AI Review：

- DB schema / migration / ORM mapping 变更。
- MQ producer / consumer / message schema / topic 配置变更。
- 缓存 key / TTL / 失效逻辑 / 序列化变更。
- 配置项、环境变量、开关项变更。
- 鉴权、权限、安全敏感文件变更。
- 大 diff 或删除关键逻辑。
- 风险规则输出 `HIGH` 或 `CRITICAL`。

#### 6.2.5 触发策略配置

- 项目级开关：是否启用 Push AI Review。
- 分支过滤：只审查指定分支或排除临时分支。
- 作者过滤：机器人提交、自动生成提交可跳过。
- 文件路径过滤：忽略 generated、test fixture、vendor 等目录。
- 频率限制：同一分支短时间内合并触发，避免连续 push 刷屏。
- 结果复用：同一 commit sha 已审查过则不重复触发。

#### 6.2.6 分阶段落地

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| Phase 1 | Push diff 使用 GitLab compare API 获取完整 diff | push 任务可拿到 beforeSha..afterSha diff |
| Phase 2 | 增加 AI Review gate 判断服务 | 只有命中条件的 push 会触发 AI |
| Phase 3 | 项目级 push AI Review 配置 | 不同项目可配置触发规则 |
| Phase 4 | 频率限制与去重 | 连续 push 不会重复刷屏 |

#### 6.2.7 预期价值

- 把问题发现从 MR 阶段提前到 commit push 阶段。
- 减少 MR 后期返工。
- 降低 AI Review 调用成本和通知噪音。
- 让规则引擎成为 AI 审查的前置过滤器。

### 6.3 本章结论

Push 阶段 AI Review 的关键不是“每次提交都审”，而是“用规则识别筛出值得 AI 审的变更”。这样既能前置问题发现，又能控制成本和噪音。

## 7. 方向三：钉钉精准触达与 File Change 深链

### 7.1 章节目标

说明如何让钉钉推送从“群消息提醒”升级为“可行动的问题处理入口”。

### 7.2 可展开目录

#### 7.2.1 当前问题

- 当前钉钉推送已经能发送审查摘要，但处理动作仍然弱。
- 普通群消息容易被忽略。
- 用户点击后需要再定位具体任务和文件变更。
- 紧急问题没有明确责任人触达机制。

#### 7.2.2 建设目标

- 高风险问题支持 @ 作者。
- 钉钉消息直接展示关键风险摘要。
- 点击消息可跳转到平台具体任务详情。
- 进一步支持跳转到具体 file change / finding 锚点。
- 普通问题不滥用 @，避免通知疲劳。

#### 7.2.3 消息分级策略

| 风险等级 | 通知策略 |
| --- | --- |
| `CRITICAL` | @ 作者，突出展示，需要尽快处理 |
| `HIGH` | 可配置 @ 作者，展示重点风险 |
| `MEDIUM` | 只推送摘要，不默认 @ |
| `LOW` | 默认不推送或合并展示 |

#### 7.2.4 钉钉消息内容目录

- 项目名称。
- 触发来源：Push / MR。
- 分支与提交信息。
- 作者。
- 最高风险等级。
- 命中风险类型：DB / MQ / CACHE / CONFIG / AI Review。
- 紧急问题摘要。
- 平台详情链接。
- File change 深链。
- 处理建议。

#### 7.2.5 File Change 深链设计

第一阶段建议使用平台内深链：

```text
http://localhost:5173/?taskId={taskId}&file={encodedFilePath}&finding={fingerprint}
```

后续可扩展为：

- 跳转到平台任务详情中的指定文件变更。
- 跳转到平台 AI finding 卡片。
- 跳转到 GitLab MR diff 中的对应文件。
- 支持按行号定位具体代码片段。

#### 7.2.6 作者匹配策略

- MR 场景优先使用 MR author。
- Push 场景优先使用 commit author。
- 如果多个 commit author，按问题涉及文件和 commit 映射责任人。
- 支持 GitLab username 与钉钉手机号 / userId 映射。
- 映射不到时只展示作者名，不执行 @。

#### 7.2.7 分阶段落地

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| Phase 1 | 钉钉消息增加高风险摘要和作者信息 | 消息能看出谁提交、风险是什么 |
| Phase 2 | 支持高风险 @ 作者 | `CRITICAL` / `HIGH` 可触达责任人 |
| Phase 3 | 平台 file change 深链 | 点击直接定位文件变更 |
| Phase 4 | GitLab diff 链接增强 | 可跳转到 GitLab 对应 MR diff |

#### 7.2.8 预期价值

- 提升高风险问题处理率。
- 减少从钉钉到平台再到代码变更的定位成本。
- 让通知变成行动入口，而不只是结果播报。

### 7.3 本章结论

钉钉推送的价值不在于“发出去”，而在于“让正确的人看到正确的问题，并能快速跳转处理”。

## 8. 方向四：模型 Provider 通用化配置

### 8.1 章节目标

说明为什么需要支持 API Key 自定义端点和模型，以及如何让平台适配更多模型服务。

### 8.2 可展开目录

#### 8.2.1 当前问题

- 当前系统已支持 OpenAI、Anthropic、DeepSeek 和自定义 OpenAI-compatible Provider。
- OpenAI / Anthropic / DeepSeek / 自定义 Provider 均可在前端维护端点、模型和 API Key。
- 企业内部可能使用代理网关、私有模型或 OpenAI-compatible 服务。
- 不同项目可能希望使用不同模型、不同 endpoint、不同超时和 token 限制。

#### 8.2.2 建设目标

- API Key 可在前端配置。
- Endpoint 可配置，不强绑定官方地址。
- Model 可配置，不强绑定默认模型。
- 支持 OpenAI-compatible endpoint。
- 支持项目级或全局级 provider 配置。
- 保留 API Key 加密或脱敏展示能力。

#### 8.2.3 配置维度

- Provider 类型：
  - `OPENAI`
  - `ANTHROPIC`
  - `DEEPSEEK`
  - `CUSTOM`
- Endpoint URL。
- Model name。
- API Key。
- Timeout。
- Max output tokens。
- Temperature。
- 是否启用。
- 默认用途：全局默认 / 项目默认 / profile 默认。

#### 8.2.4 前端页面目录

- 模型 Provider 列表。
- 新增 / 编辑 Provider。
- API Key 输入与脱敏展示。
- Endpoint 连通性测试。
- 模型名称配置。
- 设置默认 Provider。
- 项目绑定 Provider。
- Profile 绑定 Provider。

#### 8.2.5 后端能力目录

- 新增 provider 配置表。
- API Key 加密存储或最小化脱敏存储。
- Provider 运行时解析。
- OpenAI-compatible request factory。
- 连接测试接口。
- 调用失败时的错误分类：
  - 鉴权失败
  - endpoint 不可达
  - 模型不存在
  - 超时
  - 响应格式不兼容

#### 8.2.6 分阶段落地

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| Phase 1 | OpenAI / Anthropic endpoint 和 model 可配置 | 前端可修改 endpoint 和 model |
| Phase 2 | 增加 OpenAI-compatible provider | 可接入兼容 OpenAI API 的模型网关 |
| Phase 3 | 项目级 provider 绑定 | 不同项目可使用不同模型配置 |
| Phase 4 | 连通性测试与错误诊断 | 配置错误可在页面明确展示 |

#### 8.2.7 预期价值

- 支持公司内网模型网关。
- 支持私有化部署场景。
- 降低对单一模型厂商的绑定。
- 便于按成本、效果和项目敏感性选择不同模型。

### 8.3 本章结论

模型配置通用化不是审查能力本身，但它决定平台能否适配更多部署环境和团队模型策略，是后续推广落地的重要基础能力。

## 9. 方向五：Dashboard 仪表盘

### 9.1 章节目标

说明如何通过 dashboard 量化平台价值，并反向指导规则和 AI Review 优化。

### 9.2 可展开目录

#### 9.2.1 当前问题

- 当前系统保存了任务、结果和通知记录，但还缺少统一统计视图。
- 无法直观看到平台发现了多少风险、误判率是多少、哪些项目风险最多。
- 没有数据支撑规则优化和模型效果评估。

#### 9.2.2 建设目标

- 展示审查任务总览。
- 展示风险类型和风险等级趋势。
- 展示 AI Review 候选问题、有效问题、误判问题。
- 展示项目维度质量趋势。
- 展示通知触达和处理状态。
- 为技术负责人提供质量治理视角。

#### 9.2.3 Dashboard 指标目录

基础审查指标：

- 审查任务数。
- MR 审查数。
- Push 审查数。
- AI Review 触发次数。
- AI Review 跳过次数。
- 平均审查耗时。

风险指标：

- `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` 数量。
- DB / MQ / CACHE / CONFIG / API 风险分布。
- 高频风险文件。
- 高频风险项目。
- 高频风险规则。

AI Review 质量指标：

- 候选 finding 数。
- 有效 finding 数。
- 误判数。
- 不采纳数。
- 确认数。
- 修复数。
- 误判率。
- 确认率。

通知指标：

- 钉钉推送次数。
- 推送成功率。
- `SKIPPED` 数量。
- @ 作者次数。
- 高风险通知处理状态。

#### 9.2.4 页面模块目录

- 平台总览卡片。
- 审查任务趋势图。
- 风险等级分布。
- 风险类型分布。
- 项目 Top N。
- AI Review 有效性分析。
- 高频误判列表。
- 高频风险规则列表。
- 最近高风险任务列表。

#### 9.2.5 数据前提

Dashboard 建议在 feedback 能力之后建设，否则只能展示任务数量和 finding 数，无法体现 AI Review 质量。

建议先完成：

- finding feedback。
- finding 状态。
- 通知记录完善。
- 项目级配置。
- Push AI Review gate 触发记录。

#### 9.2.6 分阶段落地

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| Phase 1 | 基础任务和风险统计 | 可查看审查量、风险等级、风险类型 |
| Phase 2 | AI Review 质量统计 | 可查看候选数、有效数、误判率 |
| Phase 3 | 项目维度趋势 | 可按项目查看风险趋势 |
| Phase 4 | 规则优化分析 | 高频误判和高频风险可辅助规则调优 |

#### 9.2.7 预期价值

- 用数据证明平台是否真的减少人工审查成本。
- 帮助识别高风险项目和高风险变更类型。
- 发现规则误报和漏报方向。
- 为团队质量治理提供持续指标。

### 9.3 本章结论

Dashboard 不应过早做成“大屏”，而应基于真实反馈数据展示平台是否发现了有效问题、降低了误判、推动了处理。

## 10. 分阶段路线图

### 10.1 近期：打牢反馈与可信基础

目标：让 AI Review 结果可处理、可解释、可反馈。

建议任务：

1. 落地 finding fingerprint。
2. 新增 finding feedback 表和 API。
3. AI Review result response 携带 feedback。
4. 前端支持误判 / 不采纳 / 确认操作。
5. 有效问题数排除已取消 finding。

验收标准：

- 用户可以标记一条 AI finding。
- 刷新后状态保留。
- 已取消 finding 不计入有效问题数。

### 10.2 中期：前置触发与精准通知

目标：让问题在 push 阶段更早暴露，并让高风险问题触达责任人。

建议任务：

1. Push webhook 使用 GitLab compare API 拉取完整 diff。
2. 增加 AI Review gate 判断。
3. 项目级配置 Push AI Review 策略。
4. 钉钉高风险消息 @ 作者。
5. 平台详情页支持 file change / finding 锚点。

验收标准：

- 命中高风险规则的 push 能自动触发 AI Review。
- 未命中规则的 push 不触发 AI Review。
- 高风险问题能 @ 作者并跳转到具体文件变更。

### 10.3 中后期：沉淀经验与扩展模型

目标：让平台适应不同团队和不同模型环境。

建议任务：

1. 反馈沉淀为 review memory。
2. Review 执行前注入相关 memory。
3. Review memory 管理页。
4. Endpoint / model 可配置。
5. OpenAI-compatible provider。
6. 项目级 provider 绑定。

验收标准：

- 历史误判能影响后续 AI Review prompt。
- 不同项目可配置不同模型服务。

### 10.4 后期：数据化治理

目标：通过 dashboard 展示平台价值，并指导规则和模型优化。

建议任务：

1. 审查任务统计。
2. 风险类型趋势。
3. AI Review 有效性分析。
4. 高频误判分析。
5. 项目质量趋势。

验收标准：

- 可以按项目、时间、风险类型查看平台效果。
- 可以看到 AI Review 误判率和确认率。
- 可以找到需要优化的规则和高风险项目。

## 11. 预期收益

### 11.1 对开发者

- 更早发现提交中的风险。
- 高风险问题能被明确指出并定位到文件。
- 对误判可以反馈，不再被重复打扰。

### 11.2 对 Reviewer

- 从“通读所有 diff”转向“优先看高风险变更”。
- AI Review 和规则扫描提供候选问题。
- 反馈结果能沉淀为团队审查偏好。

### 11.3 对测试和发布负责人

- 能看到 DB / MQ / 缓存 / 配置等变更影响面。
- 能基于风险卡片决定回归重点。
- 高风险变更可提前介入。

### 11.4 对技术负责人

- 能通过 dashboard 看到项目风险趋势。
- 能发现高频误判和高频风险类型。
- 能推动规则模板和审查策略持续优化。

## 12. 一句话总结

下一阶段平台的核心方向是：以规则引擎作为可信底座，以 AI Review 作为增强审查能力，以人工反馈沉淀团队知识，以钉钉和 GitLab 串联研发工作流，最终通过 Dashboard 量化平台对研发质量的实际贡献。
