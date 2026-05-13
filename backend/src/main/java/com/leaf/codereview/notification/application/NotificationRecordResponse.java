package com.leaf.codereview.notification.application;

public record NotificationRecordResponse(
        Long id,
        Long taskId,
        Long resultId,
        String channel,
        String target,
        String status,
        String requestDigest,
        String responseBody,
        String errorMessage,
        String sentAt,
        String createdAt
) {
}
