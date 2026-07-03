# Review 生命周期与前端入口说明

## 状态

- 当前状态：前端页面入口与 Review 生命周期的使用说明。
- 关联文档：
  - `docs/36-review-platform-current-roadmap.md`：近期阶段推进总控。
  - `docs/37-review-platform-target-product-roadmap.md`：完整产品目标路线。
  - `docs/03-api-contract.md`：HTTP API 契约。
- 本文用途：说明开发者、Reviewer、管理员在一次 Review 从配置、执行、查看、反馈、评估到治理闭环中，分别应该使用哪些前端入口。

## 一、整体生命周期

平台的 Review 生命周期可以分成 7 个阶段：

```text
Review 前配置
  -> 变更进入平台
  -> 规则提醒与 AI Review 执行
  -> 任务详情查看与补证据
  -> 人工判断沉淀评估样本
  -> 质量看板与规则缺口归因
  -> 验收记录与回放证明改动有效
```

对应前端入口：

```text
设置
  -> 任务
  -> 任务详情 / 高准确模式流转 / 确定性检查
  -> 评估样本
  -> 规则缺口 / 质量看板
  -> 验收记录 / 回放记录
```

`反馈池` 当前是默认隐藏入口。它保留为项目知识和项目策略治理能力，不是默认生产主流程。

## 二、设置：Review 前配置

`设置` 用于 Review 发生前的系统和项目配置。

主要使用者：

- 平台管理员。
- 项目负责人。
- 接入负责人。

生命周期位置：

```text
Review 前配置
```

主要用途：

- 开启或关闭全局代码质量 AI Review。
- 配置 OpenAI / Anthropic / DeepSeek / XiaoMIMO / GLM / CUSTOM Provider。
- 配置模型端点、模型名称、API Key 和超时。
- 配置 AI Review Profile 和 Review Instructions。
- 配置项目组、端类型、项目端类型和默认 Profile。
- 配置项目组多模型执行项。
- 配置钉钉 webhook 和通知开关。
- 配置 Push 审核策略。

它决定：

- 哪些项目会触发 AI Review。
- 使用哪个 Provider / model / Profile。
- MR / Push 是否自动进入 Review。
- Review 结果是否推送钉钉。

边界：

- 设置不会直接创建 Review 任务。
- 设置不会修改历史 Review 结果。
- Provider API Key、token、认证头不得进入日志、progress 或前端可观测摘要。

## 三、任务：线上 Review 主入口

`任务` 是日常 Review 的主入口。

主要使用者：

- 开发者。
- Reviewer。
- Tech Lead。
- 管理员排障时也会使用。

生命周期位置：

```text
变更进入平台
  -> 规则提醒与 AI Review 执行
  -> 任务详情查看与补证据
```

任务来源：

- GitLab Merge Request Hook。
- GitLab Push Hook。
- 手动审查入口。
- 已有任务重新触发审阅。

任务列表用于查看：

- 项目、分支、作者、触发类型。
- 任务状态和 Review 状态。
- 风险等级和 finding 数。
- 项目组、端类型和 Profile。

任务详情用于查看：

- 任务基础信息和原始事件摘要。
- changed files / diff。
- 规则提醒卡片。
- 变更分析结果。
- AI Review 结果。
- 多模型 Review 子结果。
- AI Review 执行过程。
- 高准确模式流转。
- 确定性检查结果。
- 钉钉通知记录。
- Diff 完整上下文或紧凑 diff。
- AI 修复 Patch 预览。

任务详情里的关键子能力：

- `提醒卡片`：按 DB、缓存、MQ、配置等重点变更展示结构化提醒。
- `代码质量 Review`：展示 AI finding、severity、category、confidence、contextStatus、evidence 和建议。
- `高准确模式流转`：展示 Context Planner、Local Retriever、Context Pack、预算裁剪、Provider 调用和结果解析。
- `确定性检查`：展示敏感信息扫描等确定性证据。
- `补证据`：对高影响且上下文不足的 finding 触发 finding 级 refinement。
- `标注评估样本`：把 finding 沉淀为 evaluation case。

