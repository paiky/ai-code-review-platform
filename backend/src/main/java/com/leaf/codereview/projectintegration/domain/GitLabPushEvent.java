package com.leaf.codereview.projectintegration.domain;

import com.fasterxml.jackson.databind.JsonNode;

import java.time.LocalDateTime;

public record GitLabPushEvent(
        String gitProjectId,
        String projectName,
        String repositoryUrl,
        String ref,
        String branchName,
        String beforeSha,
        String afterSha,
        LocalDateTime eventTime,
        String externalUrl,
        String authorName,
        String authorUsername,
        JsonNode changedFilesSummary,
        JsonNode rawPayload
) {
}
