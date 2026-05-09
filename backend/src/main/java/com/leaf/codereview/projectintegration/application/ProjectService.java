package com.leaf.codereview.projectintegration.application;

import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import com.leaf.codereview.projectintegration.infrastructure.ProjectRepository;
import com.leaf.codereview.codequality.application.CodeQualityReviewProfileService;
import com.leaf.codereview.ruletemplate.application.RuleTemplateService;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class ProjectService {

    private final ProjectRepository projectRepository;
    private final RuleTemplateService ruleTemplateService;
    private final CodeQualityReviewProfileService codeQualityReviewProfileService;

    public ProjectService(
            ProjectRepository projectRepository,
            RuleTemplateService ruleTemplateService,
            CodeQualityReviewProfileService codeQualityReviewProfileService
    ) {
        this.projectRepository = projectRepository;
        this.ruleTemplateService = ruleTemplateService;
        this.codeQualityReviewProfileService = codeQualityReviewProfileService;
    }

    public List<ProjectRecord> listEnabledProjects() {
        return projectRepository.findAllEnabled();
    }

    public ProjectRecord updateDefaultTemplate(Long projectId, String templateCode) {
        ruleTemplateService.getEnabledTemplate(templateCode);
        projectRepository.updateDefaultTemplate(projectId, templateCode);
        return projectRepository.findById(projectId).orElseThrow();
    }

    public ProjectRecord updateDefaultCodeQualityProfile(Long projectId, String profileCode) {
        codeQualityReviewProfileService.getProfile(profileCode);
        projectRepository.updateDefaultCodeQualityProfile(projectId, profileCode);
        return projectRepository.findById(projectId).orElseThrow();
    }
}
