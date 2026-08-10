CREATE TABLE IF NOT EXISTS code_quality_agent_runtimes (
  runtime_code VARCHAR(40) NOT NULL,
  display_name VARCHAR(64) NOT NULL,
  protocol VARCHAR(32) NOT NULL,
  runner_type VARCHAR(32) NOT NULL,
  base_url VARCHAR(1024) NULL,
  model_name VARCHAR(128) NULL,
  reasoning_effort VARCHAR(16) NULL,
  tls_verify BOOLEAN NOT NULL DEFAULT TRUE,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  built_in BOOLEAN NOT NULL DEFAULT FALSE,
  sort_order INT NOT NULL DEFAULT 0,
  api_key_ciphertext TEXT NULL,
  api_key_fingerprint VARCHAR(32) NULL,
  test_request_id VARCHAR(128) NULL,
  test_status VARCHAR(32) NULL,
  test_message VARCHAR(512) NULL,
  test_duration_ms BIGINT NULL,
  test_started_at DATETIME(3) NULL,
  test_finished_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (runtime_code),
  KEY idx_code_quality_agent_runtimes_enabled_sort (enabled, sort_order, runtime_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE code_quality_agent_settings
  ADD COLUMN selected_runtime_code VARCHAR(40) NOT NULL DEFAULT 'CLAUDE_CODE_DEEPSEEK' AFTER runtime_type;

INSERT INTO code_quality_agent_runtimes (
  runtime_code,
  display_name,
  protocol,
  runner_type,
  base_url,
  model_name,
  reasoning_effort,
  tls_verify,
  enabled,
  built_in,
  sort_order,
  api_key_ciphertext,
  api_key_fingerprint,
  test_request_id,
  test_status,
  test_message,
  test_duration_ms,
  test_started_at,
  test_finished_at
)
SELECT
  'CLAUDE_CODE_DEEPSEEK',
  'Claude Code + DeepSeek',
  'ANTHROPIC_COMPATIBLE',
  'CLAUDE_CODE',
  'https://api.deepseek.com/anthropic',
  'deepseek-v4-pro[1m]',
  'high',
  TRUE,
  TRUE,
  TRUE,
  10,
  settings.api_key_ciphertext,
  settings.api_key_fingerprint,
  CASE WHEN settings.runtime_type = 'CLAUDE_CODE_DEEPSEEK' THEN settings.test_request_id END,
  CASE WHEN settings.runtime_type = 'CLAUDE_CODE_DEEPSEEK' THEN settings.test_status END,
  CASE WHEN settings.runtime_type = 'CLAUDE_CODE_DEEPSEEK' THEN settings.test_message END,
  CASE WHEN settings.runtime_type = 'CLAUDE_CODE_DEEPSEEK' THEN settings.test_duration_ms END,
  CASE WHEN settings.runtime_type = 'CLAUDE_CODE_DEEPSEEK' THEN settings.test_started_at END,
  CASE WHEN settings.runtime_type = 'CLAUDE_CODE_DEEPSEEK' THEN settings.test_finished_at END
FROM code_quality_agent_settings settings
WHERE settings.id = 1
  AND NOT EXISTS (
    SELECT 1 FROM code_quality_agent_runtimes runtime
    WHERE runtime.runtime_code = 'CLAUDE_CODE_DEEPSEEK'
  );

INSERT INTO code_quality_agent_runtimes (
  runtime_code,
  display_name,
  protocol,
  runner_type,
  base_url,
  model_name,
  reasoning_effort,
  tls_verify,
  enabled,
  built_in,
  sort_order,
  api_key_ciphertext,
  api_key_fingerprint,
  test_request_id,
  test_status,
  test_message,
  test_duration_ms,
  test_started_at,
  test_finished_at
)
SELECT
  'OPENAI_RESPONSES_CUSTOM',
  COALESCE(NULLIF(settings.custom_display_name, ''), 'Custom OpenAI Agent'),
  'OPENAI_RESPONSES',
  'OPENAI_RESPONSES_AGENT',
  settings.custom_base_url,
  COALESCE(NULLIF(settings.custom_model, ''), 'gpt-5.6-sol'),
  COALESCE(NULLIF(settings.custom_reasoning_effort, ''), 'high'),
  settings.custom_tls_verify,
  TRUE,
  FALSE,
  20,
  settings.custom_api_key_ciphertext,
  settings.custom_api_key_fingerprint,
  CASE WHEN settings.runtime_type = 'OPENAI_RESPONSES_CUSTOM' THEN settings.test_request_id END,
  CASE WHEN settings.runtime_type = 'OPENAI_RESPONSES_CUSTOM' THEN settings.test_status END,
  CASE WHEN settings.runtime_type = 'OPENAI_RESPONSES_CUSTOM' THEN settings.test_message END,
  CASE WHEN settings.runtime_type = 'OPENAI_RESPONSES_CUSTOM' THEN settings.test_duration_ms END,
  CASE WHEN settings.runtime_type = 'OPENAI_RESPONSES_CUSTOM' THEN settings.test_started_at END,
  CASE WHEN settings.runtime_type = 'OPENAI_RESPONSES_CUSTOM' THEN settings.test_finished_at END
FROM code_quality_agent_settings settings
WHERE settings.id = 1
  AND NOT EXISTS (
    SELECT 1 FROM code_quality_agent_runtimes runtime
    WHERE runtime.runtime_code = 'OPENAI_RESPONSES_CUSTOM'
  );

UPDATE code_quality_agent_settings
SET selected_runtime_code = CASE
  WHEN runtime_type = 'OPENAI_RESPONSES_CUSTOM' THEN 'OPENAI_RESPONSES_CUSTOM'
  ELSE 'CLAUDE_CODE_DEEPSEEK'
END
WHERE id = 1;
