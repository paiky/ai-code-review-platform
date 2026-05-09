package com.leaf.codereview.codequality.application;

public record CodeQualityReviewProgressEventResponse(
        Long id,
        Long taskId,
        String phase,
        String level,
        String message,
        String detail,
        String createdAt
) {
}
