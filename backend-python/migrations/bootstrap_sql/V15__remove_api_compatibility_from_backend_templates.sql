UPDATE rule_templates
SET enabled_rule_codes = JSON_REMOVE(
      enabled_rule_codes,
      JSON_UNQUOTE(JSON_SEARCH(enabled_rule_codes, 'one', 'API_COMPATIBILITY_CHECK'))
    ),
    config_json = JSON_SET(
      COALESCE(config_json, JSON_OBJECT()),
      '$.focusChangeTypes',
      JSON_ARRAY(
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
WHERE template_code = 'backend-default'
  AND JSON_SEARCH(enabled_rule_codes, 'one', 'API_COMPATIBILITY_CHECK') IS NOT NULL;

UPDATE rule_templates
SET enabled_rule_codes = JSON_REMOVE(
      enabled_rule_codes,
      JSON_UNQUOTE(JSON_SEARCH(enabled_rule_codes, 'one', 'API_COMPATIBILITY_CHECK'))
    ),
    config_json = JSON_SET(
      COALESCE(config_json, JSON_OBJECT()),
      '$.focusChangeTypes',
      JSON_ARRAY(
        'DB',
        'DB_SCHEMA',
        'DB_SQL',
        'ORM_MAPPING',
        'ENTITY_MODEL',
        'DATA_MIGRATION',
        'CONFIG'
      )
    ),
    updated_at = CURRENT_TIMESTAMP(3)
WHERE template_code = 'general-default'
  AND JSON_SEARCH(enabled_rule_codes, 'one', 'API_COMPATIBILITY_CHECK') IS NOT NULL;
