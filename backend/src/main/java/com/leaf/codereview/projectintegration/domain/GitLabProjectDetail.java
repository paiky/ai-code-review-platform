package com.leaf.codereview.projectintegration.domain;

public record GitLabProjectDetail(
        String id,
        String name,
        String pathWithNamespace,
        String webUrl
) {
}
