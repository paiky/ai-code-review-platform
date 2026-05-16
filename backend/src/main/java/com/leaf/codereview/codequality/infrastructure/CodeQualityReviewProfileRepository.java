package com.leaf.codereview.codequality.infrastructure;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.codequality.application.CodeQualityReviewProfileUpdateRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProfile;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.Optional;

@Repository
public class CodeQualityReviewProfileRepository {

    public static final String DEFAULT_PROFILE_CODE = "backend-default-ai-review";

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public CodeQualityReviewProfileRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public Optional<CodeQualityReviewProfile> findByCode(String profileCode) {
        List<CodeQualityReviewProfile> profiles = jdbcTemplate.query("""
                SELECT *
                FROM code_quality_review_profiles
                WHERE profile_code = ?
                """, rowMapper(), profileCode);
        return profiles.stream().findFirst();
    }

    public List<CodeQualityReviewProfile> findAllEnabled() {
        return jdbcTemplate.query("""
                SELECT *
                FROM code_quality_review_profiles
                WHERE enabled = TRUE AND status = 'ENABLED'
                ORDER BY id DESC
                """, rowMapper());
    }

    public void update(String profileCode, CodeQualityReviewProfile existing, CodeQualityReviewProfileUpdateRequest request) {
        jdbcTemplate.update("""
                UPDATE code_quality_review_profiles
                SET profile_name = ?,
                    enabled = ?,
                    provider_code = ?,
                    model = ?,
                    trigger_on_manual = ?,
                    trigger_on_mr = ?,
                    trigger_on_push = ?,
                    severity_threshold = ?,
                    block_on_severities = ?,
                    enabled_categories = ?,
                    ignored_paths = ?,
                    push_branch_patterns = ?,
                    push_max_changed_files = ?,
                    push_max_diff_bytes = ?,
                    push_debounce_seconds = ?,
                    trigger_only_when_risk_matched = ?,
                    review_instructions = ?
                WHERE profile_code = ?
                """,
                value(request.profileName(), existing.profileName()),
                value(request.enabled(), existing.enabled()),
                enumName(value(request.providerCode(), existing.providerCode())),
                value(request.model(), existing.model()),
                value(request.triggerOnManual(), existing.triggerOnManual()),
                value(request.triggerOnMr(), existing.triggerOnMr()),
                value(request.triggerOnPush(), existing.triggerOnPush()),
                value(request.severityThreshold(), existing.severityThreshold()),
                writeJson(value(request.blockOnSeverities(), existing.blockOnSeverities())),
                writeJson(value(request.enabledCategories(), existing.enabledCategories())),
                writeJson(value(request.ignoredPaths(), existing.ignoredPaths())),
                writeJson(value(request.pushBranchPatterns(), existing.pushBranchPatterns())),
                value(request.pushMaxChangedFiles(), existing.pushMaxChangedFiles()),
                value(request.pushMaxDiffBytes(), existing.pushMaxDiffBytes()),
                value(request.pushDebounceSeconds(), existing.pushDebounceSeconds()),
                value(request.triggerOnlyWhenRiskMatched(), existing.triggerOnlyWhenRiskMatched()),
                value(request.reviewInstructions(), existing.reviewInstructions()),
                profileCode
        );
    }

    private RowMapper<CodeQualityReviewProfile> rowMapper() {
        return (rs, rowNum) -> new CodeQualityReviewProfile(
                rs.getLong("id"),
                rs.getString("profile_code"),
                rs.getString("profile_name"),
                rs.getBoolean("enabled"),
                providerCode(rs.getString("provider_code")),
                rs.getString("model"),
                rs.getBoolean("trigger_on_manual"),
                rs.getBoolean("trigger_on_mr"),
                rs.getBoolean("trigger_on_push"),
                rs.getString("severity_threshold"),
                readJson(rs, "block_on_severities"),
                readJson(rs, "enabled_categories"),
                readJson(rs, "ignored_paths"),
                readJson(rs, "push_branch_patterns"),
                nullableInt(rs, "push_max_changed_files"),
                nullableInt(rs, "push_max_diff_bytes"),
                nullableInt(rs, "push_debounce_seconds"),
                rs.getBoolean("trigger_only_when_risk_matched"),
                rs.getString("review_instructions")
        );
    }

    private CodeQualityReviewProviderType providerCode(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return switch (value.trim()) {
            case "OPENAI_API" -> CodeQualityReviewProviderType.OPENAI;
            case "ANTHROPIC_API" -> CodeQualityReviewProviderType.ANTHROPIC;
            case "CODEX_CLI" -> null;
            default -> CodeQualityReviewProviderType.valueOf(value.trim());
        };
    }

    private String enumName(CodeQualityReviewProviderType providerCode) {
        return providerCode == null ? null : providerCode.name();
    }

    private JsonNode readJson(ResultSet rs, String column) throws SQLException {
        String value = rs.getString(column);
        if (value == null || value.isBlank()) {
            return objectMapper.createArrayNode();
        }
        try {
            return objectMapper.readTree(value);
        } catch (Exception exception) {
            return objectMapper.createArrayNode();
        }
    }

    private String writeJson(JsonNode node) {
        try {
            return objectMapper.writeValueAsString(node == null ? objectMapper.createArrayNode() : node);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("Failed to serialize code quality review profile json", exception);
        }
    }

    private Integer nullableInt(ResultSet rs, String column) throws SQLException {
        int value = rs.getInt(column);
        return rs.wasNull() ? null : value;
    }

    private <T> T value(T requestValue, T fallback) {
        return requestValue != null ? requestValue : fallback;
    }
}
