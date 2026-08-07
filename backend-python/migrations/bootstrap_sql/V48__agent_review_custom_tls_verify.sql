ALTER TABLE code_quality_agent_settings
  ADD COLUMN custom_tls_verify BOOLEAN NOT NULL DEFAULT TRUE AFTER custom_reasoning_effort;
