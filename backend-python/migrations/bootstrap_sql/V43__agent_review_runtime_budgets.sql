ALTER TABLE code_quality_agent_settings
  ADD COLUMN budget_config_json TEXT NULL AFTER api_key_fingerprint;
