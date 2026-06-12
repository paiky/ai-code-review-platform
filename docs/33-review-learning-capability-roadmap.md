# Review 自我学习能力分层规划：从反馈池到项目记忆、上下文自适应与评估闭环

## 状态

- 当前状态：能力愿景与后续推进计划已梳理；`docs/32` 的 V2-A 到 V2-E 已落地，V2-F-1 / V2-F-2 / V2-F-3 已落地，V2-F-5 本地仓库 mirror clone / fetch / worktree 最小闭环、V2-F-6 `METHOD_DELETED / METHOD_SIGNATURE_CHANGED` 引用搜索 Retriever MVP、V2-F-7 本地引用证据注入 Context Pack、V2-F-8 前端高准确模式摘要 / 人工沉淀入口熄灯、V2-F-9 生产验证与 V2-F-10 本地 workspace 清理与磁盘保护已落地。短期主线已调整为 `docs/34-local-repository-context-retrieval-plan.md` 的本地仓库上下文检索 / 高准确 Review 模式；反馈池、项目策略、上下文不足人工标记等人工沉淀能力先作为暗能力保留，生产前端默认屏蔽。下一阶段建议先补 V2-F-11 高准确模式角色流转可观测，再推进 V2-F-12 规则缺口沉淀与优先级看板，之后进入 V2-F-13 DTO / VO 字段引用检索。
- 编写时间：2026-06-10
- 前置版本：
  - `docs/29-review-feedback-v1-implementation.md`
  - `docs/30-review-feedback-v2-policy-plan.md`
  - `docs/31-review-context-aware-v1_5-plan.md`
  - `docs/32-review-feedback-v2-mainline-roadmap.md`
- 当前高准确 Review 主方案：
  - `docs/34-local-repository-context-retrieval-plan.md`
- 目标：明确 Review 反馈学习不是“把所有反馈拼进初始 Prompt”，而是分层沉淀为项目记忆、上下文策略、风险校准、去重治理和效果评估，并逐步具备自动归因、聚类、候选生成、效果验证和灰度生效能力。

## 一、核心结论

反馈池不应该只是为了调整和约束初始 Prompt。

如果所有反馈最终都被写进一个越来越长的 Prompt，会带来：

- Prompt 污染。
- 不可解释。
- 不可回滚。
- 难以评估是否真的变好。
- 容易把上下文不足、项目规则、风险等级校准、重复 finding 等不同问题混在一起。

更合理的定位是：

```text
反馈池 = Review 学习信号入口 + 人工确认工作台 + 可追溯治理中心
```

后续自我学习能力应分层建设：

```text
L1 反馈记录闭环
L2 项目策略记忆
L3 上下文自适应
L4 风险等级与重复 finding 校准
L5 评估集与效果回归
L6 半自动策略候选推荐
```

初始 Prompt 应保持相对稳定；反馈学习的主要价值在于让平台知道：

- 哪些是项目事实。
- 哪些是上下文不够。
- 哪些是风险等级偏高或偏低。
- 哪些是重复提醒。
- 哪些反馈可以作为未来评估样本。

## 二、“自我学习”的定义

这里的“自我学习”不等于系统一开始就自动改 Prompt、自动改规则、自动放行策略。

更合理的定义是：

```text
系统自动完成发现模式、归因、聚类、生成候选、评估效果、推荐应用和持续监控；
人工只负责高风险学习结果的生效开关。
```

也就是说，长期目标不是让管理员永远从零写策略，而是让平台逐步具备这些能力：

1. 自动判断反馈属于项目规则、上下文不足、等级校准、重复 finding、规则不适用、Prompt 表达不准还是评估样本。
2. 自动聚合同项目、同风险类型、同代码模式下的相似反馈。
3. 自动生成项目策略、上下文补充策略、风险校准建议或去重规则候选。
4. 自动用已确认样本评估候选是否减少误判、是否引入漏报或等级偏差。
5. 自动推荐下一步改进，并持续监控生效后的反馈变化。
6. 未来只允许低风险、可回滚、可灰度的候选在严格边界内自动生效；高风险候选仍必须人工确认。

### 自动化等级阶梯

