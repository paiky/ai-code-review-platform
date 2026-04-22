package com.leaf.codereview.riskengine.application;

import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisResult;
import com.leaf.codereview.changeanalysis.domain.ChangeEvidence;
import com.leaf.codereview.changeanalysis.domain.ChangeType;
import com.leaf.codereview.changeanalysis.domain.ImpactedResource;
import com.leaf.codereview.riskengine.domain.ReviewRole;
import com.leaf.codereview.riskengine.domain.RiskCard;
import com.leaf.codereview.riskengine.domain.RiskEvidence;
import com.leaf.codereview.riskengine.domain.RiskItem;
import com.leaf.codereview.riskengine.domain.RiskLevel;
import com.leaf.codereview.riskengine.domain.RiskRuleDefinition;
import com.leaf.codereview.riskengine.domain.RiskRuleRepository;
import com.leaf.codereview.ruletemplate.application.RuleTemplateService;
import com.leaf.codereview.ruletemplate.domain.ReviewTemplateDefinition;
import org.springframework.stereotype.Service;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
public class RiskCardGenerator {

    private static final String GENERATOR = "risk-engine-rule-v1";

    private final RiskRuleRepository riskRuleRepository;
    private final RuleTemplateService ruleTemplateService;

    public RiskCardGenerator(RiskRuleRepository riskRuleRepository, RuleTemplateService ruleTemplateService) {
        this.riskRuleRepository = riskRuleRepository;
        this.ruleTemplateService = ruleTemplateService;
    }

    public RiskCard generate(ChangeAnalysisResult analysisResult) {
        return generate(analysisResult, RuleTemplateService.DEFAULT_TEMPLATE_CODE);
    }

    public RiskCard generate(ChangeAnalysisResult analysisResult, String templateCode) {
        ReviewTemplateDefinition template = ruleTemplateService.getEnabledTemplate(templateCode);
        List<RiskRuleDefinition> enabledRules = riskRuleRepository.findRulesByCodes(template.enabledRuleCodes());
        return generate(analysisResult, enabledRules, template.recommendedChecks());
    }

    public RiskCard generate(ChangeAnalysisResult analysisResult, List<RiskRuleDefinition> enabledRules, List<String> templateRecommendedChecks) {
        List<RiskItem> riskItems = new ArrayList<>();
        int sequence = 1;
        for (RiskRuleDefinition rule : enabledRules) {
            if (!matchesRule(rule, analysisResult)) {
                continue;
            }
            riskItems.add(buildRiskItem(sequence++, rule, analysisResult));
        }

        RiskLevel overallLevel = riskItems.stream()
                .map(RiskItem::riskLevel)
                .max(Comparator.comparingInt(RiskLevel::weight))
                .orElse(RiskLevel.LOW);

        List<String> recommendedChecks = new ArrayList<>();
        if (templateRecommendedChecks != null) {
            recommendedChecks.addAll(templateRecommendedChecks);
        }
        riskItems.stream()
                .flatMap(item -> item.recommendedChecks().stream())
                .forEach(recommendedChecks::add);
        recommendedChecks = recommendedChecks.stream().distinct().toList();

        Set<ReviewRole> suggestedReviewRoles = riskItems.stream()
                .flatMap(item -> item.suggestedReviewRoles().stream())
                .collect(Collectors.toCollection(LinkedHashSet::new));

        List<ImpactedResource> affectedResources = analysisResult.impactedResources().stream()
                .distinct()
                .toList();

        return new RiskCard(
                "risk-card-" + UUID.randomUUID(),
                buildSummary(analysisResult, overallLevel, riskItems.size()),
                overallLevel,
                affectedResources,
                riskItems,
                recommendedChecks,
                suggestedReviewRoles,
                OffsetDateTime.now(),
                GENERATOR
        );
    }

