# Review 平台完整产品目标路线

## 状态

- 当前状态：完整产品目标文档。用于回答“最终要做成什么产品、用户如何使用、从当前状态到完整产品分几步走”；不负责决定当前实施阶段。
- 编写时间：2026-07-01
- 当前阶段：以用户明确指定的专题文档及其中的停止点为准。
- 历史路线归档：`docs/36-review-platform-current-roadmap.md`，已于 2026-07-24 冻结，不再维护。
- 历史与细节文档：
  - `docs/32-review-feedback-v2-mainline-roadmap.md`
  - `docs/33-review-learning-capability-roadmap.md`
  - `docs/34-local-repository-context-retrieval-plan.md`
  - `docs/35-review-quality-evaluation-and-rule-gap-governance.md`
  - `docs/39-review-accuracy-and-material-ui-roadmap.md`
  - `docs/40-review-evidence-pipeline-and-multi-target-roadmap.md`

说明：本文只在产品目标、长期里程碑或验收标准发生变化时更新。本文后续章节中把 `docs/36`
称为近期总控的内容属于历史路线记录，不再构成当前实施约束。

## 一、产品最终形态

完整产品不是一个“AI 评论机器人”，而是一个研发质量平台：

```text
代码变更进入平台
  -> 平台自动拿到 diff、仓库、上下文和项目规则
  -> 平台先做确定性检查和规则提醒
  -> 平台像受控本地 Agent 一样按需检索调用链、配置、DB、缓存、MQ、测试等证据
  -> AI 基于证据生成结构化 Review
  -> 高风险但证据不足的 finding 再定向补证据
  -> 用户在 MR / 平台 / 钉钉中处理结果
  -> 用户反馈进入评估集和项目策略
  -> 平台用回放证明后续改动是否真的减少误判
```

最终目标不是“模型说得更多”，而是：

```text
高风险结论有证据
证据不足时明确低置信
误判能被反馈和回放
规则、Retriever、Prompt、Provider 的改动能证明有效
```

## 二、用户体验目标

### 开发者

开发者不需要理解 Planner、Retriever、Context Pack。

日常体验应是：

```text
提交 MR
  -> 平台自动审查
  -> MR / 钉钉收到摘要
  -> 打开任务详情
  -> 看到必须处理、建议处理、仅提醒
  -> 点开 finding 查看证据、影响和修复建议
  -> 修复、忽略、标记误判或补充说明
```

finding 展示必须包含：

```text
问题是什么
风险等级
置信度
证据文件和行号
为什么这些证据支持结论
缺失了哪些上下文
建议如何修复
是否阻塞合并
```

### Reviewer / Tech Lead

Reviewer 需要的是影响面和可信结论：

```text
本次 MR 改了哪些关键能力
是否影响接口、DB、缓存、MQ、配置或事务
AI finding 哪些证据充分
哪些只是低置信提醒
是否有测试、编译或静态扫描失败
哪些问题必须在合并前处理
```

### 管理员

管理员关注配置和治理：

```text
项目组 / 端类型 / Profile / Provider 配置
钉钉通知和推送策略
Push / MR 自动 Review 策略
项目规则和项目事实管理
误判样本和质量看板
规则缺口是否值得补
Provider、Prompt、Retriever 改动是否变好
```

### 平台运维

平台运维关注稳定性和成本：

```text
任务队列积压
Provider 请求失败率
Review 平均耗时
token / 模型成本
本地 mirror / worktree 磁盘占用
GitLab token 和 clone 权限
数据库迁移和备份
异常任务重试与告警
```

## 三、完整产品必备能力

### A. 变更接入与任务闭环

必备：

- GitLab MR Hook / Push Hook / manual review。
- diff、changed files、base / head ref 拉取与 fallback。
- 审查任务、原始事件、分析结果、提醒卡片、AI Review 结果、通知记录落库。
- 重试、重跑、任务状态、失败原因可见。
- 钉钉通知和平台详情链接。

当前状态：基本已具备。

### B. 规则提醒卡片

必备：

- 识别接口、DB、缓存、MQ、配置等重点变更。
- 输出结构化提醒卡片，而不是散乱文本。
- 支持模板、项目配置、端类型配置。
- 支持前端展示和钉钉推送。

当前状态：基本已具备。

### C. 可信 AI Review 执行链

必备：

- Provider / Profile / Prompt 配置。
- 本地 mirror / worktree。
- Context Planner。
- Local Retriever。
- Context Pack 预算控制。
- `notInjectedEvidence` 或等价的未注入证据摘要。
- finding 的 `evidence / contextStatus / confidence / missingContext`。
- 高准确模式流转可观测。
- finding 级二次补证据执行器。

当前状态：大部分具备；finding 级二次补证据后端 MVP 与前端可观测入口已具备。

### D. 确定性检查证据

必备：

- 至少支持一种可配置检查入口，例如测试、lint、类型检查、静态扫描或敏感信息扫描。
- 检查结果能进入任务详情和 AI Review 证据包。
- 检查失败、超时、未配置都可解释。
- 确定性失败可以按项目策略决定是否阻塞。

