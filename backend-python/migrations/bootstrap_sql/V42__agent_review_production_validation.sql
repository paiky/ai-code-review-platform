CREATE TABLE IF NOT EXISTS code_quality_agent_settings (
  id BIGINT PRIMARY KEY,
  enabled BOOLEAN NOT NULL DEFAULT FALSE,
  api_key_ciphertext TEXT NULL,
  api_key_fingerprint VARCHAR(32) NULL,
  worker_id VARCHAR(128) NULL,
  worker_version VARCHAR(64) NULL,
  cli_version VARCHAR(64) NULL,
  last_worker_heartbeat_at DATETIME(3) NULL,
  test_request_id VARCHAR(128) NULL,
  test_status VARCHAR(32) NULL,
  test_message VARCHAR(512) NULL,
  test_duration_ms BIGINT NULL,
  test_started_at DATETIME(3) NULL,
  test_finished_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO code_quality_agent_settings (id, enabled)
SELECT 1, FALSE
WHERE NOT EXISTS (SELECT 1 FROM code_quality_agent_settings WHERE id = 1);

CREATE TABLE IF NOT EXISTS agent_review_runs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  review_key VARCHAR(64) NOT NULL,
  scheduler_job_id BIGINT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  requested_engine VARCHAR(32) NOT NULL DEFAULT 'AGENT',
  effective_engine VARCHAR(32) NULL,
  runner_version VARCHAR(64) NOT NULL DEFAULT 'agent-worker-v1',
  cli_version VARCHAR(64) NULL,
  model VARCHAR(128) NOT NULL DEFAULT 'deepseek-v4-pro[1m]',
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
  session_id VARCHAR(128) NULL,
  turn_count INT NOT NULL DEFAULT 0,
  tool_call_count INT NOT NULL DEFAULT 0,
  source_bytes_returned BIGINT NOT NULL DEFAULT 0,
  diff_bytes_returned BIGINT NOT NULL DEFAULT 0,
  duration_ms BIGINT NULL,
  usage_json JSON NULL,
  tool_summary_json JSON NULL,
  input_json LONGTEXT NULL,
  completion_context_json JSON NULL,
  comparison_mode BOOLEAN NOT NULL DEFAULT FALSE,
  failure_code VARCHAR(64) NULL,
  failure_message VARCHAR(1024) NULL,
  heartbeat_at DATETIME(3) NULL,
  started_at DATETIME(3) NULL,
  finished_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_agent_review_run_idempotency (idempotency_key),
  KEY idx_agent_review_runs_task_created (task_id, created_at),
  KEY idx_agent_review_runs_status_heartbeat (status, heartbeat_at),
  KEY idx_agent_review_runs_scheduler_job (scheduler_job_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE project_groups
  ADD COLUMN review_engine VARCHAR(32) NOT NULL DEFAULT 'STANDARD' AFTER default_provider_code,
  ADD COLUMN agent_source_export_allowed BOOLEAN NOT NULL DEFAULT FALSE AFTER review_engine;

ALTER TABLE code_quality_review_results
  ADD COLUMN requested_engine VARCHAR(32) NOT NULL DEFAULT 'STANDARD' AFTER error_message,
  ADD COLUMN effective_engine VARCHAR(32) NOT NULL DEFAULT 'STANDARD' AFTER requested_engine,
  ADD COLUMN agent_run_id BIGINT NULL AFTER effective_engine,
  ADD COLUMN agent_summary_json JSON NULL AFTER agent_run_id;

ALTER TABLE code_quality_scheduler_jobs
  ADD COLUMN lease_owner VARCHAR(128) NULL AFTER error_message,
  ADD COLUMN lease_expires_at DATETIME(3) NULL AFTER lease_owner,
  ADD COLUMN heartbeat_at DATETIME(3) NULL AFTER lease_expires_at,
  ADD COLUMN attempt INT NOT NULL DEFAULT 0 AFTER heartbeat_at,
  ADD COLUMN max_attempts INT NOT NULL DEFAULT 2 AFTER attempt,
  ADD COLUMN cancel_requested_at DATETIME(3) NULL AFTER max_attempts,
  ADD COLUMN idempotency_key VARCHAR(128) NULL AFTER cancel_requested_at,
  ADD KEY idx_code_quality_scheduler_jobs_agent_claim (job_type, status, lease_expires_at),
  ADD UNIQUE KEY uk_code_quality_scheduler_jobs_idempotency (idempotency_key);
