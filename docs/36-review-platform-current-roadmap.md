# Review 平台当前路线总览：准确率、必备能力与后续推进

## 状态

- 当前状态：作为 2026-07-01 起后续推进的唯一总控入口；`M10：第一个评估驱动的业务 Retriever` 已落地，等待用户验证是否进入 M11。
- 完整产品目标：`docs/37-review-platform-target-product-roadmap.md`。本文件负责近期阶段推进，`docs/37` 负责最终产品形态和长期路线。
- 关联历史文档：
  - `docs/32-review-feedback-v2-mainline-roadmap.md`：V2 反馈学习、项目策略、Context Pack 和高准确模式阶段记录。
  - `docs/33-review-learning-capability-roadmap.md`：长期学习能力愿景。
  - `docs/34-local-repository-context-retrieval-plan.md`：本地仓库上下文检索和高准确 Review 细节。
  - `docs/35-review-quality-evaluation-and-rule-gap-governance.md`：规则缺口治理和质量评估路线。
- 本文件用途：回答“近期哪些能力必须先补、当前缺什么、下一步先做什么”。完整产品目标和长期阶段路线见 `docs/37-review-platform-target-product-roadmap.md`。后续阶段推进优先更新本文件，再按需更新细节文档。

## 一、通俗结论

完整的 Review 平台不应该是：

```text
把 diff 发给模型，让模型猜风险。
```

它应该是：

```text
像受控本地 Agent 一样拿到仓库和上下文，
先查证据、跑确定性检查，再让模型基于证据判断。
```

准确率不能靠更长 Prompt 保证。准确率来自：

```text
拿对上下文
  + 确定性工具
  + 证据约束
  + finding 级二次补证据
  + 人工反馈和评估回放
```

因此后续主线不是“继续无限补规则”，而是“双线并行”：

```text
在线 Review 能力：把平台 Review Worker 做成受控本地 Agent。
离线质量治理：用评估集和回放证明每次改动真的减少误判。
```

## 二、能力分级

### 必须具备：平台能稳定审查

这些能力是 Review 平台的基础闭环。没有它们，平台只能算 demo。

| 能力 | 说明 | 当前状态 |
|---|---|---|
| GitLab webhook / 手动入口 | 能接收 MR、Push、manual review | 已具备 |
| diff / changed files 拉取与 fallback | 能稳定拿到变更输入 | 已具备 |
| 审查任务、结果、通知落库 | 能追踪任务和结果 | 已具备 |
| 规则提醒卡片 | 对 DB、缓存、MQ、配置等高价值变更先做结构化提醒 | 已具备 |
| AI Provider / Profile / Prompt 配置 | 支持多模型、多模板和项目配置 | 已具备 |
| 任务列表、任务详情、设置页 | 用户能看结果、调配置、重试 | 已具备 |
| 钉钉通知 | 审查结果能推送到团队工作流 | 已具备 |

### 必须具备：平台 Review 要可信

这些能力决定 Review 是否能接近本地 Agent，而不是 diff-only 猜测。

| 能力 | 说明 | 当前状态 |
|---|---|---|
| 本地 mirror / worktree | 平台能 checkout 当前任务源码 | 已具备 |
| Context Planner | 能判断这次变更需要查什么上下文 | 已具备 |
| Local Retriever | 能按 signal 检索引用、调用方或关联文件 | 部分具备 |
| Context Pack 预算控制 | 只把有限、可解释、预算内证据交给模型 | 已具备 |
| 未注入证据摘要 | 让模型知道存在被裁剪证据，避免误把缺失当不存在 | 已具备 |
| finding 的 evidence / contextStatus / confidence | 每个结论必须说明证据和不确定性 | 已具备 |
| 高准确模式流转可观测 | 用户能看到 Planner、Retriever、预算裁剪和 Provider 过程 | 已具备 |
| finding 级二次补证据 | 对高风险但证据不足的 finding 再定向检索 | 后端 MVP 与前端可观测已具备 |
| 确定性检查接入 | 编译、测试、lint、静态安全扫描等硬证据 | 已具备敏感信息扫描 MVP |

