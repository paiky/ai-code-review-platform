# AI Review 平台方向调整：V1.5 动态上下文增强落地计划

## 一、背景

当前平台已经完成 V1「风险反馈记录闭环」：

- 风险项 / AI finding 可以提交反馈。
- 反馈可以入库。
- 任务详情可以回显反馈状态。
- 已有反馈池页面支持筛选、查看和状态流转。

原计划 V2 是继续推进「项目规则候选与策略注入」：

- 管理员从反馈池中把高价值反馈转换为项目级 Review 策略。
- 策略可以启用、停用、编辑。
- 后续 AI Review 时把已启用项目策略注入 Prompt。

这个 V2 方向仍然有价值，但最近出现了一个更优先的问题：

> AI Review 只基于 diff 或 change files 判断，容易因为上下文不足产生误判。

典型场景：

1. 第一次 Review 发现存在重复方法，提示风险。
2. 用户删除一个重复方法。
3. 重新 Review 时，AI 只看到 diff 中“删除了一个方法”。
4. AI 没有看到另一个重复方法仍然存在，也没有看到引用关系。
5. 于是误报“删除方法可能导致调用风险”。

这个问题不是单纯靠「反馈学习」能解决的，因为它本质上不是项目规范不匹配，而是 Review 输入上下文不足。

因此，当前方向建议调整为：

> V1 已完成后，不立即全面进入 V2 项目策略注入，而是先插入 V1.5「动态上下文增强」，优先解决 diff-only review 导致的上下文不足型误判。

---

## 二、方向调整结论

### 原路线

```text
V1 风险反馈闭环
  -> V2 项目规则候选与策略注入
  -> V3 反馈分析、模型效果评估、Prompt/策略版本管理
```

### 调整后路线

```text
V1 风险反馈闭环
  -> V1.5 动态上下文增强
  -> V2 项目规则候选与策略注入
  -> V3 反馈分析、模型效果评估、Prompt/策略版本管理
```

### 为什么需要插入 V1.5

V2 主要解决的是：

```text
项目组规范、项目约定、团队习惯导致的误判
```

例如：

- 本项目统一由 GlobalExceptionHandler 处理异常。
- 本项目接口统一由网关鉴权。
- 本项目 Redis key 统一由工具类生成。
- 某些写法在当前项目中被允许。

V1.5 主要解决的是：

```text
AI 因为只看 diff，没有读取足够上下文，导致判断不准
```

例如：

- 删除方法但没有读取引用关系。
- 修改方法签名但没有读取调用方。
- 修改接口但没有读取调用链。
- 修改 DB 字段但没有读取实体、Mapper、迁移脚本。
- 修改缓存逻辑但没有读取缓存读写双方。
- 修改 MQ 生产逻辑但没有读取消费者。

这两类问题都重要，但当前遇到的误判属于第二类，所以需要先建设动态上下文能力。

---

## 三、V1.5 功能定位

V1.5 不做复杂 RAG，不做向量库，不做全量项目上下文，不做自动训练模型。

V1.5 的目标是：

> 在 Review 前或 Review 中，根据变更类型，按需补充最小必要上下文，让 AI 不再只基于 diff 武断判断。

核心原则：

1. 不一次性喂整个项目。
2. 不让 AI 无限自由读取文件。
3. 先用规则识别高风险上下文场景。
4. 对少数高频场景补充最小必要上下文。
5. 当上下文仍不足时，风险卡片应输出「需要确认」，而不是直接判定为高风险。
6. 后续再逐步让 AI 参与上下文规划。

---

## 四、V1.5 和 V2 的关系

V1.5 不替代 V2。

二者分工如下：

| 能力 | 解决的问题 | 示例 |
|---|---|---|
| V1 反馈闭环 | 用户能标记 AI 结果是否有用 | 有用、误判、等级过高、重复 |
| V1.5 动态上下文增强 | AI 看得不够导致误判 | 删除方法但未看引用关系 |
| V2 项目策略注入 | 项目规范和通用规则不一致 | 本项目统一网关鉴权 |
| V3 评估和策略优化 | 改进是否真的变好 | 误判率、采纳率、回归评测 |

