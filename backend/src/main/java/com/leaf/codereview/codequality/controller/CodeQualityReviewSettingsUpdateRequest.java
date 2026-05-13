package com.leaf.codereview.codequality.controller;

import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;

public record CodeQualityReviewSettingsUpdateRequest(
        Boolean mrAutoReviewEnabled,
        Boolean dingtalkNotificationEnabled,
        CodeQualityReviewProviderType reviewProvider,
        String openAiApiKey,
        Boolean clearOpenAiApiKey,
        String anthropicApiKey,
        Boolean clearAnthropicApiKey
) {
}
