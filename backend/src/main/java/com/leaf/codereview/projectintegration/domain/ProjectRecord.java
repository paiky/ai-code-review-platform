package com.leaf.codereview.projectintegration.domain;

public record ProjectRecord(
        Long id,
        String name,
        String gitProvider,
        String gitProjectId,
        String repositoryUrl,
        String defaultTemplateCode,
        String status
) {
}