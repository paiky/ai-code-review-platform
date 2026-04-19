CREATE TABLE notification_webhooks (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  channel VARCHAR(32) NOT NULL DEFAULT 'DINGTALK',
  webhook_url VARCHAR(1024) NOT NULL,
  secret_ref VARCHAR(256) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ENABLED',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  KEY idx_channel_status (channel, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_git_project (git_provider, git_project_id),
  KEY idx_status (status),
  KEY idx_dingtalk_webhook (dingtalk_webhook_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
  started_at DATETIME(3) NULL,
  finished_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  KEY idx_project_created (project_id, created_at),
  KEY idx_status_created (status, created_at),
  KEY idx_external_source (trigger_type, external_source_id),
  KEY idx_template_code (template_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_task (task_id),
  KEY idx_project_created (project_id, created_at),
  KEY idx_risk_level (risk_level),
  KEY idx_template_code (template_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_template_version (template_code, version),
  KEY idx_template_status (template_code, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
  sent_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  KEY idx_task (task_id),
  KEY idx_result (result_id),
  KEY idx_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO rule_templates (
  template_code,
  template_name,
  target_type,
  version,
  enabled_rule_codes,
  config_json,
  status,
  description
) VALUES (
  'backend-default',
  '后端默认审查模板',
  'BACKEND',
  1,
  JSON_ARRAY(
    'API_COMPATIBILITY_CHECK',
    'DB_CHANGE_CHECK',
    'CACHE_CONSISTENCY_CHECK',
    'MQ_IDEMPOTENCY_CHECK',
    'CONFIG_RELEASE_CHECK',
    'OBSERVABILITY_CHECK'
  ),
  JSON_OBJECT(
    'focusChangeTypes', JSON_ARRAY('API', 'DB', 'CACHE', 'MQ', 'CONFIG'),
    'defaultRiskLevel', 'LOW'
  ),
  'ENABLED',
  'MVP 后端默认审查模板，先以规则识别为主。'
);
