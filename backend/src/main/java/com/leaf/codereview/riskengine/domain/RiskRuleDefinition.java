package com.leaf.codereview.riskengine.domain;

import com.leaf.codereview.changeanalysis.domain.ChangeType;

import java.util.List;
import java.util.Set;

public record RiskRuleDefinition(
        String ruleCode,
        ChangeType changeType,
        RiskLevel riskLevel,
        String title,
        String description,
        String impact,
        List<String> recommendedChecks,
        Set<ReviewRole> suggestedReviewRoles
) {
    public RiskRuleDefinition {
        recommendedChecks = recommendedChecks == null ? List.of() : List.copyOf(recommendedChecks);
        suggestedReviewRoles = suggestedReviewRoles == null ? Set.of() : Set.copyOf(suggestedReviewRoles);
    }
}