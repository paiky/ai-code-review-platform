ALTER TABLE code_quality_model_providers
  ADD COLUMN tls_verify BOOLEAN NOT NULL DEFAULT TRUE AFTER reasoning_effort;
