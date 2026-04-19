package com.leaf.codereview.riskengine.domain;

import com.leaf.codereview.changeanalysis.domain.ChangeType;
import com.leaf.codereview.changeanalysis.domain.ImpactedResource;

import java.util.List;
import java.util.Set;

public record RiskItem(
        String riskId,
        String ruleCode,
        ChangeType category,
        RiskLevel riskLevel,
        String title,
        String description,
        String impact,
        List<ImpactedResource> affectedResources,
        List<RiskEvidence> evidences,
        List<String> recommendedChecks,
        Set<ReviewRole> suggestedReviewRoles
) {
    public RiskItem {
        affectedResources = affectedResources == null ? List.of() : List.copyOf(affectedResources);
        evidences = evidences == null ? List.of() : List.copyOf(evidences);
        recommendedChecks = recommendedChecks == null ? List.of() : List.copyOf(recommendedChecks);
        suggestedReviewRoles = suggestedReviewRoles == null ? Set.of() : Set.copyOf(suggestedReviewRoles);
    }
}