V1.5 也会反哺 V1：

- 用户反馈原因中增加「上下文不足」。
- 平台统计哪些风险类型经常因为上下文不足被误判。
- 后续优化 Context Planner 的触发策略。

V1.5 也会支撑 V2：

- 项目策略注入解决“项目规则”。
- 动态上下文补充解决“证据不足”。
- 两者共同构成 context-aware review。

---

## 五、V1.5 用户体验目标

### 1. 风险卡片不再只给结论

风险卡片建议增加以下字段：

- `contextStatus`：上下文状态。
- `confidence`：模型判断置信度。
- `evidence`：判断依据。
- `missingContext`：缺失上下文。
- `contextSummary`：本次已补充的上下文摘要。

枚举建议：

```text
contextStatus:
- SUFFICIENT
- PARTIAL
- INSUFFICIENT

confidence:
- HIGH
- MEDIUM
- LOW
```

### 2. 上下文不足时，输出「需要确认」

不要让 AI 在上下文不足时直接报高风险。

推荐输出方式：

```text
该变更删除了 xxx 方法，但当前未提供引用搜索结果，无法确认是否仍有调用方。
当前仅标记为“需要确认”，不建议作为确定高风险。
建议补充引用关系或编译结果后再判断。
```

### 3. 用户反馈原因增加上下文不足类型

反馈原因增加：

```text
AI 缺少上下文
```

并进一步细分：

- 缺少同文件上下文。
- 缺少调用方。
- 缺少被调用方。
- 缺少引用关系。
- 缺少类继承关系。
- 缺少项目规则。
- 缺少数据库表结构。
- 缺少配置。
- 缺少历史变更背景。
- 缺少编译/测试结果。

---

## 六、V1.5 技术方案

### 1. 新增 ReviewContext 概念

用于承载本次 Review 的上下文。

```java
class ReviewContext {
    diff: string
    changedFiles: List[ChangedFile]
    fileContexts: List[FileContext]
    symbolContexts: List[SymbolContext]
    referenceContexts: List[ReferenceContext]
    projectPolicies: List[ProjectPolicyContext]
    contextStatus: string
    contextSummary: string
}
```

Python 项目中可按现有风格使用 Pydantic model 或普通 dict/dataclass。

### 2. 新增 ContextRequest

用于表达“需要补充什么上下文”。

```java
class ContextRequest {
    type: string
    target: string
    filePath: string
    reason: string
    priority: int
}
```

建议类型：

```text
SAME_FILE_CONTEXT
SAME_CLASS_METHODS
REFERENCE_SEARCH
CALLER_CONTEXT
CALLEE_CONTEXT
RELATED_FILE
DB_SCHEMA_CONTEXT
CONFIG_CONTEXT
PROJECT_POLICY_CONTEXT
```

### 3. 新增 ContextPlanner

职责：

> 根据 change analysis result / diff 特征，判断需要补充哪些上下文。

最小接口：

```java
interface ContextPlanner {
    List<ContextRequest> plan(ChangeAnalysisResult analysisResult, DiffSummary diffSummary);
}
```

V1.5 先不让 AI 自由规划，先用规则策略。

### 4. 新增 ContextRetriever

职责：

> 根据 ContextRequest 拉取上下文，并做长度裁剪和摘要。

最小接口：

```java
interface ContextRetriever {
    ReviewContext retrieve(List<ContextRequest> requests, ContextBudget budget);
}
```

### 5. 新增 ContextBudget

避免上下文无限膨胀。

建议默认限制：

```text
单文件最多 300 行
单个上下文片段最多 4000 字符
引用搜索结果最多 20 条
总上下文最多 12000 字符
```

后续可配置化。

---

## 七、V1.5 优先支持场景

V1.5 不要一开始覆盖所有变更类型。

优先支持：

```text
METHOD_DELETED
METHOD_SIGNATURE_CHANGED
```

也就是先解决当前遇到的“删除方法误判”。

### 1. METHOD_DELETED 场景

触发条件：

