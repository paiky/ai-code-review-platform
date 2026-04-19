package com.leaf.codereview.changeanalysis.domain;

import java.util.List;

public record RuleMatch(
        ChangeType changeType,
        ChangedFile changedFile,
        List<ImpactedResource> impactedResources,
        List<ChangeEvidence> evidences
) {
    public RuleMatch {
        impactedResources = impactedResources == null ? List.of() : List.copyOf(impactedResources);
        evidences = evidences == null ? List.of() : List.copyOf(evidences);
    }
}