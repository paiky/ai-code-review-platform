package com.leaf.codereview.codequality.domain;

import java.time.OffsetDateTime;
import java.util.List;

public record CodeQualityReviewResult(
        CodeQualityReviewProviderType provider,
        String status,
        String overallLevel,
        String summary,
        List<CodeQualityFinding> findings,
        String rawOutput,
        Integer exitCode,
        String errorMessage,
        OffsetDateTime startedAt,
        OffsetDateTime finishedAt
) {
    public static CodeQualityReviewResult running(
            CodeQualityReviewProviderType provider,
            OffsetDateTime startedAt
    ) {
        return new CodeQualityReviewResult(provider, "RUNNING", null, "AI code review is running", List.of(), null, null, null, startedAt, null);
    }

    public static CodeQualityReviewResult success(
            CodeQualityReviewProviderType provider,
            String overallLevel,
            String summary,
            List<CodeQualityFinding> findings,
            String rawOutput,
            Integer exitCode,
            OffsetDateTime startedAt,
            OffsetDateTime finishedAt
    ) {
        return new CodeQualityReviewResult(provider, "SUCCESS", overallLevel, summary, findings, rawOutput, exitCode, null, startedAt, finishedAt);
    }

    public static CodeQualityReviewResult failed(
            CodeQualityReviewProviderType provider,
            String errorMessage,
            String rawOutput,
            Integer exitCode,
            OffsetDateTime startedAt,
            OffsetDateTime finishedAt
    ) {
        return new CodeQualityReviewResult(provider, "FAILED", null, null, List.of(), rawOutput, exitCode, errorMessage, startedAt, finishedAt);
    }
}
