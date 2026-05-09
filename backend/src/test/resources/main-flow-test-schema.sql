DROP TABLE IF EXISTS gitlab_mr_webhook_events;
DROP TABLE IF EXISTS code_quality_review_progress_events;
DROP TABLE IF EXISTS code_quality_review_results;
DROP TABLE IF EXISTS code_quality_review_profiles;
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
  default_code_quality_profile_code VARCHAR(64) NOT NULL DEFAULT 'backend-default-ai-review',
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

CREATE TABLE code_quality_review_profiles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  profile_code VARCHAR(64) NOT NULL UNIQUE,
  profile_name VARCHAR(128) NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  provider VARCHAR(32) NOT NULL DEFAULT 'CODEX_CLI',
  model VARCHAR(128) NULL,
  trigger_on_manual BOOLEAN NOT NULL DEFAULT TRUE,
  trigger_on_mr BOOLEAN NOT NULL DEFAULT TRUE,
  trigger_on_push BOOLEAN NOT NULL DEFAULT FALSE,
  severity_threshold VARCHAR(32) NOT NULL DEFAULT 'MAJOR',
  block_on_severities CLOB NOT NULL,
  enabled_categories CLOB NOT NULL,
  ignored_paths CLOB NOT NULL,
  push_branch_patterns CLOB NOT NULL,
  push_max_changed_files INT NULL,
  push_max_diff_bytes INT NULL,
  push_debounce_seconds INT NULL,
  trigger_only_when_risk_matched BOOLEAN NOT NULL DEFAULT TRUE,
  codex_prompt CLOB NULL,
  openai_instructions CLOB NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ENABLED',
  description VARCHAR(512) NULL,
  created_at TIMESTAMP(3) NULL,
  updated_at TIMESTAMP(3) NULL
);

CREATE TABLE code_quality_review_results (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL UNIQUE,
  project_id BIGINT NOT NULL,
  profile_code VARCHAR(64) NOT NULL,
  provider VARCHAR(32) NOT NULL,
  model VARCHAR(128) NULL,
  status VARCHAR(32) NOT NULL,
  overall_level VARCHAR(32) NULL,
  summary CLOB NULL,
  finding_count INT NOT NULL DEFAULT 0,
  findings_json CLOB NOT NULL,
  raw_output CLOB NULL,
  exit_code INT NULL,
  error_message VARCHAR(1024) NULL,
  started_at TIMESTAMP(3) NULL,
  finished_at TIMESTAMP(3) NULL,
  created_at TIMESTAMP(3) NULL,
  updated_at TIMESTAMP(3) NULL
);

CREATE TABLE code_quality_review_settings (
  id BIGINT PRIMARY KEY,
  mr_auto_review_enabled BOOLEAN NOT NULL DEFAULT TRUE,
  review_provider VARCHAR(32) NOT NULL DEFAULT 'CODEX_CLI',
  openai_api_key VARCHAR(1024) NULL,
  anthropic_api_key VARCHAR(1024) NULL,
  created_at TIMESTAMP(3) NULL,
  updated_at TIMESTAMP(3) NULL
);

CREATE TABLE code_quality_review_progress_events (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  phase VARCHAR(64) NOT NULL,
  level VARCHAR(32) NOT NULL DEFAULT 'INFO',
  message VARCHAR(512) NOT NULL,
  detail CLOB NULL,
  created_at TIMESTAMP(3) NULL
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
  '["DB_SCHEMA_CHANGE_CHECK","DB_SQL_CHANGE_CHECK","ORM_MAPPING_CHANGE_CHECK","ENTITY_MODEL_CHANGE_CHECK","DATA_MIGRATION_CHECK","DB_SCHEMA_SYNC_SUSPECT_CHECK","CACHE_KEY_CHANGE_CHECK","CACHE_TTL_CHANGE_CHECK","CACHE_INVALIDATION_CHANGE_CHECK","CACHE_READ_WRITE_CHANGE_CHECK","CACHE_SERIALIZATION_CHANGE_CHECK","MQ_PRODUCER_CHANGE_CHECK","MQ_CONSUMER_CHANGE_CHECK","MQ_MESSAGE_SCHEMA_CHANGE_CHECK","MQ_TOPIC_CONFIG_CHANGE_CHECK","MQ_RETRY_DLQ_CHANGE_CHECK","CONFIG_RELEASE_CHECK"]',
  '{"focusChangeTypes":["DB_SCHEMA","DATA_MIGRATION","ENTITY_MODEL"],"recommendedChecks":["Check focused database changes","Confirm rollback and monitoring"]}',
  'ENABLED',
  'Test backend template'
);

INSERT INTO code_quality_review_profiles (
  profile_code,
  profile_name,
  enabled,
  provider,
  model,
  trigger_on_manual,
  trigger_on_mr,
  trigger_on_push,
  severity_threshold,
  block_on_severities,
  enabled_categories,
  ignored_paths,
  push_branch_patterns,
  push_max_changed_files,
  push_max_diff_bytes,
  push_debounce_seconds,
  trigger_only_when_risk_matched,
  codex_prompt,
  openai_instructions,
  status,
  description
) VALUES (
  'backend-default-ai-review',
  'Backend default AI code review',
  TRUE,
  'CODEX_CLI',
  NULL,
  TRUE,
  TRUE,
  FALSE,
  'MAJOR',
  '["CRITICAL"]',
  '["CORRECTNESS","SECURITY","TRANSACTION","SQL_PERFORMANCE","CACHE_CONSISTENCY","MQ_CONSISTENCY","EXCEPTION_HANDLING","TEST_GAP"]',
  '["**/generated/**","**/target/**","**/dist/**"]',
  '["main","develop","release/*"]',
  30,
  200000,
  300,
  TRUE,
  'Only report actionable code quality issues.',
  'Review only the supplied diff and return strict JSON.',
  'ENABLED',
  'Default backend AI code quality review profile.'
);

INSERT INTO code_quality_review_settings (
  id,
  mr_auto_review_enabled
) VALUES (
  1,
  TRUE
);
