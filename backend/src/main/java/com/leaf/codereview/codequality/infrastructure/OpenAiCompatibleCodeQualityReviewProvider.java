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
import org.springframework.http.HttpHeaders;
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
public class OpenAiCompatibleCodeQualityReviewProvider implements CodeQualityReviewProvider {

    private final CodeQualityModelProviderRepository providerRepository;
    private final CodeQualityReviewProperties properties;
    private final ObjectMapper objectMapper;
    private final CodeQualityReviewProgressTracker progressTracker;

    public OpenAiCompatibleCodeQualityReviewProvider(
            CodeQualityModelProviderRepository providerRepository,
            CodeQualityReviewProperties properties,
            ObjectMapper objectMapper,
            CodeQualityReviewProgressTracker progressTracker
    ) {
        this.providerRepository = providerRepository;
        this.properties = properties;
        this.objectMapper = objectMapper;
        this.progressTracker = progressTracker;
    }

    @Override
    public boolean supports(CodeQualityReviewProviderType type) {
        return type == CodeQualityReviewProviderType.DEEPSEEK || type == CodeQualityReviewProviderType.CUSTOM;
    }

    @Override
    public CodeQualityReviewProviderType type() {
        return CodeQualityReviewProviderType.DEEPSEEK;
    }

    @Override
    public CodeQualityReviewResult review(CodeQualityReviewRequest request) {
        return review(request, type());
    }

    @Override
    public CodeQualityReviewResult review(CodeQualityReviewRequest request, CodeQualityReviewProviderType providerType) {
        CodeQualityModelProvider provider = providerRepository.getRequired(providerType);
        if (!provider.enabled()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, providerType + " model provider is disabled");
        }
        String apiKey = firstText(provider.apiKey(), providerType == CodeQualityReviewProviderType.DEEPSEEK ? properties.deepSeekApiKey() : null);
        if (!StringUtils.hasText(apiKey)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, providerType + " API key is required for code quality review");
        }
        if (!StringUtils.hasText(provider.endpointUrl())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, providerType + " endpointUrl is required for code quality review");
        }
        if (!StringUtils.hasText(request.diffText())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "diffText is required for code quality review");
        }

        OffsetDateTime startedAt = OffsetDateTime.now();
        try {
            String model = firstText(request.model(), provider.modelName());
            if (!StringUtils.hasText(model)) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, providerType + " modelName is required for code quality review");
            }
            String endpoint = chatCompletionsUrl(provider.endpointUrl());
            Map<String, Object> requestBody = buildRequest(model, request);
            progressTracker.info(providerType + "_REQUEST", "准备调用 OpenAI-compatible Chat Completions API", "url=" + endpoint + ", model=" + model);
            String responseBody = restClient().post()
                    .uri(endpoint)
                    .contentType(MediaType.APPLICATION_JSON)
                    .header(HttpHeaders.AUTHORIZATION, "Bearer " + apiKey)
                    .body(requestBody)
                    .retrieve()
                    .body(String.class);
            progressTracker.info(providerType + "_RESPONSE", providerType + " API 已返回响应", "responseBytes=" + (responseBody == null ? 0 : responseBody.length()));
            String outputText = extractOutputText(responseBody);
            progressTracker.info(providerType + "_PARSED", providerType + " API 响应文本已提取", "outputBytes=" + outputText.length());
            return toResult(providerType, outputText, responseBody, startedAt);
        } catch (Exception exception) {
            progressTracker.error(providerType + "_FAILED", providerType + " API Review 执行失败", exception.getMessage());
            return CodeQualityReviewResult.failed(providerType, exception.getMessage(), null, null, startedAt, OffsetDateTime.now());
        }
    }

    private Map<String, Object> buildRequest(String model, CodeQualityReviewRequest request) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("model", model);
        body.put("stream", false);
        body.put("response_format", Map.of("type", "json_object"));
        body.put("messages", List.of(
                Map.of("role", "system", "content", systemPrompt(request)),
                Map.of("role", "user", "content", userPrompt(request))
        ));
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

    private CodeQualityReviewResult toResult(CodeQualityReviewProviderType providerType, String outputText, String responseBody, OffsetDateTime startedAt) throws JsonProcessingException {
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
                    providerType.name()
            ));
        }
        return CodeQualityReviewResult.success(
                providerType,
                card.path("overallLevel").asText(null),
                card.path("summary").asText(providerType + " review completed"),
                findings,
                responseBody,
                null,
                startedAt,
                OffsetDateTime.now()
        );
    }

    private String extractOutputText(String responseBody) throws JsonProcessingException {
        JsonNode root = objectMapper.readTree(responseBody);
        JsonNode content = root.path("choices").path(0).path("message").path("content");
        if (content.isMissingNode() || content.isNull() || !StringUtils.hasText(content.asText())) {
            throw new IllegalArgumentException("OpenAI-compatible response does not contain choices[0].message.content");
        }
        return content.asText();
    }

    private RestClient restClient() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        Duration timeout = Duration.ofSeconds(properties.openAiTimeoutSeconds());
        factory.setConnectTimeout(timeout);
        factory.setReadTimeout(timeout);
        return RestClient.builder().requestFactory(factory).build();
    }

    private String chatCompletionsUrl(String endpointUrl) {
        String trimmed = endpointUrl.trim();
        if (trimmed.endsWith("/chat/completions")) {
            return trimmed;
        }
        return trimmed.replaceAll("/+$", "") + "/chat/completions";
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
