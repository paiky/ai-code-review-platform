UPDATE rule_templates
SET enabled_rule_codes = JSON_ARRAY(
      'DB_DATA_WRITE_CHANGE_CHECK',
      'CACHE_WRITE_DELETE_CHANGE_CHECK',
      'MQ_CONFIG_CHANGE_CHECK',
      'CONFIG_RELEASE_CHECK'
    ),
    config_json = JSON_SET(
      COALESCE(config_json, JSON_OBJECT()),
      '$.focusRuleCodes',
      JSON_ARRAY(
        'DB_DATA_WRITE_CHANGE_CHECK',
        'CACHE_WRITE_DELETE_CHANGE_CHECK',
        'MQ_CONFIG_CHANGE_CHECK',
        'CONFIG_RELEASE_CHECK'
      ),
      '$.focusChangeTypes',
      JSON_ARRAY('DB_DATA_WRITE', 'CACHE_WRITE_DELETE', 'MQ_CONFIG', 'CONFIG')
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE template_code = 'backend-default' AND version = 1;

UPDATE rule_templates
SET enabled_rule_codes = JSON_ARRAY(
      'DB_DATA_WRITE_CHANGE_CHECK',
      'CONFIG_RELEASE_CHECK'
    ),
    config_json = JSON_SET(
      COALESCE(config_json, JSON_OBJECT()),
      '$.focusRuleCodes',
      JSON_ARRAY('DB_DATA_WRITE_CHANGE_CHECK', 'CONFIG_RELEASE_CHECK'),
      '$.focusChangeTypes',
      JSON_ARRAY('DB_DATA_WRITE', 'CONFIG')
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE template_code = 'general-default' AND version = 1;