- diff 中存在方法删除。
- 或 change analyzer 能识别出删除了函数/方法。

需要补充上下文：

1. 被删除方法签名。
2. 被删除方法所在文件/类的结构摘要。
3. 同文件剩余方法列表。
4. 同名或相似方法。
5. 全项目引用搜索结果。
6. 如果项目已有测试/编译结果，也可附带结果摘要。

Prompt 判断要求：

```text
当发现方法被删除时，不要仅凭删除行为判断为风险。
必须结合：
1. 是否仍有调用方引用该方法；
2. 是否存在等价替代方法；
3. 调用方是否已迁移；
4. 删除是否属于重复代码清理；
5. 如果上下文不足，应输出“需要确认”，不要直接输出高风险。
```

理想输出：

```text
该变更删除了一个重复方法。
根据引用搜索结果，当前未发现该方法仍被调用；
同类中仍保留了等价方法 xxx；
因此不建议判定为风险，可作为代码清理处理。
```

如果上下文仍不足：

```text
该变更删除了 xxx 方法，但当前未提供引用搜索结果，无法确认是否存在调用方。
当前仅标记为“需要确认”，不作为确定高风险。
```

### 2. METHOD_SIGNATURE_CHANGED 场景

触发条件：

- 方法参数数量变化。
- 方法名变化。
- 返回值变化。
- 可见性变化。

需要补充上下文：

1. 修改前后方法签名。
2. 引用搜索结果。
3. 调用方摘要。
4. 同类重载方法列表。
5. 编译或测试结果摘要。

---

## 八、建议数据结构调整

### 1. 反馈表增强

当前已有 `review_item_feedbacks`。

建议增加或兼容扩展以下字段：

- `context_missing_type`
- `context_comment`

如果不希望立即改表，也可以先复用 `reason_type` 和 `reason_text`：

```text
reason_type = CONTEXT_MISSING
reason_text = 用户说明缺少什么上下文
```

### 2. AI finding / risk item 输出增强

如果当前 findings 是 JSON 结构，建议增加：

```json
{
  "contextStatus": "PARTIAL",
  "confidence": "MEDIUM",
  "evidence": [
    "diff 中删除了 xxx 方法",
    "未发现调用方迁移信息",
    "未提供引用搜索结果"
  ],
  "missingContext": [
    "REFERENCE_SEARCH",
    "CALLER_CONTEXT"
  ],
  "contextSummary": "本次仅基于 diff 和变更文件片段判断"
}
```

如果短期不想改动所有 UI，可先在 finding 的 body/details 中追加结构化文本。

---

## 九、后端落地阶段

### 阶段 1：梳理当前 Review 输入

目标：

确认当前 AI Review 到底拿到了哪些上下文。

Agent 需要阅读：

- `backend-python/app/code_quality/*`
- `backend-python/app/review_record/*`
- `backend-python/app/change_analyzer/*`
- GitLab diff 拉取逻辑
- prompt 构造逻辑

输出：

1. 当前 Review 输入包含哪些字段。
2. 是否只有 diff。
3. 是否能拿到完整 changed file。
4. 是否有项目目录路径。
5. 是否已有 grep / rg / 代码搜索能力。
6. 当前 findings schema 是否容易扩展 contextStatus / evidence。

本阶段不编码，先输出分析结论。

### 阶段 2：增加上下文字段输出

目标：

先让 AI Review 的结果能表达“上下文不足”。

改动：

1. Prompt 中要求输出 contextStatus、confidence、evidence、missingContext。
2. 后端 schema 兼容这些字段。
3. 前端卡片展示这些字段。
4. 当上下文不足时，风险等级不得直接标为 HIGH，除非属于安全/数据一致性硬风险。

验收：

- AI finding 可以显示上下文状态。
- 用户能看到这条风险是“证据充分”还是“需要确认”。

### 阶段 3：METHOD_DELETED 动态上下文补充

目标：

优先解决删除方法误判。

改动：

1. 新增 ContextPlanner 最小实现。
2. 识别 diff 中的方法删除。
3. 对删除的方法执行引用搜索。
4. 获取同文件/同类方法摘要。
5. 将补充上下文注入 Prompt。
6. Prompt 明确不能仅凭“删除方法”判高风险。

