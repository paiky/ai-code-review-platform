# 领域模型与数据库设计

## 1. 核心领域对象

### 1.1 Project

表示一个接入平台的代码项目。

关键字段：

- id：平台内部项目 ID。
- name：项目名称。
- gitProvider：代码托管平台，MVP 固定为 GITLAB。
- gitProjectId：GitLab 项目 ID。
- repositoryUrl：仓库地址。
- defaultTemplateCode：默认审查模板，例如 `backend-default`。
- dingTalkWebhookId：默认钉钉通知配置引用。
- status：ENABLED / DISABLED。

### 1.2 ReviewTask

表示一次审查任务。

关键字段：

- id：任务 ID。
- projectId：所属项目。
- triggerType：GITLAB_MR_WEBHOOK / MANUAL / JENKINS。
- externalSourceId：外部来源 ID，例如 GitLab MR iid。
- externalUrl：MR、构建或手动任务详情链接。
- sourceBranch / targetBranch。
- commitSha / beforeSha / afterSha。
- authorName / authorUsername。
- templateCode。
- status：PENDING / RUNNING / SUCCESS / FAILED。
- riskLevel：NONE / LOW / MEDIUM / HIGH / CRITICAL。
- errorMessage。
- startedAt / finishedAt。

### 1.3 ChangeAnalysisResult

表示变更影响分析结果。MVP 可作为 JSON 存储在审查结果表中。

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
- category：API / DB / CACHE / MQ / CONFIG / RELEASE / OBSERVABILITY。
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

表示一次审查输出的完整风险卡片。

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

表示审查模板，例如 `backend-default`。

关键字段：

- id。
- templateCode。
- templateName。
- description。
- targetType：BACKEND / FRONTEND / GENERAL。
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

## 2. 枚举定义

### 2.1 ChangeType

- API
- DB
- CACHE
- MQ
- CONFIG

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

### 2.4 TriggerType

- GITLAB_MR_WEBHOOK
- JENKINS
- MANUAL

### 2.5 NotificationStatus

- PENDING
- SUCCESS
- FAILED
- SKIPPED

## 3. 数据库表结构

以下为 MVP 最小表结构设计。字段类型可在具体实现时按 MySQL 版本和 ORM 规范调整。

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
  risk_level VARCHAR(32) NULL,
  error_message VARCHAR(1024) NULL,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  KEY idx_project_created (project_id, created_at),
  KEY idx_status_created (status, created_at),
  KEY idx_external_source (trigger_type, external_source_id)
);
```

### 3.3 review_results

审查结果表，保存变更分析结果和风险卡片 JSON。

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

钉钉 webhook 配置表。虽然题目要求至少包含推送记录，MVP 建议单独保存 webhook 配置，避免把敏感配置散落在项目表中。

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

## 4. 领域关系

```text
Project 1 -> N ReviewTask
ReviewTask 1 -> 1 ReviewResult
ReviewTask 1 -> N NotificationRecord
ReviewTemplate 1 -> N ReviewTask
Project N -> 1 ReviewTemplate by default_template_code
Project N -> 1 NotificationWebhook by dingtalk_webhook_id
```

## 5. MVP 示例模板

`backend-default` 应至少启用以下规则方向：

- API 兼容性检查。
- DB 结构或 SQL 变更检查。
- 缓存一致性检查。
- MQ 幂等与重复消费检查。
- 配置变更灰度与回滚检查。
- 监控、告警、回滚检查。
