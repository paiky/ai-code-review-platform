ALTER TABLE code_quality_model_providers
  ADD COLUMN catalog_visible BOOLEAN NOT NULL DEFAULT FALSE AFTER timeout_seconds;

ALTER TABLE code_quality_model_providers
  ADD COLUMN reasoning_effort VARCHAR(16) NULL AFTER catalog_visible;

UPDATE code_quality_model_providers
SET catalog_visible = CASE
  WHEN catalog_visible = TRUE
    OR built_in = FALSE
    OR TRIM(COALESCE(api_key, '')) <> '' THEN TRUE
  ELSE FALSE
END;

UPDATE code_quality_model_providers
SET reasoning_effort = 'high'
WHERE provider_type = 'OPENAI_RESPONSES'
  AND reasoning_effort IS NULL;
