CREATE TABLE IF NOT EXISTS review_quality_governance_runs (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    project_id BIGINT NOT NULL,
    report_id BIGINT NOT NULL,
    issue_id BIGINT NULL,
    evidence_key VARCHAR(64) NOT NULL,
    source VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    input_json JSON NOT NULL,
    result_json JSON NOT NULL,
    model_calls INT NOT NULL DEFAULT 0,
    attempt INT NOT NULL DEFAULT 0,
    lease_owner VARCHAR(64) NULL,
    lease_until DATETIME(6) NULL,
    error_code VARCHAR(64) NULL,
    available_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NULL,
    UNIQUE KEY uk_quality_governance_evidence (project_id, evidence_key),
    KEY idx_quality_governance_claim (status, available_at, id),
    KEY idx_quality_governance_lease (status, lease_until, id),
    KEY idx_quality_governance_report (project_id, report_id, id),
    KEY idx_quality_governance_issue (project_id, issue_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS review_quality_governance_controls (
    issue_id BIGINT NOT NULL PRIMARY KEY,
    revision INT NOT NULL DEFAULT 0,
    paused TINYINT(1) NOT NULL DEFAULT 0,
    priority VARCHAR(16) NULL,
    conclusion VARCHAR(1000) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS review_quality_governance_events (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    kind VARCHAR(32) NOT NULL,
    details JSON NOT NULL,
    created_at DATETIME(6) NOT NULL,
    KEY idx_quality_governance_event (run_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
