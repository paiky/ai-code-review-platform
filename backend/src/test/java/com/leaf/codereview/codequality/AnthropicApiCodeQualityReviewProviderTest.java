package com.leaf.codereview.codequality;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.codequality.domain.CodeQualityModelProvider;
import com.leaf.codereview.codequality.domain.CodeQualityModelProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewMode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.infrastructure.AnthropicApiCodeQualityReviewProvider;
import com.leaf.codereview.codequality.infrastructure.CodeQualityModelProviderRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressEventRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressTracker;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
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

class AnthropicApiCodeQualityReviewProviderTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private HttpServer server;

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void callsMessagesApiAndParsesStructuredFindings() throws IOException {
        CapturedRequest capturedRequest = new CapturedRequest();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/messages", exchange -> {
            capturedRequest.apiKey = exchange.getRequestHeaders().getFirst("x-api-key");
            capturedRequest.anthropicVersion = exchange.getRequestHeaders().getFirst("anthropic-version");
            capturedRequest.body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            byte[] response = """
                    {
                      "content": [
                        {
                          "type": "text",
                          "text": "{\\"summary\\":\\"发现 1 个问题\\",\\"overallLevel\\":\\"HIGH\\",\\"findings\\":[{\\"severity\\":\\"CRITICAL\\",\\"category\\":\\"SQL\\",\\"filePath\\":\\"OrderMapper.xml\\",\\"startLine\\":12,\\"endLine\\":14,\\"title\\":\\"缺少索引\\",\\"body\\":\\"新增查询会触发全表扫描\\",\\"suggestion\\":\\"补充联合索引\\",\\"confidence\\":\\"HIGH\\"}]}"
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
        when(providerRepository.getRequired(CodeQualityReviewProviderType.ANTHROPIC)).thenReturn(new CodeQualityModelProvider(
                1L,
                CodeQualityReviewProviderType.ANTHROPIC,
                "Anthropic",
                CodeQualityModelProviderType.ANTHROPIC_MESSAGES,
                "http://127.0.0.1:" + server.getAddress().getPort() + "/v1/messages",
                "claude-test",
                true,
                "db-a...-key",
                "db-anthropic-key",
                true,
                true,
                20,
                true,
                null
        ));
        AnthropicApiCodeQualityReviewProvider provider = new AnthropicApiCodeQualityReviewProvider(
                properties("http://127.0.0.1:" + server.getAddress().getPort() + "/v1/messages"),
                providerRepository,
                objectMapper,
                new CodeQualityReviewProgressTracker(mock(CodeQualityReviewProgressEventRepository.class))
        );

        CodeQualityReviewResult result = provider.review(new CodeQualityReviewRequest(
                null,
                CodeQualityReviewMode.DIFF_TEXT,
                "main",
                "abc123",
                "MR !1",
                null,
                "只报告会导致线上缺陷的问题",
                "+ select * from orders where user_id = ?",
                List.of("OrderMapper.xml")
        ));

        assertThat(result.status()).isEqualTo("SUCCESS");
        assertThat(result.provider()).isEqualTo(CodeQualityReviewProviderType.ANTHROPIC);
        assertThat(result.overallLevel()).isEqualTo("HIGH");
        assertThat(result.findings()).hasSize(1);
        assertThat(result.findings().getFirst().source()).isEqualTo("ANTHROPIC");
        assertThat(capturedRequest.apiKey).isEqualTo("db-anthropic-key");
        assertThat(capturedRequest.anthropicVersion).isEqualTo("2023-06-01");
        assertThat(capturedRequest.body).contains("claude-test", "只报告会导致线上缺陷的问题", "OrderMapper.xml");
    }

    private CodeQualityReviewProperties properties(String messagesUrl) {
        return new CodeQualityReviewProperties(
                true,
                CodeQualityReviewProviderType.ANTHROPIC,
                "",
                "",
                "",
                600,
                "",
                "https://api.openai.com/v1/responses",
                "gpt-5.4",
                120,
                "env-anthropic-key",
                messagesUrl,
                "claude-test",
                120
        );
    }

    private static class CapturedRequest {
        String apiKey;
        String anthropicVersion;
        String body;
    }
}
