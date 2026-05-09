package com.leaf.codereview.reviewrecord.application;

import com.fasterxml.jackson.databind.JsonNode;

public record ReviewTaskListItemResponse(
        Long id,
        Long projectId,
        String projectName,
        String triggerType,
        String externalSourceId,
        String externalUrl,
        String sourceBranch,
        String targetBranch,
        String authorName,
        String templateCode,
        String status,
        String riskLevel,
        Integer riskItemCount,
        JsonNode focusIndicators,
        String createdAt,
        String finishedAt
) {
}
