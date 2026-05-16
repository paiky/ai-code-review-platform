package com.leaf.codereview.codequality.infrastructure;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.codequality.application.CodeQualityReviewProvider;
import com.leaf.codereview.codequality.domain.CodeQualityFinding;
import com.leaf.codereview.codequality.domain.CodeQualityModelProvider;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Component
public class AnthropicApiCodeQualityReviewProvider implements CodeQualityReviewProvider {

    private final CodeQualityReviewProperties properties;
    private final CodeQualityModelProviderRepository providerRepository;
    private final ObjectMapper objectMapper;
    private final CodeQualityReviewProgressTracker progressTracker;

    public AnthropicApiCodeQualityReviewProvider(
            CodeQualityReviewProperties properties,
            CodeQualityModelProviderRepository providerRepository,
            ObjectMapper objectMapper,
            CodeQualityReviewProgressTracker progressTracker
    ) {
        this.properties = properties;
        this.providerRepository = providerRepository;
        this.objectMapper = objectMapper;
        this.progressTracker = progressTracker;
    }

    @Override
    public CodeQualityReviewProviderType type() {
        return CodeQualityReviewProviderType.ANTHROPIC;
    }

    @Override
    public CodeQualityReviewResult review(CodeQualityReviewRequest request) {
        CodeQualityModelProvider modelProvider = providerRepository.getRequired(type());
        String apiKey = firstText(modelProvider.apiKey(), properties.anthropicApiKey());
        if (!StringUtils.hasText(apiKey)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "ANTHROPIC_API_KEY is required for Anthropic API code quality review");
        }
        if (!modelProvider.enabled()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Anthropic model provider is disabled");
        }
        if (!StringUtils.hasText(request.diffText())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "diffText is required for Anthropic API code quality review");
        }

        OffsetDateTime startedAt = OffsetDateTime.now();
        try {
            String endpointUrl = firstText(modelProvider.endpointUrl(), properties.anthropicMessagesUrl());
            String model = firstText(request.model(), firstText(modelProvider.modelName(), properties.anthropicModel()));
            progressTracker.info("ANTHROPIC_REQUEST", "准备调用 Anthropic Messages API", "url=" + endpointUrl + ", model=" + model);
            String responseBody = restClient().post()
                    .uri(endpointUrl)
                    .contentType(MediaType.APPLICATION_JSON)
                    .header("x-api-key", apiKey)
                    .header("anthropic-version", "2023-06-01")
                    .body(buildRequest(model, request))
                    .retrieve()
                    .body(String.class);
            progressTracker.info("ANTHROPIC_RESPONSE", "Anthropic API 已返回响应", "responseBytes=" + (responseBody == null ? 0 : responseBody.length()));
            String outputText = extractOutputText(responseBody);
            progressTracker.info("ANTHROPIC_PARSED", "Anthropic API 响应文本已提取", "outputBytes=" + outputText.length());
            return toResult(outputText, responseBody, startedAt);
        } catch (Exception exception) {
            progressTracker.error("ANTHROPIC_FAILED", "Anthropic API Review 执行失败", exception.getMessage());
            return CodeQualityReviewResult.failed(type(), exception.getMessage(), null, null, startedAt, OffsetDateTime.now());
        }
    }

    private Map<String, Object> buildRequest(String model, CodeQualityReviewRequest request) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("model", model);
        body.put("max_tokens", 4096);
        body.put("system", systemPrompt(request));
        body.put("messages", List.of(Map.of(
                "role", "user",
                "content", userPrompt(request)
        )));
        return body;
    }

    private String systemPrompt(CodeQualityReviewRequest request) {
        String instructions = StringUtils.hasText(request.instructions()) ? request.instructions() : "只报告可执行的代码质量问题。";
        return """
                你是资深代码质量审核助手。只审查用户提供的 diff，不要编造不存在的文件或行号。
                必须只返回 JSON，不要 Markdown，不要代码块。
                JSON 字段必须为 summary、overallLevel、findings。
                findings 每项字段必须为 severity、category、filePath、startLine、endLine、title、body、suggestion、confidence。
                severity 只能是 MINOR、MAJOR、CRITICAL；overallLevel 只能是 LOW、MEDIUM、HIGH、CRITICAL；confidence 只能是 LOW、MEDIUM、HIGH。
                你可以参考上下文，但最终只能报告由 changed files 白名单中的 diff 引入的问题。

                用户自定义审核规则：
                %s
                """.formatted(instructions);
    }

    private String userPrompt(CodeQualityReviewRequest request) {
        return """
                Review mode: %s
                Base ref: %s
                Commit sha: %s
                Title: %s
                Changed files: %s

                Diff:
                %s
                """.formatted(
                request.mode(),
                valueOrDash(request.baseRef()),
                valueOrDash(request.commitSha()),
                valueOrDash(request.title()),
                request.changedFiles() == null ? List.of() : request.changedFiles(),
                valueOrDash(request.diffText())
        );
    }

    private RestClient restClient() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        Duration timeout = Duration.ofSeconds(properties.anthropicTimeoutSeconds());
        factory.setConnectTimeout(timeout);
        factory.setReadTimeout(timeout);
        return RestClient.builder().requestFactory(factory).build();
    }

    private CodeQualityReviewResult toResult(String outputText, String responseBody, OffsetDateTime startedAt) throws JsonProcessingException {
        JsonNode card = objectMapper.readTree(stripJsonFence(outputText));
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
                    "ANTHROPIC"
            ));
        }
        return CodeQualityReviewResult.success(
                type(),
                card.path("overallLevel").asText(null),
                card.path("summary").asText("Anthropic API review completed"),
                findings,
                responseBody,
                null,
                startedAt,
                OffsetDateTime.now()
        );
    }

    private String extractOutputText(String responseBody) throws JsonProcessingException {
        JsonNode root = objectMapper.readTree(responseBody);
        StringBuilder builder = new StringBuilder();
        for (JsonNode content : root.path("content")) {
            if ("text".equals(content.path("type").asText()) && content.hasNonNull("text")) {
                builder.append(content.path("text").asText());
            }
        }
        if (builder.isEmpty()) {
            throw new IllegalArgumentException("Anthropic response does not contain text content");
        }
        return builder.toString();
    }

    private String stripJsonFence(String value) {
        String trimmed = value == null ? "" : value.trim();
        if (trimmed.startsWith("```")) {
            trimmed = trimmed.replaceFirst("^```(?:json)?\\s*", "");
            trimmed = trimmed.replaceFirst("\\s*```$", "");
        }
        return trimmed;
    }

    private String firstText(String primary, String fallback) {
        return StringUtils.hasText(primary) ? primary : fallback;
    }

    private String valueOrDash(String value) {
        return StringUtils.hasText(value) ? value : "-";
    }
}
