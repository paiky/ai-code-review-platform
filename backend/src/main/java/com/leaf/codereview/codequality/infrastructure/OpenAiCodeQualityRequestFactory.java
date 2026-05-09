package com.leaf.codereview.codequality.infrastructure;

import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Component
public class OpenAiCodeQualityRequestFactory {

    public Map<String, Object> buildRequest(CodeQualityReviewProperties properties, CodeQualityReviewRequest request) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("model", StringUtils.hasText(request.model()) ? request.model() : properties.openAiModel());
        body.put("instructions", buildInstructions(request));
        body.put("input", buildInput(request));
        body.put("text", Map.of("format", buildJsonSchemaFormat()));
        body.put("store", false);
        return body;
    }

    public String renderInstructions(CodeQualityReviewRequest request) {
        return buildInstructions(request);
    }

    private String buildInstructions(CodeQualityReviewRequest request) {
        String base = """
                You are a senior code reviewer. Review only the supplied changed code and return strict JSON.
                Focus on correctness, maintainability, security, data consistency, concurrency, transaction boundaries,
                SQL/cache/MQ misuse, exception handling, observability, and missing tests.
                Do not include markdown. Do not invent files or line numbers that are absent from the input.
                """;
        if (StringUtils.hasText(request.instructions())) {
            return base + "\nAdditional review instructions:\n" + request.instructions();
        }
        return base;
    }

    private String buildInput(CodeQualityReviewRequest request) {
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

    private Map<String, Object> buildJsonSchemaFormat() {
        return Map.of(
                "type", "json_schema",
                "name", "code_quality_review_card",
                "strict", true,
                "schema", Map.of(
                        "type", "object",
                        "additionalProperties", false,
                        "required", List.of("summary", "overallLevel", "findings"),
                        "properties", Map.of(
                                "summary", Map.of("type", "string"),
                                "overallLevel", Map.of("type", "string", "enum", List.of("LOW", "MEDIUM", "HIGH", "CRITICAL")),
                                "findings", Map.of(
                                        "type", "array",
                                        "items", Map.of(
                                                "type", "object",
                                                "additionalProperties", false,
                                                "required", List.of(
                                                        "severity", "category", "filePath", "startLine", "endLine",
                                                        "title", "body", "suggestion", "confidence"
                                                ),
                                                "properties", Map.of(
                                                        "severity", Map.of("type", "string", "enum", List.of("MINOR", "MAJOR", "CRITICAL")),
                                                        "category", Map.of("type", "string"),
                                                        "filePath", Map.of("type", "string"),
                                                        "startLine", Map.of("type", "integer"),
                                                        "endLine", Map.of("type", "integer"),
                                                        "title", Map.of("type", "string"),
                                                        "body", Map.of("type", "string"),
                                                        "suggestion", Map.of("type", "string"),
                                                        "confidence", Map.of("type", "string", "enum", List.of("LOW", "MEDIUM", "HIGH"))
                                                )
                                        )
                                )
                        )
                )
        );
    }

    private String valueOrDash(String value) {
        return StringUtils.hasText(value) ? value : "-";
    }
}
