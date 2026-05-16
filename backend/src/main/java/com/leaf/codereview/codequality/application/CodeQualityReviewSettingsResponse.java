package com.leaf.codereview.codequality.application;

public record CodeQualityReviewSettingsResponse(
        boolean mrAutoReviewEnabled,
        boolean dingtalkNotificationEnabled,
        String defaultProviderCode,
        String updatedAt
) {
}