当前状态：已具备敏感信息扫描 MVP 和 Context Pack 摘要注入；首次 AI Review 前自动 Preflight 尚未实现，按 `docs/40` 阶段 1 推进；lint、测试命令、类型检查等更多确定性工具待后续阶段。

### E. 质量评估与回放

必备：

- evaluation cases / gold cases。
- 人工 verdict：有效、误判、等级过高、等级过低、上下文不足、重复、漏报。
- 按项目、Provider、Profile、风险类型筛选。
- evaluation run / baseline / candidate 记录。
- 能比较改动前后的误判、漏报、等级偏差、耗时和成本。
- 规则缺口和 finding 级误判归因。

当前状态：评估样本、二次补证据、回放版本记录、质量看板、finding 级规则缺口归因和规则 / Retriever 改动验收门禁已具备 MVP；真实批量回放仍待后续阶段。

### F. 项目知识与反馈治理

必备：

- 用户可反馈 finding。
- 人工确认后的项目事实可沉淀为项目策略。
- 策略只影响同项目，支持启停、编辑、追溯。
- 上下文不足反馈进入 Context Planner / Retriever backlog。
- 不自动降级、不自动忽略高风险 finding。

当前状态：后端具备，生产前端默认隐藏；后续是否恢复入口取决于质量治理阶段。

### G. 平台运维与安全边界

必备：

- 任务队列、失败重试、进度事件。
- token、认证头、源码片段、provider raw output 的日志与前端脱敏边界。
- mirror / worktree 清理。
- Provider 成本、超时、失败率监控。
- 数据库迁移、备份、升级文档。

当前状态：部分具备，成本和运维看板不足。

## 四、可选能力

以下能力有价值，但不是完整产品第一阶段必须项：

- AST / LSP / tree-sitter 精确符号解析。
- 向量库 / RAG。
- 多模型仲裁。
- 自动生成并启用项目策略。
- 自动降级或自动忽略 finding。
- 跨项目策略共享。
- IDE 插件。
- 自动生成修复 MR。
- 复杂权限体系和组织级多租户。

原则：

```text
没有评估样本证明收益之前，不把可选能力变成主线。
```

## 五、从当前到完整产品的阶段路线

### T0：路线收口

目标：

- 明确 `docs/36` 是近期总控。
- 明确本文件是完整产品目标。
- 停止在 32~35 之间来回寻找下一阶段。

当前状态：已完成文档收口。

### T1：可信 Review 基础补齐

目标：

让平台从“能审查”升级为“能解释为什么这样审查”。

范围：

- P1：Review 质量评估集 MVP。
- P2：finding 级二次补证据执行器 MVP。
- P3：Review 回放与版本记录 MVP。
- P4：确定性检查证据接入 MVP。

验收：

- 至少能沉淀一批真实 finding 样本。
- 能标注有效、误判、上下文不足、等级问题、漏报。
- 高风险但上下文不足的 finding 能触发定向补证据。
- 至少一种确定性检查结果进入任务详情和 AI Review 证据包。
- 能记录一次 baseline / candidate 对比。

### T2：高频业务上下文补齐

目标：

基于评估样本和规则缺口，补最有收益的业务 Retriever。

候选能力：

- 缓存 key、读取点、写入点、删除点、过期策略检索。
- MQ producer、consumer、topic、group、幂等逻辑检索。
- 配置读取点、默认值、环境覆盖检索。
- 跨端调用方，例如前端引用后端接口。
- 测试覆盖和测试断言检索。

进入条件：

- 评估集证明该类缺口造成真实误判、漏报或上下文不足。
- 有明确目标样本。
- 有预算和耗时影响评估。

验收：

- 目标样本上下文充分性提升。
- 误判下降或漏报减少。
- 没有明显增加噪声、耗时或 token 成本。

### T3：质量治理产品化

目标：

让质量评估不只是后台数据，而是管理员可用的产品能力。

范围：

- Review 质量看板。
- Provider / Profile / 风险类型维度误判率。
- 上下文不足率、等级偏差、重复 finding、漏报样本。
- 规则 / Retriever 改动验收门禁。
- 规则缺口与 finding 级归因看板，并把现有“规则缺口”一级入口收敛为质量治理下的诊断维度。

验收：

- 管理员能回答最近误判集中在哪里。
- 管理员能判断是否值得补下一个 Retriever。
- 每次规则或 Prompt 改动有准入和退出记录。
- 规则缺口不再单独驱动实现优先级，必须和 evaluation case、回放结果或 finding 级归因关联后才进入后续 Retriever 决策。

### T4：项目知识与团队治理

目标：

让平台记住每个项目的工程事实，但不污染全局 Prompt。

范围：

- 恢复或优化反馈池入口。
- 项目策略管理产品化。
- 策略版本、来源反馈、启停、回滚。
- 项目组级配置建议，但不自动跨项目生效。
- Prompt 预览和策略注入可观测。

验收：

