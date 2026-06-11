CREATE TABLE IF NOT EXISTS project_review_policies (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  policy_type VARCHAR(64) NOT NULL,
  risk_type VARCHAR(64) NULL,
  title VARCHAR(255) NOT NULL,
  content TEXT NOT NULL,
  source_feedback_id BIGINT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  version INT NOT NULL DEFAULT 1,
  created_by VARCHAR(128) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  KEY idx_project_review_policies_project_enabled (project_id, enabled),
  KEY idx_project_review_policies_project_risk_type (project_id, risk_type),
  KEY idx_project_review_policies_source_feedback (source_feedback_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
