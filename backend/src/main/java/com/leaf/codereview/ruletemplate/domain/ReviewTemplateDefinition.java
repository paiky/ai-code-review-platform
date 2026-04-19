package com.leaf.codereview.ruletemplate.domain;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.List;

public record ReviewTemplateDefinition(
        Long id,
        String templateCode,
        String templateName,
        String targetType,
        Integer version,
        List<String> enabledRuleCodes,
        List<String> recommendedChecks,
        JsonNode config,
        String status,
        String description
) {
    public ReviewTemplateDefinition {
        enabledRuleCodes = enabledRuleCodes == null ? List.of() : List.copyOf(enabledRuleCodes);
        recommendedChecks = recommendedChecks == null ? List.of() : List.copyOf(recommendedChecks);
    }
}