- 项目策略能减少特定项目反复误判。
- 策略可追溯、可回滚。
- 上下文不足反馈不会被错误转换为项目策略。

### T5：工程化与规模化

目标：

让平台适合长期在团队内运行。

范围：

- Review 调度队列增强。
- 并发、限流、超时、重试策略。
- Provider 成本统计和失败率监控。
- 本地仓库缓存容量和清理策略可视化。
- 部署、备份、升级和回滚流程。
- 审计日志和敏感信息脱敏。

验收：

- 多项目并发 Review 稳定。
- 失败任务可诊断、可重试。
- 运维能看到成本、耗时、失败率和磁盘占用。

### T6：高级智能化

目标：

在治理边界清楚后，再引入更强的自动化能力。

候选能力：

- 自动聚类相似误判。
- 自动生成项目策略候选。
- 自动生成 Retriever / Prompt 改进候选。
- 多模型对比和候选 Provider 推荐。
- 低风险学习结果灰度启用和自动回滚。
- IDE / MR 双向交互。
- 自动修复建议升级为可提交 patch。

进入条件：

- 已有评估集和回放。
- 已有质量看板。
- 已有策略启停、回滚和审计。

验收：

- 自动候选不直接生效，高风险结果必须人工确认。
- 生效后能持续监控误判、漏报和负面反馈。

## 六、完整产品验收标准

完整产品至少要能回答这些问题：

1. 本次 MR 改了哪些关键能力？
2. 哪些问题必须处理，哪些只是建议，哪些只是提醒？
3. 每个高风险 finding 的证据是什么？
4. 哪些 finding 上下文不足，为什么不足？
5. 平台是否查过调用方、DB、缓存、MQ、配置或测试？
6. 确定性检查有没有失败？
7. 用户标记误判后，平台如何沉淀和回放？
8. 最近一次规则、Retriever、Prompt 或 Provider 调整是否真的变好？
9. 哪些项目、Provider、Profile、风险类型最容易误判？
10. 下一个要补的能力是基于样本证明，还是只是看起来应该补？

如果这些问题答不上来，平台还不是完整产品。

## 七、当前推荐下一步

当前不直接进入 MQ、配置等后续 Retriever。

推荐从 `docs/36` 的近期阶段继续：

```text
docs/40 阶段 1：首次 Review 前确定性检查 Preflight
```

M1-M10 和 docs/39 已完成。阶段 1 先修复 `SECRET_SCAN` 只能人工运行、无法进入首次 Review Context Pack 的时序缺口；之后再建立 Planner 多端感知基线。后续进入 MQ、配置、测试覆盖、跨端调用方或任一语言 Retriever 前，仍必须由评估样本、归因、回放和验收记录证明高价值。

## 八、Agent 总控 Prompt

```text
请阅读 AGENTS.md、README.md、docs/36-review-platform-current-roadmap.md、docs/37-review-platform-target-product-roadmap.md、docs/40-review-evidence-pipeline-and-multi-target-roadmap.md。

docs/36 是近期阶段总控，docs/37 是完整产品目标。后续推进必须先满足 docs/36 当前阶段，不要直接跳到 docs/37 的远期能力。

当前 M10 和 docs/39 已落地，等待用户确认是否进入 docs/40 阶段 1“首次 Review 前确定性检查 Preflight”。每次只推进一个阶段。允许自主修改 backend-python、frontend、docs、examples、tests 中与当前阶段直接相关的文件；不要修改 legacy Java backend；不要做自动 Prompt 改写、自动风险降级、自动忽略 finding、模型微调、复杂 RAG、跨项目策略共享或无限制全项目扫描。

每个阶段完成后必须停止，输出“改了什么、为什么、如何验证”，等待用户验证并明确回复“继续下一阶段”后再推进。
```

## 九、Goal 模式使用规则

`docs/37` 不建议直接作为一个超大 Goal：

```text
把 Review 平台推进到完整产品
```

原因：

- 完整产品跨度很大，包含产品体验、后端能力、前端页面、评估治理、运维和远期智能化。
- 一次性 Goal 容易绕过每阶段验收，导致方向失控。
- 很多阶段必须依赖真实任务样本、用户反馈或生产验证，不能靠 Agent 一次性闭门完成。

正确方式是把 `docs/37` 当作最终目标地图，把 `docs/36` 当作当前阶段执行单。Goal 模式每次只创建一个阶段或一个阶段内的小目标。

### 推荐 Goal 粒度

推荐按这个粒度创建 Goal：

```text
完成 M9：规则 / Retriever 改动验收门禁
完成 M10：第一个评估驱动的业务 Retriever
完成 T2 中某一个经评估确认的专项 Retriever
完成 T4 中项目知识与反馈治理产品化
```

不推荐创建：

```text
完成整个 docs/37
补齐所有 Retriever
实现完整高准确 Review
实现完整自学习平台
实现全部可选能力
```

### 每个 Goal 的固定输入

每个 Goal 开始前必须明确：

