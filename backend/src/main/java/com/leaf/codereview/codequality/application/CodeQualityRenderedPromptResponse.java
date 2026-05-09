package com.leaf.codereview.codequality.application;

public record CodeQualityRenderedPromptResponse(
        String profileCode,
        String provider,
        String model,
        String prompt,
        String promptHash,
        int promptLength
) {
}
