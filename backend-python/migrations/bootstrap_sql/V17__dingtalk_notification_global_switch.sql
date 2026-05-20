ALTER TABLE code_quality_review_settings
  ADD COLUMN dingtalk_notification_enabled BOOLEAN NOT NULL DEFAULT TRUE AFTER mr_auto_review_enabled;
