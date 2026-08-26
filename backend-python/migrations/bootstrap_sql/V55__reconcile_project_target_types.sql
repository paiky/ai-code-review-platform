UPDATE project_target_configs AS config
JOIN (
  SELECT candidate.project_id, candidate.selected_config_id
  FROM (
    SELECT
      project_id,
      MAX(
        CASE
          WHEN COALESCE(description, '') NOT IN (
            '默认后端端类型配置',
            '自动识别创建的端类型配置',
            '路径映射创建的端类型配置',
            '恢复自动识别的端类型配置',
            '单端类型默认配置'
          ) THEN id
          ELSE NULL
        END
      ) AS selected_config_id,
      SUM(
        CASE
          WHEN COALESCE(description, '') NOT IN (
            '默认后端端类型配置',
            '自动识别创建的端类型配置',
            '路径映射创建的端类型配置',
            '恢复自动识别的端类型配置',
            '单端类型默认配置'
          ) THEN 1
          ELSE 0
        END
      ) AS manual_config_count,
      COUNT(*) AS enabled_config_count
    FROM project_target_configs
    WHERE enabled = TRUE
    GROUP BY project_id
  ) AS candidate
  WHERE candidate.manual_config_count = 1
    AND candidate.enabled_config_count > 1
) AS resolved
  ON resolved.project_id = config.project_id
SET
  config.enabled = (config.id = resolved.selected_config_id),
  config.updated_at = CURRENT_TIMESTAMP(3)
WHERE config.enabled = TRUE;

UPDATE projects AS project
JOIN project_target_configs AS config
  ON config.project_id = project.id
 AND config.enabled = TRUE
SET
  project.target_type = config.target_type,
  project.supported_target_types = JSON_ARRAY(config.target_type),
  project.default_template_code = config.template_code,
  project.default_code_quality_profile_code = config.code_quality_profile_code,
  project.default_code_quality_provider_code = config.provider_code,
  project.updated_at = CURRENT_TIMESTAMP(3);
