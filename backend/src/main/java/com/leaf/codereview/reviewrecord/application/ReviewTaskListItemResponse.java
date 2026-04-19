package com.leaf.codereview.reviewrecord.application;

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
        String createdAt,
        String finishedAt
) {
}