边界：

- 任务详情展示 AI Review 原结果，不静默覆盖 finding。
- finding 级补证据只作为显式覆盖层，不自动降级、不自动忽略 finding。
- 任务重新触发用于调试和对比，不代表 GitLab 上真实 MR 被重新提交。

## 四、评估样本：把人工判断沉淀为质量样本

`评估样本` 用于 Review 后的质量评估沉淀。

主要使用者：

- Reviewer。
- Tech Lead。
- 质量治理管理员。

生命周期位置：

```text
任务详情查看
  -> 人工判断
  -> 沉淀评估样本
```

典型入口：

- 任务详情 -> 代码质量 Review -> 展开某条 finding -> 标注评估样本。
- 顶部导航 -> 评估样本 -> 查询和筛选样本。

evaluation case 表达的是人工质量判断，例如：

- `TRUE_POSITIVE`：有效问题。
- `FALSE_POSITIVE`：误判。
- `LEVEL_TOO_HIGH`：等级过高。
- `LEVEL_TOO_LOW`：等级过低。
- `CONTEXT_MISSING`：上下文不足。
- `DUPLICATE`：重复 finding。
- `MISSING_FINDING`：漏报。

它用于回答：

- 哪些 finding 被人工确认是误判。
- 哪些风险类型上下文不足。
- 哪些项目、Provider、Profile 的质量问题集中。
- 后续 Retriever、Prompt、规则或 Provider 改动是否有样本依据。

边界：

- evaluation case 不修改原 AI Review 结果。
- evaluation case 不创建反馈池记录。
- evaluation case 不生成项目策略。
- evaluation case 不触发模型回放。

## 五、规则缺口：解释上下文为什么不足

`规则缺口` 是高准确模式诊断入口。

主要使用者：

- 平台开发者。
- 质量治理管理员。
- 排查 Review 准确率问题的 Tech Lead。

生命周期位置：

```text
任务详情 / 高准确模式流转
  -> 规则缺口聚合
  -> 质量治理诊断
```

它聚合来自 `CONTEXT_PACK_BUILT` progress event 的安全摘要，解释：

- Planner 命中了哪些 signal。
- 哪些 requested context 不可用。
- 哪些 signal 还没有 Retriever 支持。
- 本地仓库是否准备失败。
- Local Retriever 是否失败或只部分可用。
- Context Pack 是否发生预算裁剪。
- 哪些证据命中了但未注入。

常见缺口类型：

- `UNSUPPORTED_PLANNER_SIGNAL`：Planner 命中 signal，但 Retriever 不支持。
- `UNAVAILABLE_REQUESTED_CONTEXT`：请求的上下文不可用。
- `RETRIEVAL_FAILED`：本地检索失败或不完整。
- `BUDGET_CUT`：证据因预算被裁剪。

使用原则：

- 规则缺口只解释问题，不单独决定实现优先级。
- 是否补 Retriever 必须结合 evaluation cases、rule gap attribution、evaluation runs 和 acceptance gates。
- `FREQUENCY_ONLY` 只能说明高频观察，不能证明该缺口导致误判或漏报。

边界：

- 规则缺口不会自动补 Retriever。
- 规则缺口不会自动修改 Prompt。
- 规则缺口不会自动降级或忽略 finding。

## 六、质量看板：判断 Review 质量问题集中在哪里

`质量看板` 是质量治理主入口。

主要使用者：

- 管理员。
- Tech Lead。
- 平台负责人。

生命周期位置：

```text
评估样本沉淀
  -> 聚合质量指标
  -> 判断下一步治理方向
```

质量看板基于 evaluation cases 聚合：

- 样本数。
- 误判数 / 误判率。
- 上下文不足数 / 上下文不足率。
- 等级过高 / 等级过低。
- 重复 finding。
- 漏报样本。
- 项目维度统计。
- Provider 维度统计。
- Profile 维度统计。
- 风险类型维度统计。

