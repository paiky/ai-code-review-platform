package com.leaf.codereview.reviewrecord.application;

import com.fasterxml.jackson.databind.JsonNode;

public record ReviewTaskDetailResponse(
        Long id,
        Long projectId,
        String projectName,
        String gitProjectId,
        String triggerType,
        String mrId,
        String externalUrl,
        String sourceBranch,
        String targetBranch,
        String commitSha,
        String authorName,
        String authorUsername,
        String templateCode,
        String status,
        String riskLevel,
        String eventAction,
        String eventTime,
        JsonNode changedFilesSummary,
        JsonNode rawPayload,
        String createdAt,
        String updatedAt
) {
}