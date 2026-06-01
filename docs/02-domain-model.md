# 领域模型与数据库设计

> 状态说明：本文描述平台核心领域对象与 MVP 基线表结构。§3 的 SQL 对应 `V1__init_mvp_schema.sql` 起点；后续字段与表以 `backend-python/migrations/bootstrap_sql/` 和 `backend-python/app/**/models.py` 为准。完整 API 字段见 `03-api-contract.md`，提醒卡片 JSON 见 `04-risk-card-schema.md`。

## 1. 核心领域对象

### 1.1 Project

表示一个接入平台的代码项目。

关键字段：

- id：平台内部项目 ID。
- groupId：所属项目组。
- name：项目名称。
- gitProvider：代码托管平台，当前固定为 GITLAB。
- gitProjectId：GitLab 项目 ID。
- repositoryUrl：仓库地址。
- supportedTargetTypes / detectedTargetTypes / targetDetectionJson：项目支持的端类型与自动识别结果。
- defaultTemplateCode：默认规则提醒模板，例如 `backend-default`。
- defaultCodeQualityProfileCode / defaultCodeQualityProviderCode：默认 AI Review profile 与 provider。
- dingTalkWebhookId：默认钉钉通知配置引用。
- status：ENABLED / DISABLED。

端类型明细配置见 `ProjectTargetConfig`（§6.1）。

### 1.2 ReviewTask

表示一次审查任务。

关键字段：

- id：任务 ID。
- projectId：所属项目。
- triggerType：GITLAB_MR_WEBHOOK / GITLAB_PUSH_WEBHOOK / MANUAL / JENKINS。
- externalSourceId：外部来源 ID，例如 GitLab MR iid 或 push 事件标识。
- externalUrl：MR、Push、构建或手动任务详情链接。
- sourceBranch / targetBranch。
- commitSha / beforeSha / afterSha。
- authorName / authorUsername。
- templateCode：规则提醒模板。
- targetType / targetTypesJson：本次任务主端类型与涉及端类型列表。
- codeQualityProfileCode：本次任务使用的 AI Review profile。
- status：PENDING / RUNNING / SUCCESS / FAILED。表示规则提醒主链路执行状态。
- reviewStatus：NOT_TRIGGERED / REVIEWING / NO_RISK / MINOR / MAJOR / CRITICAL /
  SKIPPED / REVIEW_FAILED / TASK_FAILED。用于任务列表展示和筛选；由 AI Review 结果与任务状态聚合得出。
- riskLevel：NONE / LOW / MEDIUM / HIGH / CRITICAL。
- errorMessage。
- startedAt / finishedAt。

### 1.3 ChangeAnalysisResult

表示变更影响分析结果，通常作为 JSON 存储在 `review_results.change_analysis_json`。

关键字段：

- summary：变更摘要。
- changedFiles：变更文件列表。
- changeTypes：命中的变更类型集合。
- impactedResources：受影响资源集合。
- evidences：识别证据。

### 1.4 RiskItem

表示一个结构化风险项。

关键字段：

- riskId：风险项 ID。
- category：API / DB / CACHE / MQ / CONFIG / RELEASE / OBSERVABILITY 及细分子类型。
- severity：LOW / MEDIUM / HIGH / CRITICAL。
- title：风险标题。
- description：风险说明。
- impact：可能影响。
- evidences：证据。
- suggestions：建议。
- checkItems：推荐检查项。
- ownerRoles：建议关注角色。
- source：规则、AI 或人工来源。

### 1.5 RiskCard

表示一次审查输出的完整提醒卡片。

关键字段：

- schemaVersion。
- cardId。
- taskId。
- project。
- trigger。
- changeSummary。
- impactScope。
- riskSummary。
- riskItems。
- recommendedActions。
- notification。
- metadata。

完整 JSON schema 见 `04-risk-card-schema.md`。

### 1.6 ReviewTemplate

表示规则提醒模板，例如 `backend-default`。数据库表名为 `rule_templates`。

关键字段：

- id。
- templateCode。
- templateName。
- description。
- targetType：BACKEND / WEB_PC / GENERAL 等端类型。
- enabledRuleCodes。
- configJson。
- status。
- version。

