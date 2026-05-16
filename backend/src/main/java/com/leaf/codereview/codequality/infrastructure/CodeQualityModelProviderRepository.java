package com.leaf.codereview.codequality.infrastructure;

import com.leaf.codereview.codequality.application.CodeQualityModelProviderResponse;
import com.leaf.codereview.codequality.controller.CodeQualityModelProviderUpdateRequest;
import com.leaf.codereview.codequality.domain.CodeQualityModelProvider;
import com.leaf.codereview.codequality.domain.CodeQualityModelProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.util.StringUtils;

import java.sql.Timestamp;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Optional;

@Repository
public class CodeQualityModelProviderRepository {

    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ISO_LOCAL_DATE_TIME;

    private final JdbcTemplate jdbcTemplate;
    private final CodeQualityReviewProperties properties;

    public CodeQualityModelProviderRepository(JdbcTemplate jdbcTemplate, CodeQualityReviewProperties properties) {
        this.jdbcTemplate = jdbcTemplate;
        this.properties = properties;
    }

    public List<CodeQualityModelProviderResponse> findAllResponses() {
        ensureDefaults();
        return jdbcTemplate.query("""
                SELECT p.*, s.default_provider_code
                FROM code_quality_model_providers p
                CROSS JOIN code_quality_review_settings s
                WHERE s.id = 1
                ORDER BY p.sort_order ASC, p.id ASC
                """, (rs, rowNum) -> new CodeQualityModelProviderResponse(
                rs.getString("provider_code"),
                rs.getString("provider_name"),
                rs.getString("provider_type"),
                rs.getString("endpoint_url"),
                rs.getString("model_name"),
                rs.getBoolean("enabled"),
                rs.getBoolean("built_in"),
                rs.getString("provider_code").equals(rs.getString("default_provider_code")),
                StringUtils.hasText(rs.getString("api_key")),
                mask(rs.getString("api_key")),
                formatTimestamp(rs.getTimestamp("updated_at"))
        ));
    }

    public Optional<CodeQualityModelProvider> findByCode(CodeQualityReviewProviderType providerCode) {
        ensureDefaults();
        List<CodeQualityModelProvider> providers = jdbcTemplate.query("""
                SELECT p.*, s.default_provider_code
                FROM code_quality_model_providers p
                CROSS JOIN code_quality_review_settings s
                WHERE p.provider_code = ? AND s.id = 1
                """, (rs, rowNum) -> new CodeQualityModelProvider(
                rs.getLong("id"),
                CodeQualityReviewProviderType.valueOf(rs.getString("provider_code")),
                rs.getString("provider_name"),
                CodeQualityModelProviderType.valueOf(rs.getString("provider_type")),
                rs.getString("endpoint_url"),
                rs.getString("model_name"),
                StringUtils.hasText(rs.getString("api_key")),
                mask(rs.getString("api_key")),
                rs.getString("api_key"),
                rs.getBoolean("enabled"),
                rs.getBoolean("built_in"),
                rs.getInt("sort_order"),
                rs.getString("provider_code").equals(rs.getString("default_provider_code")),
                formatTimestamp(rs.getTimestamp("updated_at"))
        ), providerCode.name());
        return providers.stream().findFirst();
    }

    public CodeQualityModelProvider getRequired(CodeQualityReviewProviderType providerCode) {
        return findByCode(providerCode)
                .orElseThrow(() -> new BusinessException(ErrorCode.BAD_REQUEST, "Model provider not found: " + providerCode));
    }

    public void update(CodeQualityReviewProviderType providerCode, CodeQualityModelProviderUpdateRequest request) {
        ensureDefaults();
        CodeQualityModelProvider existing = getRequired(providerCode);
        jdbcTemplate.update("""
                UPDATE code_quality_model_providers
                SET provider_name = ?,
                    endpoint_url = ?,
                    model_name = ?,
                    api_key = ?,
                    enabled = ?
                WHERE provider_code = ?
                """,
                firstText(request.providerName(), existing.providerName()),
                blankToNull(firstText(request.endpointUrl(), existing.endpointUrl())),
                blankToNull(firstText(request.modelName(), existing.modelName())),
                nextApiKey(existing.apiKey(), request),
                request.enabled() == null ? existing.enabled() : request.enabled(),
                providerCode.name()
        );
    }

