CREATE TABLE code_quality_scheduler_jobs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    job_type VARCHAR(32) NOT NULL,
    task_id BIGINT NOT NULL,
    project_id BIGINT NULL,
    finding_index INT NULL,
    status VARCHAR(32) NOT NULL,
    priority INT NOT NULL,
    label VARCHAR(255) NULL,
    file_path VARCHAR(512) NULL,
    error_message VARCHAR(1024) NULL,
    queued_at DATETIME NULL,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_code_quality_scheduler_jobs_status_priority (status, priority, queued_at),
    INDEX idx_code_quality_scheduler_jobs_task (task_id, job_type)
);
