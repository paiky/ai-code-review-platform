package com.leaf.codereview.codequality.application;

import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class CodeQualityReviewService {

    private final CodeQualityReviewProperties properties;
    private final List<CodeQualityReviewProvider> providers;

    public CodeQualityReviewService(CodeQualityReviewProperties properties, List<CodeQualityReviewProvider> providers) {
        this.properties = properties;
        this.providers = providers;
    }

    public CodeQualityReviewResult review(CodeQualityReviewRequest request) {
        return review(request, null);
    }

    public CodeQualityReviewResult review(CodeQualityReviewRequest request, CodeQualityReviewProviderType providerType) {
        if (!properties.enabled()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Code quality review is disabled");
        }
        CodeQualityReviewProviderType selectedProvider = providerType == null ? properties.provider() : providerType;
        return providers.stream()
                .filter(provider -> provider.supports(selectedProvider))
                .findFirst()
                .orElseThrow(() -> new BusinessException(ErrorCode.BAD_REQUEST, "Unsupported code quality review provider: " + selectedProvider))
                .review(request, selectedProvider);
    }
}
