package com.leaf.codereview.riskengine.domain;

import java.util.Collection;
import java.util.List;

public interface RiskRuleRepository {

    List<RiskRuleDefinition> findEnabledRules();

    default List<RiskRuleDefinition> findRulesByCodes(Collection<String> ruleCodes) {
        if (ruleCodes == null || ruleCodes.isEmpty()) {
            return List.of();
        }
        return findEnabledRules().stream()
                .filter(rule -> ruleCodes.contains(rule.ruleCode()))
                .toList();
    }
}