ALTER TABLE code_quality_model_providers
  ADD COLUMN timeout_seconds INT NULL AFTER api_key;
