ALTER TABLE projects
  MODIFY COLUMN target_type VARCHAR(32) NOT NULL DEFAULT 'GENERAL';

SET @drop_legacy_webhook_index = (
  SELECT IF(
    COUNT(*) > 0,
    'ALTER TABLE notification_webhooks DROP INDEX idx_notification_webhooks_group_channel_enabled',
    'SELECT 1'
  )
  FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'notification_webhooks'
    AND index_name = 'idx_notification_webhooks_group_channel_enabled'
);

PREPARE drop_legacy_webhook_index_statement FROM @drop_legacy_webhook_index;
EXECUTE drop_legacy_webhook_index_statement;
DEALLOCATE PREPARE drop_legacy_webhook_index_statement;

SET @drop_current_webhook_index = (
  SELECT IF(
    COUNT(*) > 0,
    'ALTER TABLE notification_webhooks DROP INDEX idx_notification_webhooks_channel_enabled',
    'SELECT 1'
  )
  FROM information_schema.statistics
  WHERE table_schema = DATABASE()
    AND table_name = 'notification_webhooks'
    AND index_name = 'idx_notification_webhooks_channel_enabled'
);

PREPARE drop_current_webhook_index_statement FROM @drop_current_webhook_index;
EXECUTE drop_current_webhook_index_statement;
DEALLOCATE PREPARE drop_current_webhook_index_statement;

ALTER TABLE notification_webhooks
  DROP COLUMN project_group_id,
  ADD INDEX idx_notification_webhooks_channel_enabled (channel, enabled, status);

ALTER TABLE projects
  DROP COLUMN group_id,
  DROP COLUMN supported_target_types;

DROP TABLE project_group_ai_review_models;
DROP TABLE project_groups;
