package com.leaf.codereview.codequality.infrastructure;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.codequality.domain.CodeQualityFinding;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Component
public class CodexCliOutputParser {

    private static final Pattern FINDING_START_PATTERN = Pattern.compile(
            "^\\s*(?:(?:[-*]|\\d+[.)])\\s*)?(Critical|High|Medium|Low|Major|Minor|严重|高风险|中风险|低风险)\\s*[:：]\\s*(.+)$",
            Pattern.CASE_INSENSITIVE
    );
    private static final Pattern MARKDOWN_LINK_PATTERN = Pattern.compile("\\[[^]]+]\\(<?([^)>\r\n]+)>?\\)");
    private static final Pattern LINE_SUFFIX_PATTERN = Pattern.compile("^(.*):(\\d+)$");

    private final ObjectMapper objectMapper;

    public CodexCliOutputParser(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public String failureMessage(String rawOutput, String stderr) {
        String codexError = extractCodexError(rawOutput);
        if (StringUtils.hasText(codexError)) {
            return codexError;
        }
        if (StringUtils.hasText(stderr)) {
            return stderr;
        }
        return "Codex CLI review failed";
    }

    public List<CodeQualityFinding> findings(String rawOutput) {
        if (!StringUtils.hasText(rawOutput)) {
            return List.of();
        }
        List<CodeQualityFinding> findings = new ArrayList<>();
        String currentSeverity = null;
        StringBuilder currentBody = new StringBuilder();
        for (String line : rawOutput.lines().toList()) {
            String trimmedLine = line.trim();
            if (trimmedLine.startsWith("**")) {
                appendFinding(findings, currentSeverity, currentBody.toString());
                currentSeverity = null;
                currentBody = new StringBuilder();
                continue;
            }
            Matcher matcher = FINDING_START_PATTERN.matcher(line);
            if (matcher.matches()) {
                appendFinding(findings, currentSeverity, currentBody.toString());
                currentSeverity = normalizeSeverity(matcher.group(1));
                currentBody = new StringBuilder(matcher.group(2).trim());
                continue;
            }
            if (currentSeverity != null && StringUtils.hasText(trimmedLine) && !looksLikeListItem(trimmedLine)) {
                currentBody.append('\n').append(trimmedLine);
            }
        }
        appendFinding(findings, currentSeverity, currentBody.toString());
        return findings;
    }

    public String overallLevel(List<CodeQualityFinding> findings) {
        if (findings == null || findings.isEmpty()) {
            return null;
        }
        if (findings.stream().anyMatch(finding -> "CRITICAL".equals(finding.severity()))) {
            return "CRITICAL";
        }
        if (findings.stream().anyMatch(finding -> "HIGH".equals(finding.severity()))) {
            return "HIGH";
        }
        if (findings.stream().anyMatch(finding -> "MEDIUM".equals(finding.severity()))) {
            return "MEDIUM";
        }
        return "LOW";
    }

    public String summary(String rawOutput, List<CodeQualityFinding> findings) {
        if (findings != null && !findings.isEmpty()) {
            return "发现 " + findings.size() + " 个 Codex 代码质量问题";
        }
        if (!StringUtils.hasText(rawOutput)) {
            return "Codex CLI review completed";
        }
        return rawOutput.lines()
                .filter(StringUtils::hasText)
                .findFirst()
                .orElse("Codex CLI review completed");
    }

    private void appendFinding(List<CodeQualityFinding> findings, String severity, String body) {
        if (!StringUtils.hasText(severity) || !StringUtils.hasText(body)) {
            return;
        }
        Location location = extractLocation(body);
        findings.add(new CodeQualityFinding(
                severity,
                "CODE_QUALITY",
                location.filePath(),
                location.line(),
                location.line(),
                title(body),
                body,
                null,
                "MEDIUM",
                "CODEX_CLI"
        ));
    }

    private Location extractLocation(String body) {
        Matcher linkMatcher = MARKDOWN_LINK_PATTERN.matcher(body);
        if (!linkMatcher.find()) {
            return new Location(null, null);
        }
        String target = linkMatcher.group(1);
        Matcher lineMatcher = LINE_SUFFIX_PATTERN.matcher(target);
        if (!lineMatcher.matches()) {
            return new Location(target, null);
        }
        try {
            return new Location(lineMatcher.group(1), Integer.parseInt(lineMatcher.group(2)));
        } catch (NumberFormatException ignored) {
            return new Location(target, null);
        }
    }

    private String title(String body) {
        String withoutLinks = body.replaceAll("\\[([^]]+)]\\(<?[^)>]+>?\\)", "$1");
        int sentenceEnd = withoutLinks.indexOf('.');
        String title = sentenceEnd > 0 ? withoutLinks.substring(0, sentenceEnd) : withoutLinks;
        return title.length() <= 160 ? title : title.substring(0, 157) + "...";
    }

    private String normalizeSeverity(String severity) {
        return switch (severity.toLowerCase(Locale.ROOT)) {
            case "critical" -> "CRITICAL";
            case "high", "major" -> "HIGH";
            case "medium", "minor" -> "MEDIUM";
            case "严重" -> "CRITICAL";
            case "高风险" -> "HIGH";
            case "中风险" -> "MEDIUM";
            case "低风险" -> "LOW";
            default -> "LOW";
        };
    }

    private boolean looksLikeListItem(String line) {
        return line.startsWith("- ") || line.startsWith("* ") || line.matches("^\\d+[.)]\\s+.*");
    }

    private String extractCodexError(String rawOutput) {
        if (!StringUtils.hasText(rawOutput)) {
            return null;
        }
        return rawOutput.lines()
                .map(this::parseCodexErrorLine)
                .filter(StringUtils::hasText)
                .findFirst()
                .orElse(null);
    }

    private String parseCodexErrorLine(String line) {
        try {
            JsonNode node = objectMapper.readTree(line);
            String type = node.path("type").asText();
            if ("error".equals(type)) {
                return cleanMessage(node.path("message").asText());
            }
            if ("turn.failed".equals(type)) {
                return cleanMessage(node.path("error").path("message").asText());
            }
        } catch (Exception ignored) {
            return null;
        }
        return null;
    }

    private String cleanMessage(String message) {
        if (!StringUtils.hasText(message)) {
            return null;
        }
        try {
            JsonNode node = objectMapper.readTree(message);
            String detail = node.path("detail").asText();
            if (StringUtils.hasText(detail)) {
                return detail;
            }
        } catch (Exception ignored) {
            // Codex sometimes emits plain text and sometimes a JSON string.
        }
        return message;
    }

    private record Location(String filePath, Integer line) {
    }
}
