INSERT INTO code_quality_model_providers (
  provider_code, provider_name, provider_type, endpoint_url, model_name, api_key, enabled, built_in, sort_order
) VALUES (
  'GLM', '智谱 GLM', 'OPENAI_CHAT_COMPATIBLE', 'https://open.bigmodel.cn/api/paas/v4', 'glm-5.1', NULL, TRUE, TRUE, 37
)
ON DUPLICATE KEY UPDATE
  provider_name = VALUES(provider_name),
  provider_type = VALUES(provider_type),
  endpoint_url = COALESCE(code_quality_model_providers.endpoint_url, VALUES(endpoint_url)),
  model_name = COALESCE(code_quality_model_providers.model_name, VALUES(model_name)),
  enabled = VALUES(enabled),
  built_in = VALUES(built_in),
  sort_order = VALUES(sort_order);
