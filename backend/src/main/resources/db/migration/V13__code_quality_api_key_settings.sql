ALTER TABLE code_quality_review_settings
  ADD COLUMN openai_api_key VARCHAR(1024) NULL AFTER mr_auto_review_enabled,
  ADD COLUMN anthropic_api_key VARCHAR(1024) NULL AFTER openai_api_key;
