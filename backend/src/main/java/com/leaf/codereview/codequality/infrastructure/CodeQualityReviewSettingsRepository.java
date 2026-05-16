package com.leaf.codereview.codequality.infrastructure;

import com.leaf.codereview.codequality.application.CodeQualityReviewSettingsResponse;
import com.leaf.codereview.codequality.controller.CodeQualityReviewSettingsUpdateRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

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
                SELECT mr_auto_review_enabled, dingtalk_notification_enabled, default_provider_code, updated_at
                FROM code_quality_review_settings
                WHERE id = ?
                """, (rs, rowNum) -> new CodeQualityReviewSettingsResponse(
                rs.getBoolean("mr_auto_review_enabled"),
                rs.getBoolean("dingtalk_notification_enabled"),
                reviewProvider(rs.getString("default_provider_code")).name(),
                formatTimestamp(rs.getTimestamp("updated_at"))
        ), SETTINGS_ID);
        return settings.stream().findFirst().orElse(new CodeQualityReviewSettingsResponse(true, true, CodeQualityReviewProviderType.DEEPSEEK.name(), null));
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
        if (request.defaultProviderCode() != null) {
            jdbcTemplate.update("""
                    UPDATE code_quality_review_settings
                    SET default_provider_code = ?
                    WHERE id = ?
                    """, reviewProvider(request.defaultProviderCode()).name(), SETTINGS_ID);
        }
        return get();
    }

    public boolean mrAutoReviewEnabled() {
        return get().mrAutoReviewEnabled();
    }

    public boolean dingtalkNotificationEnabled() {
        return get().dingtalkNotificationEnabled();
    }

    public CodeQualityReviewProviderType reviewProvider() {
        ensureRow();
        String provider = jdbcTemplate.queryForObject("""
                SELECT default_provider_code
                FROM code_quality_review_settings
                WHERE id = ?
                """, String.class, SETTINGS_ID);
        return reviewProvider(provider);
    }

    public CodeQualityReviewSettingsResponse updateDefaultProvider(CodeQualityReviewProviderType provider) {
        ensureRow();
        jdbcTemplate.update("""
                UPDATE code_quality_review_settings
                SET default_provider_code = ?
                WHERE id = ?
                """, provider.name(), SETTINGS_ID);
        return get();
    }

    private void ensureRow() {
        jdbcTemplate.update("""
                INSERT INTO code_quality_review_settings (id, mr_auto_review_enabled, dingtalk_notification_enabled, default_provider_code)
                VALUES (?, TRUE, TRUE, ?)
                ON DUPLICATE KEY UPDATE id = id
                """, SETTINGS_ID, CodeQualityReviewProviderType.DEEPSEEK.name());
    }

    private String formatTimestamp(Timestamp timestamp) {
        if (timestamp == null) {
            return null;
        }
        return timestamp.toLocalDateTime().format(DATE_TIME_FORMATTER);
    }

    private CodeQualityReviewProviderType reviewProvider(String provider) {
        if (provider == null || provider.isBlank()) {
            return CodeQualityReviewProviderType.DEEPSEEK;
        }
        return switch (provider.trim()) {
            case "OPENAI_API" -> CodeQualityReviewProviderType.OPENAI;
            case "ANTHROPIC_API" -> CodeQualityReviewProviderType.ANTHROPIC;
            case "CODEX_CLI" -> CodeQualityReviewProviderType.DEEPSEEK;
            default -> CodeQualityReviewProviderType.valueOf(provider.trim());
        };
    }
}
