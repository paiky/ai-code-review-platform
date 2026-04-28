# 四项能力收口任务清单

## 0. 背景结论

当前系统已具备 MVP 主链路，但四项能力成熟度不同：

1. GitLab MR 自动审查已具备；Push 自动审查已能触发，但当前仅基于 push payload 文件列表，尚未拉取完整 diff。
2. 后端业务与技术 code review 仍处于规则启发式风险识别阶段，不等同于完整漏洞扫描、性能分析、代码调优。
3. DB / MQ / Redis / 配置感知已有较细规则，但页面需要优先展示业务更关心的粗粒度指标。
4. 钉钉推送已具备基础能力，但当前按模板关注标签过滤，不是“所有高风险必推”，且项目级 webhook 配置未完成。

本轮目标不是回滚已有细粒度规则，而是在其上增加更稳定的产品展示层和验证闭环。

## 1. 新任务清单

### P0：GitLab Push 拉完整 diff

目标：Push Hook 和 MR Hook 一样能基于完整 diff 做审查。

任务：

1. 新增 GitLab compare API client。
2. Push Hook 收到后，使用 `projectId + beforeSha + afterSha` 拉取 compare diff。
3. compare diff 成功时，`changedFilesSummary.source = gitlab_compare_api`。
4. compare diff 失败时，回退到当前 push payload 文件列表，`source = push_payload`，任务不中断。
5. 补 Push Hook 集成测试，覆盖 compare 成功和 fallback 两条路径。

验收：

- push 一个 commit 后自动生成 `GITLAB_PUSH_WEBHOOK` 任务。
- 任务详情中能看到 diff 文件数和来源。
- 能识别代码内容中的 API / DB / MQ / Redis / CONFIG 风险，而不只看文件名。

### P1：四项粗粒度关注指标展示

目标：前端优先展示用户关心的粗粒度指标：

- DB 表结构变更
- MQ 配置变更
- Redis 配置变更
- `@Value` 配置变更

任务：

1. 保留现有细粒度 `ChangeType` 和风险规则。
2. 新增粗粒度关注指标模型，例如 `focusIndicators`。
3. 后端从细粒度结果聚合出粗粒度指标。
4. 风险卡片 JSON 增加粗粒度指标字段，或在查询 VO 层派生返回。
5. 前端任务详情页优先展示粗粒度指标，再展开细粒度风险项。
6. 任务列表页增加指标标签，便于一眼判断是否涉及 DB / MQ / Redis / `@Value`。

验收：

- 修改 Flyway DDL 时，页面优先显示“DB 表结构变更”。
- 修改 MQ topic/group/consumerGroup 配置时，页面优先显示“MQ 配置变更”。
- 修改 Redis 连接、key、TTL、cache 配置时，页面优先显示“Redis 配置变更”。
- 修改或新增 `@Value("${xxx}")` 时，页面优先显示“@Value 配置变更”。
- 细粒度风险项仍保留，不丢失当前已有解释能力。

### P2：后端 code review 能力边界显式化

目标：明确当前系统能审什么、不能审什么，避免把 MVP 风险识别误解为完整代码审查。

任务：

1. README 和页面文案中明确当前审查类型是“变更风险审查”。
2. 风险卡片中区分：
   - 变更影响风险
   - 兼容性风险
   - 配置 / 发布风险
   - 待增强的代码质量风险
3. 新增技术审查规则规划：
   - 潜在 NPE / 边界条件
   - 慢 SQL / 大表更新风险
   - 循环内远程调用 / DB 调用
   - 日志敏感信息
   - 异常吞掉 / 重试风暴
4. 暂不把这些标为已完成，先形成规则 backlog。

验收：

- 用户能从页面和 README 看出当前不是 SAST、不是完整 AI code review。
- 新增规则 backlog 可逐步实现，不影响当前主链路。

### P3：高风险钉钉推送策略收口

目标：实现“触发高风险时能推送”，同时保留模板关注标签能力。

任务：

1. 明确推送策略优先级：
   - CRITICAL / HIGH 是否必推。
   - `focusChangeTypes` 是否只作为附加过滤。
   - 无关注项但有高风险时是否推送摘要。
2. 新增模板配置项：
   - `notifyRiskLevels`
   - `focusChangeTypes`
   - `notifyWhenNoFocusedItem`
3. DingTalk formatter 增强 DB / MQ / Redis / `@Value` 粗粒度指标展示。
4. 项目级钉钉 webhook 配置进入后续任务，不阻塞本轮高风险推送策略。
5. 补通知单元测试，覆盖高风险必推、未命中关注标签、未配置 webhook 三类情况。

验收：

- 配置 webhook 后，高风险任务能推送钉钉。
- 未配置 webhook 时仍记录 `SKIPPED`，不阻断审查。
- 推送内容优先展示粗粒度指标和关键风险项。

## 2. 详细改动点

### 2.1 GitLab Push compare diff

后端新增或调整：

- `GitLabClient`
  - 新增 `compare(String projectId, String fromSha, String toSha)`。
  - 调用：

```text
GET /api/v4/projects/{projectId}/repository/compare?from={beforeSha}&to={afterSha}
```

- `GitLabDiffFile`
  - 复用现有结构承载 compare 返回的 diff 文件。

