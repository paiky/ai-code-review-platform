UPDATE rule_templates
SET config_json = JSON_SET(
      COALESCE(config_json, JSON_OBJECT()),
      '$.focusChangeTypes',
      JSON_ARRAY('DB_SCHEMA', 'DATA_MIGRATION', 'ENTITY_MODEL')
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE template_code = 'backend-default' AND version = 1;
