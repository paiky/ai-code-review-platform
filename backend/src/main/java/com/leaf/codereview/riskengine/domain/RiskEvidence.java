package com.leaf.codereview.riskengine.domain;

public record RiskEvidence(
        String filePath,
        Integer lineStart,
        Integer lineEnd,
        String snippet,
        String matcher
) {
}