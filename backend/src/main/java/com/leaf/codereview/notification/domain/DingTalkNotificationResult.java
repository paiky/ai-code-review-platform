package com.leaf.codereview.notification.domain;

public record DingTalkNotificationResult(
        NotificationStatus status,
        String target,
        String requestDigest,
        String responseBody,
        String errorMessage
) {
}