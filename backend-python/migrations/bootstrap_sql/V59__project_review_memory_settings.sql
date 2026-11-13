ALTER TABLE project_review_settings
  ADD COLUMN memory_enabled BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE project_review_settings
  ADD COLUMN memory_settings_version INT NOT NULL DEFAULT 1;