验收：

- 删除重复方法时，Review 能看到仍存在的相似方法。
- 如果未发现引用，应降低风险或不报风险。
- 如果无法搜索引用，应输出“需要确认”。

### 阶段 4：反馈原因接入上下文不足

目标：

让 V1 反馈数据开始反哺上下文策略。

改动：

1. 反馈弹窗增加「AI 缺少上下文」。
2. 反馈池支持筛选 `CONTEXT_MISSING`。
3. 反馈统计增加上下文不足数量。
4. 不自动改策略，只做统计和展示。

验收：

- 用户可以标记“上下文不足型误判”。
- 管理员可以看到哪些风险类型上下文不足最多。

### 阶段 5：再回到 V2 项目策略注入

完成 V1.5 后，再继续原 docs/30 的 V2：

1. 从反馈生成 project_review_policies。
2. 策略启用/停用/编辑。
3. Review 时注入项目策略。
4. rendered prompt 可预览策略注入。

---

## 十、V1.5 不做范围

当前不要做：

- 不接向量库。
- 不做复杂 RAG。
- 不做全量项目扫描。
- 不让 AI 自由无限读取文件。
- 不自动修改全局 Prompt。
- 不做模型微调。
- 不做跨项目策略共享。
- 不改变 V1 feedback 的基础语义。
- 不直接替代 V2 项目策略方案。

---

## 十一、Agent 执行总控 Prompt

```text
请先阅读以下文档：

- AGENTS.md
- README.md
- docs/29-review-feedback-v1-implementation.md
- docs/30-review-feedback-v2-policy-plan.md
- docs/31-review-context-aware-v1_5-plan.md

当前方向有调整：V1 已完成，V2 项目规则候选仍然保留，但暂时不要直接进入 V2 编码。请先插入 V1.5「动态上下文增强」阶段，优先解决 AI Review 只看 diff 导致上下文不足误判的问题。

背景场景：
删除重复方法后，AI 只看到 diff 中删除了一个方法，却没有读取同文件剩余方法和引用关系，于是误报“删除方法可能导致风险”。这类问题应优先通过 Context Planner / Context Retriever 的最小能力解决，而不是只靠反馈学习或项目规则注入。

请不要直接大范围编码。先完成阶段 1：梳理当前 Review 输入上下文来源，输出分析报告，包括：
1. 当前 code quality review 输入给模型的字段有哪些；
2. 当前是否只包含 diff/change files；
3. 是否能拿到完整变更文件内容；
4. 是否能按方法名或文本做引用搜索；
5. 当前 prompt/schema 是否支持扩展 contextStatus、confidence、evidence、missingContext；
6. 给出 V1.5 最小改动点和文件清单；
7. 不要实现 RAG、向量库、全量项目扫描；
8. 不要修改 legacy Java backend；
9. 不要推进 docs/30 的 V2 project_review_policies 编码，等 V1.5 阶段确认后再继续。

阶段 1 完成后停止，输出“分析了什么、建议怎么改、下一阶段怎么落地、如何验证”，等待用户明确回复继续。
```

---

## 十二、V1.5 分阶段 Agent Prompt

### 阶段 1：上下文输入分析

```text
请只执行 V1.5 阶段 1：分析当前 AI Review 输入上下文。

范围：
- backend-python/app/code_quality/*
- backend-python/app/review_record/*
- backend-python/app/change_analyzer/*
- GitLab diff 拉取相关代码
- frontend/src/App.jsx 中 AI finding 展示相关代码

要求：
1. 不编码或只补充分析文档；
2. 输出当前 Review 输入链路；
3. 判断是否只看 diff；
4. 判断能否拿到完整文件；
5. 判断能否做引用搜索；
6. 判断 findings schema 和前端是否方便展示 contextStatus/confidence/evidence/missingContext；
7. 给出 V1.5 阶段 2/3 的最小改动建议。

完成后停止。
```

### 阶段 2：风险卡片上下文状态字段

