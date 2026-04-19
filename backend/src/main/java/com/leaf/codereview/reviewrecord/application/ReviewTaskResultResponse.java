package com.leaf.codereview.reviewrecord.application;

import com.fasterxml.jackson.databind.JsonNode;

public record ReviewTaskResultResponse(
        Long taskId,
        String riskLevel,
        Integer riskItemCount,
        String summary,
        JsonNode changeAnalysis,
        JsonNode riskCard
) {
}