当前 Local Retriever 已支持：

```text
METHOD_DELETED
METHOD_SIGNATURE_CHANGED
DTO_FIELD_CHANGED
FIELD_DELETED
DB_SQL_MAPPER_CHANGED
CACHE_WRITE_DELETE_CHANGED
```

当前还没有专项支持：

```text
MQ_CONFIG_CHANGED
CONFIG_FILE_CHANGED
跨仓 / 前端调用方
测试覆盖与测试执行证据
```

### 必须具备：平台能持续变准

这些能力决定后续补规则、补 Retriever、调 Prompt 是否有证据，而不是凭感觉。

| 能力 | 说明 | 当前状态 |
|---|---|---|
| 反馈记录 | 用户能标记有效、误判、等级问题、上下文不足 | 后端具备，生产前端默认隐藏 |
| 项目策略 | 人工确认后的项目事实可注入后续 Review | 后端具备，生产前端默认隐藏 |
| 规则缺口看板 | 聚合 Planner / Retriever / 预算 / Prompt 缺口 | 已具备；后续收敛为质量治理子能力 |
| 规则缺口推荐 | 给出是否值得补、补什么、下一阶段 prompt | 已具备；后续必须结合评估样本 / 回放，不再单独作为实现依据 |
| Review 质量评估集 | 沉淀 gold cases，记录 finding 是有效、误判、等级过高、上下文不足或漏报 | 已具备 MVP |
| Review 回放与版本记录 | 对比改动前后误判、漏报、耗时、成本 | 已具备 MVP |
| Review 质量看板 | 按项目、Provider、Profile、风险类型聚合误判、上下文不足、等级偏差、重复和漏报 | 已具备 MVP |
| finding 级缺口归因 | 判断某个误判是否真由某个规则缺口导致 | 缺失 |

### 可选增强

这些能力有价值，但不应早于质量评估和在线证据链。

| 能力 | 说明 | 当前建议 |
|---|---|---|
| 缓存 / MQ / 配置专项 Retriever | 补更多业务上下文 | 等评估集证明高频误判后再做 |
| AST / LSP / tree-sitter | 更精准符号解析 | 先不用，除非 rg 启发式误差明显 |
| 向量库 / RAG | 语义检索项目知识 | 暂缓，不作为近期主线 |
| 多模型仲裁 | 用多个模型互相校验 | 可选，成本和解释复杂度较高 |
| 自动降级 / 自动忽略 finding | 自动改变 Review 结论 | 暂缓，风险高 |
| 自动生成并启用项目策略 | 半自动学习 | 远期，只能人工确认后生效 |
| 跨项目策略共享 | 复用团队经验 | 远期，先保证项目内可信 |

## 三、当前是否缺少必须能力

结论：当前产品已经具备“能运行的 Review 平台”和“高准确模式基础设施”，但离“成熟可信 Review 平台”还缺 3 类必须能力。

### 缺口 1：Review 质量评估集

这是当前最关键缺口。

没有评估集时，只能知道：

```text
平台发现了哪些规则缺口。
```

但不能知道：

```text
这些缺口是否真的导致误判。
补完后误判是否下降。
是否引入漏报、噪声、耗时或 token 成本上涨。
```

因此当前必须先完成 P1 / M1：Review 质量评估集 MVP。

### 缺口 2：finding 级二次补证据执行器

当前 V2-F-16 只有设计，没有编码实现。

这会导致平台第一轮 Review 发现“疑似风险”后，仍然缺少一次更像本地 Agent 的定向追查：

```text
这个 finding 依赖调用方吗？
这个 finding 依赖配置读取点吗？
这个 finding 依赖测试覆盖吗？
这个 finding 依赖外部接口兼容吗？
```

成熟形态中，高风险但上下文不足的 finding 不应该直接定论，应触发二次补证据。

