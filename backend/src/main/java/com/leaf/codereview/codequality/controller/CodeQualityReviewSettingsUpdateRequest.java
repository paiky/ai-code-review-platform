package com.leaf.codereview.codequality.controller;

public record CodeQualityReviewSettingsUpdateRequest(
        Boolean mrAutoReviewEnabled,
        Boolean dingtalkNotificationEnabled,
        String defaultProviderCode
) {
}
