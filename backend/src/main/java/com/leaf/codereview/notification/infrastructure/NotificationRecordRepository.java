package com.leaf.codereview.notification.infrastructure;

import com.leaf.codereview.notification.application.NotificationRecordResponse;
import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;

@Repository
public class NotificationRecordRepository {

    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ISO_LOCAL_DATE_TIME;

    private final JdbcTemplate jdbcTemplate;

    public NotificationRecordRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void saveDingTalkRecord(Long taskId, Long resultId, DingTalkNotificationResult result) {
        jdbcTemplate.update("""
                INSERT INTO notification_records (
                  task_id, result_id, channel, target, status,
                  request_digest, response_body, error_message, sent_at
                ) VALUES (?, ?, 'DINGTALK', ?, ?, ?, ?, ?, ?)
                """,
                taskId,
                resultId,
                result.target(),
                result.status().name(),
                result.requestDigest(),
                result.responseBody(),
                result.errorMessage(),
                result.status().name().equals("SKIPPED") ? null : LocalDateTime.now()
        );
    }

    public List<NotificationRecordResponse> findByTaskId(Long taskId) {
        return jdbcTemplate.query("""
                SELECT id, task_id, result_id, channel, target, status,
                       request_digest, response_body, error_message, sent_at, created_at
                FROM notification_records
                WHERE task_id = ?
                ORDER BY id ASC
                """, (rs, rowNum) -> mapResponse(rs), taskId);
    }

    private NotificationRecordResponse mapResponse(ResultSet rs) throws SQLException {
        return new NotificationRecordResponse(
                rs.getLong("id"),
                rs.getLong("task_id"),
                nullableLong(rs, "result_id"),
                rs.getString("channel"),
                rs.getString("target"),
                rs.getString("status"),
                rs.getString("request_digest"),
                rs.getString("response_body"),
                rs.getString("error_message"),
                formatTimestamp(rs.getTimestamp("sent_at")),
                formatTimestamp(rs.getTimestamp("created_at"))
        );
    }

    private Long nullableLong(ResultSet rs, String column) throws SQLException {
        long value = rs.getLong(column);
        return rs.wasNull() ? null : value;
    }

    private String formatTimestamp(java.sql.Timestamp timestamp) {
        return timestamp == null ? null : timestamp.toLocalDateTime().format(DATE_TIME_FORMATTER);
    }
}