### 缺口 3：确定性检查证据不足

AI 不应该承担所有判断。

成熟平台应逐步接入：

```text
编译结果
单元测试 / 指定测试
lint
类型检查
Semgrep / CodeQL / Sonar 类静态规则
敏感信息扫描
```

这些不是都要马上做，但“确定性工具结果进入 Review 证据包”是成熟平台必备方向。

## 四、后续推进顺序

### 当前主线

```text
P0：统一文档入口和路线判断（本文件）
  -> M1：Review 质量评估集后端 MVP（已完成）
  -> M2：评估样本前端与任务详情入口（已完成）
  -> M3：finding 级二次补证据后端 MVP（已完成）
  -> M4：二次补证据前端可观测（已完成）
  -> M5：Review 回放与版本记录 MVP（已完成）
  -> M6：确定性检查证据接入 MVP（已完成）
  -> M7：Review 质量看板 MVP（已完成）
  -> M8：规则缺口与 finding 级归因（已完成）
  -> M9：规则 / Retriever 改动验收门禁（已完成）
  -> M10：第一个评估驱动的业务 Retriever（已完成）
  -> M11：业务 Retriever 扩展循环（下一阶段）
```

### 为什么不是继续补缓存 / MQ / 配置 Retriever

缓存、MQ、配置 Retriever 都有价值，但现在直接补会带来两个问题：

1. 只能证明平台“查得更多”，不能证明 Review “更准”。
2. 每补一个 Retriever 都增加复杂度、耗时、预算和解释成本。

所以后续规则是：

```text
没有评估样本证明的 Retriever，不进入实现主线。
```

可以例外的情况：

```text
用户明确提供真实任务、真实误判、明确缺失上下文，并确认只补这一类缺口。
```

此时按 G0 收口，只做当前确认缺口，做完停止。

### 规则缺口模块收敛方向

规则缺口模块短期保留，因为它仍能解释高准确模式中 Planner / Retriever / 预算裁剪为什么没有拿到足够上下文。但它不再作为“下一步实现什么 Retriever”的独立主线入口。

后续收敛规则：

1. M5 / M6 之前不删除规则缺口模块，继续作为任务详情和治理排查的辅助信息。
2. M7 Review 质量看板落地后，优先把“误判率、上下文不足率、漏报样本、等级偏差”作为主入口；规则缺口只作为解释维度。
3. M8 finding 级归因落地后，规则缺口推荐必须区分“高频缺口”和“已被样本证明关联误判 / 漏报的缺口”。
4. 若 M7 / M8 已覆盖现有规则缺口看板的核心判断能力，前端可将“规则缺口”从一级导航降级到“质量治理 / 高准确模式诊断”子页，或合并进质量看板。
5. 收敛不删除历史数据和后端聚合能力，除非已有替代 API 能覆盖任务诊断、缺口归因和回放对比需要。

## 五、用户体验目标

成熟平台对普通开发的体验应该是简单的：

```text
提交 MR
  -> 等待平台自动审查
  -> 看必须处理 / 建议处理 / 仅提醒
  -> 点开 finding 看证据
  -> 接受、修复、忽略或反馈
```

finding 展示必须清楚：

```text
问题是什么
风险等级
置信度
证据来自哪些文件和行
为什么这些证据能支持结论
缺了哪些上下文
建议怎么修
```

如果证据不足，平台应该直接说：

```text
上下文不足，当前只能给出低 / 中置信提醒。
```

而不是伪装成高置信结论。

管理员体验应该是：

```text
查看最近误判最多的项目 / Provider / Profile / 风险类型
查看哪些规则缺口和误判有关
查看最近一次能力补齐是否真的改善样本
决定是否补下一个 Retriever、调整 Prompt、接入确定性工具或沉淀项目策略
```

## 六、阶段落地 Prompt

### 总控 Prompt

