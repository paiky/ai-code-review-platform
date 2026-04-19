package com.leaf.codereview.projectintegration.application;

public record GitLabWebhookResponse(
        Long taskId,
        String status,
        String projectId,
        String projectName,
        String mrId
) {
}