### 1.7 NotificationRecord

表示一次推送记录。

关键字段：

- id。
- taskId。
- resultId。
- channel：DINGTALK。
- target。
- status：PENDING / SUCCESS / FAILED / SKIPPED。
- requestDigest。
- responseBody。
- errorMessage。
- sentAt。

### 1.8 ReviewResult

表示一次规则提醒链路的结果快照。

关键字段：

- id。
- taskId / projectId。
- templateCode。
- targetType。
- reminderCardEnabled：该端类型是否启用提醒卡片。
- riskLevel / riskItemCount。
- changeAnalysisJson / riskCardJson。
- summary。

## 2. 枚举定义

### 2.1 ChangeType

- API
- DB
- CACHE
- MQ
- CONFIG

细粒度子类型见 `06-change-analysis-rules.md`。

### 2.2 RiskSeverity

- NONE
- LOW
- MEDIUM
- HIGH
- CRITICAL

### 2.3 ReviewTaskStatus

- PENDING
- RUNNING
- SUCCESS
- FAILED

### 2.4 ReviewStatus

- NOT_TRIGGERED
- REVIEWING
- NO_RISK
- MINOR
- MAJOR
- CRITICAL
- SKIPPED
- REVIEW_FAILED
- TASK_FAILED

### 2.5 TriggerType

- GITLAB_MR_WEBHOOK
- GITLAB_PUSH_WEBHOOK
- MANUAL
- JENKINS

### 2.6 NotificationStatus

- PENDING
- SUCCESS
- FAILED
- SKIPPED

## 3. MVP 基线表结构

以下为 MVP 最小表结构设计，对应 `V1__init_mvp_schema.sql`。字段类型可在具体实现时按 MySQL 版本和 ORM 规范调整；后续 migration 新增的列不在此逐条展开。

### 3.1 projects

项目接入表。

```sql
CREATE TABLE projects (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  git_provider VARCHAR(32) NOT NULL DEFAULT 'GITLAB',
  git_project_id VARCHAR(128) NOT NULL,
  repository_url VARCHAR(512) NULL,
  default_template_code VARCHAR(64) NOT NULL DEFAULT 'backend-default',
  dingtalk_webhook_id BIGINT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ENABLED',
  description VARCHAR(512) NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_git_project (git_provider, git_project_id),
  KEY idx_status (status)
);
```

后续扩展：`group_id`、`supported_target_types`、`default_code_quality_profile_code` 等，见 `V8`、`V24`。

### 3.2 review_tasks

审查任务表。

```sql
CREATE TABLE review_tasks (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  trigger_type VARCHAR(64) NOT NULL,
  external_source_id VARCHAR(128) NULL,
  external_url VARCHAR(512) NULL,
  source_branch VARCHAR(255) NULL,
  target_branch VARCHAR(255) NULL,
  commit_sha VARCHAR(128) NULL,
  before_sha VARCHAR(128) NULL,
  after_sha VARCHAR(128) NULL,
  author_name VARCHAR(128) NULL,
  author_username VARCHAR(128) NULL,
  template_code VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  review_status VARCHAR(32) NOT NULL DEFAULT 'NOT_TRIGGERED',
  risk_level VARCHAR(32) NULL,
  error_message VARCHAR(1024) NULL,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  KEY idx_project_created (project_id, created_at),
  KEY idx_status_created (status, created_at),
  KEY idx_review_status_created (review_status, created_at),
  KEY idx_external_source (trigger_type, external_source_id)
);
```

后续扩展：`target_type`、`target_types_json`、`code_quality_profile_code`，见 `V24`。

### 3.3 review_results

审查结果表，保存变更分析结果和提醒卡片 JSON。

```sql
CREATE TABLE review_results (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  project_id BIGINT NOT NULL,
  template_code VARCHAR(64) NOT NULL,
  risk_level VARCHAR(32) NOT NULL,
  risk_item_count INT NOT NULL DEFAULT 0,
  change_analysis_json JSON NOT NULL,
  risk_card_json JSON NOT NULL,
  summary VARCHAR(1024) NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_task (task_id),
  KEY idx_project_created (project_id, created_at),
  KEY idx_risk_level (risk_level)
);
```