| 等级 | 能力 | 平台能自动做什么 | 人工角色 | 当前状态 |
|---|---|---|---|---|
| Level 0 | 人工反馈记录 | 记录反馈、回显、进入反馈池 | 提交和审核反馈 | 已完成 V1 |
| Level 1 | 自动分类和统计 | 按反馈类型、原因、项目、风险类型自动归因和统计 | 修正错误归因 | 上下文不足统计已在 V2-E 轻量落地；自动归因待后续 |
| Level 2 | 自动聚类相似反馈 | 发现同项目、同风险类型、同描述模式的重复误判 | 审核聚类是否合理 | 待 V4 |
| Level 3 | 自动生成候选 | 生成项目策略、上下文策略、等级校准或去重候选 | 确认是否生效 | 待 V4 |
| Level 4 | 自动评估候选效果 | 用评估集验证误判率、漏报风险和等级变化 | 决策是否采用 | 待 V3 / V4 |
| Level 5 | 低风险灰度自动生效 | 对低风险、可回滚候选做灰度启用和自动回滚 | 设置边界和审批高风险项 | 远期 |

当前已经具备 V1 反馈闭环、V2 项目策略记忆、V2-E 上下文不足轻量统计，以及 V2-F-1 / V2-F-2 / V2-F-3 Context Pack V0 后端闭环和 Context Planner 最小规则。短期优先用本地仓库上下文检索提升单次 Review 证据质量；真正的“自我”仍会从后续自动归因统计、V3 的评估集、V4 的自动聚类和候选生成开始显现。

## 三、学习信号分流

同一条反馈背后可能代表不同问题，不能统一处理成 Prompt 文案。

| 反馈信号 | 代表的问题 | 推荐沉淀位置 | 是否改初始 Prompt |
|---|---|---|---|
| `FALSE_POSITIVE + PROJECT_ALLOWED` | 项目规范与通用规则不一致 | 项目策略 `PROJECT_RULE` / `CONTEXT_FACT` | 否 |
| `FALSE_POSITIVE + CONTEXT_MISSING` | 模型看得不够 | Context Planner / Context Pack 策略 | 否 |
| `LEVEL_TOO_HIGH` | 风险等级校准问题 | Severity calibration / Profile 配置建议 | 通常否 |
| `DUPLICATE` | finding 去重或历史识别不足 | 指纹、去重规则、相似 finding 合并 | 否 |
| `RULE_NOT_APPLICABLE` | 规则模板或端类型配置不匹配 | Rule template / focus change types / target config | 否 |
| `DESCRIPTION_INACCURATE` | 输出表达或解释不清 | Prompt 输出协议或文案模板候选 | 可能 |
| `USEFUL` | 正样本 | 评估集 / gold cases | 否 |
| `FIXED` | finding 被采纳修复 | 评估集、规则有效性统计 | 否 |
| 后续可补 `MISSING_FINDING` | 漏报 | 评估集、规则覆盖、Prompt 关注点候选 | 可能 |

结论：

```text
只有“输出表达不准、审查关注点缺失、漏报模式稳定”这类反馈，才可能进入 Prompt 改进候选。
多数反馈应进入策略、上下文、校准、去重或评估层。
```

## 四、分层能力说明

### L1：反馈记录闭环

当前状态：已完成 V1。

能力：

- 风险项 / AI finding 提交反馈。
- 反馈入库。
- 任务详情回显。
- 反馈池筛选、查看和状态流转。

价值：

- 给后续学习提供可信数据源。
- 让用户知道反馈被平台记录，而不是消失在一次对话中。

不足：

- 不影响后续 Review。
- 不产生项目记忆。
- 不统计改进效果。

### L2：项目策略记忆

当前状态：V2-A 到 V2-D 已落地，详见 `docs/32-review-feedback-v2-mainline-roadmap.md`。

能力：

```text
高质量反馈
  -> 管理员确认
  -> 项目策略 / 项目事实
  -> 后续 AI Review 注入
```

典型策略：

- 本项目统一由网关鉴权，Controller 未显式鉴权不应直接判定高风险。
- 本项目统一使用 GlobalExceptionHandler，Controller 未显式 try-catch 不应直接判定异常处理缺失。
- 本项目 Redis key 统一由工具类生成，不能仅凭局部字符串片段判定 key 不规范。

亮点：

- 平台开始记住“这个项目应该怎么审”。
- 策略可追溯到来源反馈。
- 策略可启用、停用、编辑、回滚。
- 不污染全局 Prompt，不影响其它项目。

