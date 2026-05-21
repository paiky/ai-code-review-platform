ALTER TABLE code_quality_review_profiles
  ADD COLUMN push_min_changed_files INT NULL DEFAULT 10 AFTER push_branch_patterns,
  ADD COLUMN push_min_diff_bytes INT NULL DEFAULT 30000 AFTER push_min_changed_files,
  ADD COLUMN push_min_commit_count INT NULL DEFAULT 3 AFTER push_min_diff_bytes;

UPDATE code_quality_review_profiles
SET
  push_branch_patterns = JSON_ARRAY('develop', 'feature/*', 'bugfix/*', 'hotfix/*'),
  push_min_changed_files = 10,
  push_min_diff_bytes = 30000,
  push_min_commit_count = 3,
  push_max_changed_files = 80,
  push_max_diff_bytes = 300000,
  push_debounce_seconds = 300,
  trigger_only_when_risk_matched = FALSE
WHERE profile_code = 'backend-default-ai-review';

CREATE TABLE code_quality_push_review_gate_decisions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  project_id BIGINT NOT NULL,
  branch_name VARCHAR(255) NULL,
  profile_code VARCHAR(64) NULL,
  provider VARCHAR(64) NULL,
  decision VARCHAR(32) NOT NULL,
  ai_review_scheduled BOOLEAN NOT NULL DEFAULT FALSE,
  reason_code VARCHAR(64) NOT NULL,
  reason_summary VARCHAR(512) NOT NULL,
  metrics_json JSON NOT NULL,
  matched_rules_json JSON NOT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_push_gate_task (task_id),
  KEY idx_push_gate_project_branch_created (project_id, branch_name, created_at),
  KEY idx_push_gate_decision_created (decision, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
