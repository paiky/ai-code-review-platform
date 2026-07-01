# Review 质量评估与规则缺口治理推进计划

## 状态

- 当前总控入口：`docs/36-review-platform-current-roadmap.md`。本文件保留质量评估与规则缺口治理细节；近期阶段顺序以 `docs/36` 为准。
- 当前状态：新增方向文档。`docs/32`、`docs/33`、`docs/34` 已完成规则缺口看板、规则缺口推荐算法、本地仓库上下文检索、DTO / VO 字段引用检索、预算裁剪保护和 finding 级二阶段补证据设计。当前正在补最新一批高分规则缺口。
- 编写时间：2026-06-23
- 关联文档：
  - `docs/32-review-feedback-v2-mainline-roadmap.md`
  - `docs/33-review-learning-capability-roadmap.md`
  - `docs/34-local-repository-context-retrieval-plan.md`
- 目标：把“规则缺口补齐”从默认主线调整为“质量评估驱动的候选改进”，避免陷入永远补规则、却无法证明误判减少的循环。

## 一、背景

当前平台已经具备一套高准确 Review 的基础设施：

```text
GitLab webhook / manual review
  -> diff / changed files
  -> Context Planner
  -> 本地 mirror / worktree
  -> Local Retriever
  -> Context Pack
  -> AI Review
  -> progress / 高准确模式流转
  -> 规则缺口看板
```

规则缺口看板解决了一个重要问题：

```text
这次 Review 中，系统知道哪些上下文应该补，但当前 Planner / Retriever / 预算 / Prompt 还不能充分支持。
```

但它没有解决另一个更关键的问题：

```text
这些缺口是否真的造成误判？
补完某个缺口后，误判是否下降？
是否引入新的漏报、噪声、耗时或 token 成本？
```

当前继续补最新高分缺口是可以接受的短期收口动作，尤其当该缺口来自真实任务、真实反馈和明确高频场景。但如果后续持续按“看板高分 -> 补规则 -> 再看下一个高分”推进，平台会逐渐变成规则维护系统，而不是可验证变准的 Review 系统。

## 二、方向判断

规则缺口不是代码风险，也不是产品质量指标。它是平台能力缺口。

因此：

- 可以用规则缺口发现候选改进。
- 不能用规则缺口数量直接代表 Review 质量。
- 不能只因为某个缺口分高就默认进入实现。
- 不能把“补了规则”当成“减少了误判”。
- 后续每个规则 / Retriever / Prompt / 预算策略改动，都应能通过样本回放或人工标注证明收益。

新的主线判断：

```text
规则缺口看板 = 候选 backlog / 诊断入口
质量评估集 = 是否值得补、补完是否变好的验收入口
```

## 三、当前规则补齐的边界

当前正在补最新一批缺口规则，本计划不要求中断当前工作。

但从本批规则补齐开始，应增加最小治理边界：

1. 必须记录补齐原因：来自哪个缺口、哪些任务、哪些 signal、哪些误判或上下文不足现象。
2. 必须记录变更前预期：希望减少哪类误判，或提升哪类 finding 的上下文充分性。
3. 必须补最小回归样例：至少覆盖目标 signal 的正例、误判例或上下文不足例。
4. 完成后必须停止，不自动继续补下一类缺口。
5. 下一阶段优先建设质量评估与回放能力，而不是继续扩展 DB / 缓存 / MQ / 配置等更多 Retriever。

## 四、后续推进路线

### G0：当前高分缺口规则补齐收口

目标：

把当前正在补的最新规则缺口完成并收口，但不把它扩展为长期“补规则主线”。

要求：

- 明确本次补齐的缺口类型、signal、requested context 和建议能力。
- 不扩大到未确认的其它 Retriever。
- 不自动修改 Prompt 或风险等级。
- 不自动降级、不自动忽略 finding。
- 补齐后更新对应文档中的落地记录。
- 补最小测试和样例，至少证明新规则能产生预期上下文或缺口状态变化。

完成后停止，进入 G1。

