package com.leaf.codereview.changeanalysis.domain;

import java.util.List;
import java.util.Set;

public record ChangeAnalysisResult(
        String summary,
        int changedFileCount,
        Set<ChangeType> changeTypes,
        List<AnalyzedFile> changedFiles,
        List<ImpactedResource> impactedResources,
        List<ChangeEvidence> evidences
) {
    public ChangeAnalysisResult {
        changeTypes = changeTypes == null ? Set.of() : Set.copyOf(changeTypes);
        changedFiles = changedFiles == null ? List.of() : List.copyOf(changedFiles);
        impactedResources = impactedResources == null ? List.of() : List.copyOf(impactedResources);
        evidences = evidences == null ? List.of() : List.copyOf(evidences);
    }
}