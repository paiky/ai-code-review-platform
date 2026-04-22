package com.leaf.codereview.riskengine;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.leaf.codereview.changeanalysis.application.ChangeAnalysisService;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisRequest;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisResult;
import com.leaf.codereview.changeanalysis.domain.ChangeType;
import com.leaf.codereview.changeanalysis.domain.ChangedFile;
import com.leaf.codereview.changeanalysis.domain.ResourceType;
import com.leaf.codereview.changeanalysis.rule.ApiChangeRule;
import com.leaf.codereview.changeanalysis.rule.CacheChangeRule;
import com.leaf.codereview.changeanalysis.rule.ConfigChangeRule;
import com.leaf.codereview.changeanalysis.rule.DbChangeRule;
import com.leaf.codereview.changeanalysis.rule.MqChangeRule;
import com.leaf.codereview.riskengine.application.RiskCardGenerator;
import com.leaf.codereview.riskengine.domain.RiskCard;
import com.leaf.codereview.riskengine.infrastructure.ClasspathRiskRuleRepository;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.StreamSupport;

import static org.assertj.core.api.Assertions.assertThat;

class RiskCardSchemaTest {

    private final ObjectMapper objectMapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .build();

    private final ChangeAnalysisService analysisService = new ChangeAnalysisService(List.of(
            new ApiChangeRule(),
            new DbChangeRule(),
            new CacheChangeRule(),
            new MqChangeRule(),
            new ConfigChangeRule()
    ));

    @Test
    void documentedSchemaEnumsStayAlignedWithDomainEnums() throws Exception {
        JsonNode schema = loadDocumentedRiskCardSchema();

        assertThat(enumValues(schema.at("/$defs/changeType")))
                .containsAll(Arrays.stream(ChangeType.values()).map(Enum::name).toList());
        assertThat(enumValues(schema.at("/$defs/resourceType")))
                .containsAll(Arrays.stream(ResourceType.values()).map(Enum::name).toList());
        assertThat(enumValues(schema.at("/$defs/riskItem/properties/confidence")))
                .contains("LOW", "MEDIUM", "HIGH");
    }

    @Test
    void generatedRiskCardMatchesDocumentedShapeForDbMqAndCacheFineTypes() throws Exception {
        JsonNode schema = loadDocumentedRiskCardSchema();
        ChangeAnalysisResult analysisResult = analysisService.analyze(new ChangeAnalysisRequest(List.of(
                ChangedFile.of("src/main/resources/mapper/OrderMapper.xml", "+ select id, status from orders where id = #{id}"),
                ChangedFile.of("src/main/java/com/demo/order/OrderCacheService.java", "+ redisTemplate.delete(\"order:detail\" + id);"),
                ChangedFile.of("src/main/java/com/demo/order/message/OrderPaidMessage.java", "+ private String deviceModel;")
        ), null));
        ClasspathRiskRuleRepository repository = new ClasspathRiskRuleRepository(new ObjectMapper());
        RiskCardGenerator generator = new RiskCardGenerator(repository, null);

        RiskCard riskCard = generator.generate(analysisResult, repository.findEnabledRules(), List.of());
        JsonNode cardJson = objectMapper.valueToTree(riskCard);

        assertRequiredFieldsPresent(cardJson, schema.get("required"));
        assertThat(cardJson.path("riskItems")).hasSize(3);

        JsonNode dbItem = riskItemByCategory(cardJson, "DB_SQL");
        assertFineGrainedRiskItem(dbItem, "DB_SQL_CHANGE_CHECK", "MEDIUM");

        JsonNode cacheItem = riskItemByCategory(cardJson, "CACHE_INVALIDATION");
        assertFineGrainedRiskItem(cacheItem, "CACHE_INVALIDATION_CHANGE_CHECK", "HIGH");

        JsonNode mqItem = riskItemByCategory(cardJson, "MQ_MESSAGE_SCHEMA");
        assertFineGrainedRiskItem(mqItem, "MQ_MESSAGE_SCHEMA_CHANGE_CHECK", "HIGH");

        assertThat(changeTypesFromEvidences(cardJson))
                .contains("DB_SQL", "CACHE_INVALIDATION", "MQ_MESSAGE_SCHEMA");
    }

    private void assertFineGrainedRiskItem(JsonNode item, String ruleCode, String confidence) {
        assertThat(item.path("ruleCode").asText()).isEqualTo(ruleCode);
        assertThat(item.path("confidence").asText()).isEqualTo(confidence);
        assertThat(item.path("reason").asText()).isNotBlank();
        assertThat(item.path("relatedSignals").isArray()).isTrue();
        assertThat(item.path("evidences").isArray()).isTrue();
        assertThat(item.path("evidences")).isNotEmpty();
        assertThat(item.path("recommendedChecks")).isNotEmpty();
        assertThat(item.path("suggestedReviewRoles")).isNotEmpty();
    }

    private void assertRequiredFieldsPresent(JsonNode objectNode, JsonNode requiredFields) {
        assertThat(requiredFields.isArray()).isTrue();
        requiredFields.forEach(field -> assertThat(objectNode.has(field.asText()))
                .as("required field %s", field.asText())
                .isTrue());
    }

    private JsonNode riskItemByCategory(JsonNode cardJson, String category) {
        return StreamSupport.stream(cardJson.path("riskItems").spliterator(), false)
                .filter(item -> category.equals(item.path("category").asText()))
                .findFirst()
                .orElseThrow(() -> new AssertionError("Missing risk item category: " + category));
    }

    private Set<String> changeTypesFromEvidences(JsonNode cardJson) {
        return StreamSupport.stream(cardJson.path("affectedResources").spliterator(), false)
                .map(resource -> resource.path("evidence").path("changeType").asText())
                .filter(value -> !value.isBlank())
                .collect(Collectors.toSet());
    }

    private Set<String> enumValues(JsonNode enumNode) {
        return StreamSupport.stream(enumNode.path("enum").spliterator(), false)
                .filter(JsonNode::isTextual)
                .map(JsonNode::asText)
                .collect(Collectors.toSet());
    }

    private JsonNode loadDocumentedRiskCardSchema() throws IOException {
        String markdown = Files.readString(Path.of("..", "docs", "04-risk-card-schema.md"));
        String schemaJson = extractJsonFenceAfter(markdown, "\"title\": \"RiskCard\"");
        return objectMapper.readTree(schemaJson);
    }

    private String extractJsonFenceAfter(String markdown, String marker) {
        int markerIndex = markdown.indexOf(marker);
        assertThat(markerIndex).as("RiskCard schema marker exists").isGreaterThanOrEqualTo(0);
        int fenceStart = markdown.lastIndexOf("```json", markerIndex);
        int contentStart = markdown.indexOf('\n', fenceStart) + 1;
        int fenceEnd = markdown.indexOf("```", contentStart);
        assertThat(fenceStart).as("schema json fence start").isGreaterThanOrEqualTo(0);
        assertThat(contentStart).as("schema json content start").isGreaterThan(0);
        assertThat(fenceEnd).as("schema json fence end").isGreaterThan(contentStart);
        return markdown.substring(contentStart, fenceEnd);
    }
}
