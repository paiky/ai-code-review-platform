CREATE TABLE IF NOT EXISTS project_groups (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  group_name VARCHAR(128) NOT NULL,
  group_code VARCHAR(64) NULL,
  default_provider_code VARCHAR(64) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ENABLED',
  description VARCHAR(512) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_project_group_code (group_code),
  KEY idx_project_group_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO project_groups (group_name, group_code, status, description)
VALUES ('默认项目组', 'default', 'ENABLED', '系统默认项目组')
ON DUPLICATE KEY UPDATE
  group_name = VALUES(group_name),
  status = VALUES(status),
  description = VALUES(description),
  updated_at = CURRENT_TIMESTAMP(3);

ALTER TABLE projects
  ADD COLUMN group_id BIGINT NULL AFTER id,
  ADD COLUMN supported_target_types JSON NULL AFTER repository_url,
  ADD COLUMN detected_target_types JSON NULL AFTER supported_target_types,
  ADD COLUMN target_detection_json JSON NULL AFTER detected_target_types;

UPDATE projects
SET group_id = (SELECT id FROM project_groups WHERE group_code = 'default' LIMIT 1)
WHERE group_id IS NULL;

UPDATE projects
SET supported_target_types = JSON_ARRAY('BACKEND')
WHERE supported_target_types IS NULL;

CREATE TABLE IF NOT EXISTS project_target_configs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  target_type VARCHAR(32) NOT NULL,
  template_code VARCHAR(64) NOT NULL,
  code_quality_profile_code VARCHAR(64) NULL,
  provider_code VARCHAR(64) NULL,
  path_patterns JSON NOT NULL,
  reminder_card_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  description VARCHAR(512) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_project_target_config (project_id, target_type),
  KEY idx_project_target_type (target_type),
  KEY idx_project_target_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO project_target_configs (
  project_id,
  target_type,
  template_code,
  code_quality_profile_code,
  provider_code,
  path_patterns,
  reminder_card_enabled,
  enabled,
  description
)
SELECT
  id,
  'BACKEND',
  default_template_code,
  default_code_quality_profile_code,
  default_code_quality_provider_code,
  JSON_ARRAY('backend-python/**', 'backend/**', 'src/main/**', 'src/test/**', 'pom.xml', 'requirements*.txt'),
  TRUE,
  TRUE,
  '默认后端端类型配置'
FROM projects
ON DUPLICATE KEY UPDATE
  template_code = VALUES(template_code),
  code_quality_profile_code = VALUES(code_quality_profile_code),
  provider_code = VALUES(provider_code),
  updated_at = CURRENT_TIMESTAMP(3);

ALTER TABLE review_tasks
  ADD COLUMN target_type VARCHAR(32) NULL AFTER template_code,
  ADD COLUMN target_types_json JSON NULL AFTER target_type,
  ADD COLUMN code_quality_profile_code VARCHAR(64) NULL AFTER target_types_json;

UPDATE review_tasks
SET target_type = 'BACKEND',
    target_types_json = JSON_ARRAY('BACKEND'),
    code_quality_profile_code = 'backend-default-ai-review'
WHERE target_type IS NULL;

ALTER TABLE review_results
  ADD COLUMN target_type VARCHAR(32) NULL AFTER template_code,
  ADD COLUMN reminder_card_enabled BOOLEAN NULL AFTER target_type;

UPDATE review_results
SET target_type = 'BACKEND',
    reminder_card_enabled = TRUE
WHERE target_type IS NULL;
