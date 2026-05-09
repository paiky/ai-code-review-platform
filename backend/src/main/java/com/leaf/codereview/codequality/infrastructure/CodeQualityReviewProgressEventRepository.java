package com.leaf.codereview.codequality.infrastructure;

import com.leaf.codereview.codequality.application.CodeQualityReviewProgressEventResponse;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;

@Repository
public class CodeQualityReviewProgressEventRepository {

    private static final int MAX_MESSAGE_LENGTH = 512;
    private static final int MAX_DETAIL_LENGTH = 4000;
    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ISO_LOCAL_DATE_TIME;

    private final JdbcTemplate jdbcTemplate;

    public CodeQualityReviewProgressEventRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void append(Long taskId, String phase, String level, String message, String detail) {
        if (taskId == null) {
            return;
        }
        jdbcTemplate.update("""
                INSERT INTO code_quality_review_progress_events (
                  task_id, phase, level, message, detail, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                taskId,
                truncate(phase, 64),
                truncate(level, 32),
                truncate(message, MAX_MESSAGE_LENGTH),
                truncate(detail, MAX_DETAIL_LENGTH),
                LocalDateTime.now()
        );
    }

    public List<CodeQualityReviewProgressEventResponse> findByTaskId(Long taskId) {
        return jdbcTemplate.query("""
                SELECT id, task_id, phase, level, message, detail, created_at
                FROM code_quality_review_progress_events
                WHERE task_id = ?
                ORDER BY id ASC
                """,
                (rs, rowNum) -> new CodeQualityReviewProgressEventResponse(
                        rs.getLong("id"),
                        rs.getLong("task_id"),
                        rs.getString("phase"),
                        rs.getString("level"),
                        rs.getString("message"),
                        rs.getString("detail"),
                        formatTimestamp(rs.getTimestamp("created_at"))
                ),
                taskId
        );
    }

    public void deleteByTaskId(Long taskId) {
        jdbcTemplate.update("DELETE FROM code_quality_review_progress_events WHERE task_id = ?", taskId);
    }

    private String truncate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength);
    }

    private String formatTimestamp(Timestamp timestamp) {
        if (timestamp == null) {
            return null;
        }
        return timestamp.toLocalDateTime().format(DATE_TIME_FORMATTER);
    }
}
