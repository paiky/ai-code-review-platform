package com.leaf.codereview.codequality;

import com.leaf.codereview.codequality.domain.CodeQualityReviewMode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.OpenAiCodeQualityRequestFactory;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class OpenAiCodeQualityRequestFactoryTest {

    private final OpenAiCodeQualityRequestFactory factory = new OpenAiCodeQualityRequestFactory();

    @Test
    void buildsResponsesApiPayloadWithStrictJsonSchema() {
        CodeQualityReviewRequest request = new CodeQualityReviewRequest(
                null,
                CodeQualityReviewMode.DIFF_TEXT,
                "main",
                null,
                "Add order flow",
                null,
                "Only report actionable findings",
                "+ public void createOrder() {}",
                List.of("OrderService.java")
        );

        Map<String, Object> body = factory.buildRequest("gpt-5.4", request);

        assertThat(body).containsEntry("model", "gpt-5.4");
        assertThat(body).containsEntry("store", false);
        assertThat((String) body.get("instructions")).contains("严格 JSON", "Only report actionable findings");
        assertThat((String) body.get("input")).contains("OrderService.java", "createOrder");
        Map<?, ?> text = (Map<?, ?>) body.get("text");
        Map<?, ?> format = (Map<?, ?>) text.get("format");
        assertThat(format.get("type")).isEqualTo("json_schema");
        assertThat(format.get("strict")).isEqualTo(true);
        assertThat(format.get("name")).isEqualTo("code_quality_review_card");
    }

    private CodeQualityReviewProperties properties() {
        return new CodeQualityReviewProperties(
                true,
                CodeQualityReviewProviderType.OPENAI,
                "",
                "",
                "",
                600,
                "test-key",
                "https://api.openai.com/v1/responses",
                "gpt-5.4",
                120,
                "",
                "https://api.anthropic.com/v1/messages",
                "claude-sonnet-4-5",
                120
        );
    }
}


