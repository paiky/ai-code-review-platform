package com.leaf.codereview.codequality.controller;

public record CodeQualityModelProviderUpdateRequest(
        String providerName,
        String endpointUrl,
        String modelName,
        String apiKey,
        Boolean clearApiKey,
        Boolean enabled
) {
}
