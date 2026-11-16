ALTER TABLE project_review_settings
  ALTER COLUMN memory_enabled SET DEFAULT TRUE;

UPDATE project_review_settings
SET memory_enabled = TRUE,
    memory_settings_version = memory_settings_version + 1
WHERE memory_enabled = FALSE;
