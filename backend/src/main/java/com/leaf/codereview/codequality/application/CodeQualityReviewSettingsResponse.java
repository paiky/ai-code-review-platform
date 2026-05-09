package com.leaf.codereview.codequality.application;

public record CodeQualityReviewSettingsResponse(
        boolean mrAutoReviewEnabled,
        String reviewProvider,
        boolean openAiApiKeyConfigured,
        String openAiApiKeyMasked,
        boolean anthropicApiKeyConfigured,
        String anthropicApiKeyMasked,
        String updatedAt
) {
}