- `GitLabPushWebhookService`
  - 当前 `buildPushChangedFilesSummary()` 保留为 fallback。
  - 新增 `resolveChangedFiles()`：
    - 优先 compare API。
    - 成功：生成 `source = gitlab_compare_api`。
    - 失败：生成 `source = push_payload`，并记录 fallback reason。

- `gitlab_push_webhook_events`
  - 当前已保存 `changed_files_summary` 和 `raw_payload`。
  - 可后续增加 `diff_source` / `fallback_reason`，也可以先放入 JSON。

测试：

- Push compare 成功：断言 `changedFilesSummary.source = gitlab_compare_api`。
- Push compare 失败：断言任务仍 SUCCESS，`source = push_payload`。

### 2.2 粗粒度关注指标模型

建议新增枚举或简单字符串字段：

```text
DB_SCHEMA_CHANGE
MQ_CONFIG_CHANGE
REDIS_CONFIG_CHANGE
VALUE_CONFIG_CHANGE
```

聚合映射：

| 粗粒度指标 | 来源信号 |
| --- | --- |
| `DB_SCHEMA_CHANGE` | `DB_SCHEMA`、`DATA_MIGRATION`，或 migration DDL 文件 |
| `MQ_CONFIG_CHANGE` | `MQ_TOPIC_CONFIG`，或配置文件中出现 rocketmq / kafka / rabbit topic/group |
| `REDIS_CONFIG_CHANGE` | `CACHE_KEY`、`CACHE_TTL`、`CACHE_INVALIDATION`、`CACHE_READ_WRITE`、`CACHE_SERIALIZATION`，或配置文件中出现 redis/cache |
| `VALUE_CONFIG_CHANGE` | diff 中出现 `@Value("${...}")`、配置 key 新增/删除、占位符变更 |

后端落点：

- 可新增 `FocusIndicator` record：

```text
code
name
riskLevel
matched
reason
evidences
sourceChangeTypes
```

- 推荐先放在 `RiskCard` 中：

```json
"focusIndicators": []
```

原因：前端和钉钉都消费风险卡片，放在 RiskCard 中最直接。

兼容策略：

- 旧风险项不删。
- 旧 `riskItems.category` 不改。
- 前端优先展示 `focusIndicators`，没有该字段时按现有风险项降级展示。

### 2.3 前端展示

任务列表页：

- 在风险等级旁展示 4 个关注指标标签。
- 命中时高亮，未命中时不展示或灰色。
- 标签建议：
  - DB 表结构
  - MQ 配置
  - Redis 配置
  - `@Value`

任务详情页：

- 风险卡片顶部新增“重点变更”区域。
- 顺序固定：
  1. DB 表结构变更
  2. MQ 配置变更
  3. Redis 配置变更
  4. `@Value` 配置变更
- 每个指标展示：
  - 是否命中
  - 风险级别
  - 命中原因
  - 证据文件
- 下方继续展示现有细粒度风险项、证据、推荐检查项。

### 2.4 @Value 配置感知

新增规则：

- `ValueConfigChangeRule` 或纳入 `ConfigChangeRule`。

识别条件：

- Java/Kotlin diff 中出现：

```text
@Value("${xxx}")
@Value("${xxx:default}")
```

- 配置文件中出现对应 key 的新增/删除/改名。

第一轮只做启发式：

- 看到 `@Value(` 即命中 `VALUE_CONFIG_CHANGE`。
- 提取 `${...}` 中的 key 作为资源名。
- 推荐检查默认值、环境变量、Nacos / application 配置是否同步。

### 2.5 钉钉推送

后端：

- `DingTalkNotifier.formatMarkdown()`
  - 在风险项前增加“重点指标”段落。
  - 展示命中的 DB / MQ / Redis / `@Value`。

- 模板配置建议：

```json
{
  "notifyRiskLevels": ["HIGH", "CRITICAL"],
  "focusChangeTypes": ["DB_SCHEMA", "DATA_MIGRATION", "ENTITY_MODEL"],
  "notifyWhenNoFocusedItem": true
}
```

策略：

- 如果风险等级在 `notifyRiskLevels` 中：推送。
- 如果未达到风险等级，但命中 `focusChangeTypes`：推送。
- 如果都不命中：记录 `SKIPPED`。

### 2.6 文档与验收脚本

README：

- 明确 MR 与 Push 的能力差异。
- 明确 Push compare diff 完成后才具备更准确代码内容识别。
- 增加四个粗粒度指标说明。

examples：

- 保留 MR mock。
- 保留 Push mock。
- 增加 `@Value` 配置变更样例。
- 增加 Redis / MQ 配置样例。

测试：

- `MainReviewFlowIntegrationTest`
  - MR diff path。
  - Push compare path。
  - Push fallback path。

- `ChangeAnalysisServiceTest`
  - DB 表结构。
  - MQ 配置。
  - Redis 配置。
  - `@Value` 配置。

- `DingTalkNotifierTest`
  - 高风险必推。
  - 粗粒度指标展示。
  - 未配置 webhook SKIPPED。

## 3. 建议执行顺序

1. 先做 Push compare diff，补齐自动触发审查的准确性。
2. 再做粗粒度关注指标后端模型和聚合。
3. 再改前端任务列表和详情页展示。
4. 再补 `@Value` 配置识别规则。
5. 最后收口钉钉高风险推送策略和格式。

这样推进的好处是：先保证输入数据足够准确，再优化风险表达和通知，不会在不完整 diff 上过早打磨展示。
