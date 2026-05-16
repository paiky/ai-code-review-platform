package com.leaf.codereview.codequality;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.codequality.domain.CodeQualityModelProvider;
import com.leaf.codereview.codequality.domain.CodeQualityModelProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewMode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.infrastructure.CodeQualityModelProviderRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressEventRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressTracker;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.OpenAiCompatibleCodeQualityReviewProvider;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class OpenAiCompatibleCodeQualityReviewProviderTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private HttpServer server;

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void callsChatCompletionsApiAndParsesStructuredFindings() throws IOException {
        CapturedRequest capturedRequest = new CapturedRequest();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/chat/completions", exchange -> {
            capturedRequest.authorization = exchange.getRequestHeaders().getFirst("Authorization");
            capturedRequest.body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            byte[] response = """
                    {
                      "choices": [
                        {
                          "message": {
                            "content": "{\\"summary\\":\\"发现 1 个问题\\",\\"overallLevel\\":\\"HIGH\\",\\"findings\\":[{\\"severity\\":\\"MAJOR\\",\\"category\\":\\"CORRECTNESS\\",\\"filePath\\":\\"OrderService.java\\",\\"startLine\\":8,\\"endLine\\":9,\\"title\\":\\"缺少空值校验\\",\\"body\\":\\"本次新增入口直接使用参数，空值会触发异常。\\",\\"suggestion\\":\\"补充参数校验。\\",\\"confidence\\":\\"HIGH\\"}]}"
                          }
                        }
                      ]
                    }
                    """.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        server.start();
        CodeQualityModelProviderRepository providerRepository = mock(CodeQualityModelProviderRepository.class);
        when(providerRepository.getRequired(CodeQualityReviewProviderType.DEEPSEEK)).thenReturn(new CodeQualityModelProvider(
                1L,
                CodeQualityReviewProviderType.DEEPSEEK,
                "DeepSeek",
                CodeQualityModelProviderType.OPENAI_CHAT_COMPATIBLE,
                "http://127.0.0.1:" + server.getAddress().getPort(),
                "deepseek-test",
                true,
                "db-d...-key",
                "db-deepseek-key",
                true,
                true,
                30,
                true,
                null
        ));
        OpenAiCompatibleCodeQualityReviewProvider provider = new OpenAiCompatibleCodeQualityReviewProvider(
                providerRepository,
                properties(),
                objectMapper,
                new CodeQualityReviewProgressTracker(mock(CodeQualityReviewProgressEventRepository.class))
        );

        CodeQualityReviewResult result = provider.review(new CodeQualityReviewRequest(
                null,
                CodeQualityReviewMode.DIFF_TEXT,
                "main",
                "abc123",
                "MR !2",
                null,
                "只报告会导致线上缺陷的问题",
                "+ order.getUserId().trim();",
                List.of("OrderService.java")
        ), CodeQualityReviewProviderType.DEEPSEEK);

        assertThat(result.status()).isEqualTo("SUCCESS");
        assertThat(result.provider()).isEqualTo(CodeQualityReviewProviderType.DEEPSEEK);
        assertThat(result.overallLevel()).isEqualTo("HIGH");
        assertThat(result.findings()).hasSize(1);
        assertThat(result.findings().getFirst().source()).isEqualTo("DEEPSEEK");
        assertThat(capturedRequest.authorization).isEqualTo("Bearer db-deepseek-key");
        assertThat(capturedRequest.body)
                .contains("deepseek-test", "json_object", "只报告会导致线上缺陷的问题", "OrderService.java");
    }

    private CodeQualityReviewProperties properties() {
        return new CodeQualityReviewProperties(
                true,
                CodeQualityReviewProviderType.DEEPSEEK,
                "",
                "https://api.openai.com/v1/responses",
                "gpt-5.4",
                120,
                "",
                "https://api.anthropic.com/v1/messages",
                "claude-sonnet-4-5",
                120,
                "env-deepseek-key",
                "https://api.deepseek.com",
                "deepseek-v4-pro"
        );
    }

    private static class CapturedRequest {
        String authorization;
        String body;
    }
}
