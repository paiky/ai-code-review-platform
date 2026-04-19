package com.leaf.codereview.changeanalysis.domain;

public record ChangeEvidence(
        ChangeType changeType,
        String filePath,
        Integer lineStart,
        Integer lineEnd,
        String snippet,
        String matcher
) {
}