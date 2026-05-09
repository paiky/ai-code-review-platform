package com.leaf.codereview.riskengine.application;

import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisResult;
import com.leaf.codereview.changeanalysis.domain.ChangeEvidence;
import com.leaf.codereview.changeanalysis.domain.ChangeType;
import com.leaf.codereview.changeanalysis.domain.ImpactedResource;
import com.leaf.codereview.changeanalysis.rule.ValueConfigChangeRule;
import com.leaf.codereview.riskengine.domain.FocusIndicator;
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
import java.util.EnumSet;
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
            if (isLowSignalApiCompatibilityRule(rule)) {
                continue;
            }
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
                buildSummary(analysisResult, overallLevel, riskItems),
                overallLevel,
                affectedResources,
                buildFocusIndicators(analysisResult, riskItems),
                riskItems,
                recommendedChecks,
                suggestedReviewRoles,
                OffsetDateTime.now(),
                GENERATOR
        );
    }

    private List<FocusIndicator> buildFocusIndicators(ChangeAnalysisResult analysisResult, List<RiskItem> riskItems) {
        return List.of(
                buildFocusIndicator(
                        "DB_SCHEMA_CHANGE",
                        "DB 表/字段变更",
                        EnumSet.of(ChangeType.DB_SCHEMA, ChangeType.DATA_MIGRATION, ChangeType.ENTITY_MODEL, ChangeType.ORM_MAPPING),
                        RiskLevel.HIGH,
                        analysisResult,
                        riskItems
                ),
                buildFocusIndicator(
                        "MQ_CONFIG_CHANGE",
                        "MQ 配置变更",
                        EnumSet.of(ChangeType.MQ_TOPIC_CONFIG),
                        RiskLevel.MEDIUM,
                        analysisResult,
                        riskItems
                ),
                buildFocusIndicator(
                        "REDIS_CONFIG_CHANGE",
                        "Redis 配置变更",
                        EnumSet.of(
                                ChangeType.CACHE_KEY,
                                ChangeType.CACHE_TTL,
                                ChangeType.CACHE_INVALIDATION,
                                ChangeType.CACHE_READ_WRITE,
                                ChangeType.CACHE_SERIALIZATION
                        ),
                        RiskLevel.MEDIUM,
                        analysisResult,
                        riskItems
                ),
                buildValueConfigFocusIndicator(analysisResult, riskItems)
        );
    }

    private FocusIndicator buildFocusIndicator(
            String code,
            String name,
            Set<ChangeType> sourceChangeTypes,
            RiskLevel defaultRiskLevel,
            ChangeAnalysisResult analysisResult,
            List<RiskItem> riskItems
    ) {
        boolean matched = !sourceChangeTypes.isEmpty()
                && analysisResult.changeTypes().stream().anyMatch(sourceChangeTypes::contains);
        List<RiskEvidence> evidences = analysisResult.evidences().stream()
                .filter(evidence -> sourceChangeTypes.contains(evidence.changeType()))
                .map(this::toRiskEvidence)
                .distinct()
                .toList();
        RiskLevel riskLevel = riskItems.stream()
                .filter(item -> item.category() != null && sourceChangeTypes.contains(item.category()))
                .map(RiskItem::riskLevel)
                .max(Comparator.comparingInt(RiskLevel::weight))
                .orElse(matched ? defaultRiskLevel : null);
        Set<ChangeType> matchedTypes = analysisResult.changeTypes().stream()
                .filter(sourceChangeTypes::contains)
                .collect(Collectors.toCollection(LinkedHashSet::new));

        return new FocusIndicator(
                code,
                name,
                riskLevel,
                matched,
                focusIndicatorReason(name, matched, matchedTypes),
                evidences,
                matchedTypes
        );
    }

    private FocusIndicator buildValueConfigFocusIndicator(ChangeAnalysisResult analysisResult, List<RiskItem> riskItems) {
        List<RiskEvidence> evidences = analysisResult.evidences().stream()
                .filter(evidence -> ValueConfigChangeRule.RULE_CODE.equals(evidence.matcher()))
                .map(this::toRiskEvidence)
                .distinct()
                .toList();
        boolean matched = !evidences.isEmpty();
        RiskLevel riskLevel = matched
                ? riskItems.stream()
                        .filter(item -> item.category() == ChangeType.CONFIG)
                        .map(RiskItem::riskLevel)
                        .max(Comparator.comparingInt(RiskLevel::weight))
                        .orElse(RiskLevel.MEDIUM)
                : null;
        Set<ChangeType> sourceChangeTypes = matched ? Set.of(ChangeType.CONFIG) : Set.of();

        return new FocusIndicator(
                "VALUE_CONFIG_CHANGE",
                "@Value 配置变更",
                riskLevel,
                matched,
                matched ? "命中 @Value 配置占位符变更。" : "未命中 @Value 配置变更信号。",
                evidences,
                sourceChangeTypes
        );
    }

    private String focusIndicatorReason(String name, boolean matched, Set<ChangeType> matchedTypes) {
        if (!matched) {
            return "未命中" + name + "信号。";
        }
        String signals = matchedTypes.stream()
                .map(this::changeTypeLabel)
                .collect(Collectors.joining(", "));
        return "命中变更类型：" + signals + "。";
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
            signals.add("实体模型变更");
        }
        if (analysisResult.changeTypes().contains(ChangeType.ORM_MAPPING)) {
            signals.add("ORM/MyBatis 映射变更");
        }
        if (!analysisResult.changeTypes().contains(ChangeType.DB_SCHEMA)) {
            signals.add("未检测到 migration 或 DDL");
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

    private boolean isLowSignalApiCompatibilityRule(RiskRuleDefinition rule) {
        return "API_COMPATIBILITY_CHECK".equals(rule.ruleCode()) || rule.changeType() == ChangeType.API;
    }

    private String buildSummary(ChangeAnalysisResult analysisResult, RiskLevel riskLevel, List<RiskItem> riskItems) {
        if (riskItems.isEmpty()) {
            return "未命中需要关注的风险规则。本次分析文件数：" + analysisResult.changedFileCount() + "。";
        }
        String changeTypes = riskItems.stream()
                .map(RiskItem::category)
                .distinct()
                .map(this::changeTypeLabel)
                .collect(Collectors.joining(", "));
        return "本次重点风险涉及 " + changeTypes + "，生成 " + riskItems.size() + " 个风险项，整体风险等级为 " + riskLevel.name() + "。";
    }

    private String changeTypeLabel(ChangeType changeType) {
        if (changeType == null) {
            return "-";
        }
        return switch (changeType) {
            case API -> "接口";
            case DB -> "数据库";
            case DB_SCHEMA -> "DB 表结构";
            case DB_SQL -> "SQL";
            case ORM_MAPPING -> "ORM/MyBatis 映射";
            case ENTITY_MODEL -> "实体模型";
            case DATA_MIGRATION -> "数据迁移";
            case CACHE -> "缓存";
            case CACHE_KEY -> "缓存 Key";
            case CACHE_TTL -> "缓存 TTL";
            case CACHE_INVALIDATION -> "缓存失效";
            case CACHE_READ_WRITE -> "缓存读写";
            case CACHE_SERIALIZATION -> "缓存序列化";
            case MQ -> "MQ";
            case MQ_PRODUCER -> "MQ 生产者";
            case MQ_CONSUMER -> "MQ 消费者";
            case MQ_MESSAGE_SCHEMA -> "MQ 消息结构";
            case MQ_TOPIC_CONFIG -> "MQ Topic/消费组配置";
            case MQ_RETRY_DLQ -> "MQ 重试/死信";
            case CONFIG -> "配置";
        };
    }
}
