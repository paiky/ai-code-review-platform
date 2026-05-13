package com.leaf.codereview.codequality.infrastructure;

import com.leaf.codereview.codequality.application.CodeQualityReviewSettingsResponse;
import com.leaf.codereview.codequality.controller.CodeQualityReviewSettingsUpdateRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.util.StringUtils;

import java.sql.Timestamp;
import java.time.format.DateTimeFormatter;
import java.util.List;

@Repository
public class CodeQualityReviewSettingsRepository {

    private static final long SETTINGS_ID = 1L;
    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ISO_LOCAL_DATE_TIME;

    private final JdbcTemplate jdbcTemplate;

    public CodeQualityReviewSettingsRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public CodeQualityReviewSettingsResponse get() {
        ensureRow();
        List<CodeQualityReviewSettingsResponse> settings = jdbcTemplate.query("""
                SELECT mr_auto_review_enabled, dingtalk_notification_enabled, review_provider, openai_api_key, anthropic_api_key, updated_at
                FROM code_quality_review_settings
                WHERE id = ?
                """, (rs, rowNum) -> new CodeQualityReviewSettingsResponse(
                rs.getBoolean("mr_auto_review_enabled"),
                rs.getBoolean("dingtalk_notification_enabled"),
                reviewProvider(rs.getString("review_provider")).name(),
                StringUtils.hasText(rs.getString("openai_api_key")),
                mask(rs.getString("openai_api_key")),
                StringUtils.hasText(rs.getString("anthropic_api_key")),
                mask(rs.getString("anthropic_api_key")),
                formatTimestamp(rs.getTimestamp("updated_at"))
        ), SETTINGS_ID);
        return settings.stream().findFirst().orElse(new CodeQualityReviewSettingsResponse(true, true, CodeQualityReviewProviderType.CODEX_CLI.name(), false, null, false, null, null));
    }

    public CodeQualityReviewSettingsResponse updateMrAutoReviewEnabled(boolean enabled) {
        ensureRow();
        jdbcTemplate.update("""
                UPDATE code_quality_review_settings
                SET mr_auto_review_enabled = ?
                WHERE id = ?
                """, enabled, SETTINGS_ID);
        return get();
    }

    public CodeQualityReviewSettingsResponse update(CodeQualityReviewSettingsUpdateRequest request) {
        ensureRow();
        if (request.mrAutoReviewEnabled() != null) {
            jdbcTemplate.update("""
                    UPDATE code_quality_review_settings
                    SET mr_auto_review_enabled = ?
                    WHERE id = ?
                    """, request.mrAutoReviewEnabled(), SETTINGS_ID);
        }
        if (request.dingtalkNotificationEnabled() != null) {
            jdbcTemplate.update("""
                    UPDATE code_quality_review_settings
                    SET dingtalk_notification_enabled = ?
                    WHERE id = ?
                    """, request.dingtalkNotificationEnabled(), SETTINGS_ID);
        }
        if (request.reviewProvider() != null) {
            jdbcTemplate.update("""
                    UPDATE code_quality_review_settings
                    SET review_provider = ?
                    WHERE id = ?
                    """, request.reviewProvider().name(), SETTINGS_ID);
        }
        if (Boolean.TRUE.equals(request.clearOpenAiApiKey())) {
            jdbcTemplate.update("""
                    UPDATE code_quality_review_settings
                    SET openai_api_key = NULL
                    WHERE id = ?
                    """, SETTINGS_ID);
        } else if (request.openAiApiKey() != null) {
            jdbcTemplate.update("""
                    UPDATE code_quality_review_settings
                    SET openai_api_key = ?
                    WHERE id = ?
                    """, blankToNull(request.openAiApiKey()), SETTINGS_ID);
        }
        if (Boolean.TRUE.equals(request.clearAnthropicApiKey())) {
            jdbcTemplate.update("""
                    UPDATE code_quality_review_settings
                    SET anthropic_api_key = NULL
                    WHERE id = ?
                    """, SETTINGS_ID);
        } else if (request.anthropicApiKey() != null) {
            jdbcTemplate.update("""
                    UPDATE code_quality_review_settings
                    SET anthropic_api_key = ?
                    WHERE id = ?
                    """, blankToNull(request.anthropicApiKey()), SETTINGS_ID);
        }
        return get();
    }

    public boolean mrAutoReviewEnabled() {
        return get().mrAutoReviewEnabled();
    }

    public boolean dingtalkNotificationEnabled() {
        return get().dingtalkNotificationEnabled();
    }

    public String openAiApiKey() {
        ensureRow();
        return jdbcTemplate.queryForObject("""
                SELECT openai_api_key
                FROM code_quality_review_settings
                WHERE id = ?
                """, String.class, SETTINGS_ID);
    }

    public String anthropicApiKey() {
        ensureRow();
        return jdbcTemplate.queryForObject("""
                SELECT anthropic_api_key
                FROM code_quality_review_settings
                WHERE id = ?
                """, String.class, SETTINGS_ID);
    }

    public CodeQualityReviewProviderType reviewProvider() {
        ensureRow();
        String provider = jdbcTemplate.queryForObject("""
                SELECT review_provider
                FROM code_quality_review_settings
                WHERE id = ?
                """, String.class, SETTINGS_ID);
        return reviewProvider(provider);
    }

    private void ensureRow() {
        jdbcTemplate.update("""
                INSERT INTO code_quality_review_settings (id, mr_auto_review_enabled, dingtalk_notification_enabled, review_provider)
                VALUES (?, TRUE, TRUE, ?)
                ON DUPLICATE KEY UPDATE id = id
                """, SETTINGS_ID, CodeQualityReviewProviderType.CODEX_CLI.name());
    }

    private String formatTimestamp(Timestamp timestamp) {
        if (timestamp == null) {
            return null;
        }
        return timestamp.toLocalDateTime().format(DATE_TIME_FORMATTER);
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

    private CodeQualityReviewProviderType reviewProvider(String provider) {
        if (!StringUtils.hasText(provider)) {
            return CodeQualityReviewProviderType.CODEX_CLI;
        }
        return CodeQualityReviewProviderType.valueOf(provider.trim());
    }
}
