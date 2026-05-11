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
                你是资深后端代码质量审核助手。只审查用户提供的 diff，必须返回严格 JSON，不要 Markdown。
                JSON 字段名和枚举值保持英文；summary、title、body、suggestion 必须使用简体中文。
                只报告本次变更引入的、可执行的代码质量问题，不报告历史存量问题。
                重点关注正确性、数据一致性、安全、事务边界、SQL 性能、缓存一致性、MQ 一致性、异常处理、可观测性和关键测试缺口。
                不报告纯代码风格、命名偏好、格式、注释或主观重构建议。
                不要编造输入中不存在的文件或行号；缺少证据时不要报告，除非潜在影响很高且必须人工确认。
                你可以参考上下文，但最终只能报告由 changed files 白名单中的 diff 引入的问题。
                """;
        if (StringUtils.hasText(request.instructions())) {
            return base + "\n用户自定义审核规则：\n" + request.instructions();
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
