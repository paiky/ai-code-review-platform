package com.leaf.codereview.riskengine.domain;

import com.leaf.codereview.changeanalysis.domain.ChangeType;

import java.util.List;
import java.util.Set;

public record FocusIndicator(
        String code,
        String name,
        RiskLevel riskLevel,
        boolean matched,
        String reason,
        List<RiskEvidence> evidences,
        Set<ChangeType> sourceChangeTypes
) {
    public FocusIndicator {
        evidences = evidences == null ? List.of() : List.copyOf(evidences);
        sourceChangeTypes = sourceChangeTypes == null ? Set.of() : Set.copyOf(sourceChangeTypes);
    }
}