### G1：Review 质量评估集 MVP

目标：

建立最小 gold cases，让平台开始记录“哪些 finding 是有效、误判、等级过高、上下文不足或漏报”。

最小数据：

- taskId
- reviewKey
- findingId 或 finding fingerprint
- projectId
- profileCode
- providerCode / model
- riskType
- severity
- contextStatus
- verdict：`TRUE_POSITIVE / FALSE_POSITIVE / LEVEL_TOO_HIGH / LEVEL_TOO_LOW / CONTEXT_MISSING / DUPLICATE / MISSING_FINDING / UNKNOWN`
- humanComment
- source：人工标注、反馈池、线上验证记录
- createdAt / updatedAt

首版可以先做后端数据结构、API 和最小前端入口，也可以先做文档化人工样本清单；不要求一开始自动跑模型。

验收：

- 能沉淀至少一批真实样本。
- 能按项目、Provider、Profile、风险类型筛选。
- 能区分误判、上下文不足、等级问题和漏报。
- 不自动影响 Review 结果。

### G2：Review 回放与版本记录

目标：

让规则、Retriever、Prompt、预算策略或 Provider 变更可以在同一批样本上做前后对比。

首版不要求真实大规模模型重跑，可以先记录可复现实验元数据：

- evaluationRunId
- sampleSetId
- profileCode
- providerCode / model
- promptVersion 或 promptHash
- contextPackVersion
- retrieverVersion
- ruleGapVersion
- localRepoContextEnabled
- input task / diff / context 摘要
- output finding 摘要
- run status
- reviewer notes

后续再接真实批量回放。

验收：

- 能记录一次“变更前 baseline”和一次“变更后 candidate”。
- 能对比 finding 数量、误判数、上下文不足数、等级变化和执行成本。
- 不要求自动判定胜负，但必须能支持人工判断。

### G3：规则缺口与 finding 级归因

目标：

把规则缺口从 task 级近似统计推进到 finding 级归因，回答“这个 finding 的误判是否真的由这个缺口导致”。

要求：

- 在 finding 或 evaluation case 中记录关联的 rule gap summary。
- 支持标注归因：
  - `RULE_GAP_CAUSED`
  - `RULE_GAP_RELATED`
  - `NOT_RULE_GAP`
  - `PROMPT_ISSUE`
  - `MODEL_REASONING_ISSUE`
  - `PROJECT_POLICY_MISSING`
  - `INSUFFICIENT_LABEL`
- 规则缺口看板推荐算法可以读取归因统计，但不能把 task 级近似统计当成精确证据。

验收：

- 至少能对一批误判 finding 标注是否由规则缺口导致。
- 看板推荐理由能区分“高频缺口”和“已证明关联误判的缺口”。

### G4：规则 / Retriever 改动验收门禁

目标：

让后续每个补规则动作都有明确准入和退出标准。

推荐门禁：

- 准入：
  - 缺口高频，或影响关键项目 / 关键风险类型。
  - 至少有若干已标注样本证明它和误判、漏报或上下文不足相关。
  - 有明确的可实现补齐策略和预算影响评估。
- 退出：
  - 目标样本误判下降或上下文充分性提升。
  - 关键漏报没有增加。
  - finding 数量没有明显膨胀。
  - token、耗时、检索失败率在可接受范围内。

首版门禁可以先由文档和测试记录执行，后续再做成系统化看板。

### G5：质量效果看板

目标：

从“规则缺口看板”补齐到“Review 质量看板”。

核心指标：

- 样本数。
- 人工确认有效率。
- 误判率。
- 上下文不足率。
- 等级偏高 / 偏低率。
- 重复 finding 比例。
- 漏报样本数。
- 按项目 / Provider / Profile / 风险类型拆分。
- 规则补齐前后对比。

验收：

- 能回答最近一次规则补齐是否改善目标样本。
- 能回答哪个 Provider / Profile / 风险类型最容易误判。
- 能回答是否值得继续补下一个规则缺口。

## 五、推荐执行顺序

