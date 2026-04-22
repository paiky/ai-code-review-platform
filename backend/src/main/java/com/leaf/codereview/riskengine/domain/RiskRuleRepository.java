package com.leaf.codereview.riskengine.domain;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public interface RiskRuleRepository {

    List<RiskRuleDefinition> findEnabledRules();

    default List<RiskRuleDefinition> findRulesByCodes(Collection<String> ruleCodes) {
        if (ruleCodes == null || ruleCodes.isEmpty()) {
            return List.of();
        }
        Set<String> expandedRuleCodes = new LinkedHashSet<>(ruleCodes);
        if (expandedRuleCodes.contains("DB_CHANGE_CHECK")) {
            expandedRuleCodes.addAll(List.of(
                    "DB_SCHEMA_CHANGE_CHECK",
                    "DB_SQL_CHANGE_CHECK",
                    "ORM_MAPPING_CHANGE_CHECK",
                    "ENTITY_MODEL_CHANGE_CHECK",
                    "DATA_MIGRATION_CHECK",
                    "DB_SCHEMA_SYNC_SUSPECT_CHECK"
            ));
        }
        return findEnabledRules().stream()
                .filter(rule -> expandedRuleCodes.contains(rule.ruleCode()))
                .toList();
    }
}
