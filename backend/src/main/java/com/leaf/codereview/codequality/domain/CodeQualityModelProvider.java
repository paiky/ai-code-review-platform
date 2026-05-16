package com.leaf.codereview.codequality.domain;

public record CodeQualityModelProvider(
        Long id,
        CodeQualityReviewProviderType providerCode,
        String providerName,
        CodeQualityModelProviderType providerType,
        String endpointUrl,
        String modelName,
        boolean apiKeyConfigured,
        String apiKeyMasked,
        String apiKey,
        boolean enabled,
        boolean builtIn,
        int sortOrder,
        boolean defaultProvider,
        String updatedAt
) {
}
