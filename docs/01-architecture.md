# MVP 架构设计

## 1. 架构原则

- 模块化：每个核心能力独立成模块，模块之间通过清晰 DTO / VO 传递数据。
- 配置优先：项目接入、规则模板、钉钉 webhook、GitLab token 均通过配置或数据库管理。
- 规则优先：一期先实现可解释、可测试的规则引擎，AI 作为后续增强点。
- 结构化输出：风险结果统一产出 RiskCard JSON，不直接输出不可解析的大段文本。
- 异步可扩展：MVP 可先同步执行，模块边界预留异步任务队列能力。
- 可测试：变更分析、规则匹配、风险卡片生成、通知发送均应能独立测试。

## 2. 技术选型

- 后端：Java Spring Boot。
- 数据库：MySQL。
- 前端：React + Ant Design。
- 外部系统：GitLab webhook / GitLab API、钉钉机器人 webhook。
- 缓存：Redis 暂不作为 MVP 必需项，仅保留后续扩展空间。
- 消息：MVP 不引入 MQ，仅在应用内保留异步 job 抽象。

## 3. 模块边界

### 3.1 project-integration

负责项目和外部系统接入。

职责：

- 管理项目基本信息。
- 保存 GitLab 项目映射、仓库地址、默认模板。
- 保存钉钉 webhook 配置引用。
- 对接 GitLab API 拉取 MR diff / changed files。

输入：

- 项目配置。
- GitLab webhook payload。
- GitLab project id、MR iid、commit sha。

输出：

- ProjectIntegrationContext。
- ChangedFile 列表。
- DiffContent。

### 3.2 review-record

负责审查任务生命周期与审查结果持久化。

职责：

- 创建 ReviewTask。
- 更新任务状态：PENDING、RUNNING、SUCCESS、FAILED。
- 保存 ReviewResult 与 RiskCard JSON。
- 提供审查任务列表和详情查询。

输入：

- WebhookTriggerCommand。
- RiskCard。
- 执行状态和错误信息。

输出：

- ReviewTaskVO。
- ReviewResultVO。

### 3.3 change-analysis

负责从 changed files 与 diff 中识别变更类型和影响面。

职责：

- 解析文件路径、扩展名、diff 内容。
- 识别 API / DB / CACHE / MQ / CONFIG 五类变更。
- 生成 ChangeAnalysisResult。
- 记录证据：文件路径、diff 片段、匹配规则、命中的符号或资源。

输入：

- ChangedFile 列表。
- DiffContent。

输出：

- ChangeAnalysisResult。

### 3.4 rule-template

负责规则模板配置与启用策略。

职责：

- 管理 ReviewTemplate。
- 管理 RuleDefinition。
- 提供 `backend-default` 模板。
- 根据项目、触发来源和模板 code 返回启用规则集合。

输入：

- templateCode。
- projectId。
- changeTypes。

输出：

- ActiveRuleSet。

### 3.5 risk-engine

负责基于分析结果和规则集合生成风险项。

职责：

- 执行规则匹配。
- 生成 RiskItem。
- 计算风险等级和建议检查项。
- 生成 RiskCard。

输入：

- ChangeAnalysisResult。
- ActiveRuleSet。
- ReviewTaskContext。

输出：

- RiskCard。
- RiskItem 列表。

### 3.6 notification

负责风险卡片推送。

职责：

- 将 RiskCard 转换为钉钉 Markdown / ActionCard。
- 调用钉钉 webhook。
- 保存 NotificationRecord。
- 支持失败记录和后续重试扩展。

输入：

- RiskCard。
- NotificationTarget。

输出：

- NotificationRecord。

### 3.7 knowledge-base

MVP 只保留占位，不实现复杂知识库。

职责：

- 后续接收人工反馈、历史问题、团队规范。
- 后续为风险规则和 AI 增强提供上下文。

## 4. 数据流

### 4.1 GitLab MR 自动审查主流程

```text
GitLab
  -> POST /api/webhooks/gitlab/merge-request
  -> WebhookController 校验事件
  -> ReviewTaskService 创建审查任务
  -> GitLabClient 获取 changed files / diff
  -> ChangeAnalysisService 生成 ChangeAnalysisResult
  -> RuleTemplateService 加载 backend-default
  -> RiskEngine 生成 RiskItem 与 RiskCard
  -> ReviewResultService 保存 RiskCard
  -> DingTalkNotifier 推送摘要
  -> NotificationService 保存推送记录
  -> Web Admin 查询任务与卡片
```

### 4.2 Web 查看流程

```text
React Admin
  -> GET /api/review-tasks
  -> GET /api/review-tasks/{taskId}
  -> GET /api/review-tasks/{taskId}/risk-card
  -> 渲染任务状态、影响面、风险项和推荐检查项
```

## 5. 分层建议

后端建议采用以下包结构：

```text
com.example.codereview
  common
    dto
    enums
    exception
    response
  projectintegration
    controller
    application
    domain
    infrastructure
  reviewrecord
    controller
    application
    domain
    infrastructure
  changeanalysis
    application
    domain
    rule
  ruletemplate
    controller
    application
    domain
    infrastructure
  riskengine
    application
    domain
    rule
  notification
    application
    domain
    infrastructure
  knowledgebase
```

## 6. MVP 同步与异步边界

MVP 可以先同步执行 webhook 审查链路，以降低复杂度。但接口和状态设计应支持后续异步化：

- webhook 接收后立即创建 ReviewTask。
- ReviewTask 状态从 PENDING 进入 RUNNING。
- 后续可将分析任务投递到 job executor 或 MQ。
- 前端通过任务状态查询执行结果。

推荐 MVP 阶段保留 `ReviewJobExecutor` 抽象，即使内部先同步调用。

## 7. 错误处理策略

- GitLab webhook 无效：返回 400，不创建任务。
- 项目未接入：返回 404 或创建失败任务，推荐返回 404。
- GitLab API 拉取失败：任务置为 FAILED，记录错误摘要。
- 规则模板不存在：使用项目默认模板；仍不存在则任务 FAILED。
- 风险项为空：任务 SUCCESS，生成低风险或无风险卡片。
- 钉钉推送失败：不影响 ReviewTask 成功状态，但 NotificationRecord 记录 FAILED。

## 8. 前端页面边界

MVP 前端只做基础管理后台：

- 审查任务列表：项目、MR、分支、状态、风险等级、创建时间。
- 审查任务详情：触发信息、变更摘要、影响范围、风险项列表。
- 风险卡片详情：直接按 RiskCard JSON 渲染。
- 规则模板只读展示：MVP 可先展示 `backend-default`。