```text
请只执行 V1.5 阶段 2：让 AI finding / risk card 支持上下文状态表达。

范围：
- backend-python/app/code_quality/prompt.py
- backend-python/app/code_quality/service.py
- backend-python/app/code_quality/repository.py 如需兼容字段
- frontend/src/App.jsx
- frontend/src/styles.css
- 相关 contract/unit tests
- docs/31 阶段 2 验证记录

要求：
1. finding 输出支持 contextStatus、confidence、evidence、missingContext、contextSummary；
2. 前端卡片能展示上下文状态和判断依据；
3. Prompt 明确：上下文不足时输出 NEED_CONFIRM 或 LOW/MEDIUM confidence，不要武断输出高风险；
4. 不做引用搜索；
5. 不做项目策略注入；
6. 不做 RAG。

完成后运行后端相关测试和前端 build，停止等待用户验证。
```

### 阶段 3：METHOD_DELETED 上下文补充

```text
请只执行 V1.5 阶段 3：为 METHOD_DELETED 场景实现最小动态上下文补充。

范围：
- backend-python/app/code_quality/*
- backend-python/app/change_analyzer/* 如需扩展删除方法识别
- 可新增 backend-python/app/review_context/*
- 相关 tests
- docs/31 阶段 3 验证记录

要求：
1. 识别 diff 中删除的方法；
2. 生成 ContextRequest：SAME_CLASS_METHODS、REFERENCE_SEARCH；
3. 使用项目现有文件内容或本地仓库路径进行最小引用搜索；
4. 获取同文件/同类方法摘要；
5. 将补充上下文注入 AI Review prompt；
6. Prompt 明确删除方法不能仅凭 diff 判高风险；
7. 如果引用搜索不可用，输出 contextStatus=INSUFFICIENT 或 PARTIAL；
8. 控制上下文预算，不要全量喂项目。

完成后停止，输出验证方式。
```

### 阶段 4：反馈池接入 CONTEXT_MISSING

```text
请只执行 V1.5 阶段 4：让 V1 feedback 支持上下文不足型反馈。

范围：
- backend-python/app/review_feedback/*
- frontend/src/App.jsx
- frontend/src/styles.css
- 相关 tests
- docs/31 阶段 4 验证记录

要求：
1. 反馈原因增加 CONTEXT_MISSING；
2. 可选择缺少的上下文类型；
3. 反馈池支持筛选上下文不足；
4. 不自动改 Prompt；
5. 不自动影响后续 Review；
6. 只做记录和统计。

完成后停止。
```

### 阶段 5：恢复 V2 项目策略落地

```text
V1.5 完成并验证后，再回到 docs/30-review-feedback-v2-policy-plan.md，继续 V2 项目规则候选与策略注入。

要求：
- 保留 V1.5 的 context-aware review 能力；
- V2 只处理项目规则/项目事实；
- 不把上下文不足误判强行沉淀为项目规则；
- 项目策略注入和动态上下文补充是两条互补能力。
```

---

## 十三、验收标准

V1.5 完成后应满足：

1. AI Review 结果能展示上下文状态。
2. 风险卡片能展示判断依据和缺失上下文。
3. 删除方法场景不会仅凭 diff 删除动作直接报高风险。
4. 删除重复方法时，系统会尝试补充同文件方法列表和引用搜索结果。
5. 如果上下文仍不足，AI 输出“需要确认”，而不是武断判断。
6. 用户可以在反馈中标记“AI 缺少上下文”。
7. 反馈池可以筛选上下文不足型反馈。
8. V2 项目策略方案仍保留，但在 V1.5 后继续推进。

---

## 十四、推荐当前下一步

当前不要直接让 agent 执行 docs/30 V2 阶段 1。

建议下一步执行：

```text
请阅读 docs/31-review-context-aware-v1_5-plan.md，先执行 V1.5 阶段 1：上下文输入分析，不要编码。
```

等 agent 输出当前 Review 输入链路后，再决定：

- 是否能直接实现 METHOD_DELETED 引用搜索；
- 是否需要先补 changed file 完整内容；
- 是否已有本地仓库路径可用；
- 是否需要先扩展 finding schema。

