CREATE TABLE code_quality_model_providers (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  provider_code VARCHAR(64) NOT NULL,
  provider_name VARCHAR(128) NOT NULL,
  provider_type VARCHAR(64) NOT NULL,
  endpoint_url VARCHAR(512) NULL,
  model_name VARCHAR(128) NULL,
  api_key VARCHAR(1024) NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  built_in BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order INT NOT NULL DEFAULT 0,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  UNIQUE KEY uk_provider_code (provider_code),
  KEY idx_enabled_sort (enabled, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO code_quality_model_providers (
  provider_code, provider_name, provider_type, endpoint_url, model_name, api_key, enabled, built_in, sort_order
) VALUES
  ('OPENAI', 'OpenAI', 'OPENAI_RESPONSES', 'https://api.openai.com/v1/responses', 'gpt-5.5', NULL, TRUE, TRUE, 10),
  ('ANTHROPIC', 'Anthropic / Claude', 'ANTHROPIC_MESSAGES', 'https://api.anthropic.com/v1/messages', 'claude-sonnet-4-5', NULL, TRUE, TRUE, 20),
  ('DEEPSEEK', 'DeepSeek', 'OPENAI_CHAT_COMPATIBLE', 'https://api.deepseek.com', 'deepseek-v4-pro', NULL, TRUE, TRUE, 30),
  ('XIAOMIMO', 'XiaoMIMO / Xiaomi MiMo', 'OPENAI_CHAT_COMPATIBLE', 'https://api.xiaomimimo.com/v1', 'mimo-v2.5-pro', NULL, TRUE, TRUE, 35),
  ('CUSTOM', '自定义 OpenAI-compatible', 'OPENAI_CHAT_COMPATIBLE', NULL, NULL, NULL, FALSE, TRUE, 40)
ON DUPLICATE KEY UPDATE
  provider_name = VALUES(provider_name),
  provider_type = VALUES(provider_type),
  endpoint_url = COALESCE(code_quality_model_providers.endpoint_url, VALUES(endpoint_url)),
  model_name = COALESCE(code_quality_model_providers.model_name, VALUES(model_name)),
  enabled = VALUES(enabled),
  built_in = VALUES(built_in),
  sort_order = VALUES(sort_order);

UPDATE code_quality_model_providers
SET api_key = (SELECT openai_api_key FROM code_quality_review_settings WHERE id = 1)
WHERE provider_code = 'OPENAI'
  AND api_key IS NULL
  AND EXISTS (
    SELECT 1 FROM code_quality_review_settings
    WHERE id = 1 AND openai_api_key IS NOT NULL AND openai_api_key <> ''
  );

UPDATE code_quality_model_providers
SET api_key = (SELECT anthropic_api_key FROM code_quality_review_settings WHERE id = 1)
WHERE provider_code = 'ANTHROPIC'
  AND api_key IS NULL
  AND EXISTS (
    SELECT 1 FROM code_quality_review_settings
    WHERE id = 1 AND anthropic_api_key IS NOT NULL AND anthropic_api_key <> ''
  );

ALTER TABLE code_quality_review_settings
  ADD COLUMN default_provider_code VARCHAR(64) NOT NULL DEFAULT 'DEEPSEEK' AFTER dingtalk_notification_enabled;

UPDATE code_quality_review_settings
SET default_provider_code = CASE review_provider
  WHEN 'OPENAI_API' THEN 'OPENAI'
  WHEN 'ANTHROPIC_API' THEN 'ANTHROPIC'
  ELSE 'DEEPSEEK'
END;

ALTER TABLE projects
  ADD COLUMN default_code_quality_provider_code VARCHAR(64) NULL AFTER default_code_quality_profile_code,
  ADD KEY idx_code_quality_provider (default_code_quality_provider_code);

ALTER TABLE code_quality_review_profiles
  ADD COLUMN provider_code VARCHAR(64) NULL AFTER provider,
  ADD COLUMN review_instructions TEXT NULL AFTER openai_instructions;

UPDATE code_quality_review_profiles
SET provider_code = CASE provider
      WHEN 'OPENAI_API' THEN 'OPENAI'
      WHEN 'ANTHROPIC_API' THEN 'ANTHROPIC'
      WHEN 'CODEX_CLI' THEN NULL
      ELSE provider
    END,
    review_instructions = COALESCE(NULLIF(openai_instructions, ''), NULLIF(codex_prompt, ''));
