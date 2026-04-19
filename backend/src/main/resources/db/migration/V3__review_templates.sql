INSERT INTO rule_templates (
  template_code,
  template_name,
  target_type,
  version,
  enabled_rule_codes,
  config_json,
  status,
  description
) VALUES
(
  'frontend-default',
  '前端默认审查模板',
  'FRONTEND',
  1,
  JSON_ARRAY('API_COMPATIBILITY_CHECK', 'CONFIG_RELEASE_CHECK'),
  JSON_OBJECT(
    'focusChangeTypes', JSON_ARRAY('API', 'CONFIG'),
    'defaultRiskLevel', 'LOW',
    'recommendedChecks', JSON_ARRAY(
      '确认 API 调用参数、响应字段与后端契约一致。',
      '确认路由、权限、环境变量和构建配置变更已覆盖测试。',
      '确认核心页面和异常状态有基础回归。'
    )
  ),
  'ENABLED',
  'MVP 前端默认审查模板，关注接口调用兼容与配置变更。'
),
(
  'general-default',
  '通用默认审查模板',
  'GENERAL',
  1,
  JSON_ARRAY('API_COMPATIBILITY_CHECK', 'DB_CHANGE_CHECK', 'CONFIG_RELEASE_CHECK'),
  JSON_OBJECT(
    'focusChangeTypes', JSON_ARRAY('API', 'DB', 'CONFIG'),
    'defaultRiskLevel', 'LOW',
    'recommendedChecks', JSON_ARRAY(
      '确认本次变更影响范围已被说明。',
      '确认关键路径已有回归用例。',
      '确认发布、回滚和监控安排清晰。'
    )
  ),
  'ENABLED',
  'MVP 通用默认审查模板，适用于未明确技术栈的变更。'
)
ON DUPLICATE KEY UPDATE
  template_name = VALUES(template_name),
  target_type = VALUES(target_type),
  enabled_rule_codes = VALUES(enabled_rule_codes),
  config_json = VALUES(config_json),
  status = VALUES(status),
  description = VALUES(description),
  updated_at = CURRENT_TIMESTAMP(3);

UPDATE rule_templates
SET config_json = JSON_SET(
  COALESCE(config_json, JSON_OBJECT()),
  '$.recommendedChecks',
  JSON_ARRAY(
    '确认接口、数据库、缓存、MQ、配置变更已按风险项逐一检查。',
    '确认高风险改动已有回滚方案和监控告警。',
    '确认测试覆盖核心链路和异常场景。'
  )
)
WHERE template_code = 'backend-default' AND version = 1;