- 本次 Goal 对应 `docs/36` 或 `docs/37` 的哪个阶段。
- 本次只解决哪个必须能力缺口。
- 本次允许修改哪些目录。
- 本次不做哪些事。
- 本次验收要跑哪些测试或人工验证。
- 完成后是否必须停止等待用户确认。

### 每个 Goal 的完成条件

每个 Goal 完成时必须输出：

- 改了什么。
- 为什么做。
- 对应解决了 `docs/36` / `docs/37` 的哪个能力缺口。
- 如何验证。
- 哪些测试已跑，哪些没跑以及原因。
- 下一阶段建议，但不得自动继续。

如果涉及实现改动，还必须：

- 补 API / schema / DTO 文档。
- 补最小测试。
- 补示例数据或最小验证步骤。
- 如遇到新的踩坑或误判根因，更新 `docs/10-local-dev-pitfalls.md`。

### 当前可启动的 Goal

当前可启动的 Goal 是：

```text
完成 docs/40 阶段 1：首次 Review 前确定性检查 Preflight。
```

建议 Goal 文案：

```text
请基于 AGENTS.md、README.md、docs/36-review-platform-current-roadmap.md、docs/37-review-platform-target-product-roadmap.md、docs/40-review-evidence-pipeline-and-multi-target-roadmap.md，完成 docs/40 阶段 1：首次 Review 前确定性检查 Preflight。

范围：
- backend-python
- frontend
- backend-python/tests
- docs / examples 中与阶段 1 直接相关的文件

目标：
- 在 MR、Push、manual、retry 的首次 Provider 调用前自动运行内置 SECRET_SCAN。
- 同一 task 同一次多模型调度只运行一次，各 reviewKey 复用同一结果。
- 检查失败默认 fail-open，将脱敏失败摘要写入 progress 和 Context Pack 后继续 Review。
- 保留现有手动运行 / 重跑 API，不做合并阻塞，不修改 finding。

要求：
- 先核对所有触发路径和多模型 fan-out 点，再确定 Preflight 编排位置。
- 补最小单元、契约和主链路测试；只有涉及前端变化时才运行前端 build。
- 更新 README、docs/36 和 docs/40 阶段记录。
- 完成后停止，输出改了什么、为什么、如何验证、遗留风险和下一阶段，等待用户确认是否进入 docs/40 阶段 2。
```

### Goal 模式停止规则

即使 Goal 模式开启，也必须遵守：

```text
一个 Goal 只完成一个阶段。
阶段完成后停止。
等待用户验证并明确确认“继续下一阶段”后，再启动下一个 Goal。
```

不得在同一个 Goal 中连续推进：

```text
P1 -> P2 -> P3
T1 -> T2
业务 Retriever A -> 业务 Retriever B
质量评估 -> 自动策略生效
```

## 十、完整开发阶段清单

本节把完整产品路线拆成可逐个开启 Goal 的开发阶段。阶段编号用于长期维护；每个阶段完成后必须停止，等待用户验证后再进入下一阶段。

### 阶段总览

```text
M0 路线收口
  -> M1 评估样本后端 MVP
  -> M2 评估样本前端与任务详情入口
  -> M3 finding 级二次补证据后端 MVP
  -> M4 二次补证据前端可观测
  -> M5 Review 回放与版本记录 MVP
  -> M6 确定性检查证据接入 MVP
  -> M7 Review 质量看板 MVP
  -> M8 规则缺口与 finding 级归因
  -> M9 规则 / Retriever 改动验收门禁
  -> M10 第一个评估驱动的业务 Retriever
  -> docs/40 阶段 1~3 证据前置与多端能力基线
  -> M11 业务 Retriever 扩展循环
  -> M12 项目知识与反馈治理产品化
  -> M13 平台运维、成本与安全治理
  -> M14 合并门禁与团队质量策略
  -> M15 高级智能化与自动候选
  -> M16 完整产品验收与发布收口
```

### M0：路线收口

状态：已完成。

目标：

- 建立 `docs/36` 近期总控。
- 建立 `docs/37` 完整产品目标。
- 旧文档 32~35 只作为历史阶段和细节参考。

产出：

- `docs/36-review-platform-current-roadmap.md`
- `docs/37-review-platform-target-product-roadmap.md`
- README 文档入口更新。

验收：

- 新对话能明确先读 `docs/36` 和 `docs/37`。
- 后续阶段不再从 32~35 中选择互相冲突的下一步。

### M1：评估样本后端 MVP

状态：已完成后端 MVP（2026-07-01），等待用户验证是否进入 M2。

目标：

- 建立 Review 质量评估集的后端基础。
- 能把某个 finding 或人工补充样本沉淀为 evaluation case。

范围：

- `backend-python`
- migrations / bootstrap SQL
- contract tests
- `docs/03-api-contract.md`
- examples 如需新增

核心能力：

