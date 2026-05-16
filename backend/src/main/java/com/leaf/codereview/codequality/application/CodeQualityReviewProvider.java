package com.leaf.codereview.codequality.application;

import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;

public interface CodeQualityReviewProvider {

    CodeQualityReviewProviderType type();

    default boolean supports(CodeQualityReviewProviderType type) {
        return type() == type;
    }

    default CodeQualityReviewResult review(CodeQualityReviewRequest request, CodeQualityReviewProviderType providerType) {
        return review(request);
    }

    CodeQualityReviewResult review(CodeQualityReviewRequest request);
}
