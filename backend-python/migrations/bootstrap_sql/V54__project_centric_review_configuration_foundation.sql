ALTER TABLE projects
  ADD COLUMN target_type VARCHAR(32) NULL AFTER git_project_id;

ALTER TABLE projects
  ADD INDEX idx_projects_target_type_status (target_type, status);

ALTER TABLE notification_webhooks
  ADD COLUMN project_group_id BIGINT NULL;

ALTER TABLE notification_webhooks
  ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE notification_webhooks
  ADD COLUMN description VARCHAR(512) NULL;

ALTER TABLE notification_webhooks
  ADD COLUMN last_test_status VARCHAR(32) NOT NULL DEFAULT 'UNTESTED';

ALTER TABLE notification_webhooks
  ADD COLUMN last_test_at DATETIME(3) NULL;

ALTER TABLE notification_webhooks
  ADD COLUMN last_test_message VARCHAR(1024) NULL;

CREATE TABLE IF NOT EXISTS project_review_settings (
  project_id BIGINT NOT NULL,
  trigger_on_mr BOOLEAN NOT NULL DEFAULT TRUE,
  trigger_on_push BOOLEAN NOT NULL DEFAULT FALSE,
  trigger_only_when_risk_matched BOOLEAN NOT NULL DEFAULT FALSE,
  auto_fix_preview_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  auto_fix_preview_severities JSON NULL,
  push_branch_patterns JSON NULL,
  push_min_changed_files INT NULL DEFAULT 10,
  push_min_diff_bytes INT NULL DEFAULT 30000,
  push_min_commit_count INT NULL DEFAULT 3,
  push_max_changed_files INT NULL DEFAULT -1,
  push_max_diff_bytes INT NULL DEFAULT -1,
  push_debounce_seconds INT NULL DEFAULT 300,
  created_at DATETIME(3) NOT NULL,
  updated_at DATETIME(3) NOT NULL,
  PRIMARY KEY (project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS project_ai_review_models (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  review_key VARCHAR(64) NOT NULL,
  provider_code VARCHAR(64) NOT NULL,
  model_name VARCHAR(128) NULL,
  display_name VARCHAR(128) NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order INT NOT NULL DEFAULT 0,
  created_at DATETIME(3) NOT NULL,
  updated_at DATETIME(3) NOT NULL,
  UNIQUE KEY uk_project_ai_review_model_key (project_id, review_key),
  KEY idx_project_ai_review_models_project (project_id, enabled, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS project_notification_webhooks (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  webhook_id BIGINT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME(3) NOT NULL,
  updated_at DATETIME(3) NOT NULL,
  UNIQUE KEY uk_project_notification_webhook (project_id, webhook_id),
  KEY idx_project_notification_webhooks_project (project_id, enabled),
  KEY idx_project_notification_webhooks_webhook (webhook_id, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
