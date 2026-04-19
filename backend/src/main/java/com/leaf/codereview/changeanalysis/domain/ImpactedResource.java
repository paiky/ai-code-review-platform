package com.leaf.codereview.changeanalysis.domain;

public record ImpactedResource(
        ResourceType resourceType,
        String name,
        String operation,
        String filePath,
        ChangeEvidence evidence
) {
}