同时展示辅助诊断：

- evaluation run 摘要。
- finding refinement 摘要。
- deterministic check 摘要。
- rule gap attribution 摘要。
- acceptance gate 摘要。

它用于回答：

- 最近误判集中在哪些项目。
- 哪些 Provider / Profile 的质量问题更多。
- 哪些风险类型更容易上下文不足。
- 是否已有样本证明某个规则缺口导致误判或漏报。
- 是否值得进入下一个 Retriever、Prompt、规则或 Provider 改动。

边界：

- 主指标只来自 evaluation cases。
- 看板不把回放 item 或确定性检查重复计为样本。
- 看板不自动选择胜出版本。
- 看板不自动修改 Prompt、项目策略或 finding。

## 七、验收记录：记录能力改动的准入和退出

`验收记录` 对应规则、Retriever、Prompt、Context Pack、确定性检查或 Provider 改动的治理记录。

主要使用者：

- 平台负责人。
- 质量治理管理员。
- 负责能力改动的开发者。

生命周期位置：

```text
质量看板 / 规则缺口 / 评估样本
  -> 创建准入记录
  -> 实施一个能力改动
  -> 回放或人工验证
  -> 填写退出结果
```

准入记录应说明：

- 要改什么能力。
- 解决哪个明确问题。
- 关联哪些 evaluation cases。
- 关联哪些 evaluation runs。
- 关联哪些安全 rule gap summary。
- 预期收益。
- 风险评估。
- 成本估算。
- 决策人和决策时间。

退出记录应说明：

- 是否改善。
- false positive delta。
- context missing delta。
- missing finding delta。
- finding count delta。
- duration delta。
- token cost delta。
- 结论说明。

使用原则：

- 每次补 Retriever 前必须有准入记录。
- 每次能力改动后必须补退出结果。
- 一条验收记录只对应一次明确能力改动。

边界：

- 验收记录不是 CI gate。
- 验收记录不阻塞真实合并。
- 验收记录不自动修改线上 Review 行为。
- 验收记录不写回 evaluation cases、evaluation runs、AI Review result、finding、Prompt 或项目策略。

## 八、回放记录：对比 baseline 和 candidate

`回放记录` 用于保存 evaluation run / review replay run。

主要使用者：

- 平台开发者。
- 质量治理管理员。

生命周期位置：

```text
有 evaluation cases
  -> 创建 baseline / candidate run
  -> 记录样本结果摘要
  -> 支撑验收记录退出结论
```

回放记录保存：

- sample set。
- Provider。
- Profile。
- model。
- prompt hash。
- Context Pack version。
- Retriever version。
- rule gap version。
- baseline 元信息。
- candidate 元信息。
- 每个样本的结果摘要。

它用于回答：

- 改动前后 finding 数是否变化。
- 误判是否下降。
- 上下文不足是否下降。
- 漏报是否减少。
- 耗时和成本是否上升。

边界：

- 当前 MVP 不自动批量调用真实模型。
- 回放记录不自动修改 Prompt。
- 回放记录不自动选择胜出版本。
- 回放记录不修改原 Review 结果、项目策略、finding 等级或忽略状态。

## 九、反馈池：默认隐藏的项目知识治理入口

`反馈池` 当前生产前端默认隐藏。

主要使用者：

- 项目负责人。
- 平台管理员。

生命周期位置：

```text
用户反馈 finding
  -> 反馈池审核
  -> 人工确认后沉淀项目策略候选
```

反馈池和评估样本的区别：

| 能力 | 主要目的 | 是否影响项目知识 |
|---|---|---|
| 评估样本 | 质量评估、误判统计、回放对比 | 不直接影响 |
| 反馈池 | 用户反馈台账、项目策略候选、项目知识治理 | 人工确认后可影响 |

反馈池可以支持：

- 查看风险项 / finding 反馈。
- 标记反馈状态。
- 筛选上下文不足反馈。
- 统计缺失上下文类型。
- 从有效反馈生成项目策略候选。
- 管理项目策略启停。