短期建议：

```text
G0 当前规则补齐收口
  -> G1 Review 质量评估集 MVP
  -> G2 Review 回放与版本记录
  -> G3 规则缺口与 finding 级归因
  -> G4 规则 / Retriever 改动验收门禁
  -> G5 质量效果看板
  -> 再决定是否进入新的具体 Retriever
```

不建议：

```text
G0 当前规则补齐
  -> 继续补 DB Retriever
  -> 继续补缓存 Retriever
  -> 继续补 MQ Retriever
  -> 继续补配置 Retriever
  -> 再继续补更多规则
```

原因是第二条路线会不断扩大系统复杂度，却仍然无法证明 Review 质量变好。

## 六、与现有文档关系

### 与 docs/32 的关系

`docs/32` 继续记录 V2 反馈学习和高准确模式已落地阶段。

本文件不否定 V2-F-12 / V2-F-17 的价值，而是补上后续治理层：

```text
V2-F-17：给出规则缺口补齐建议
docs/35：决定哪些建议值得做，以及做完如何证明有效
```

### 与 docs/33 的关系

`docs/33` 已经把评估集与效果回归放在 L5 / V3。

本文件把它提前为下一阶段主线，是因为当前已经具备规则缺口看板和一批真实高准确模式数据，如果继续只补规则，会先进入复杂度陷阱。

### 与 docs/34 的关系

`docs/34` 负责本地仓库上下文检索和高准确 Review 模式。

本文件不要求停止本地检索能力，而是把后续本地检索扩展变成评估驱动：

```text
不是看见缺口就补 Retriever。
而是先证明该缺口导致误判，再补 Retriever，再用回放证明变好。
```

## 七、总控 Prompt

```text
请阅读 AGENTS.md、README.md、docs/32-review-feedback-v2-mainline-roadmap.md、docs/33-review-learning-capability-roadmap.md、docs/34-local-repository-context-retrieval-plan.md、docs/35-review-quality-evaluation-and-rule-gap-governance.md。

当前允许先完成用户正在推进的最新高分规则缺口补齐，但该工作只能作为 G0 收口，不得自动扩展到其它缺口或其它 Retriever。G0 完成后，下一阶段优先进入 Review 质量评估与回放能力建设，而不是继续机械补规则。

后续推进按 docs/35 的 G1 到 G5 分阶段执行。每次只推进一个阶段。允许自主修改 backend-python、frontend、docs、examples、tests 中与当前阶段直接相关的文件；不要修改 legacy Java backend；不要做自动 Prompt 改写、自动风险降级、自动忽略 finding、模型微调、复杂 RAG、跨项目策略共享或无限制全项目扫描。

每个阶段完成后必须停止，输出“改了什么、为什么、如何验证”，等待用户验证并明确回复“继续下一阶段”后再推进。
```

## 八、分阶段落地 Prompt

### G0 Prompt：当前高分缺口规则补齐收口

```text
请只完成当前用户已经确认的高分规则缺口补齐，并按 docs/35 的 G0 收口。

要求：
- 先说明本次补齐对应的缺口类型、signal、requested context 和建议能力。
- 只补当前确认的规则 / Retriever / 预算 / Prompt 约束，不扩展其它缺口。
- 补最小测试和样例，证明新能力能覆盖目标场景。
- 在相关 docs 中记录本次补齐原因、边界和验证结果。
- 不自动降级、不自动忽略 finding、不做自动 Prompt 改写。
- 完成后停止，不进入下一条规则缺口。
```

### G1 Prompt：Review 质量评估集 MVP

```text
请只设计并落地 Review 质量评估集 MVP。

范围需先分析后确定，默认以 backend-python、frontend、docs、tests 为主，不修改 legacy Java backend。

要求：
- 建立最小 gold cases / evaluation cases 数据结构。
- 支持记录 taskId、reviewKey、findingId 或 fingerprint、projectId、provider、profile、riskType、severity、contextStatus、人工 verdict 和备注。
- 支持按项目、Provider、Profile、风险类型筛选。
- 首版不要求真实批量模型回放。
- 不自动影响 Review 结果。
- 补 API 契约、测试和最小使用说明。

完成后停止，等待用户验证。
```