    private RiskItem buildRiskItem(int sequence, RiskRuleDefinition rule, ChangeAnalysisResult analysisResult) {
        List<ImpactedResource> affectedResources = analysisResult.impactedResources().stream()
                .filter(resource -> matchesRuleResource(resource, rule))
                .toList();

        List<RiskEvidence> evidences = analysisResult.evidences().stream()
                .filter(evidence -> matchesRuleEvidence(evidence, rule))
                .map(this::toRiskEvidence)
                .toList();

        return new RiskItem(
                rule.ruleCode() + "-" + String.format("%03d", sequence),
                rule.ruleCode(),
                rule.changeType(),
                rule.riskLevel(),
                rule.title(),
                rule.description(),
                rule.impact(),
                affectedResources,
                evidences,
                rule.recommendedChecks(),
                rule.suggestedReviewRoles(),
                rule.confidence(),
                rule.reason(),
                relatedSignals(rule, analysisResult)
        );
    }

    private boolean matchesRule(RiskRuleDefinition rule, ChangeAnalysisResult analysisResult) {
        if ("DB_SCHEMA_SYNC_SUSPECT_CHECK".equals(rule.ruleCode())) {
            return analysisResult.changeTypes().contains(ChangeType.ENTITY_MODEL)
                    && analysisResult.changeTypes().contains(ChangeType.ORM_MAPPING)
                    && !analysisResult.changeTypes().contains(ChangeType.DB_SCHEMA);
        }
        return analysisResult.changeTypes().contains(rule.changeType());
    }

    private boolean matchesRuleResource(ImpactedResource resource, RiskRuleDefinition rule) {
        return resource.evidence() != null && matchesRuleChangeType(resource.evidence().changeType(), rule);
    }

    private boolean matchesRuleEvidence(ChangeEvidence evidence, RiskRuleDefinition rule) {
        return matchesRuleChangeType(evidence.changeType(), rule);
    }

    private boolean matchesRuleChangeType(ChangeType actualChangeType, RiskRuleDefinition rule) {
        if ("DB_SCHEMA_SYNC_SUSPECT_CHECK".equals(rule.ruleCode())) {
            return actualChangeType == ChangeType.ENTITY_MODEL || actualChangeType == ChangeType.ORM_MAPPING;
        }
        if (rule.changeType() == ChangeType.DB) {
            return actualChangeType.isDbFamily();
        }
        if (rule.changeType() == ChangeType.CACHE) {
            return actualChangeType.isCacheFamily();
        }
        if (rule.changeType() == ChangeType.MQ) {
            return actualChangeType.isMqFamily();
        }
        return actualChangeType == rule.changeType();
    }

    private List<String> relatedSignals(RiskRuleDefinition rule, ChangeAnalysisResult analysisResult) {
        if (!"DB_SCHEMA_SYNC_SUSPECT_CHECK".equals(rule.ruleCode())) {
            return List.of();
        }
        List<String> signals = new ArrayList<>();
        if (analysisResult.changeTypes().contains(ChangeType.ENTITY_MODEL)) {
            signals.add("entity model changed");
        }
        if (analysisResult.changeTypes().contains(ChangeType.ORM_MAPPING)) {
            signals.add("ORM/MyBatis mapping changed");
        }
        if (!analysisResult.changeTypes().contains(ChangeType.DB_SCHEMA)) {
            signals.add("migration or DDL not detected");
        }
        return signals;
    }

    private RiskEvidence toRiskEvidence(ChangeEvidence evidence) {
        return new RiskEvidence(
                evidence.filePath(),
                evidence.lineStart(),
                evidence.lineEnd(),
                evidence.snippet(),
                evidence.matcher()
        );
    }

    private String buildSummary(ChangeAnalysisResult analysisResult, RiskLevel riskLevel, int riskItemCount) {
        String changeTypes = analysisResult.changeTypes().stream()
                .map(Enum::name)
                .collect(Collectors.joining(", "));
        if (riskItemCount == 0) {
            return "未命中风险规则。本次分析文件数：" + analysisResult.changedFileCount() + "。";
        }
        return "本次变更涉及 " + changeTypes + "，生成 " + riskItemCount + " 个风险项，整体风险等级为 " + riskLevel.name() + "。";
    }
}