- evaluation case 表结构。
- verdict 枚举：`TRUE_POSITIVE / FALSE_POSITIVE / LEVEL_TOO_HIGH / LEVEL_TOO_LOW / CONTEXT_MISSING / DUPLICATE / MISSING_FINDING / UNKNOWN`。
- 记录 `taskId / reviewKey / findingId 或 fingerprint / projectId / provider / profile / riskType / severity / contextStatus / humanComment / source`。
- M1 只记录 Provider / Profile、风险类型、等级、上下文状态和 finding 快照；Review 上下文摘要、rule gap 归因和 Context Pack 摘要放到 M5 / M8 后续阶段。
- 查询接口支持项目、Provider、Profile、风险类型、verdict 筛选。
- 不影响原 Review 结果。

边界：

- `evaluation_cases` 是质量评估样本，不替代 `review_item_feedbacks` 反馈池。
- M1 不做前端入口，前端标注和样本列表放到 M2。
- M1 不做真实模型回放，baseline / candidate 放到 M5。
- M1 不自动修改 Review 结果、风险等级、项目策略或 Prompt。

验收：

- 能通过 API 创建、查询、更新 evaluation case。
- 有契约测试。
- README 或 API 文档写清最小使用方式。

落地记录：

- 新增独立 `evaluation_cases` 后端模块和 bootstrap SQL，和 `review_item_feedbacks` 保持分离。
- 支持从已有 AI finding 或人工补充样本创建 evaluation case，并按项目、Provider、Profile、风险类型、verdict 查询。
- 支持更新 verdict、人工备注和样本标注字段；不回写原 Review 结果、不触发反馈池、项目策略、通知或模型回放。
- 已补 `docs/03-api-contract.md`、README 最小用法和后端契约测试。

停止点：

- 当前停止，等待用户确认是否进入 M2。

### M2：评估样本前端与任务详情入口

状态：已完成最小入口（2026-07-01），等待用户用真实任务验证。

目标：

- 让用户能从任务详情把 finding 标注为评估样本。
- 让管理员能查看基础样本列表。

范围：

- `frontend`
- 必要的后端小修
- docs / tests

核心能力：

- finding 卡片增加“标注样本 / 反馈为评估样本”入口。
- 支持选择 verdict 和填写备注。
- 新增或复用页面展示 evaluation cases 列表。
- 支持基本筛选。

验收：

- 能从真实任务详情沉淀至少一条样本。
- 前端 build 通过。
- 不恢复完整反馈池复杂能力，只做评估样本最小入口。

落地记录：

- 任务详情页 AI finding 操作区新增“标注评估样本”，提交 `source=AI_FINDING`、`taskId`、`reviewKey`、`fingerprint`、Provider、Profile、风险类型、等级、上下文状态、verdict 和人工说明。
- 新增“评估样本”基础列表页，支持按项目、Provider、Profile、风险类型、verdict 查询。
- 该阶段不修改原 Review 结果，不创建 review feedback，不生成项目策略，不触发模型回放。

停止点：

- 完成后停止，等待用户用真实任务标注一批样本。

### M3：finding 级二次补证据后端 MVP

状态：已完成后端 MVP（2026-07-01），M4 前端可观测、M5 回放记录、M6 确定性检查、M7 质量看板与 M8 规则缺口归因也已完成，等待用户验证是否进入 M9。

目标：

- 对高影响且上下文不足的 finding 做定向补证据。

范围：

- `backend-python/app/code_quality`
- `backend-python/app/review_context`
- migrations 如需持久化 refinement 结果
- tests

核心能力：

- 识别候选 finding：高影响、`contextStatus=PARTIAL / INSUFFICIENT`、存在缺口摘要。
- 复用 worktree、Planner、Retriever 和 Context Pack 预算。
- 只围绕少数 finding 检索，不重跑整个 Review。
- 记录 refinement 过程和结果。
- refinement 作为覆盖层展示，不静默覆盖原 finding。
- 失败不改变原 Review 结果。

验收：

- 至少一个单元 / 契约测试覆盖补证据计划、执行和失败降级。
- progress 不泄露 token、本地绝对路径、大段源码或 provider raw output。

落地记录：

- 新增 `code_quality_finding_refinements` 表，保存 finding 定位、触发条件、检索计划、证据摘要、仍缺失上下文、失败原因和时间。
- 新增 `POST /api/review-tasks/{taskId}/code-quality-refinements` 与 `GET /api/review-tasks/{taskId}/code-quality-refinements`，支持按 `reviewKey + findingIndex` 或 `fingerprint` 定位。
- 只允许 `CRITICAL / MAJOR / HIGH` 且 `PARTIAL / INSUFFICIENT` 的 finding 触发补证据；结果作为 `/code-quality-results` 的 `refinementOverlay` 显式覆盖层返回，不覆盖原 finding。
- 首版同步执行，不调用真实模型，不改 Prompt，不生成项目策略，不做前端可观测页面。

停止点：

- 已完成并停止；M5 已在后续阶段落地。

### M4：二次补证据前端可观测

状态：已完成最小前端可观测（2026-07-01），等待用户基于真实任务验证。

目标：

- 用户能看懂某个 finding 是否做过二次补证据，以及补到了什么。

范围：

- `frontend`
- 少量 API 展示字段调整
- docs / build

核心能力：

