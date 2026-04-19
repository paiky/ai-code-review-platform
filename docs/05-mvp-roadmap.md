# MVP 实施路线图

## 1. 实施原则

- 每次只做一个小目标。
- 先补文档，再写代码。
- 先数据结构与接口，再业务逻辑。
- 先规则引擎，再 AI 增强。
- 先打通完整链路，再优化识别精度。
- 每个阶段都要有测试和 demo 数据。

## 2. 阶段一：设计与骨架

目标：让项目从文档进入可实施状态。

交付物：

- MVP 文档：
  - `00-product-overview.md`
  - `01-architecture.md`
  - `02-domain-model.md`
  - `03-api-contract.md`
  - `04-risk-card-schema.md`
  - `05-mvp-roadmap.md`
- 后端模块划分说明。
- 风险卡片 schema。
- 数据库表结构。
- API 契约。

验收标准：

- 所有核心模块边界明确。
- 主链路输入输出明确。
- 风险卡片可作为前端和钉钉的统一数据源。
- 数据库至少覆盖项目、审查任务、审查结果、规则模板、推送记录。

## 3. 阶段二：后端基础工程与数据结构

目标：搭建 Spring Boot MVP 基础骨架，但不急于实现复杂规则。

建议顺序：

1. 创建后端 Spring Boot 项目。
2. 建立模块包结构。
3. 定义枚举、DTO、VO、Entity。
4. 建立数据库 migration 或 schema 初始化。
5. 提供统一响应结构、异常结构和 traceId。
6. 准备 demo 项目与 `backend-default` 模板初始数据。

验收标准：

- 应用能本地启动。
- 数据库能初始化。
- 项目、模板、任务基础表可读写。
- DTO / VO 与文档字段保持一致。

## 4. 阶段三：GitLab webhook 与任务落库

目标：先让外部触发变成内部 ReviewTask。

建议顺序：

1. 实现 GitLab webhook controller。
2. 校验事件类型和 token。
3. 将 payload 映射为 WebhookTriggerCommand。
4. 根据 GitLab project id 查找 Project。
5. 创建 ReviewTask。
6. 保存 raw payload 摘要或必要字段。
7. 用 demo webhook payload 做集成测试。

验收标准：

- POST demo GitLab MR payload 后生成 ReviewTask。
- 非 MR 事件或无效项目有明确错误。
- 任务状态流转可观测。

## 5. 阶段四：变更获取与变更分析

目标：识别 API / DB / CACHE / MQ / CONFIG 五类基础变更。

建议顺序：

1. 定义 ChangedFile、DiffContent、ChangeAnalysisResult。
2. 实现 GitLab diff 获取接口封装。
3. 支持测试模式下直接读取 demo diff。
4. 实现基于路径和关键词的初版分析器：
   - API：Controller、RequestMapping、GetMapping、PostMapping、DTO。
   - DB：mapper、sql、migration、entity、repository。
   - CACHE：Redis、Cacheable、CacheEvict、cache key。
   - MQ：producer、consumer、topic、listener。
   - CONFIG：yml、yaml、properties、nacos、feature flag。
5. 输出影响资源和 evidence。

验收标准：

- demo diff 能产出 ChangeAnalysisResult。
- 每类变更至少有一个可测试样例。
- 分析结果能保存到 `review_results.change_analysis_json`。

## 6. 阶段五：规则模板与风险引擎

目标：用 `backend-default` 规则模板生成结构化 RiskItem。

建议顺序：

1. 初始化 `backend-default` 模板。
2. 定义 RuleDefinition 和 RuleContext。
3. 实现基础规则：
   - `API_COMPATIBILITY_CHECK`
   - `DB_CHANGE_CHECK`
   - `CACHE_CONSISTENCY_CHECK`
   - `MQ_IDEMPOTENCY_CHECK`
   - `CONFIG_RELEASE_CHECK`
   - `OBSERVABILITY_CHECK`
4. 根据命中规则生成 RiskItem。
5. 根据最高风险项计算 RiskSummary。
6. 生成符合 schema 的 RiskCard。

验收标准：

- demo diff 能生成 RiskCard。
- RiskCard JSON 通过 schema 校验。
- 无风险项时也能生成 `NONE` 或 `LOW` 风险卡片。
- 规则结果可解释，包含 evidence 和 ruleCode。

## 7. 阶段六：钉钉推送与推送记录

目标：将 RiskCard 推送到钉钉，并记录推送结果。

建议顺序：

1. 定义 NotificationTarget 和 NotificationRecord。
2. 将 RiskCard 转换为钉钉 Markdown。
3. 调用钉钉 webhook。
4. 保存 SUCCESS / FAILED / SKIPPED 记录。
5. 钉钉配置为空时跳过推送但不影响审查任务成功。

验收标准：

- 配置真实 webhook 时能收到风险摘要。
- 配置缺失或调用失败时有明确记录。
- 推送失败不覆盖审查结果成功状态。

## 8. 阶段七：最小 Web 管理页面

目标：让审查记录可被查看。

建议顺序：

1. 创建 React + Ant Design 前端项目。
2. 实现任务列表页。
3. 实现任务详情页。
4. 实现风险卡片渲染组件。
5. 展示影响范围、风险等级、风险项、推荐行动和推送状态。

验收标准：

- 可以查看 demo 审查任务列表。
- 可以进入任务详情查看 RiskCard。
- 页面不依赖钉钉消息文本，而是直接渲染 RiskCard JSON。

## 9. 阶段八：README、测试和 demo 闭环

目标：让项目可本地验证。

交付物：

- README 启动说明。
- 数据库初始化说明。
- demo GitLab webhook payload。
- demo diff / changed files。
- 钉钉 webhook 配置说明。
- 单元测试：
  - 变更分析器测试。
  - 风险规则测试。
  - RiskCard schema 测试。
- 集成测试：
  - webhook -> task -> analysis -> risk card -> notification record。

验收标准：

- 本地按 README 能跑通。
- 至少一条完整链路可验证：

```text
webhook -> 分析 -> 风险卡片 -> 推送 -> 落库 -> 页面查看
```

## 10. 推荐实现顺序总览

1. 后端项目骨架与数据库 schema。
2. 核心 DTO / VO / Entity / enum。
3. `backend-default` 模板和 demo 数据。
4. GitLab webhook controller 与 ReviewTask 落库。
5. GitLab diff 获取与 demo diff 输入。
6. ChangeAnalysisResult 生成。
7. RuleEngine 与 RiskCard 生成。
8. ReviewResult 落库。
9. DingTalkNotifier 与 NotificationRecord。
10. React + Ant Design 最小页面。
11. README、测试和 demo 验证。

## 11. MVP 后续增强方向

- Jenkins 构建后触发审查。
- Web 页面手动发起审查。
- 前端模板 `frontend-default`。
- 通用模板 `general-default`。
- 人工反馈回流。
- 知识库和历史相似问题提示。
- AI 对风险项描述、上下文补全和建议项生成做增强。
