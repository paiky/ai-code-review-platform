package com.leaf.codereview.riskengine.domain;

import java.util.List;

public record RiskRuleSet(List<RiskRuleDefinition> rules) {
    public RiskRuleSet {
        rules = rules == null ? List.of() : List.copyOf(rules);
    }
}