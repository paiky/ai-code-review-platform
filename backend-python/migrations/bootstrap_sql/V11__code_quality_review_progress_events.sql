CREATE TABLE code_quality_review_progress_events (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  phase VARCHAR(64) NOT NULL,
  level VARCHAR(32) NOT NULL DEFAULT 'INFO',
  message VARCHAR(512) NOT NULL,
  detail TEXT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  KEY idx_task_created (task_id, created_at),
  KEY idx_task_id (task_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