```text
请阅读 AGENTS.md、README.md、docs/36-review-platform-current-roadmap.md、docs/37-review-platform-target-product-roadmap.md。

当前后续推进以 docs/36 为近期总控入口，docs/37 是完整产品目标。docs/32、docs/33、docs/34、docs/35 作为历史阶段记录和细节参考，不再作为下一阶段判断入口。

后续目标是把平台 Review Worker 做成受控本地 Agent，并用质量评估集 / 回放证明每次改动是否真的减少误判。不要继续机械地按规则缺口看板补缓存、MQ、配置或其它 Retriever，除非用户提供明确真实误判并确认只补当前缺口。

每次只推进一个阶段。允许自主修改 backend-python、frontend、docs、examples、tests 中与当前阶段直接相关的文件；不要修改 legacy Java backend；不要做自动 Prompt 改写、自动风险降级、自动忽略 finding、模型微调、复杂 RAG、跨项目策略共享或无限制全项目扫描。

每个阶段完成后必须停止，输出“改了什么、为什么、如何验证”，等待用户验证并明确回复“继续下一阶段”后再推进。
```

### P1 Prompt：Review 质量评估集 MVP

```text
请只落地 docs/36 的 P1：Review 质量评估集 MVP。

目标：
- 建立最小 evaluation cases / gold cases 数据结构。
- 支持记录 taskId、reviewKey、findingId 或 fingerprint、projectId、provider、profile、riskType、severity、contextStatus、人工 verdict 和备注。
- 支持按项目、Provider、Profile、风险类型筛选。
- 能从任务详情或后台 API 沉淀样本。
- 预留或记录本次 Review 的关键上下文摘要：项目策略注入摘要、rule gap 摘要、local retriever 摘要、prompt/profile/provider 标识。
- 首版不要求真实批量模型回放。
- 不自动影响 Review 结果。
- 不替代现有 `review_item_feedbacks` 反馈池；后续可以从反馈生成 evaluation case，但两者语义保持独立。

范围：
- backend-python
- frontend
- docs / examples / tests 中与本阶段直接相关的文件

完成后运行相关后端测试和前端 build，并停止等待验证。
```

### P2 Prompt：finding 级二次补证据执行器 MVP

```text
请只落地 docs/36 的 P2：finding 级二次补证据执行器 MVP。

目标：
- 对高影响且 contextStatus=PARTIAL / INSUFFICIENT 的 finding 做定向补证据。
- 复用本地 worktree、Planner、Retriever 和 Context Pack 预算能力。
- 不重跑整个 Review，只对少数 finding 做补充判定。
- 补证据结果作为显式覆盖层，不静默覆盖原 finding，不自动降级或忽略。
- 失败不影响原 Review 结果。

完成后补测试和前端最小展示，并停止等待验证。
```

### P3 Prompt：Review 回放与版本记录 MVP

```text
请只落地 docs/36 的 P3：Review 回放与版本记录 MVP。

目标：
- 能创建 evaluation run。
- 能记录 sample set、profile、provider、model、prompt hash、context pack version、retriever version、规则缺口版本、执行状态和结果摘要。
- 能记录 baseline 与 candidate 的对比数据。
- 首版可以不自动批量调用真实模型，但数据结构和 API 要支持后续接入。
- 不自动改 Prompt，不自动选择胜出版本。

完成后停止等待验证。
```

### P4 Prompt：确定性检查证据接入 MVP

```text
请只设计并落地 docs/36 的 P4：确定性检查证据接入 MVP。

目标：
- 选择一个最小确定性检查入口，例如 lint、测试命令配置、静态规则扫描或敏感信息扫描。
- 将检查结果作为结构化证据进入 Review 任务详情和 AI Review Context Pack。
- 检查失败、超时或未配置时必须可解释，不阻断原有 Review。
- 不要求一次性接入所有语言和工具。

完成后停止等待验证。
```

## 七、进度维护规则

后续维护时遵守：