- finding 卡片展示补证据状态。
- 展示新增证据摘要、仍缺失上下文和置信度变化说明。
- 高准确模式流转增加 finding 级补证据节点。

验收：

- 前端 build 通过。
- 至少一个有 refinement 数据的任务能展示完整流程。

落地记录：

- 任务详情页只在 `CRITICAL / MAJOR / HIGH` 且 `PARTIAL / INSUFFICIENT` 的 AI finding 上展示“补证据 / 重新补证据”操作。
- finding 展开区展示 `refinementOverlay` 的状态、触发条件、检索计划摘要、补到的证据摘要、仍缺失上下文和失败原因，并明确不覆盖原 finding。
- 高准确模式流转新增 finding 级补证据汇总节点，只展示安全统计摘要，不展示源码、token、认证头、本地绝对路径或 provider raw output。

停止点：

- 已完成并停止；回放记录已在后续阶段落地，当前等待用户基于真实任务验证体验。

### M5：Review 回放与版本记录 MVP

状态：已完成 MVP（2026-07-01），M6 确定性检查、M7 质量看板与 M8 规则缺口归因也已完成，等待用户验证是否进入 M9。

目标：

- 建立 baseline / candidate 对比的记录能力，为后续证明“变准”做基础。

范围：

- `backend-python`
- frontend 最小列表或详情
- docs / tests

核心能力：

- evaluation run 表结构。
- 记录 sample set、Provider、Profile、model、prompt hash、Context Pack version、Retriever version、rule gap version。
- 记录 baseline / candidate 的 finding 摘要、状态、耗时和备注。
- 首版可人工触发和人工记录，不要求批量调用真实模型。

验收：

- 能创建一次 baseline run 和一次 candidate run。
- 能对比样本数量、finding 数量、误判数、上下文不足数、耗时。

停止点：

- 已完成并停止；M6 / M7 / M8 已在后续阶段落地，当前等待用户确认是否进入 M9。

落地记录：

- 新增 `evaluation_runs` 和 `evaluation_run_items`，记录 sample set、Provider、Profile、model、prompt hash、Context Pack version、Retriever version、rule gap version、baseline / candidate、状态、耗时和结果摘要。
- 新增 `POST /api/evaluation-runs`、`GET /api/evaluation-runs`、`GET /api/evaluation-runs/{runId}`、`PUT /api/evaluation-runs/{runId}/items/{itemId}`，支持基于已有 evaluation cases 初始化 run 并人工记录每个样本的结果摘要。
- 前端新增顶部导航“回放记录”，提供 run 列表和详情页；不做模型执行、质量看板或胜出版本选择。
- 该阶段不自动调用真实模型，不修改 Prompt，不修改原 Review 结果、项目策略、finding 等级或忽略状态。

### M6：确定性检查证据接入 MVP

状态：已完成 MVP（2026-07-01），等待用户用真实项目验证。

目标：

- 让 Review 不只依赖 AI，而能引入编译、测试、lint 或静态扫描结果。

范围：

- `backend-python`
- project / profile 配置
- frontend 展示
- tests / docs

核心能力：

- 支持配置一个最小检查命令或检查类型。
- 执行检查有超时、失败降级和日志脱敏。
- 检查结果进入任务详情和 AI Review Context Pack。
- 未配置不阻断 Review。

首选切入：

- 优先选择最容易跨项目落地的检查，例如敏感信息扫描、lint 命令配置或测试命令配置。

验收：

- 至少一种确定性检查结果能在任务详情可见。
- AI Review Prompt 能看到结构化检查摘要。
- 失败、超时、未配置都有清晰状态。

停止点：

- 完成后停止，等待用户用真实项目验证。

落地记录：

- 新增 `deterministic_check_runs` 表，记录 task、project、check type、状态、配置快照、耗时、失败原因、结果摘要和脱敏命中项。
- 新增 `GET /api/review-tasks/{taskId}/deterministic-checks` 与 `POST /api/review-tasks/{taskId}/deterministic-checks/run`，MVP 仅支持 `SECRET_SCAN`。
- 敏感信息扫描只处理当前任务 diff 新增行，不做全仓扫描、不执行外部命令；命中项只返回规则类型、相对路径、行号 / hunk 位置和脱敏证据摘要。
- AI Review Context Pack 注入 `deterministicChecks.securitySummary`，任务详情新增“确定性检查”tab；该阶段不自动阻塞合并、不修改 Prompt、不修改 Review 结果、不降级或忽略 finding、不生成项目策略。

### M7：Review 质量看板 MVP

状态：已完成 MVP（2026-07-01），M8 规则缺口与 finding 级归因也已完成，等待用户验证是否进入 M9。

目标：

- 管理员能看出当前 Review 质量问题集中在哪里。

范围：

- backend 聚合 API
- frontend 看板
- docs / tests

核心指标：

- 样本数。
- 误判率。
- 上下文不足率。
- 等级偏高 / 偏低数。
- 重复 finding 数。
- 漏报样本数。
- 按项目、Provider、Profile、风险类型拆分。