首版边界：

- 只注入 `PROJECT_RULE / CONTEXT_FACT`。
- 暂缓自动忽略、自动降级、跨项目共享。

### L3：上下文自适应

当前状态：V1.5 已完成上下文状态表达；V2-E 已补上下文不足筛选、缺失上下文类型和统计；V2-F-1 已落地 Context Pack V0 后端最小闭环，V2-F-2 已补同文件上下文片段 V0，V2-F-3 已补 Context Planner 最小规则，V2-F-5 已补本地 mirror clone / fetch / task head worktree 准备闭环，V2-F-6 已补删除方法 / 签名变更的本地引用搜索 Retriever MVP，V2-F-7 已把本地引用证据按预算注入 Context Pack，V2-F-8 已在前端展示高准确模式证据摘要并默认屏蔽人工沉淀入口，V2-F-9 已完成生产验证与效果复盘。当前 Context Pack 会注入 changed files 摘要、同文件上下文可用性说明、预算内同文件片段、上下文不足反馈统计摘要、`contextPlan / plannerSignals / requestedContexts`、`localRepositoryContext`、`localReferenceSearch` 摘要、`localReferenceContext` 引用证据和 `unavailableContexts`。

2026-06-11 调整：L3 的短期实现重点从“继续增加人工上下文反馈统计”调整为“本地仓库上下文检索”。也就是先通过本地 mirror clone / fetch、task worktree、`rg` 引用搜索和 bounded snippets 提升单次 Review 准确率，再用反馈池和评估集验证效果。

能力：

```text
上下文不足反馈
  -> 统计缺失上下文类型
  -> 优化 Context Planner
  -> 下次 Review 补充更合适的证据
```

这类反馈不应该转成项目策略。例如：

```text
删除方法被误报风险
```

更可能说明模型缺少：

- 同文件剩余方法。
- 引用搜索结果。
- 调用方迁移信息。
- 编译或测试结果。

推荐演进：

1. 先统计 `CONTEXT_MISSING`。
2. 已完成通用 `Context Pack V0` 后端最小闭环和同文件上下文片段 V0。
3. 已完成 Context Planner 最小规则，把删除方法、签名变更、字段 / DTO、DB / SQL / mapper、缓存写入删除、MQ 配置和配置文件变更转成 requested context 提示。
4. 当前优先按 `docs/34` 实现本地仓库检索：先支持删除方法 / 方法签名变更的引用搜索，再逐步扩展 DTO、DB、缓存、MQ 和配置检索。

亮点：

- 不是让模型“记住别报这个”，而是让模型“下次看更多证据再判断”。

### L4：风险等级与重复 finding 校准

当前状态：未落地。

能力：

- 从 `LEVEL_TOO_HIGH / LEVEL_TOO_LOW` 反馈中发现等级偏差。
- 从 `DUPLICATE` 反馈中发现重复 finding。
- 给管理员提供校准建议。

示例：

- 某项目 `TEST_GAP` 长期被用户标记等级过高，可以提示是否调整该项目测试缺口风险上限。
- 某类相同 finding 多次出现，可以优化 fingerprint 或合并展示。
- 某 Provider 在某类问题上等级明显偏高，可作为 Provider/Profile 调优依据。

首版建议：

- 只做统计和建议。
- 不自动降级。
- 不自动删除 finding。

亮点：

- Review 结果不再只看单次模型输出，而是能被长期反馈校准。

### L5：评估集与效果回归

当前状态：未落地，是后续“自我学习可信度”的关键。

能力：

```text
已确认反馈
  -> gold cases
  -> Prompt / Provider / 策略变更前后回归
  -> 判断误判率、漏报率、等级准确性是否改善
```

可以回答：

- 新 Prompt 是否减少误判。
- 新 Provider 是否更容易漏报。
- 某条项目策略是否导致安全问题被压低。
- 最近 30 天误判率是否下降。

建议样本来源：

- `USEFUL`：正样本。
- `FIXED`：被采纳修复样本。
- `FALSE_POSITIVE + VALID`：误判样本。
- `LEVEL_TOO_HIGH`：等级校准样本。
- 后续 `MISSING_FINDING`：漏报样本。

亮点：

- 从“我们会学习”升级为“我们能证明学习后变好了”。

### L6：半自动策略候选推荐

