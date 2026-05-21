ALTER TABLE code_quality_review_settings
  ADD COLUMN review_enabled BOOLEAN NOT NULL DEFAULT FALSE AFTER id;