边界：

- 反馈池默认不展示，需前端构建开关启用。
- 上下文不足反馈不会自动生成项目策略。
- 项目策略必须人工确认后才可启用。
- 不自动降级、不自动忽略 finding。

## 十、版本更新与通知入口

`版本更新` 用于查看近期功能变化、部署注意和验证提示。

右上角通知图标用于查看最近 AI Review 执行失败记录，并可跳转任务详情。

这两个入口不改变 Review 生命周期状态，只提供：

- 变更说明。
- 运维提示。
- 失败任务快速入口。

## 十一、角色视角

### 开发者

主要使用：

- `任务`
- `任务详情`
- 钉钉通知链接

关注：

- 本次 MR / Push 有哪些提醒。
- AI Review finding 是否需要修。
- Diff 和证据是否足够。

### Reviewer / Tech Lead

主要使用：

- `任务`
- `任务详情`
- `评估样本`
- `质量看板`

关注：

- 哪些问题必须处理。
- 哪些 finding 证据充分。
- 哪些是上下文不足或误判。
- 是否需要沉淀评估样本。

### 管理员

主要使用：

- `设置`
- `质量看板`
- `规则缺口`
- `验收记录`
- `回放记录`
- 可选启用 `反馈池`

关注：

- Review 配置是否正确。
- 质量问题集中在哪里。
- 下一个能力改动是否有样本证明。
- 改动后是否真的改善。

### 平台开发者

主要使用：

- `任务详情 / 高准确模式流转`
- `规则缺口`
- `质量看板`
- `验收记录`
- `回放记录`

关注：

- Planner / Retriever / Context Pack 是否按预期工作。
- 是否存在安全边界泄露。
- 是否具备实现下一个 Retriever 的证据链。

## 十二、常见闭环

### 线上 Review 闭环

```text
设置项目和 Provider
  -> GitLab MR / Push 触发任务
  -> 任务详情查看提醒卡片和 AI Review
  -> 必要时补证据或查看确定性检查
  -> 钉钉通知团队
```

### 误判治理闭环

```text
任务详情发现误判
  -> 标注评估样本为 FALSE_POSITIVE
  -> 编辑 rule gap attribution
  -> 质量看板观察误判集中维度
  -> 创建验收记录
  -> 实施一个能力改动
  -> 回放记录对比
  -> 更新验收记录退出结果
```

### 上下文不足治理闭环

```text
任务详情发现 contextStatus=PARTIAL / INSUFFICIENT
  -> 触发 finding 级补证据
  -> 若仍不足，标注 evaluation case 为 CONTEXT_MISSING
  -> 关联规则缺口归因
  -> 在质量看板确认是否高频且样本证明
  -> 满足条件后进入单个 Retriever 改动
```

### Retriever 改动闭环

```text
规则缺口高频
  -> evaluation cases 证明误判 / 漏报 / 上下文不足
  -> rule gap attribution 标记 CAUSED / RELATED
  -> 创建 RETRIEVER acceptance gate
  -> 实现一个 Retriever
  -> 创建或更新 evaluation run
  -> 记录退出结果
  -> 停止等待下一轮确认
```

## 十三、当前阶段使用建议

当前 M10 已落地缓存 Retriever。进入 M11 后，不应只因为规则缺口高频就实现 MQ、配置、测试覆盖或跨端调用方 Retriever。

M11 的正确使用顺序是：

```text
任务详情 / 规则缺口
  -> 标注评估样本
  -> 编辑规则缺口归因
  -> 质量看板确认样本证明
  -> 验收记录创建准入
  -> 回放记录建立 baseline
  -> 再实现一个 Retriever
```

如果没有 evaluation cases、rule gap attribution、evaluation runs 或 acceptance gates，应先补证据，不实现新的业务 Retriever。

M12 是项目知识与反馈治理产品化，应在不破坏 M11 证据原则的前提下推进。若提前做 M12，建议先做服务于证据补齐的最小工作流，而不是自动启用项目策略或自动改 Prompt。
