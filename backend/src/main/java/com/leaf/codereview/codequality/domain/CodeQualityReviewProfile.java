package com.leaf.codereview.codequality.domain;

import com.fasterxml.jackson.databind.JsonNode;

public record CodeQualityReviewProfile(
        Long id,
        String profileCode,
        String profileName,
        boolean enabled,
        CodeQualityReviewProviderType providerCode,
        String model,
        boolean triggerOnManual,
        boolean triggerOnMr,
        boolean triggerOnPush,
        String severityThreshold,
        JsonNode blockOnSeverities,
        JsonNode enabledCategories,
        JsonNode ignoredPaths,
        JsonNode pushBranchPatterns,
        Integer pushMaxChangedFiles,
        Integer pushMaxDiffBytes,
        Integer pushDebounceSeconds,
        boolean triggerOnlyWhenRiskMatched,
        String reviewInstructions
) {
    public CodeQualityReviewProfile(
            Long id,
            String profileCode,
            String profileName,
            boolean enabled,
            CodeQualityReviewProviderType providerCode,
            String model,
            boolean triggerOnManual,
            boolean triggerOnMr,
            boolean triggerOnPush,
            String severityThreshold,
            JsonNode blockOnSeverities,
            JsonNode enabledCategories,
            JsonNode ignoredPaths,
            JsonNode pushBranchPatterns,
            Integer pushMaxChangedFiles,
            Integer pushMaxDiffBytes,
            Integer pushDebounceSeconds,
            boolean triggerOnlyWhenRiskMatched,
            String ignoredCodexPrompt,
            String reviewInstructions
    ) {
        this(
                id,
                profileCode,
                profileName,
                enabled,
                providerCode,
                model,
                triggerOnManual,
                triggerOnMr,
                triggerOnPush,
                severityThreshold,
                blockOnSeverities,
                enabledCategories,
                ignoredPaths,
                pushBranchPatterns,
                pushMaxChangedFiles,
                pushMaxDiffBytes,
                pushDebounceSeconds,
                triggerOnlyWhenRiskMatched,
                reviewInstructions
        );
    }
}
