package com.leaf.codereview.ruletemplate.application;

import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import com.leaf.codereview.ruletemplate.domain.ReviewTemplateDefinition;
import com.leaf.codereview.ruletemplate.infrastructure.RuleTemplateRepository;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;

@Service
public class RuleTemplateService {

    public static final String DEFAULT_TEMPLATE_CODE = "backend-default";

    private final RuleTemplateRepository ruleTemplateRepository;

    public RuleTemplateService(RuleTemplateRepository ruleTemplateRepository) {
        this.ruleTemplateRepository = ruleTemplateRepository;
    }

    public List<ReviewTemplateDefinition> listEnabledTemplates() {
        return ruleTemplateRepository.findEnabledTemplates();
    }

    public ReviewTemplateDefinition getEnabledTemplate(String templateCode) {
        String resolvedCode = StringUtils.hasText(templateCode) ? templateCode : DEFAULT_TEMPLATE_CODE;
        return ruleTemplateRepository.findLatestEnabledByCode(resolvedCode)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND, "Review template not found: " + resolvedCode));
    }
}