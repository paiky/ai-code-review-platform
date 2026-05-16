package com.leaf.codereview.codequality.infrastructure;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.codequality.application.CodeQualityReviewResultResponse;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Optional;
import java.util.List;

@Repository
public class CodeQualityReviewResultRepository {

    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ISO_LOCAL_DATE_TIME;

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public CodeQualityReviewResultRepository(
            JdbcTemplate jdbcTemplate,
            ObjectMapper objectMapper
    ) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public Long save(Long taskId, Long projectId, String profileCode, String model, CodeQualityReviewResult result) {
        jdbcTemplate.update("""
                INSERT INTO code_quality_review_results (
                  task_id, project_id, profile_code, provider, model, status,
                  overall_level, summary, finding_count, findings_json, raw_output,
                  exit_code, error_message, started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                  project_id = VALUES(project_id),
                  profile_code = VALUES(profile_code),
                  provider = VALUES(provider),
                  model = VALUES(model),
                  status = VALUES(status),
                  overall_level = VALUES(overall_level),
                  summary = VALUES(summary),
                  finding_count = VALUES(finding_count),
                  findings_json = VALUES(findings_json),
                  raw_output = VALUES(raw_output),
                  exit_code = VALUES(exit_code),
                  error_message = VALUES(error_message),
                  started_at = VALUES(started_at),
                  finished_at = VALUES(finished_at)
                """,
                taskId,
                projectId,
                profileCode,
                result.provider().name(),
                model,
                result.status(),
                result.overallLevel(),
                truncate(result.summary(), 1024),
                result.findings().size(),
                writeJson(result.findings()),
                result.rawOutput(),
                result.exitCode(),
                truncate(result.errorMessage(), 1024),
                toTimestamp(result.startedAt()),
                toTimestamp(result.finishedAt())
        );
        return jdbcTemplate.queryForObject("SELECT id FROM code_quality_review_results WHERE task_id = ?", Long.class, taskId);
    }

    public Optional<CodeQualityReviewResultResponse> findByTaskId(Long taskId) {
        List<CodeQualityReviewResultResponse> results = jdbcTemplate.query("""
                SELECT task_id, project_id, profile_code, provider, model, status,
                       overall_level, summary, finding_count, findings_json, raw_output,
                       exit_code, error_message, started_at, finished_at
                FROM code_quality_review_results
                WHERE task_id = ?
                """, (rs, rowNum) -> mapResponse(rs), taskId);
        return results.stream().findFirst();
    }

    public boolean existsByTaskId(Long taskId) {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(1) FROM code_quality_review_results WHERE task_id = ?",
                Integer.class,
                taskId
        );
        return count != null && count > 0;
    }

    public int markStaleRunningAsFailed(int timeoutSeconds) {
        LocalDateTime cutoff = LocalDateTime.now().minusSeconds(Math.max(timeoutSeconds, 60));
        return jdbcTemplate.update("""
                UPDATE code_quality_review_results
                SET status = 'FAILED',
                    error_message = ?,
                    finished_at = ?,
                    updated_at = ?
                WHERE status = 'RUNNING'
                  AND updated_at < ?
                """,
                "AI Review was interrupted or timed out before backend startup. Please retry it manually.",
                LocalDateTime.now(),
                LocalDateTime.now(),
                cutoff
        );
    }

    private CodeQualityReviewResultResponse mapResponse(ResultSet rs) throws SQLException {
        String provider = rs.getString("provider");
        JsonNode findings = readJson(rs.getString("findings_json"));
        Integer findingCount = nullableInt(rs, "finding_count");
        String overallLevel = rs.getString("overall_level");
        String summary = rs.getString("summary");
        return new CodeQualityReviewResultResponse(
                rs.getLong("task_id"),
                rs.getLong("project_id"),
                rs.getString("profile_code"),
                provider,
                rs.getString("model"),
                rs.getString("status"),
                overallLevel,
                summary,
                findingCount,
                findings,
                rs.getString("raw_output"),
                nullableInt(rs, "exit_code"),
                rs.getString("error_message"),
                formatTimestamp(rs.getTimestamp("started_at")),
                formatTimestamp(rs.getTimestamp("finished_at"))
        );
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("Failed to serialize code quality review result", exception);
        }
    }

    private JsonNode readJson(String value) {
        if (value == null || value.isBlank()) {
            return objectMapper.createArrayNode();
        }
        try {
            return objectMapper.readTree(value);
        } catch (Exception exception) {
            return objectMapper.createArrayNode();
        }
    }

    private Timestamp toTimestamp(OffsetDateTime time) {
        return time == null ? null : Timestamp.from(time.toInstant());
    }

    private Integer nullableInt(ResultSet rs, String column) throws SQLException {
        int value = rs.getInt(column);
        return rs.wasNull() ? null : value;
    }

    private String formatTimestamp(Timestamp timestamp) {
        if (timestamp == null) {
            return null;
        }
        return timestamp.toLocalDateTime().format(DATE_TIME_FORMATTER);
    }

    private String truncate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }

}
