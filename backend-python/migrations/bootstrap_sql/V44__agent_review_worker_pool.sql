CREATE TABLE IF NOT EXISTS code_quality_agent_workers (
  worker_id VARCHAR(128) PRIMARY KEY,
  worker_version VARCHAR(64) NULL,
  cli_version VARCHAR(64) NULL,
  state VARCHAR(16) NOT NULL DEFAULT 'IDLE',
  capacity INT NOT NULL DEFAULT 1,
  active_job_id BIGINT NULL,
  active_run_id BIGINT NULL,
  started_at DATETIME(3) NOT NULL,
  last_heartbeat_at DATETIME(3) NOT NULL,
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  KEY idx_code_quality_agent_workers_heartbeat (last_heartbeat_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