验收：

- 能回答最近误判最多的项目 / Provider / Profile / 风险类型。
- 能辅助判断是否值得补下一个 Retriever。
- 能承接现有规则缺口看板的主要诊断入口，后续允许将“规则缺口”一级导航降级或合并到质量看板。

停止点：

- 已完成并停止；M8 已在后续阶段落地，当前等待用户确认是否进入 M9。

落地记录：

- 新增只读 `/api/review-quality/dashboard` 聚合 API，不新增统计表，不改变 evaluation case / run / deterministic check 既有语义。
- 主指标以 `evaluation_cases.verdict` 为准，展示样本数、误判率、上下文不足率、等级偏高 / 偏低、重复 finding 和漏报样本。
- 支持按项目、Provider、Profile、风险类型、verdict 过滤，并返回项目 / Provider / Profile / 风险类型 top 维度摘要。
- evaluation runs、finding refinements、deterministic checks 只作为辅助诊断摘要；M7 不做 finding 级归因、不自动改 Prompt、不自动选胜出版本、不生成项目策略、不降级或忽略 finding。
- 前端新增顶部导航“质量看板”，展示过滤器、核心指标卡、verdict 分布、维度聚合表和辅助诊断区。

### M8：规则缺口与 finding 级归因

状态：已完成 MVP（2026-07-02），等待用户验证是否进入 M9。

目标：

- 把“规则缺口是否导致误判”从 task 级近似推进到 finding 级判断。

范围：

- evaluation case 扩展
- rule gap dashboard 扩展
- frontend 标注入口
- tests / docs

核心能力：

- 在 evaluation case 中关联 rule gap 摘要。
- 支持归因：`RULE_GAP_CAUSED / RULE_GAP_RELATED / NOT_RULE_GAP / PROMPT_ISSUE / MODEL_REASONING_ISSUE / PROJECT_POLICY_MISSING / INSUFFICIENT_LABEL`。
- 规则缺口推荐区分“高频缺口”和“已证明关联误判的缺口”。
- 收敛规则缺口产品入口：保留后端聚合和历史数据，把前端独立看板降级为质量治理 / 高准确模式诊断子页，或合并进质量看板。

验收：

- 能对一批误判 finding 标注归因。
- 看板推荐理由能显示归因依据。
- 一级“规则缺口”入口是否保留有明确结论：保留、降级或合并，并在 README / docs/36 中同步说明。

停止点：

- 已完成并停止，等待用户确认是否进入 M9。

落地记录：

- 扩展 evaluation case，保存规则缺口归因类型、脱敏 rule gap 摘要、归因说明、归因人和归因时间。
- 新增 `GET / PUT /api/evaluation-cases/{caseId}/rule-gap-attribution`，创建 AI finding 样本时自动带入最新 `CONTEXT_PACK_BUILT` 安全 rule gap 摘要。
- 质量看板新增 `ruleGapAttributionSummary`；规则缺口看板推荐项新增 `recommendationBasis` 和 `attributionSignals`，区分高频缺口与已被 evaluation case 证明关联的缺口。
- 前端“评估样本”新增编辑归因入口，“质量看板”和“规则缺口”展示归因统计摘要。

### M9：规则 / Retriever 改动验收门禁

状态：已完成 MVP（2026-07-02），M10 已在后续阶段落地。

目标：

- 让每次补规则、补 Retriever、调 Prompt 都有准入和退出记录。

范围：

- backend 数据结构 / API
- frontend 最小管理页
- docs / tests

核心能力：

- 准入记录：目标缺口、关联样本、预期收益、风险、成本。
- 退出记录：误判变化、上下文充分性变化、漏报风险、finding 数量变化、耗时 / token 影响。
- 不自动阻断线上 Review，先作为治理记录。

验收：

- 能为一次能力改动创建验收记录。
- 能关联 evaluation runs 和样本。

停止点：

- 完成后停止，后续才进入评估驱动的业务 Retriever。

落地记录：

- 新增 `review_quality_acceptance_gates` 表和 `/api/review-quality/acceptance-gates` 创建 / 查询 / 更新 API，记录 changeType、status、provider、profile、riskType、evaluationCaseIds、evaluationRunIds、安全 ruleGapSummary、admission 和 exit。
- 前端新增顶部导航“验收记录”，支持列表过滤、创建 / 编辑和详情查看；质量看板展示 `acceptanceGateSummary`。
- 该阶段只做人工治理记录，不自动阻断线上 Review，不自动选择胜出版本，不自动修改 Prompt、项目策略或 finding。

### M10：第一个评估驱动的业务 Retriever

状态：已完成 MVP（2026-07-02），等待用户验证是否进入 M11。

目标：

- 只选择一个由评估样本证明高价值的业务 Retriever。

候选：

- 缓存 Retriever。
- MQ Retriever。
- 配置 Retriever。
- 测试覆盖 Retriever。
- 跨端调用方 Retriever。

进入条件：

- M1~M9 已完成。
- 有样本证明该类缺口造成误判、漏报或上下文不足。
- 用户确认只补这一类。

