package com.leaf.codereview.projectintegration.domain;

public record ProjectRecord(
        Long id,
        String name,
        String gitProvider,
        String gitProjectId,
        String repositoryUrl,
        String defaultTemplateCode,
        String defaultCodeQualityProfileCode,
        String defaultCodeQualityProviderCode,
        String status
) {
    public ProjectRecord(
            Long id,
            String name,
            String gitProvider,
            String gitProjectId,
            String repositoryUrl,
            String defaultTemplateCode,
            String defaultCodeQualityProfileCode,
            String status
    ) {
        this(id, name, gitProvider, gitProjectId, repositoryUrl, defaultTemplateCode, defaultCodeQualityProfileCode, null, status);
    }
}
