package com.leaf.codereview.notification.infrastructure;

import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;

@Repository
public class NotificationRecordRepository {

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
}