1. 新阶段是否开始，只看本文件的“后续推进顺序”和用户确认。
2. 旧文档只补充历史落地记录，不再写互相竞争的“下一阶段建议”。
3. 每完成一个阶段，在本文件新增落地记录，写清：
   - 改了什么。
   - 为什么做。
   - 解决了哪个必须能力缺口。
   - 如何验证。
   - 下一阶段是什么。
4. 未经用户确认，不继续补下一个 Retriever。
5. 涉及新踩坑、误判根因、环境问题时，同步更新 `docs/10-local-dev-pitfalls.md`。

## 八、当前下一步

当前 M10 第一个评估驱动的业务 Retriever 已落地，等待用户验证：

```text
M10：第一个评估驱动的业务 Retriever
```

### M1 落地记录（2026-07-01）

- 改了什么：新增 `evaluation_cases` 后端模块、数据库 bootstrap SQL、创建 / 查询 / 更新 API、契约测试和最小使用文档。
- 为什么做：先建立质量评估样本的后端基础，让 AI finding 或人工漏报样本可以沉淀为 gold case。
- 解决的缺口：补齐“Review 质量评估集”最小数据结构和后台 API。
- 如何验证：运行 `backend-python/tests/contract/test_evaluation_cases_api_contract.py`，并用 `/api/evaluation-cases` 创建、筛选、更新样本。
- 下一阶段：M2 评估样本前端与任务详情入口；未经用户确认不继续推进。

### M2 落地记录（2026-07-01）

- 改了什么：任务详情页 AI finding 操作区新增“标注评估样本”入口；新增顶部导航“评估样本”基础列表页，支持按项目、Provider、Profile、风险类型和 verdict 查询。
- 为什么做：让真实 Review finding 可以被人工沉淀为评估样本，并让管理员能查看最小样本集。
- 解决的缺口：补齐“Review 质量评估集”的最小前端标注和查询入口。
- 如何验证：运行前端 build；在真实任务详情标注一条 AI finding 后，进入“评估样本”列表按 verdict 或项目筛选确认可见。
- 下一阶段：M3 finding 级二次补证据后端 MVP；未经用户确认不继续推进。

### M3 落地记录（2026-07-01）

- 改了什么：新增 `code_quality_finding_refinements` 后端表、同步触发 / 查询 API、finding-scoped Context Pack 补证据执行、`/code-quality-results` 的 `refinementOverlay` 显式覆盖层和契约测试。
- 为什么做：让高影响且 `contextStatus=PARTIAL / INSUFFICIENT` 的 finding 可以围绕单个问题定向补证据，而不是重跑整个 Review 或静默修改原结论。
- 解决的缺口：补齐“finding 级二次补证据执行器”的后端 MVP。
- 如何验证：运行 `tests/contract/test_code_quality_finding_refinements_api_contract.py`；用 `POST /api/review-tasks/{taskId}/code-quality-refinements` 按 `reviewKey + findingIndex` 或 `fingerprint` 触发补证据，再用 `GET /api/review-tasks/{taskId}/code-quality-refinements` 和 `/code-quality-results` 查看覆盖层。
- 下一阶段：M4 二次补证据前端可观测；未经用户确认不继续推进。

### M4 落地记录（2026-07-01）

- 改了什么：任务详情页 AI finding 增加“补证据 / 重新补证据”操作，只对高影响且上下文不足的候选 finding 展示；finding 展开区展示 `refinementOverlay` 状态、触发条件、检索计划摘要、证据摘要、仍缺失上下文和失败原因；高准确模式流转新增 finding 级补证据汇总节点。
- 为什么做：让用户能看懂某个 finding 是否做过二次补证据、补到了什么、还缺什么，并明确补证据结果只是显式覆盖层。
- 解决的缺口：补齐“finding 级二次补证据”的前端可观测和手动触发入口。
- 如何验证：运行前端 build；在任务详情中确认只有 `CRITICAL / MAJOR / HIGH` 且 `PARTIAL / INSUFFICIENT` finding 显示补证据操作，触发后在对应 finding 和高准确模式流转中看到覆盖层摘要。
- 下一阶段：M5 Review 回放与版本记录 MVP；未经用户确认不继续推进。

