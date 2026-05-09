package com.leaf.codereview.codequality.domain;

import java.util.List;

public record CodeQualityReviewRequest(
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
}