当前状态：远期能力。

能力：

```text
多条相似反馈
  -> 系统聚类
  -> 生成策略草案
  -> 管理员确认
  -> 小范围启用
  -> 持续观察效果
```

原则：

- 系统只推荐，不自动生效。
- 管理员确认后才注入。
- 生效后可观察误判率是否下降。
- 策略导致争议时可停用或回滚。

亮点：

- 平台开始具备半自动学习能力，但仍保留人类治理边界。

## 五、自动学习闭环

长期闭环应从“用户反馈”走到“可验证改进”：

```text
反馈进入反馈池
  -> 系统自动归因
  -> 系统聚类相似反馈
  -> 系统生成候选学习结果
  -> 评估集验证候选效果
  -> 人工确认或低风险灰度
  -> 后续 Review 生效
  -> 持续监控反馈变化
  -> 无效或有副作用则停用 / 回滚
```

不同候选的生效目标不同：

- 项目规则候选：进入 `project_review_policies`。
- 上下文候选：进入 Context Planner / Context Pack backlog。
- 等级校准候选：进入 Profile 或项目级 severity calibration。
- 去重候选：进入 finding fingerprint / dedupe 规则。
- Prompt 候选：进入 Prompt/Profile 版本候选，并经过评估集回归。

## 六、产品亮点表达

对外可以总结为三句话：

### 1. 项目级记忆

平台能记住每个项目已经确认的工程事实和审查约定，而不是每次都让模型从零判断。

### 2. 上下文自适应

平台能从“上下文不足”反馈中学习下次应该补什么证据，而不是只靠更长 Prompt 硬猜。

### 3. 可验证改进

每条学习都可追溯、可停用、可回滚，并能通过反馈统计和评估集验证是否真的降低误判。

## 七、推荐后续路线

### 当前主线

```text
V2：项目策略记忆
  -> V2-A 后端策略库与反馈转策略 API
  -> V2-B 策略 Prompt 注入与可观测
  -> V2-C 前端反馈池生成策略与项目策略管理
  -> V2-D 文档与示例收口
  -> V2-E 上下文不足反馈轻量统计
```

### 下一轮增强

```text
V2-F / 高准确 Review：本地仓库上下文检索
  -> 已完成：本地 mirror clone / fetch / worktree
  -> 已完成：METHOD_DELETED / METHOD_SIGNATURE_CHANGED 引用搜索
  -> 已完成：引用证据注入 Context Pack
  -> 已完成：前端展示高准确模式证据摘要
  -> 已完成：人工沉淀能力前端默认屏蔽
  -> 已完成：生产验证与效果复盘
  -> 本地 workspace 清理与磁盘保护
```

说明：V2.5 的反馈自动归因和更完整上下文不足统计不取消，但后移到本地检索生产验证和 workspace 清理硬化之后。

### 中期能力

```text
V3：Review 质量评估集与效果看板
  -> gold cases
  -> Prompt / Provider / 策略变更回归
  -> 误判率、采纳率、等级准确性
```

### 后续能力

```text
V3.5：风险等级与重复 finding 校准
V4：自动聚类与半自动策略候选推荐
V5：更完整的项目知识检索 / 语义索引 / RAG 候选
V6：低风险学习结果灰度自动生效与自动回滚
```

### V2 到 V6 的学习推进关系

```text
V2：先让学习结果有地方生效，也就是项目策略记忆
V2-F：先通过本地仓库检索提升单次 Review 证据质量
V2.5：让系统自动归因和统计反馈信号
V3：建立评估集，让系统知道本地检索、Prompt、策略或 Provider 改动有没有变好
V3.5：做风险等级和重复 finding 的校准建议
V4：自动聚类反馈并生成候选策略 / 候选规则
V5：从反馈分布中学习 Context Planner 该补什么上下文，并考虑更完整语义索引
V6：在严格边界下做低风险灰度自动生效和自动回滚
```

## 八、反馈处理决策树

```text
收到反馈
  -> 是否信息充分？
      否 -> status=INSUFFICIENT，等待补充
      是 -> 继续
  -> 是否项目规则或项目事实？
      是 -> 候选 project_review_policies
      否 -> 继续
  -> 是否上下文不足？
      是 -> 进入 CONTEXT_MISSING 统计和 Context Planner backlog
      否 -> 继续
  -> 是否等级问题？
      是 -> 进入 severity calibration backlog
      否 -> 继续
  -> 是否重复提醒？
      是 -> 进入 dedupe/fingerprint backlog
      否 -> 继续
  -> 是否表达不准或审查关注点缺失？
      是 -> 进入 Prompt/Profile 改进候选
      否 -> 进入评估集或普通归档
```