### M5 落地记录（2026-07-01）

- 改了什么：新增 `evaluation_runs` / `evaluation_run_items` 后端表、创建 / 查询 / 更新 item 摘要 API、run 聚合刷新、契约测试和顶部导航“回放记录”最小列表 / 详情入口。
- 为什么做：让评估样本可以沉淀为一次可追溯的 baseline / candidate 运行记录，为后续真实模型回放和质量对比提供版本基础。
- 解决的缺口：补齐“Review 回放与版本记录”的最小数据结构、API 和前端可观测入口。
- 如何验证：运行 `tests/contract/test_evaluation_cases_api_contract.py` 与 `tests/contract/test_evaluation_runs_api_contract.py`；用 `POST /api/evaluation-runs` 基于已有样本创建 run，再用 `PUT /api/evaluation-runs/{runId}/items/{itemId}` 保存样本结果摘要，并在前端“回放记录”查看列表和详情。
- 下一阶段：M6 确定性检查证据接入 MVP；未经用户确认不继续推进。

### M6 落地记录（2026-07-01）

- 改了什么：新增 `deterministic_check_runs` 后端表、敏感信息扫描 API、只扫 diff 新增行的内置规则集、Context Pack 安全摘要注入、契约测试和任务详情“确定性检查”最小 tab。
- 为什么做：让 Review 平台先接入一种跨项目可用、低风险的确定性证据，而不是只依赖 AI 对 diff 推理。
- 解决的缺口：补齐“确定性检查证据接入”的 MVP，检查结果可进入任务详情和 AI Review Context Pack。
- 如何验证：运行 `tests/contract/test_deterministic_checks_api_contract.py` 与 `tests/unit/test_review_context_pack.py`；在任务详情“确定性检查”tab 手动运行敏感信息扫描，确认状态、耗时、摘要、脱敏命中项和失败 / 不适用原因可见。
- 下一阶段：M7 Review 质量看板 MVP；未经用户确认不继续推进。

### M7 落地记录（2026-07-01）

- 改了什么：新增 `/api/review-quality/dashboard` 只读聚合 API，基于 evaluation cases 统计样本数、误判率、上下文不足率、等级偏差、重复和漏报，并按项目 / Provider / Profile / 风险类型输出 top 维度；前端新增顶部导航“质量看板”，展示过滤器、核心指标卡、verdict 分布、维度聚合表和回放 / 补证据 / 确定性检查辅助摘要。
- 为什么做：让管理员能先回答“质量问题集中在哪里”，把评估样本和回放记录变成可观察治理入口，而不是继续凭规则缺口直觉补 Retriever。
- 解决的缺口：补齐“Review 质量看板”的 MVP，质量治理主入口开始从规则缺口转向人工 verdict 和样本统计。
- 如何验证：运行 `tests/contract/test_review_quality_dashboard_api_contract.py`、`tests/contract/test_evaluation_cases_api_contract.py`、`tests/contract/test_evaluation_runs_api_contract.py`；运行前端 build；在“质量看板”按项目、Provider、Profile、风险类型和 verdict 筛选确认统计变化。
- 下一阶段：M8 规则缺口与 finding 级归因；未经用户确认不继续推进。

### M8 落地记录（2026-07-02）

