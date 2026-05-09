package com.leaf.codereview.codequality.application;

public record CodeQualityManualReviewResponse(
        Long taskId,
        String status,
        String profileCode,
        String provider,
        String overallLevel,
        Integer findingCount
) {
}
