ALTER TABLE project_groups
  ADD COLUMN default_code_quality_profile_code VARCHAR(64) NULL AFTER group_code;

UPDATE project_groups
SET group_name = '默认通用项目组'
WHERE group_code = 'default' AND group_name = '默认项目组';

CREATE TABLE IF NOT EXISTS target_type_path_mappings (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  target_type VARCHAR(32) NOT NULL,
  path_patterns JSON NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order INT NOT NULL DEFAULT 0,
  description VARCHAR(512) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_target_type_path_mapping (target_type),
  KEY idx_target_type_path_mapping_enabled (enabled, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO target_type_path_mappings (
  target_type,
  path_patterns,
  enabled,
  sort_order,
  description
)
VALUES
  ('APP_IOS', JSON_ARRAY('ios/**', '**/*.swift', '**/*.m', '**/*.mm', 'Podfile'), TRUE, 10, '系统默认端类型路径映射'),
  ('APP_ANDROID', JSON_ARRAY('android/**', '**/*.kt', '**/*.kts', 'build.gradle', 'settings.gradle', '**/*.gradle'), TRUE, 20, '系统默认端类型路径映射'),
  ('WEB_PC', JSON_ARRAY('frontend/**', 'web/**', 'src/**/*.tsx', 'src/**/*.jsx', 'src/**/*.vue', 'package.json'), TRUE, 30, '系统默认端类型路径映射'),
  ('BACKEND', JSON_ARRAY('src/main/java/**', 'src/main/resources/**', 'src/*.java', 'src/**/*.java', 'pom.xml', 'backend-python/**', 'backend/**'), TRUE, 40, '系统默认端类型路径映射')
ON DUPLICATE KEY UPDATE
  path_patterns = VALUES(path_patterns),
  enabled = VALUES(enabled),
  sort_order = VALUES(sort_order),
  description = VALUES(description),
  updated_at = CURRENT_TIMESTAMP(3);