## 九、数据与治理原则

### 必须可追溯

所有学习结果应能追溯到：

- 来源任务。
- 来源 finding / risk item。
- 来源反馈。
- 管理员确认记录。

### 必须可回滚

所有会影响后续 Review 的学习结果都应支持：

- 启用。
- 停用。
- 编辑。
- 查看版本或更新时间。

### 不自动扩大影响范围

首版项目策略只影响同一 `project_id`。

暂不做：

- 项目组共享。
- 平台级共享。
- 跨项目自动迁移。

### 不把上下文不足误判变成项目规则

如果反馈原因是 `CONTEXT_MISSING`，默认不允许直接转换为项目策略。

因为它的正确处理方式是补上下文，而不是告诉模型以后忽略这类问题。

### 不自动修改初始 Prompt

Prompt 改进应作为候选变更，经过：

- 人工确认。
- 评估集回归。
- 版本记录。
- 可回滚。

### 自动学习也必须可治理

即使进入 Level 3 以后，系统生成的候选也必须保留治理边界：

- 候选来源可追溯。
- 候选影响范围可计算。
- 候选生效前可预览。
- 生效后可监控反馈变化。
- 出现负面信号可自动建议停用。
- 高风险候选必须人工确认。

## 十、分阶段落地 Prompt

### 总控 Prompt

```text
请阅读 AGENTS.md、README.md、docs/29-review-feedback-v1-implementation.md、docs/30-review-feedback-v2-policy-plan.md、docs/32-review-feedback-v2-mainline-roadmap.md、docs/33-review-learning-capability-roadmap.md。

后续 Review 学习能力按 docs/33 的分层模型和自动化等级阶梯推进。不要把所有反馈都直接写入初始 Prompt。每条反馈应先判断属于项目策略、上下文不足、风险校准、重复 finding、规则配置、Prompt/Profile 改进还是评估样本。

当前 docs/32 的 V2-A 到 V2-E 已落地，V2-F-1 / V2-F-2 / V2-F-3 / V2-F-5 / V2-F-6 / V2-F-7 / V2-F-8 / V2-F-9 / V2-F-10 已落地或已验收。后续短期主线按 docs/34 进入 V2-F-11：高准确模式角色流转可观测；V2-F-11 验收后再进入 V2-F-12：规则缺口沉淀与优先级看板；V2-F-12 验收后再进入 V2-F-13：DTO / VO 字段引用检索。反馈池、项目策略、上下文不足人工标记等人工沉淀能力先保留后端和数据结构，但生产前端默认屏蔽入口。更完整的自动归因统计、评估集、风险校准、自动聚类和半自动策略候选仍作为后续阶段。

每次只推进一个阶段。允许自主修改 backend-python、frontend、docs、examples、tests 中与当前阶段直接相关的文件；不要修改 legacy Java backend；不要做自动 Prompt 改写、自动风险降级、自动忽略 finding、模型微调、复杂 RAG、跨项目策略共享或无限制全项目扫描。

每个阶段完成后必须停止，输出“改了什么、为什么、如何验证”，等待用户验证并明确回复“继续下一阶段”后再推进。
```

### V2.5 Prompt：反馈自动归因与上下文不足统计

```text
请只落地 Review 学习 V2.5：反馈自动归因与上下文不足统计。

说明：`CONTEXT_MISSING` 筛选、缺失上下文类型和基础分布统计已在 docs/32 V2-E 轻量落地。本阶段若继续推进，应聚焦自动归因标签和更完整的统计分析，不重复实现 V2-E。

范围：
- backend-python/app/review_feedback/*
- frontend/src/App.jsx
- frontend/src/styles.css
- 相关 tests
- docs/33 验证记录

要求：
- 根据 feedbackType、reasonType、sourceType、riskType、contextStatus 等字段给反馈生成学习归因标签。
- 反馈原因支持 CONTEXT_MISSING 筛选。
- 支持选择缺失上下文类型。
- 反馈池展示上下文不足数量和分布。
- 不自动创建项目策略。
- 不自动影响后续 Review。
- 不自动改 Prompt。

完成后停止。
```