---

## 十五、阶段 1 检阅结论与阶段 2 最小落地记录

### 阶段 1 输入链路结论

已核对当前 Python 后端主链路：

```text
GitLab MR / Push / 手动 AI Review
  -> code_quality.service 构造 review_request
  -> prompt.render_instructions / prompt.render_input
  -> Provider HTTP 调用
  -> providers._normalize_finding
  -> code_quality_review_results.findings_json
  -> 前端任务详情 AI finding 展示
```

当前模型输入主要包含：

- `mode`
- `baseRef`
- `commitSha`
- `title`
- `changedFiles`
- `diffText`
- profile / manual 合并后的 `instructions`

结论：

1. 当前 AI Review 执行时基本仍是 diff-first，没有把完整文件、引用搜索或调用关系注入模型。
2. GitLab webhook 任务已具备按需读取完整文件的能力：`GET /api/review-tasks/{taskId}/diff-context` 会基于 `before_sha / after_sha` 和 GitLab Repository Files API 读取 raw file。
3. changed files 摘要中保留了 `diffText`、`oldPath/newPath/path`、新增 / 删除 / 重命名标记和 `changeType`，能支撑后续 METHOD_DELETED 的最小 Context Planner。
4. 当前代码没有服务端全项目引用搜索能力；阶段 3 需要先限定为 GitLab API 可读文件上下文、任务 changed files、以及可配置本地仓库路径下的受控文本搜索，不应直接全量扫描远端项目。
5. finding 已有 `confidence` 字段，并且后端存储为 JSON、前端已展示，所以扩展 `contextStatus / evidence / missingContext / contextSummary` 不需要数据库迁移。
6. Provider 归一化当前会丢弃未知 finding 字段，因此阶段 2 必须同时改 prompt schema 和 `_normalize_finding`。

### 可以开始落地的最小范围

可以先落地 V1.5 阶段 2，范围只包括“上下文状态表达”：

- 扩展 AI Review 输出协议和 OpenAI strict JSON schema。
- Provider 归一化保留上下文状态字段。
- 前端 AI finding 卡片展示上下文状态、判断依据、缺失上下文和上下文摘要。
- Prompt 明确：上下文不足时只能低 / 中置信度，且除安全、数据一致性、线上正确性硬风险外，不应直接输出高风险或紧急。

本阶段仍不做：

- 不做 METHOD_DELETED 引用搜索。
- 不做项目策略注入。
- 不做 RAG / 向量库 / 全量项目扫描。
- 不改 legacy Java backend。

### 阶段 2 验证命令

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_code_quality_prompt.py tests\contract\test_code_quality_api_contract.py::test_xiaomimo_provider_uses_openai_compatible_request
$env:NO_PAUSE="1"; .\scripts\run-frontend.cmd build
```

### 阶段 2 落地结果

落地时间：2026-06-10。

已完成：

- `prompt.render_instructions` 和 OpenAI strict JSON schema 已要求 finding 输出 `contextStatus / evidence / missingContext / contextSummary`。
- Provider finding 归一化已保留上下文字段；旧响应缺字段时默认 `contextStatus=PARTIAL`，避免历史 mock 或旧模型输出直接失败。
- 前端任务详情 AI finding 卡片已展示上下文状态、缺失上下文标签、上下文摘要和判断依据。
- README 已补充上下文状态展示能力说明。

已验证：

```powershell
$env:NO_PAUSE="1"; .\scripts\run-backend.cmd test tests\unit\test_code_quality_prompt.py tests\contract\test_code_quality_api_contract.py::test_xiaomimo_provider_uses_openai_compatible_request
```

结果：7 passed。

```powershell
$env:NO_PAUSE="1"; .\scripts\run-frontend.cmd build
```

结果：build passed；仅保留既有 Vite chunk size warning。

下一阶段建议继续阶段 3：实现 METHOD_DELETED 的最小 Context Planner / Context Retriever，只覆盖删除方法场景，不扩大到 RAG、向量库或全量扫描。
