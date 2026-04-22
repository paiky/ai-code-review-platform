UPDATE rule_templates
SET enabled_rule_codes = JSON_ARRAY(
      'API_COMPATIBILITY_CHECK',
      'DB_SCHEMA_CHANGE_CHECK',
      'DB_SQL_CHANGE_CHECK',
      'ORM_MAPPING_CHANGE_CHECK',
      'ENTITY_MODEL_CHANGE_CHECK',
      'DATA_MIGRATION_CHECK',
      'DB_SCHEMA_SYNC_SUSPECT_CHECK',
      'CACHE_KEY_CHANGE_CHECK',
      'CACHE_TTL_CHANGE_CHECK',
      'CACHE_INVALIDATION_CHANGE_CHECK',
      'CACHE_READ_WRITE_CHANGE_CHECK',
      'CACHE_SERIALIZATION_CHANGE_CHECK',
      'MQ_PRODUCER_CHANGE_CHECK',
      'MQ_CONSUMER_CHANGE_CHECK',
      'MQ_MESSAGE_SCHEMA_CHANGE_CHECK',
      'MQ_TOPIC_CONFIG_CHANGE_CHECK',
      'MQ_RETRY_DLQ_CHANGE_CHECK',
      'CONFIG_RELEASE_CHECK'
    ),
    config_json = JSON_SET(
      COALESCE(config_json, JSON_OBJECT()),
      '$.focusChangeTypes',
      JSON_ARRAY(
        'API',
        'DB',
        'DB_SCHEMA',
        'DB_SQL',
        'ORM_MAPPING',
        'ENTITY_MODEL',
        'DATA_MIGRATION',
        'CACHE',
        'CACHE_KEY',
        'CACHE_TTL',
        'CACHE_INVALIDATION',
        'CACHE_READ_WRITE',
        'CACHE_SERIALIZATION',
        'MQ',
        'MQ_PRODUCER',
        'MQ_CONSUMER',
        'MQ_MESSAGE_SCHEMA',
        'MQ_TOPIC_CONFIG',
        'MQ_RETRY_DLQ',
        'CONFIG'
      )
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE template_code = 'backend-default' AND version = 1;