    public void ensureDefaults() {
        jdbcTemplate.update("""
                INSERT INTO code_quality_review_settings (id, mr_auto_review_enabled, dingtalk_notification_enabled, default_provider_code)
                VALUES (1, TRUE, TRUE, ?)
                ON DUPLICATE KEY UPDATE id = id
                """, CodeQualityReviewProviderType.DEEPSEEK.name());
        upsertDefault(CodeQualityReviewProviderType.OPENAI, "OpenAI", CodeQualityModelProviderType.OPENAI_RESPONSES,
                properties.openAiResponsesUrl(), properties.openAiModel(), properties.openAiApiKey(), true, 10);
        upsertDefault(CodeQualityReviewProviderType.ANTHROPIC, "Anthropic / Claude", CodeQualityModelProviderType.ANTHROPIC_MESSAGES,
                properties.anthropicMessagesUrl(), properties.anthropicModel(), properties.anthropicApiKey(), true, 20);
        upsertDefault(CodeQualityReviewProviderType.DEEPSEEK, "DeepSeek", CodeQualityModelProviderType.OPENAI_CHAT_COMPATIBLE,
                properties.deepSeekBaseUrl(), properties.deepSeekModel(), properties.deepSeekApiKey(), true, 30);
        upsertDefault(CodeQualityReviewProviderType.CUSTOM, "自定义 OpenAI-compatible", CodeQualityModelProviderType.OPENAI_CHAT_COMPATIBLE,
                null, null, null, false, 40);
    }

    private void upsertDefault(
            CodeQualityReviewProviderType providerCode,
            String providerName,
            CodeQualityModelProviderType providerType,
            String endpointUrl,
            String modelName,
            String apiKey,
            boolean enabled,
            int sortOrder
    ) {
        jdbcTemplate.update("""
                INSERT INTO code_quality_model_providers (
                  provider_code, provider_name, provider_type, endpoint_url, model_name, api_key, enabled, built_in, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, TRUE, ?)
                ON DUPLICATE KEY UPDATE
                  provider_name = VALUES(provider_name),
                  provider_type = VALUES(provider_type),
                  endpoint_url = COALESCE(code_quality_model_providers.endpoint_url, VALUES(endpoint_url)),
                  model_name = COALESCE(code_quality_model_providers.model_name, VALUES(model_name)),
                  api_key = COALESCE(code_quality_model_providers.api_key, VALUES(api_key)),
                  built_in = TRUE,
                  sort_order = VALUES(sort_order)
                """,
                providerCode.name(),
                providerName,
                providerType.name(),
                blankToNull(endpointUrl),
                blankToNull(modelName),
                blankToNull(apiKey),
                enabled,
                sortOrder
        );
    }

    private String nextApiKey(String existingApiKey, CodeQualityModelProviderUpdateRequest request) {
        if (Boolean.TRUE.equals(request.clearApiKey())) {
            return null;
        }
        if (request.apiKey() != null) {
            return blankToNull(request.apiKey());
        }
        return existingApiKey;
    }

    private String firstText(String primary, String fallback) {
        return StringUtils.hasText(primary) ? primary.trim() : fallback;
    }

    private String blankToNull(String value) {
        return StringUtils.hasText(value) ? value.trim() : null;
    }

    private String mask(String value) {
        if (!StringUtils.hasText(value)) {
            return null;
        }
        String trimmed = value.trim();
        if (trimmed.length() <= 8) {
            return "****";
        }
        return trimmed.substring(0, Math.min(4, trimmed.length())) + "..." + trimmed.substring(trimmed.length() - 4);
    }

    private String formatTimestamp(Timestamp timestamp) {
        if (timestamp == null) {
            return null;
        }
        return timestamp.toLocalDateTime().format(DATE_TIME_FORMATTER);
    }
}
