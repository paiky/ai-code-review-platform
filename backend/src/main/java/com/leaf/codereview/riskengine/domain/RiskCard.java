package com.leaf.codereview.riskengine.domain;

import com.leaf.codereview.changeanalysis.domain.ImpactedResource;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Set;

public record RiskCard(
        String cardId,
        String summary,
        RiskLevel riskLevel,
        List<ImpactedResource> affectedResources,
        List<FocusIndicator> focusIndicators,
        List<RiskItem> riskItems,
        List<String> recommendedChecks,
        Set<ReviewRole> suggestedReviewRoles,
        OffsetDateTime generatedAt,
        String generator
) {
    public RiskCard(
            String cardId,
            String summary,
            RiskLevel riskLevel,
            List<ImpactedResource> affectedResources,
            List<RiskItem> riskItems,
            List<String> recommendedChecks,
            Set<ReviewRole> suggestedReviewRoles,
            OffsetDateTime generatedAt,
            String generator
    ) {
        this(
                cardId,
                summary,
                riskLevel,
                affectedResources,
                List.of(),
                riskItems,
                recommendedChecks,
                suggestedReviewRoles,
                generatedAt,
                generator
        );
    }

    public RiskCard {
        affectedResources = affectedResources == null ? List.of() : List.copyOf(affectedResources);
        focusIndicators = focusIndicators == null ? List.of() : List.copyOf(focusIndicators);
        riskItems = riskItems == null ? List.of() : List.copyOf(riskItems);
        recommendedChecks = recommendedChecks == null ? List.of() : List.copyOf(recommendedChecks);
        suggestedReviewRoles = suggestedReviewRoles == null ? Set.of() : Set.copyOf(suggestedReviewRoles);
    }
}
