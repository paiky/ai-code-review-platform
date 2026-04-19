package com.leaf.codereview.changeanalysis;

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
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

class ChangeAnalysisServiceTest {

    private final ChangeAnalysisService service = new ChangeAnalysisService(List.of(
            new ApiChangeRule(),
            new DbChangeRule(),
            new CacheChangeRule(),
            new MqChangeRule(),
            new ConfigChangeRule()
    ));

    @Test
    void detectsApiChangeFromSpringController() {
        ChangeAnalysisResult result = analyze(ChangedFile.of(
                "src/main/java/com/demo/order/OrderController.java",
                "+ @GetMapping(\"/api/orders/{id}\")\n+ public OrderResponse detail(@PathVariable Long id) { return service.detail(id); }"
        ));

        assertThat(result.changeTypes()).containsExactly(ChangeType.API);
        assertThat(result.impactedResources()).anySatisfy(resource -> {
            assertThat(resource.resourceType()).isEqualTo(ResourceType.API);
            assertThat(resource.name()).isEqualTo("GET /api/orders/{id}");
        });
    }

    @Test
    void detectsDbChangeFromMapperSql() {
        ChangeAnalysisResult result = analyze(ChangedFile.of(
                "src/main/resources/mapper/OrderMapper.xml",
                "+ select id, status from orders where id = #{id}"
        ));

        assertThat(result.changeTypes()).containsExactly(ChangeType.DB);
        assertThat(result.impactedResources()).anySatisfy(resource -> {
            assertThat(resource.resourceType()).isEqualTo(ResourceType.DB_TABLE);
            assertThat(resource.name()).isEqualTo("orders");
        });
    }

    @Test
    void detectsCacheChangeFromRedisUsage() {
        ChangeAnalysisResult result = analyze(ChangedFile.of(
                "src/main/java/com/demo/order/OrderCacheService.java",
                "+ redisTemplate.opsForValue().set(\"order:detail\" + id, value);"
        ));

        assertThat(result.changeTypes()).containsExactly(ChangeType.CACHE);
        assertThat(result.impactedResources()).anySatisfy(resource -> {
            assertThat(resource.resourceType()).isEqualTo(ResourceType.CACHE_KEY);
            assertThat(resource.name()).isEqualTo("order:detail");
        });
    }

    @Test
    void detectsMqChangeFromListenerAnnotation() {
        ChangeAnalysisResult result = analyze(ChangedFile.of(
                "src/main/java/com/demo/order/OrderPaidConsumer.java",
                "+ @RocketMQMessageListener(topic = \"order-paid-topic\", consumerGroup = \"order-service\")"
        ));

        assertThat(result.changeTypes()).containsExactly(ChangeType.MQ);
        assertThat(result.impactedResources()).anySatisfy(resource -> {
            assertThat(resource.resourceType()).isEqualTo(ResourceType.MQ_TOPIC);
            assertThat(resource.name()).isEqualTo("order-paid-topic");
        });
    }

    @Test
    void detectsConfigChangeFromApplicationYaml() {
        ChangeAnalysisResult result = analyze(ChangedFile.of(
                "src/main/resources/application.yml",
                "+ order:\n+   feature-enabled: true"
        ));

        assertThat(result.changeTypes()).containsExactly(ChangeType.CONFIG);
        assertThat(result.impactedResources()).anySatisfy(resource -> {
            assertThat(resource.resourceType()).isEqualTo(ResourceType.CONFIG_KEY);
            assertThat(resource.name()).isEqualTo("order");
        });
    }

    @Test
    void detectsMultipleChangeTypesAcrossFiles() {
        ChangeAnalysisResult result = service.analyze(new ChangeAnalysisRequest(List.of(
                ChangedFile.of("src/main/java/com/demo/order/OrderController.java", "+ @PostMapping(\"/api/orders\")"),
                ChangedFile.of("src/main/resources/mapper/OrderMapper.xml", "+ update orders set status = #{status}"),
                ChangedFile.of("src/main/resources/application.yml", "+ rocketmq:\n+   name-server: localhost:9876")
        ), null));

        assertThat(result.changeTypes()).containsExactlyInAnyOrder(ChangeType.API, ChangeType.DB, ChangeType.CONFIG, ChangeType.MQ);
        assertThat(result.changedFileCount()).isEqualTo(3);
        assertThat(result.changedFiles()).hasSize(3);
        assertThat(result.summary()).contains("matched change types");
    }

    @Test
    void returnsEmptyChangeTypesWhenNoRuleMatches() {
        ChangeAnalysisResult result = analyze(ChangedFile.of(
                "README.md",
                "+ update project introduction"
        ));

        assertThat(result.changeTypes()).isEmpty();
        assertThat(result.impactedResources()).isEmpty();
        assertThat(result.evidences()).isEmpty();
    }

    private ChangeAnalysisResult analyze(ChangedFile changedFile) {
        return service.analyze(new ChangeAnalysisRequest(List.of(changedFile), null));
    }
}