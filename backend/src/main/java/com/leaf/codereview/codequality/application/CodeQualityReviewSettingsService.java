package com.leaf.codereview.codequality.application;

import com.leaf.codereview.codequality.controller.CodeQualityReviewSettingsUpdateRequest;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewSettingsRepository;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import org.springframework.stereotype.Service;

@Service
public class CodeQualityReviewSettingsService {

    private final CodeQualityReviewSettingsRepository repository;

    public CodeQualityReviewSettingsService(CodeQualityReviewSettingsRepository repository) {
        this.repository = repository;
    }

    public CodeQualityReviewSettingsResponse get() {
        return repository.get();
    }

    public CodeQualityReviewSettingsResponse update(CodeQualityReviewSettingsUpdateRequest request) {
        if (request == null || !hasAnyUpdate(request)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "At least one setting is required");
        }
        return repository.update(request);
    }

    private boolean hasAnyUpdate(CodeQualityReviewSettingsUpdateRequest request) {
        return request.mrAutoReviewEnabled() != null
                || request.dingtalkNotificationEnabled() != null
                || request.defaultProviderCode() != null;
    }
}
