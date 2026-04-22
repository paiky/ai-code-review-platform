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
        if (expandedRuleCodes.contains("CACHE_CONSISTENCY_CHECK")) {
            expandedRuleCodes.addAll(List.of(
                    "CACHE_KEY_CHANGE_CHECK",
                    "CACHE_TTL_CHANGE_CHECK",
                    "CACHE_INVALIDATION_CHANGE_CHECK",
                    "CACHE_READ_WRITE_CHANGE_CHECK",
                    "CACHE_SERIALIZATION_CHANGE_CHECK"
            ));
        }
        if (expandedRuleCodes.contains("MQ_IDEMPOTENCY_CHECK")) {
            expandedRuleCodes.addAll(List.of(
                    "MQ_PRODUCER_CHANGE_CHECK",
                    "MQ_CONSUMER_CHANGE_CHECK",
                    "MQ_MESSAGE_SCHEMA_CHANGE_CHECK",
                    "MQ_TOPIC_CONFIG_CHANGE_CHECK",
                    "MQ_RETRY_DLQ_CHANGE_CHECK"
            ));
        }
        return findEnabledRules().stream()
                .filter(rule -> expandedRuleCodes.contains(rule.ruleCode()))
                .toList();
    }
}