### V3 Prompt：评估集与效果看板

```text
请只设计并落地 Review 学习 V3 的最小评估集能力。

范围按实现前分析确定，但不得修改 legacy Java backend。

要求：
- 从已确认反馈中沉淀 gold cases。
- 能按项目、Provider、Profile、风险类型查看样本。
- 能记录一次 Prompt / Provider / 策略变更前后的评估结果。
- 不要求真实模型批量重跑，首版可以先做数据结构、API 和人工导入/标注。
- 不自动改 Prompt。

完成后停止。
```

### V3.5 Prompt：风险等级与重复 Finding 校准

```text
请只设计并落地 Review 学习 V3.5 的最小校准分析能力。

要求：
- 统计 LEVEL_TOO_HIGH / DUPLICATE 等反馈。
- 输出项目、风险类型、Provider、Profile 维度的校准建议。
- 不自动降级。
- 不自动删除 finding。
- 不自动改 Prompt。

完成后停止。
```

### V4 Prompt：半自动策略候选推荐

```text
请只设计 Review 学习 V4：自动聚类与半自动策略候选推荐。

要求：
- 根据多条相似 VALID 反馈自动聚类，并生成项目策略草案。
- 草案必须管理员确认后才生效。
- 草案必须可追溯到来源反馈集合。
- 不自动启用。
- 不跨项目共享。

先输出设计和最小数据结构，不编码，等待确认。
```

### V6 Prompt：低风险学习结果灰度自动生效

```text
请只设计 Review 学习 V6：低风险学习结果灰度自动生效与自动回滚。

要求：
- 只允许低风险、可回滚、作用域明确的学习结果进入灰度。
- 高风险策略、自动降级、自动忽略 finding 仍必须人工确认。
- 设计灰度范围、监控指标、负面信号和自动回滚规则。
- 先输出设计，不编码，等待确认。
```

## 十一、验收标准

长期 Review 学习能力应满足：

1. 反馈不会被无差别拼进初始 Prompt。
2. 项目策略可以从反馈人工确认生成，并只影响同项目。
3. 上下文不足反馈能进入统计和 Context Planner backlog。
4. 等级过高和重复提醒能进入校准分析。
5. 有用、已修复、误判样本能逐步形成评估集。
6. 所有会影响后续 Review 的学习结果都可追溯、可停用、可回滚。
7. 平台能用数据说明 Review 质量是否改善，而不仅是声称“已学习”。
8. 系统能自动完成反馈归因、相似反馈聚类、候选学习结果生成和候选效果评估。
9. 自动生效仅限低风险、可灰度、可回滚场景，高风险学习结果必须人工确认。

## 十二、当前下一步

当前不优先恢复人工沉淀产品入口，也不建议马上扩展 DB / 缓存 / MQ / 配置检索器。V2-F-10 已完成后，先补高准确模式角色流转可观测，解决 Planner / Retriever / Snippet / 预算裁剪难以理解的问题；再把规则缺口沉淀成跨任务优先级看板；之后优先扩展 DTO / VO 字段引用检索，覆盖任务 669 这类真实高频场景。

下一步按 `docs/34-local-repository-context-retrieval-plan.md` 推进本地仓库上下文检索：

```text
V2-F-4：本地仓库检索主方案与前端人工沉淀熄灯
V2-F-5：本地仓库 mirror clone / fetch / worktree 最小闭环（已完成）
V2-F-6：METHOD_DELETED / METHOD_SIGNATURE_CHANGED 引用搜索 Retriever MVP（已完成）
V2-F-7：本地引用证据注入 Context Pack（已完成）
V2-F-8：前端展示高准确模式证据摘要，并屏蔽人工沉淀入口（已完成）
V2-F-9：生产验证与效果复盘（已验收）
V2-F-10：本地 workspace 清理与磁盘保护（已完成）
V2-F-11：高准确模式角色流转可观测
V2-F-12：规则缺口沉淀与优先级看板
V2-F-13：DTO / VO 字段引用检索 Retriever
```

V2-F-13 完成后，再根据真实反馈分布决定进入 V3 评估集，或按评估结果扩展 DB / 缓存 / MQ / 配置检索。
