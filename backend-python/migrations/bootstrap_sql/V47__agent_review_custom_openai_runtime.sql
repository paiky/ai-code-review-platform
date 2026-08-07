ALTER TABLE code_quality_agent_settings
  ADD COLUMN runtime_type VARCHAR(32) NOT NULL DEFAULT 'CLAUDE_CODE_DEEPSEEK' AFTER enabled,
  ADD COLUMN custom_display_name VARCHAR(64) NULL AFTER api_key_fingerprint,
  ADD COLUMN custom_base_url VARCHAR(1024) NULL AFTER custom_display_name,
  ADD COLUMN custom_model VARCHAR(128) NULL AFTER custom_base_url,
  ADD COLUMN custom_reasoning_effort VARCHAR(16) NULL AFTER custom_model,
  ADD COLUMN custom_api_key_ciphertext TEXT NULL AFTER custom_reasoning_effort,
  ADD COLUMN custom_api_key_fingerprint VARCHAR(32) NULL AFTER custom_api_key_ciphertext;

ALTER TABLE code_quality_agent_workers
  ADD COLUMN capabilities_json TEXT NULL AFTER cli_version,
  ADD COLUMN responses_runner_version VARCHAR(64) NULL AFTER capabilities_json;

ALTER TABLE agent_review_runs
  ADD COLUMN runner_type VARCHAR(32) NOT NULL DEFAULT 'CLAUDE_CODE' AFTER runner_version,
  ADD COLUMN provider VARCHAR(32) NOT NULL DEFAULT 'DEEPSEEK' AFTER runner_type;
