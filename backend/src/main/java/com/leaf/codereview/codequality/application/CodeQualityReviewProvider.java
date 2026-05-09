package com.leaf.codereview.codequality.application;

import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;

public interface CodeQualityReviewProvider {

    CodeQualityReviewProviderType type();

    CodeQualityReviewResult review(CodeQualityReviewRequest request);
}
