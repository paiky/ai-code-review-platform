package com.leaf.codereview.codequality.application;

import com.leaf.codereview.codequality.controller.CodeQualityModelProviderUpdateRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.infrastructure.CodeQualityModelProviderRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewSettingsRepository;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;

@Service
public class CodeQualityModelProviderService {

    private final CodeQualityModelProviderRepository providerRepository;
    private final CodeQualityReviewSettingsRepository settingsRepository;

    public CodeQualityModelProviderService(
            CodeQualityModelProviderRepository providerRepository,
            CodeQualityReviewSettingsRepository settingsRepository
    ) {
        this.providerRepository = providerRepository;
        this.settingsRepository = settingsRepository;
    }

    public List<CodeQualityModelProviderResponse> list() {
        return providerRepository.findAllResponses();
    }

    public List<CodeQualityModelProviderResponse> update(String providerCode, CodeQualityModelProviderUpdateRequest request) {
        CodeQualityReviewProviderType type = providerCode(providerCode);
        if (request == null || !hasAnyUpdate(request)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "At least one provider setting is required");
        }
        providerRepository.update(type, request);
        return list();
    }

    public CodeQualityReviewSettingsResponse setDefault(String providerCode) {
        CodeQualityReviewProviderType type = providerCode(providerCode);
        providerRepository.getRequired(type);
        return settingsRepository.updateDefaultProvider(type);
    }

    private boolean hasAnyUpdate(CodeQualityModelProviderUpdateRequest request) {
        return request.providerName() != null
                || request.endpointUrl() != null
                || request.modelName() != null
                || request.apiKey() != null
                || request.clearApiKey() != null
                || request.enabled() != null;
    }

    private CodeQualityReviewProviderType providerCode(String providerCode) {
        if (!StringUtils.hasText(providerCode)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "providerCode is required");
        }
        try {
            return CodeQualityReviewProviderType.valueOf(providerCode.trim());
        } catch (IllegalArgumentException exception) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Unsupported model provider: " + providerCode);
        }
    }
}
