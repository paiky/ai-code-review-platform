package com.leaf.codereview.codequality.infrastructure;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.codequality.application.CodeQualityReviewProvider;
import com.leaf.codereview.codequality.domain.CodeQualityFinding;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Component
public class OpenAiApiCodeQualityReviewProvider implements CodeQualityReviewProvider {

    private final CodeQualityReviewProperties properties;
    private final OpenAiCodeQualityRequestFactory requestFactory;
    private final ObjectMapper objectMapper;
    private final CodeQualityReviewProgressTracker progressTracker;
    private final CodeQualityReviewSettingsRepository settingsRepository;

    public OpenAiApiCodeQualityReviewProvider(
            CodeQualityReviewProperties properties,
            OpenAiCodeQualityRequestFactory requestFactory,
            ObjectMapper objectMapper,
            CodeQualityReviewProgressTracker progressTracker,
            CodeQualityReviewSettingsRepository settingsRepository
    ) {
        this.properties = properties;
        this.requestFactory = requestFactory;
        this.objectMapper = objectMapper;
        this.progressTracker = progressTracker;
        this.settingsRepository = settingsRepository;
    }

    @Override
    public CodeQualityReviewProviderType type() {
        return CodeQualityReviewProviderType.OPENAI_API;
    }

    @Override
    public CodeQualityReviewResult review(CodeQualityReviewRequest request) {
        String apiKey = effectiveApiKey();
        if (!StringUtils.hasText(apiKey)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "OPENAI_API_KEY is required for OpenAI API code quality review");
        }
        if (!StringUtils.hasText(request.diffText())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "diffText is required for OpenAI API code quality review");
        }

        OffsetDateTime startedAt = OffsetDateTime.now();
        try {
            Map<String, Object> requestBody = requestFactory.buildRequest(properties, request);
            String requestJson = objectMapper.writeValueAsString(requestBody);
            progressTracker.info("OPENAI_REQUEST", "准备调用 OpenAI Responses API", "url=" + properties.openAiResponsesUrl() + ", model=" + firstText(request.model(), properties.openAiModel()));
            progressTracker.debug("OPENAI_REQUEST_DEBUG", "OpenAI 请求摘要", requestDebugDetail(request, requestJson));
            progressTracker.debug("OPENAI_REQUEST_PREVIEW", "OpenAI 请求预览", abbreviate(requestJson, 3000));
            String responseBody = restClient().post()
                    .uri(properties.openAiResponsesUrl())
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + apiKey)
                    .body(requestBody)
                    .retrieve()
                    .body(String.class);
            progressTracker.info("OPENAI_RESPONSE", "OpenAI API 已返回响应", "responseBytes=" + (responseBody == null ? 0 : responseBody.length()));
            progressTracker.debug("OPENAI_RESPONSE_DEBUG", "OpenAI 响应摘要", "responseBytes=" + (responseBody == null ? 0 : responseBody.length()));
            progressTracker.debug("OPENAI_RESPONSE_RAW", "OpenAI 原始响应预览", abbreviate(responseBody, 3000));
            String outputText = extractOutputText(responseBody);
            progressTracker.info("OPENAI_PARSED", "OpenAI API 响应文本已提取", "outputBytes=" + outputText.length());
            progressTracker.debug("OPENAI_OUTPUT_TEXT", "OpenAI 输出文本预览", abbreviate(outputText, 3000));
            CodeQualityReviewResult result = toResult(outputText, responseBody, startedAt);
            progressTracker.debug("OPENAI_PARSE_RESULT", "OpenAI 解析结果", "findingCount=" + result.findings().size() + ", overallLevel=" + firstText(result.overallLevel(), "-"));
            return result;
        } catch (Exception exception) {
            progressTracker.error("OPENAI_FAILED", "OpenAI API Review 执行失败", exception.getMessage());
            return CodeQualityReviewResult.failed(type(), exception.getMessage(), null, null, startedAt, OffsetDateTime.now());
        }
    }

    private RestClient restClient() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        Duration timeout = Duration.ofSeconds(properties.openAiTimeoutSeconds());
        factory.setConnectTimeout(timeout);
        factory.setReadTimeout(timeout);
        return RestClient.builder().requestFactory(factory).build();
    }

    private CodeQualityReviewResult toResult(String outputText, String responseBody, OffsetDateTime startedAt) throws JsonProcessingException {
        JsonNode card = objectMapper.readTree(outputText);
        List<CodeQualityFinding> findings = new ArrayList<>();
        for (JsonNode finding : card.path("findings")) {
            findings.add(new CodeQualityFinding(
                    finding.path("severity").asText(),
                    finding.path("category").asText(),
                    finding.path("filePath").asText(),
                    finding.path("startLine").isMissingNode() ? null : finding.path("startLine").asInt(),
                    finding.path("endLine").isMissingNode() ? null : finding.path("endLine").asInt(),
                    finding.path("title").asText(),
                    finding.path("body").asText(),
                    finding.path("suggestion").asText(),
                    finding.path("confidence").asText(),
                    "OPENAI_API"
            ));
        }
        return CodeQualityReviewResult.success(
                type(),
                card.path("overallLevel").asText(null),
                card.path("summary").asText("OpenAI API review completed"),
                findings,
                responseBody,
                null,
                startedAt,
                OffsetDateTime.now()
        );
    }

    private String extractOutputText(String responseBody) throws JsonProcessingException {
        JsonNode root = objectMapper.readTree(responseBody);
        if (root.hasNonNull("output_text")) {
            return root.path("output_text").asText();
        }
        for (JsonNode output : root.path("output")) {
            for (JsonNode content : output.path("content")) {
                if (content.hasNonNull("text")) {
                    return content.path("text").asText();
                }
            }
        }
        throw new IllegalArgumentException("OpenAI response does not contain output text");
    }

    private String firstText(String primary, String fallback) {
        return StringUtils.hasText(primary) ? primary : fallback;
    }

    private String requestDebugDetail(CodeQualityReviewRequest request, String requestJson) {
        int diffBytes = request.diffText() == null ? 0 : request.diffText().getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
        int changedFileCount = request.changedFiles() == null ? 0 : request.changedFiles().size();
        return "url=" + properties.openAiResponsesUrl()
                + ", model=" + firstText(request.model(), properties.openAiModel())
                + ", mode=" + request.mode()
                + ", baseRef=" + firstText(request.baseRef(), "-")
                + ", changedFiles=" + changedFileCount
                + ", diffBytes=" + diffBytes
                + ", requestBytes=" + (requestJson == null ? 0 : requestJson.getBytes(java.nio.charset.StandardCharsets.UTF_8).length);
    }

    private String abbreviate(String value, int maxLength) {
        if (!StringUtils.hasText(value)) {
            return "";
        }
        if (value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength) + "\n... truncated, totalChars=" + value.length();
    }

    private String effectiveApiKey() {
        String configured = settingsRepository.openAiApiKey();
        return StringUtils.hasText(configured) ? configured : properties.openAiApiKey();
    }
}
