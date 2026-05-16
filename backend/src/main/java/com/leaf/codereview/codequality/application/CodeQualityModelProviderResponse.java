package com.leaf.codereview.codequality.application;

public record CodeQualityModelProviderResponse(
        String providerCode,
        String providerName,
        String providerType,
        String endpointUrl,
        String modelName,
        boolean enabled,
        boolean builtIn,
        boolean defaultProvider,
        boolean apiKeyConfigured,
        String apiKeyMasked,
        String updatedAt
) {
}
