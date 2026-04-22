package com.leaf.codereview.riskengine;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.changeanalysis.application.ChangeAnalysisService;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisRequest;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisResult;
import com.leaf.codereview.changeanalysis.domain.ChangeType;
import com.leaf.codereview.changeanalysis.domain.ChangedFile;
import com.leaf.codereview.changeanalysis.rule.ApiChangeRule;
import com.leaf.codereview.changeanalysis.rule.CacheChangeRule;
import com.leaf.codereview.changeanalysis.rule.ConfigChangeRule;
import com.leaf.codereview.changeanalysis.rule.DbChangeRule;
import com.leaf.codereview.changeanalysis.rule.MqChangeRule;
import com.leaf.codereview.riskengine.application.RiskCardGenerator;
import com.leaf.codereview.riskengine.domain.ReviewRole;
import com.leaf.codereview.riskengine.domain.RiskCard;
import com.leaf.codereview.riskengine.domain.RiskItem;
import com.leaf.codereview.riskengine.domain.RiskLevel;
import com.leaf.codereview.riskengine.domain.RiskRuleDefinition;
import com.leaf.codereview.riskengine.infrastructure.ClasspathRiskRuleRepository;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

class RiskCardGeneratorTest {

    private final ChangeAnalysisService analysisService = new ChangeAnalysisService(List.of(
            new ApiChangeRule(),
            new DbChangeRule(),
            new CacheChangeRule(),
            new MqChangeRule(),
            new ConfigChangeRule()
    ));

    @Test
    void loadsDefaultRiskRuleConfiguration() throws Exception {
        ClasspathRiskRuleRepository repository = new ClasspathRiskRuleRepository(new ObjectMapper());

        assertThat(repository.findEnabledRules())
                .extracting(RiskRuleDefinition::ruleCode)
                .containsExactly(
                        "API_COMPATIBILITY_CHECK",
                        "DB_SCHEMA_CHANGE_CHECK",
                        "DB_SQL_CHANGE_CHECK",
                        "ORM_MAPPING_CHANGE_CHECK",
                        "ENTITY_MODEL_CHANGE_CHECK",
                        "DATA_MIGRATION_CHECK",
                        "DB_SCHEMA_SYNC_SUSPECT_CHECK",
                        "CACHE_KEY_CHANGE_CHECK",
                        "CACHE_TTL_CHANGE_CHECK",
                        "CACHE_INVALIDATION_CHANGE_CHECK",
                        "CACHE_READ_WRITE_CHANGE_CHECK",
                        "CACHE_SERIALIZATION_CHANGE_CHECK",
                        "MQ_PRODUCER_CHANGE_CHECK",
                        "MQ_CONSUMER_CHANGE_CHECK",
                        "MQ_MESSAGE_SCHEMA_CHANGE_CHECK",
                        "MQ_TOPIC_CONFIG_CHANGE_CHECK",
                        "MQ_RETRY_DLQ_CHANGE_CHECK",
                        "CONFIG_RELEASE_CHECK"
                );
    }

    @Test
    void generatesRiskItemsFromAnalysisResultByConfiguredRules() throws Exception {
        ChangeAnalysisResult analysisResult = analysisService.analyze(new ChangeAnalysisRequest(List.of(
                ChangedFile.of("src/main/java/com/demo/order/OrderController.java", "+ @GetMapping(\"/api/orders/{id}\")"),
                ChangedFile.of("src/main/resources/mapper/OrderMapper.xml", "+ select id, status from orders where id = #{id}"),
                ChangedFile.of("src/main/java/com/demo/order/OrderCacheService.java", "+ redisTemplate.opsForValue().set(\"order:detail\" + id, value);")
        ), null));
        ClasspathRiskRuleRepository repository = new ClasspathRiskRuleRepository(new ObjectMapper());
        RiskCardGenerator generator = new RiskCardGenerator(repository, null);

        RiskCard card = generator.generate(analysisResult, repository.findEnabledRules(), List.of("模板级检查项"));

        assertThat(card.summary()).contains("API", "DB", "CACHE");
        assertThat(card.riskLevel()).isEqualTo(RiskLevel.HIGH);
        assertThat(card.affectedResources()).hasSize(3);
        assertThat(card.riskItems()).hasSize(3);
        assertThat(card.riskItems()).extracting(item -> item.ruleCode())
                .containsExactly("API_COMPATIBILITY_CHECK", "DB_SQL_CHANGE_CHECK", "CACHE_READ_WRITE_CHANGE_CHECK");
        assertThat(card.riskItems()).anySatisfy(item -> {
            assertThat(item.ruleCode()).isEqualTo("DB_SQL_CHANGE_CHECK");
            assertThat(item.confidence()).isEqualTo("MEDIUM");
            assertThat(item.reason()).contains("SQL");
        });
        assertThat(card.recommendedChecks()).isNotEmpty();
        assertThat(card.suggestedReviewRoles()).contains(ReviewRole.BACKEND, ReviewRole.QA);
    }

