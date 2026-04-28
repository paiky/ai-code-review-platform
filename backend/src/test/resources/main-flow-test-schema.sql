DROP TABLE IF EXISTS gitlab_mr_webhook_events;
DROP TABLE IF EXISTS notification_records;
DROP TABLE IF EXISTS review_results;
DROP TABLE IF EXISTS review_tasks;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS rule_templates;
DROP TABLE IF EXISTS notification_webhooks;

CREATE TABLE notification_webhooks (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL,
  channel VARCHAR(32) NOT NULL DEFAULT 'DINGTALK',
  webhook_url VARCHAR(1024) NOT NULL,
  secret_ref VARCHAR(256) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ENABLED',
  created_at TIMESTAMP(3) NULL,
  updated_at TIMESTAMP(3) NULL
);

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
  created_at TIMESTAMP(3) NULL,
  updated_at TIMESTAMP(3) NULL,
  UNIQUE (git_provider, git_project_id)
);

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
  started_at TIMESTAMP(3) NULL,
  finished_at TIMESTAMP(3) NULL,
  created_at TIMESTAMP(3) NULL,
  updated_at TIMESTAMP(3) NULL
);

CREATE TABLE review_results (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL UNIQUE,
  project_id BIGINT NOT NULL,
  template_code VARCHAR(64) NOT NULL,
  risk_level VARCHAR(32) NOT NULL,
  risk_item_count INT NOT NULL DEFAULT 0,
  change_analysis_json CLOB NOT NULL,
  risk_card_json CLOB NOT NULL,
  summary VARCHAR(1024) NULL,
  created_at TIMESTAMP(3) NULL,
  updated_at TIMESTAMP(3) NULL
);

CREATE TABLE rule_templates (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  template_code VARCHAR(64) NOT NULL,
  template_name VARCHAR(128) NOT NULL,
  target_type VARCHAR(32) NOT NULL,
  version INT NOT NULL DEFAULT 1,
  enabled_rule_codes CLOB NOT NULL,
  config_json CLOB NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ENABLED',
  description VARCHAR(512) NULL,
  created_at TIMESTAMP(3) NULL,
  updated_at TIMESTAMP(3) NULL,
  UNIQUE (template_code, version)
);

CREATE TABLE notification_records (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  result_id BIGINT NULL,
  channel VARCHAR(32) NOT NULL,
  target VARCHAR(512) NULL,
  status VARCHAR(32) NOT NULL,
  request_digest VARCHAR(1024) NULL,
  response_body CLOB NULL,
  error_message VARCHAR(1024) NULL,
  sent_at TIMESTAMP(3) NULL,
  created_at TIMESTAMP(3) NULL,
  updated_at TIMESTAMP(3) NULL
);

CREATE TABLE gitlab_mr_webhook_events (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  git_project_id VARCHAR(128) NOT NULL,
  project_name VARCHAR(128) NOT NULL,
  mr_id VARCHAR(128) NOT NULL,
  event_action VARCHAR(64) NULL,
  event_time TIMESTAMP(3) NOT NULL,
  source_branch VARCHAR(255) NULL,
  target_branch VARCHAR(255) NULL,
  author_name VARCHAR(128) NULL,
  author_username VARCHAR(128) NULL,
  changed_files_summary CLOB NOT NULL,
  raw_payload CLOB NOT NULL,
  created_at TIMESTAMP(3) NULL,
  updated_at TIMESTAMP(3) NULL
);

CREATE TABLE gitlab_push_webhook_events (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  git_project_id VARCHAR(128) NOT NULL,
  project_name VARCHAR(128) NOT NULL,
  ref VARCHAR(255) NULL,
  branch_name VARCHAR(255) NULL,
  before_sha VARCHAR(128) NULL,
  after_sha VARCHAR(128) NOT NULL,
  event_time TIMESTAMP(3) NOT NULL,
  author_name VARCHAR(128) NULL,
  author_username VARCHAR(128) NULL,
  changed_files_summary CLOB NOT NULL,
  raw_payload CLOB NOT NULL,
  created_at TIMESTAMP(3) NULL,
  updated_at TIMESTAMP(3) NULL
);

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
  'Backend default review template',
  'BACKEND',
  1,
  '["API_COMPATIBILITY_CHECK","DB_SCHEMA_CHANGE_CHECK","DB_SQL_CHANGE_CHECK","ORM_MAPPING_CHANGE_CHECK","ENTITY_MODEL_CHANGE_CHECK","DATA_MIGRATION_CHECK","DB_SCHEMA_SYNC_SUSPECT_CHECK","CACHE_KEY_CHANGE_CHECK","CACHE_TTL_CHANGE_CHECK","CACHE_INVALIDATION_CHANGE_CHECK","CACHE_READ_WRITE_CHANGE_CHECK","CACHE_SERIALIZATION_CHANGE_CHECK","MQ_PRODUCER_CHANGE_CHECK","MQ_CONSUMER_CHANGE_CHECK","MQ_MESSAGE_SCHEMA_CHANGE_CHECK","MQ_TOPIC_CONFIG_CHANGE_CHECK","MQ_RETRY_DLQ_CHANGE_CHECK","CONFIG_RELEASE_CHECK"]',
  '{"focusChangeTypes":["DB_SCHEMA","DATA_MIGRATION","ENTITY_MODEL"],"recommendedChecks":["Check focused database changes","Confirm rollback and monitoring"]}',
  'ENABLED',
  'Test backend template'
);