- 改了什么：扩展 `evaluation_cases` 保存规则缺口归因类型、脱敏 rule gap 摘要、归因说明、归因人和归因时间；新增 `GET / PUT /api/evaluation-cases/{caseId}/rule-gap-attribution`；创建 AI finding 样本时自动带入最新 `CONTEXT_PACK_BUILT` 的安全 rule gap 摘要；质量看板新增 `ruleGapAttributionSummary`；规则缺口看板推荐项新增 `recommendationBasis` 和 `attributionSignals`；前端“评估样本”新增编辑归因弹窗，质量看板和规则缺口看板展示归因摘要。
- 为什么做：把“规则缺口是否导致误判 / 上下文不足 / 漏报”从 task 级近似推进到 finding / evaluation case 级人工判断，避免继续只按高频缺口直觉补 Retriever。
- 解决的缺口：补齐“finding 级缺口归因”的 MVP，让规则缺口推荐能区分高频缺口和已被评估样本证明关联的缺口。
- 如何验证：运行 `tests/contract/test_rule_gap_attribution_api_contract.py`、`tests/contract/test_evaluation_cases_api_contract.py`、`tests/contract/test_code_quality_rule_gaps_api_contract.py`、`tests/contract/test_review_quality_dashboard_api_contract.py`；运行前端 build；在“评估样本”编辑归因后，确认“质量看板”和“规则缺口”推荐依据变化。
- 下一阶段：M9 规则 / Retriever 改动验收门禁；未经用户确认不继续推进。

### M9 落地记录（2026-07-02）

- 改了什么：新增 `review_quality_acceptance_gates` 后端表、`/api/review-quality/acceptance-gates` 创建 / 查询 / 更新 API、质量看板 `acceptanceGateSummary`、顶部导航“验收记录”最小列表 / 创建 / 编辑 / 详情入口、契约测试和 API / README 文档。
- 为什么做：在进入业务 Retriever 或 Prompt 改动前，先让每次能力改动都有人工准入原因、关联 rule gap / evaluation case / evaluation run、预期收益、风险成本和退出验收结果。
- 解决的缺口：补齐“规则 / Retriever 改动验收门禁”的治理记录 MVP，让管理员能基于 M7 质量看板和 M8 finding 级归因记录为什么要做某次能力改动，以及改完后是否改善。
- 如何验证：运行 `tests/contract/test_review_quality_acceptance_gates_api_contract.py` 与 `tests/contract/test_review_quality_dashboard_api_contract.py`；运行前端 build；在“验收记录”创建准入记录，关联样本和 run，更新退出 delta 后确认质量看板展示验收记录数和最近状态。
- 下一阶段：M10 第一个评估驱动的业务 Retriever；未经用户确认不继续推进。

### M10 落地记录（2026-07-02）

- 改了什么：将 `CACHE_WRITE_DELETE_CHANGED` 纳入 Local Retriever 支持范围；Planner 从 diff 变更行提取 `cacheKeys / cacheNames / keyExpressions / cacheOperations` 安全摘要；Retriever 基于 bounded `rg --fixed-strings` 检索缓存 key、cache name、key expression 的读写 / 删除 / 过期使用点；Context Pack 将 `CACHE_USAGE_CONTEXT` 标记为 `LOCAL_CACHE_USAGE_CONTEXT`，并在预算裁剪时继续用 `notInjectedEvidence` 保护安全摘要。
- 为什么做：M8 / M9 的评估样本、rule gap 归因和验收记录已反复证明 `CACHE_WRITE_DELETE_CHANGED -> CACHE_USAGE_CONTEXT` 是高价值缺口，适合作为第一个评估驱动业务 Retriever。
- 解决的缺口：补齐缓存写入 / 删除变更的最小业务上下文检索，让新任务不再把缓存 signal 归为 `UNSUPPORTED_PLANNER_SIGNAL`。
- 如何验证：运行 `tests/unit/test_local_retriever.py`、`tests/unit/test_review_context_pack.py`、`tests/unit/test_code_quality_prompt.py` 以及相关质量治理契约测试；在高准确模式流转中确认 supported signals 包含 `CACHE_WRITE_DELETE_CHANGED`，命中后 `CACHE_USAGE_CONTEXT` 可用。
- 下一阶段：M11 业务 Retriever 扩展循环；未经用户确认不继续推进。

暂不建议进入：

```text
MQ Retriever
配置 Retriever
AST / LSP / RAG
自动降级 / 自动忽略 finding
```

除非用户提供明确真实误判，并确认先按 G0 只补当前单个高分缺口。