    @Test
    void usesMediumRiskForCacheReadWriteOnlyChange() throws Exception {
        ChangeAnalysisResult analysisResult = analysisService.analyze(new ChangeAnalysisRequest(List.of(
                ChangedFile.of("src/main/java/com/demo/order/OrderCacheService.java", "+ redisTemplate.opsForValue().get(\"order:detail\" + id);")
        ), null));
        ClasspathRiskRuleRepository repository = new ClasspathRiskRuleRepository(new ObjectMapper());
        RiskCardGenerator generator = new RiskCardGenerator(repository, null);

        RiskCard card = generator.generate(analysisResult, repository.findEnabledRules(), List.of("模板级检查项"));

        assertThat(card.riskLevel()).isEqualTo(RiskLevel.MEDIUM);
        assertThat(card.riskItems()).singleElement().satisfies(item -> {
            assertThat(item.category()).isEqualTo(ChangeType.CACHE_READ_WRITE);
            assertThat(item.riskLevel()).isEqualTo(RiskLevel.MEDIUM);
            assertThat(item.recommendedChecks()).anyMatch(check -> check.contains("缓存"));
            assertThat(item.confidence()).isEqualTo("MEDIUM");
        });
    }

    @Test
    void generatesHighRiskForMqMessageSchemaChange() throws Exception {
        ChangeAnalysisResult analysisResult = analysisService.analyze(new ChangeAnalysisRequest(List.of(
                ChangedFile.of("src/main/java/com/demo/order/message/OrderPaidMessage.java", "+ private String deviceModel;")
        ), null));
        ClasspathRiskRuleRepository repository = new ClasspathRiskRuleRepository(new ObjectMapper());
        RiskCardGenerator generator = new RiskCardGenerator(repository, null);

        RiskCard card = generator.generate(analysisResult, repository.findEnabledRules(), List.of());

        assertThat(card.riskLevel()).isEqualTo(RiskLevel.HIGH);
        assertThat(card.riskItems()).singleElement().satisfies(item -> {
            assertThat(item.ruleCode()).isEqualTo("MQ_MESSAGE_SCHEMA_CHANGE_CHECK");
            assertThat(item.category()).isEqualTo(ChangeType.MQ_MESSAGE_SCHEMA);
            assertThat(item.confidence()).isEqualTo("HIGH");
            assertThat(item.reason()).contains("message");
        });
    }

    @Test
    void supportsCriticalRiskLevelFromConfiguration() {
        ChangeAnalysisResult analysisResult = analysisService.analyze(new ChangeAnalysisRequest(List.of(
                ChangedFile.of("db/migration/V12__drop_orders.sql", "+ drop table orders")
        ), null));
        RiskRuleDefinition criticalRule = new RiskRuleDefinition(
                "DB_DROP_TABLE_CRITICAL_CHECK",
                ChangeType.DB_SCHEMA,
                RiskLevel.CRITICAL,
                "删除表属于 CRITICAL 风险",
                "检测到数据库高危变更，需要专项审批。",
                "可能导致数据不可恢复。",
                List.of("确认有完整备份。", "确认回滚方案经过演练。"),
                Set.of(ReviewRole.BACKEND, ReviewRole.DBA, ReviewRole.ARCHITECT)
        );
        RiskCardGenerator generator = new RiskCardGenerator(() -> List.of(criticalRule), null);

        RiskCard card = generator.generate(analysisResult, List.of(criticalRule), List.of());

        assertThat(card.riskLevel()).isEqualTo(RiskLevel.CRITICAL);
        assertThat(card.riskItems()).singleElement().satisfies(item -> {
            assertThat(item.ruleCode()).isEqualTo("DB_DROP_TABLE_CRITICAL_CHECK");
            assertThat(item.suggestedReviewRoles()).contains(ReviewRole.DBA, ReviewRole.ARCHITECT);
        });
    }

    @Test
    void returnsLowRiskCardWhenNoRiskRuleMatches() {
        ChangeAnalysisResult analysisResult = analysisService.analyze(new ChangeAnalysisRequest(List.of(
                ChangedFile.of("README.md", "+ update docs")
        ), null));
        RiskCardGenerator generator = new RiskCardGenerator(() -> List.of(), null);

        RiskCard card = generator.generate(analysisResult, List.of(), List.of());

        assertThat(card.riskLevel()).isEqualTo(RiskLevel.LOW);
        assertThat(card.riskItems()).isEmpty();
        assertThat(card.recommendedChecks()).isEmpty();
        assertThat(card.suggestedReviewRoles()).isEmpty();
    }

    @Test
    void generatesSuspectedSchemaSyncRiskFromEntityAndMappingWithoutMigration() throws Exception {
        ChangeAnalysisResult analysisResult = analysisService.analyze(new ChangeAnalysisRequest(List.of(
                ChangedFile.of("src/main/java/com/demo/car/entity/Car.java", "+ private String supportDeviceModel;"),
                ChangedFile.of("src/main/resources/mapper/CarMapper.xml", "+ <result column=\"support_device_model\" property=\"supportDeviceModel\" />")
        ), null));
        ClasspathRiskRuleRepository repository = new ClasspathRiskRuleRepository(new ObjectMapper());
        RiskCardGenerator generator = new RiskCardGenerator(repository, null);

        RiskCard card = generator.generate(analysisResult, repository.findEnabledRules(), List.of());

        assertThat(card.riskLevel()).isEqualTo(RiskLevel.HIGH);
        assertThat(card.riskItems()).extracting(RiskItem::ruleCode)
                .contains("ENTITY_MODEL_CHANGE_CHECK", "ORM_MAPPING_CHANGE_CHECK", "DB_SCHEMA_SYNC_SUSPECT_CHECK");
        assertThat(card.riskItems()).anySatisfy(item -> {
            assertThat(item.ruleCode()).isEqualTo("DB_SCHEMA_SYNC_SUSPECT_CHECK");
            assertThat(item.relatedSignals()).contains("entity model changed", "ORM/MyBatis mapping changed", "migration or DDL not detected");
            assertThat(item.affectedResources()).hasSize(2);
        });
    }
}
