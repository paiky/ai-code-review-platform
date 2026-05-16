package com.leaf.codereview.codequality.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;

public record CodeQualityReviewProfileUpdateRequest(
        String profileName,
        Boolean enabled,
        CodeQualityReviewProviderType providerCode,
        String model,
        Boolean triggerOnManual,
        Boolean triggerOnMr,
        Boolean triggerOnPush,
        String severityThreshold,
        JsonNode blockOnSeverities,
        JsonNode enabledCategories,
        JsonNode ignoredPaths,
        JsonNode pushBranchPatterns,
        Integer pushMaxChangedFiles,
        Integer pushMaxDiffBytes,
        Integer pushDebounceSeconds,
        Boolean triggerOnlyWhenRiskMatched,
        String reviewInstructions
) {
}
