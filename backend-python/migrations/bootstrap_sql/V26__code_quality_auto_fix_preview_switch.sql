ALTER TABLE code_quality_review_settings
  ADD COLUMN auto_fix_preview_enabled BOOLEAN NOT NULL DEFAULT FALSE AFTER dingtalk_notification_enabled;

ALTER TABLE code_quality_review_settings
  ADD COLUMN auto_fix_preview_severities TEXT NULL AFTER auto_fix_preview_enabled;
