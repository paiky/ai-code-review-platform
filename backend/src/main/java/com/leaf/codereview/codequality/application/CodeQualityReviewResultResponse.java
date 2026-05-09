package com.leaf.codereview.codequality.application;

import com.fasterxml.jackson.databind.JsonNode;

public record CodeQualityReviewResultResponse(
        Long taskId,
        Long projectId,
        String profileCode,
        String provider,
        String model,
        String status,
        String overallLevel,
        String summary,
        Integer findingCount,
        JsonNode findings,
        String rawOutput,
        Integer exitCode,
        String errorMessage,
        String startedAt,
        String finishedAt
) {
}
