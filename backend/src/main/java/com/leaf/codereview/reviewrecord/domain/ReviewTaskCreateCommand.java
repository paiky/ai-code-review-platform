package com.leaf.codereview.reviewrecord.domain;

public record ReviewTaskCreateCommand(
        Long projectId,
        String triggerType,
        String externalSourceId,
        String externalUrl,
        String sourceBranch,
        String targetBranch,
        String commitSha,
        String beforeSha,
        String afterSha,
        String authorName,
        String authorUsername,
        String templateCode,
        String status
) {
}