验收：

- 目标样本上下文充分性提升。
- 误判下降或漏报减少。
- 耗时、token、噪声在可接受范围。

停止点：

- 完成后停止，不自动进入下一个业务 Retriever。

落地记录：

- 选择缓存 Retriever 作为第一个评估驱动业务 Retriever，依据是 M8 / M9 已沉淀的 `CACHE_WRITE_DELETE_CHANGED -> CACHE_USAGE_CONTEXT -> Add cache retriever` 评估样本、rule gap 归因和验收记录。
- 后端将 `CACHE_WRITE_DELETE_CHANGED` 纳入 Local Retriever 支持范围；Planner 从 diff 变更行提取 `cacheKeys / cacheNames / keyExpressions / cacheOperations` 安全摘要；Retriever 基于 bounded `rg --fixed-strings` 检索缓存 key、cache name、key expression 的读写 / 删除 / 过期使用点。
- Context Pack 命中后将 `CACHE_USAGE_CONTEXT` 标记为 `LOCAL_CACHE_USAGE_CONTEXT`，新任务不再把缓存 signal 归为 `UNSUPPORTED_PLANNER_SIGNAL`；该能力不连接运行期缓存实例，不自动改 Prompt、项目策略或 AI finding。
- 已补单元 / 契约测试和 README / API / 路线文档说明。

### M11：业务 Retriever 扩展循环

目标：

- 按评估结果逐个补齐后续业务 Retriever。

循环规则：

```text
选择一个高价值缺口
  -> 准入记录
  -> 实现一个 Retriever
  -> 回放评估
  -> 退出记录
  -> 停止等待确认
```

验收：

- 每个 Retriever 都有独立样本、测试、回放和验收记录。
- 不因为“看起来应该补”而实现。

停止点：

- 每补一个 Retriever 都停止。

### M12：项目知识与反馈治理产品化

目标：

- 恢复并优化反馈池、项目策略和项目事实能力，让项目知识可治理。

范围：

- 反馈池 UI。
- 项目策略管理。
- 策略版本、来源反馈、启停、回滚。
- Prompt 预览和策略注入可观测。

验收：

- 项目策略能减少特定项目反复误判。
- 策略可追溯、可停用、可回滚。
- 上下文不足反馈不会被转成项目策略。

停止点：

- 完成后停止，等待用户决定是否进入运维规模化。

### M13：平台运维、成本与安全治理

目标：

- 让平台适合长期、多项目运行。

范围：

- Review 队列增强。
- 并发、限流、超时、重试。
- Provider 成本和失败率统计。
- mirror / worktree 磁盘占用可视化。
- token、认证头、源码片段、provider raw output 脱敏审计。
- 部署、备份、升级和回滚流程。

验收：

- 多项目并发任务稳定。
- 运维能看到耗时、失败率、成本和磁盘占用。
- 敏感信息不进入日志、progress 或前端。

停止点：

- 完成后停止，等待用户确认是否进入合并门禁。

### M14：合并门禁与团队质量策略

目标：

- 把 Review 结果转成可配置的团队质量策略，而不是所有问题都一刀切。

范围：

- 阻塞 / 强提醒 / 弱提醒 / 信息 的策略配置。
- 项目组级 gate policy。
- MR 状态回写或 check status 设计。
- 人工豁免和审计。

验收：

- 能按项目组配置哪些结果阻塞合并。
- AI 低置信 finding 默认不阻塞。
- 确定性失败可配置为阻塞。
- 豁免有记录。

停止点：

- 完成后停止，等待用户确认是否进入高级智能化。

### M15：高级智能化与自动候选

目标：

- 在已有评估、回放、门禁和审计基础上，引入更强自动化。

候选能力：

- 相似误判自动聚类。
- 项目策略候选自动生成。
- Retriever / Prompt 改进候选自动生成。
- 多模型对比和 Provider 推荐。
- 低风险学习结果灰度启用和自动回滚。
- 自动修复建议升级为 patch。

边界：

- 自动候选不直接生效。
- 高风险策略必须人工确认。
- 自动降级、自动忽略 finding 仍默认禁止，除非有严格灰度和回滚。

验收：

- 候选来源可追溯。
- 生效前可预览。
- 生效后可监控误判、漏报和负面反馈。

停止点：

- 每个高级能力单独立项，不打包推进。

### M16：完整产品验收与发布收口

目标：

- 按完整产品验收标准做一次总体验收。

范围：

- README。
- API 契约。
- 部署文档。
- 示例数据。
- 前端主流程。
- 后端主链路。
- 测试矩阵。

验收：

- 至少一条真实或 demo 链路跑通：
  - webhook / manual
  - 变更分析
  - 提醒卡片
  - AI Review
  - 本地上下文检索
  - 二次补证据
  - 确定性检查证据
  - evaluation case
  - 回放记录
  - 通知
  - 前端可见
- 能回答“完整产品验收标准”中的 10 个问题。

停止点：

- 输出完整发布说明、已知限制和下一轮路线。
