CREATE TABLE code_quality_fix_previews (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_id BIGINT NOT NULL,
    project_id BIGINT NOT NULL,
    finding_index INT NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    status VARCHAR(32) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(128) NULL,
    summary VARCHAR(1024) NULL,
    patch_text TEXT NULL,
    warnings_json TEXT NOT NULL,
    error_message VARCHAR(1024) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_code_quality_fix_preview_task_finding (task_id, finding_index)
);
