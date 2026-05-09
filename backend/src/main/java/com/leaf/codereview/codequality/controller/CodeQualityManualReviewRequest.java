package com.leaf.codereview.codequality.controller;

import com.leaf.codereview.codequality.domain.CodeQualityReviewMode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;

import java.util.List;

public record CodeQualityManualReviewRequest(
        Long projectId,
        String profileCode,
        String repositoryPath,
        CodeQualityReviewMode mode,
        String baseRef,
        String commitSha,
        String title,
        String model,
        String instructions,
        String diffText,
        List<String> changedFiles
) {
    public CodeQualityReviewRequest toDomain() {
        return new CodeQualityReviewRequest(
                repositoryPath,
                mode,
                baseRef,
                commitSha,
                title,
                model,
                instructions,
                diffText,
                changedFiles
        );
    }
}
