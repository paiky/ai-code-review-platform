UPDATE rule_templates
SET enabled_rule_codes = JSON_ARRAY(
      'API_COMPATIBILITY_CHECK',
      'DB_SCHEMA_CHANGE_CHECK',
      'DB_SQL_CHANGE_CHECK',
      'ORM_MAPPING_CHANGE_CHECK',
      'ENTITY_MODEL_CHANGE_CHECK',
      'DATA_MIGRATION_CHECK',
      'DB_SCHEMA_SYNC_SUSPECT_CHECK',
      'CACHE_CONSISTENCY_CHECK',
      'MQ_IDEMPOTENCY_CHECK',
      'CONFIG_RELEASE_CHECK'
    ),
    config_json = JSON_SET(
      COALESCE(config_json, JSON_OBJECT()),
      '$.focusChangeTypes',
      JSON_ARRAY('API', 'DB', 'DB_SCHEMA', 'DB_SQL', 'ORM_MAPPING', 'ENTITY_MODEL', 'DATA_MIGRATION', 'CACHE', 'MQ', 'CONFIG')
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE template_code = 'backend-default' AND version = 1;

UPDATE rule_templates
SET enabled_rule_codes = JSON_ARRAY(
      'API_COMPATIBILITY_CHECK',
      'DB_SCHEMA_CHANGE_CHECK',
      'DB_SQL_CHANGE_CHECK',
      'ORM_MAPPING_CHANGE_CHECK',
      'ENTITY_MODEL_CHANGE_CHECK',
      'DATA_MIGRATION_CHECK',
      'DB_SCHEMA_SYNC_SUSPECT_CHECK',
      'CONFIG_RELEASE_CHECK'
    ),
    config_json = JSON_SET(
      COALESCE(config_json, JSON_OBJECT()),
      '$.focusChangeTypes',
      JSON_ARRAY('API', 'DB', 'DB_SCHEMA', 'DB_SQL', 'ORM_MAPPING', 'ENTITY_MODEL', 'DATA_MIGRATION', 'CONFIG')
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE template_code = 'general-default' AND version = 1;
