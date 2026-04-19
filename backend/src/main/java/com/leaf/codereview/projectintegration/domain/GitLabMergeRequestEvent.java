package com.leaf.codereview.projectintegration.domain;

import com.fasterxml.jackson.databind.JsonNode;

import java.time.LocalDateTime;

public record GitLabMergeRequestEvent(
        String gitProjectId,
        String projectName,
        String repositoryUrl,
        String mrId,
        String eventAction,
        LocalDateTime eventTime,
        String externalUrl,
        String sourceBranch,
        String targetBranch,
        String commitSha,
        String authorName,
        String authorUsername,
        JsonNode changedFilesSummary,
        JsonNode rawPayload
) {
}