### G2 Prompt：Review 回放与版本记录

```text
请只设计并落地 Review 回放与版本记录 MVP。

要求：
- 能创建 evaluation run。
- 能记录 sample set、profile、provider、model、prompt hash、context pack version、retriever version、rule gap version、执行状态和结果摘要。
- 能记录 baseline 与 candidate 两次运行的对比数据。
- 首版可以不自动批量调用真实模型，但数据结构和 API 要支持后续接入。
- 不自动改 Prompt，不自动选择胜出版本。

完成后停止，等待用户验证。
```

### G3 Prompt：规则缺口与 Finding 级归因

```text
请只落地规则缺口与 finding 级归因能力。

要求：
- 在 evaluation case 或 finding 标注中记录相关 rule gap 摘要。
- 支持人工标注缺口归因：RULE_GAP_CAUSED / RULE_GAP_RELATED / NOT_RULE_GAP / PROMPT_ISSUE / MODEL_REASONING_ISSUE / PROJECT_POLICY_MISSING / INSUFFICIENT_LABEL。
- 规则缺口推荐算法可以读取归因统计，但必须区分 task 级近似统计和 finding 级人工归因。
- 不根据归因结果自动改规则。

完成后停止，等待用户验证。
```

### G4 Prompt：规则 / Retriever 改动验收门禁

```text
请只设计并落地规则 / Retriever 改动验收门禁 MVP。

要求：
- 为规则、Retriever、预算策略或 Prompt 约束变更建立准入和退出记录。
- 准入至少记录目标缺口、关联样本、预期收益、风险和成本。
- 退出至少记录目标样本误判变化、上下文充分性变化、漏报风险、finding 数量变化、token / 耗时影响。
- 首版可以是 API + 文档记录，不要求复杂自动评分。
- 不自动阻断线上 Review。

完成后停止，等待用户验证。
```

### G5 Prompt：Review 质量效果看板

```text
请只落地 Review 质量效果看板 MVP。

要求：
- 展示样本数、误判率、上下文不足率、等级偏差、重复 finding、漏报样本数。
- 支持按项目、Provider、Profile、风险类型筛选。
- 支持展示规则补齐前后 baseline / candidate 对比。
- 看板用于辅助决策，不自动启用或停用任何规则。

完成后停止，等待用户验证。
```

## 九、Agent 授权边界

Agent 可自主推进：

- 当前已确认规则缺口的最小补齐和测试。
- Review 评估集的数据结构、API、契约测试和最小前端入口。
- Review 回放记录的数据结构、API、契约测试和文档。
- finding 级缺口归因标注能力。
- 规则 / Retriever 改动验收记录。
- Review 质量效果看板 MVP。
- README、API 契约、docs、examples 的同步更新。

Agent 不可自主推进：

- 不修改 legacy Java backend。
- 不在没有用户确认的情况下继续补下一类规则缺口。
- 不自动改 Prompt。
- 不自动降级、自动忽略 finding 或自动放行风险。
- 不接复杂 RAG、向量库或无限制全项目扫描。
- 不做跨项目策略共享。
- 不把评估结论自动应用到生产 Review。

## 十、验收标准

本路线完成后，应能回答：

1. 当前 Review 的误判主要集中在哪些项目、Provider、Profile 和风险类型。
2. 当前规则缺口中，哪些只是高频，哪些已经被证明和误判相关。
3. 最新补齐的规则是否降低了目标样本误判。
4. 最新补齐是否带来了漏报、噪声、耗时或 token 成本上升。
5. 是否值得继续补下一个规则缺口，还是应该调整 Prompt、预算、Provider、项目策略或反馈归因。

最终目标不是“规则越补越多”，而是：

```text
每一次补规则、补 Retriever、调 Prompt 或调预算，都能被真实样本和回放结果证明是值得的。
```