后续扩展：`target_type`、`reminder_card_enabled`，见 `V24`。

### 3.4 rule_templates

规则模板表。

```sql
CREATE TABLE rule_templates (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  template_code VARCHAR(64) NOT NULL,
  template_name VARCHAR(128) NOT NULL,
  target_type VARCHAR(32) NOT NULL,
  version INT NOT NULL DEFAULT 1,
  enabled_rule_codes JSON NOT NULL,
  config_json JSON NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ENABLED',
  description VARCHAR(512) NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  UNIQUE KEY uk_template_version (template_code, version),
  KEY idx_template_status (template_code, status)
);
```

### 3.5 notification_records

推送记录表。

```sql
CREATE TABLE notification_records (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  result_id BIGINT NULL,
  channel VARCHAR(32) NOT NULL,
  target VARCHAR(512) NULL,
  status VARCHAR(32) NOT NULL,
  request_digest VARCHAR(1024) NULL,
  response_body TEXT NULL,
  error_message VARCHAR(1024) NULL,
  sent_at DATETIME NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  KEY idx_task (task_id),
  KEY idx_status_created (status, created_at)
);
```

### 3.6 notification_webhooks

钉钉 webhook 配置表。

```sql
CREATE TABLE notification_webhooks (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  channel VARCHAR(32) NOT NULL DEFAULT 'DINGTALK',
  webhook_url VARCHAR(1024) NOT NULL,
  secret_ref VARCHAR(256) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ENABLED',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  KEY idx_channel_status (channel, status)
);
```

后续扩展：`project_group_id`、`enabled`，见 `V17` 及项目组相关 migration。

## 4. 领域关系

```text
ProjectGroup 1 -> N Project
Project 1 -> N ProjectTargetConfig
Project 1 -> N ReviewTask
ReviewTask 1 -> 1 ReviewResult
ReviewTask 1 -> N NotificationRecord
ReviewTask 1 -> N CodeQualityReviewResult
ReviewTask 0..1 -> 1 GitLabMergeRequestEvent / GitLabPushEvent
ReviewTemplate(rule_templates) 1 -> N ReviewTask
Project N -> 1 ReviewTemplate by default_template_code
Project N -> 1 NotificationWebhook by dingtalk_webhook_id
```

## 5. 默认模板方向

`backend-default` 当前聚焦 DB / CACHE / MQ / CONFIG 等后端高价值变更提醒；API 兼容性检查已在 `V15__remove_api_compatibility_from_backend_templates.sql` 中从默认模板移除。具体启用规则以数据库 seed 与 `06-change-analysis-rules.md` 为准。

## 6. 扩展领域对象与表

以下对象不在 MVP 基线 SQL 中展开，开发时以 migration 与 ORM 模型为准。

| 对象 / 表 | 用途 | 主要 migration |
| --- | --- | --- |
| ProjectGroup | 项目组、默认 AI Review 策略、Push 审核策略 | V24、V25、V27、V30 |
| ProjectTargetConfig | 项目按端类型的模板、profile、路径映射 | V24 |
| TargetTypePathMapping | 全局端类型路径匹配规则 | V27 |
| GitLabMergeRequestEvent | MR webhook 原始事件 | V2 |
| GitLabPushEvent | Push webhook 原始事件 | V7 |
| CodeQualityReviewProfile | AI Review profile | V8 |
| CodeQualityReviewSettings | 全局 AI Review 开关与默认 provider | V9、V14、V20 |
| CodeQualityModelProvider | 多模型 provider 配置 | V18、V29 |
| CodeQualityReviewResult | AI Review 结果（支持多 reviewKey） | V8、V31 |
| CodeQualityReviewProgressEvent | AI Review 进度事件 | V11 |
| CodeQualityFixPreview | finding 级修复预览 | V21 |
| CodeQualitySchedulerJob | AI Review / fix preview 调度队列 | V22 |
| CodeQualityPushReviewGateDecision | Push 场景 AI Review 门禁决策 | V19 |
| ProjectGroupAiReviewModel | 项目组多模型 AI Review 配置 | V31 |

对应 ORM：`backend-python/app/project_integration/models.py`、`backend-python/app/code_quality/models.py`。
