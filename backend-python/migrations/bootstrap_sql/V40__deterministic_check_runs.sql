CREATE TABLE IF NOT EXISTS deterministic_check_runs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  project_id BIGINT NOT NULL,
  check_type VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  config_snapshot_json JSON NOT NULL,
  result_summary_json JSON NULL,
  findings_json JSON NULL,
  duration_ms BIGINT NULL,
  failure_reason VARCHAR(1024) NULL,
  started_at DATETIME(3) NULL,
  finished_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  KEY idx_deterministic_check_runs_task_type_created (task_id, check_type, created_at),
  KEY idx_deterministic_check_runs_project_created (project_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
