package com.leaf.codereview.riskengine.infrastructure;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.riskengine.domain.RiskRuleDefinition;
import com.leaf.codereview.riskengine.domain.RiskRuleRepository;
import com.leaf.codereview.riskengine.domain.RiskRuleSet;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Repository;

import java.io.IOException;
import java.util.List;

@Repository
public class ClasspathRiskRuleRepository implements RiskRuleRepository {

    private static final String DEFAULT_RULE_FILE = "risk-rules.json";

    private final List<RiskRuleDefinition> rules;

    public ClasspathRiskRuleRepository(ObjectMapper objectMapper) throws IOException {
        RiskRuleSet ruleSet = objectMapper.readValue(new ClassPathResource(DEFAULT_RULE_FILE).getInputStream(), RiskRuleSet.class);
        this.rules = ruleSet.rules();
    }

    @Override
    public List<RiskRuleDefinition> findEnabledRules() {
        return rules;
    }
}