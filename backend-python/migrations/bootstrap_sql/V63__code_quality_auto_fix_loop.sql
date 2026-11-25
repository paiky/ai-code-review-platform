CREATE TABLE IF NOT EXISTS code_quality_auto_fix_settings (
    id INT NOT NULL PRIMARY KEY,
    enabled BOOLEAN NOT NULL,
    enabled_at DATETIME(6) NULL,
    updated_at DATETIME(6) NOT NULL,
    updated_by VARCHAR(128) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO code_quality_auto_fix_settings (id, enabled, updated_at, updated_by)
VALUES (1, FALSE, CURRENT_TIMESTAMP, 'migration')
ON DUPLICATE KEY UPDATE id = id;

CREATE TABLE IF NOT EXISTS code_quality_fix_runs (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    project_id BIGINT NOT NULL,
    source_task_id BIGINT NOT NULL,
    source_mr_iid VARCHAR(32) NOT NULL,
    source_review_key VARCHAR(64) NOT NULL,
    source_review_version VARCHAR(128) NOT NULL,
    inputs_json MEDIUMTEXT NOT NULL,
    enabled_at DATETIME(6) NOT NULL,
    base_sha VARCHAR(64) NOT NULL,
    developer_sha VARCHAR(64) NOT NULL,
    developer_branch VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
    active_slot INT NULL,
    status VARCHAR(24) NOT NULL,
    step VARCHAR(24) NULL,
    reason_code VARCHAR(64) NULL,
    reason VARCHAR(512) NULL,
    cancel_requested_at DATETIME NULL,
    mr_iid VARCHAR(32) NULL,
    mr_url VARCHAR(1024) NULL,
    project_url VARCHAR(1024) NULL,
    merge_sha VARCHAR(64) NULL,
    merged_at DATETIME NULL,
    notification_json TEXT NULL,
    lease_token VARCHAR(36) NULL,
    lease_until DATETIME NULL,
    next_at DATETIME NOT NULL,
    failures INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_fix_run_mr_sha (project_id, source_mr_iid, developer_sha),
    UNIQUE KEY uk_fix_run_active_branch (project_id, developer_branch, active_slot),
    KEY idx_fix_run_task_review (source_task_id, source_review_key, id),
    KEY idx_fix_run_due (status, next_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS code_quality_fix_rounds (
    run_id BIGINT NOT NULL,
    number INT NOT NULL,
    input_sha VARCHAR(64) NOT NULL,
    commit_sha VARCHAR(64) NULL,
    pushed BOOLEAN NOT NULL DEFAULT FALSE,
    review_task_id BIGINT NULL UNIQUE,
    review_key VARCHAR(64) NULL,
    review_version VARCHAR(128) NULL,
    critical_count INT NULL,
    findings_json MEDIUMTEXT NULL,
    created_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    PRIMARY KEY (run_id, number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
