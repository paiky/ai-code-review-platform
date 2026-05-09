package com.leaf.codereview.codequality.domain;

public record CodeQualityFinding(
        String severity,
        String category,
        String filePath,
        Integer startLine,
        Integer endLine,
        String title,
        String body,
        String suggestion,
        String confidence,
        String source
) {
}
