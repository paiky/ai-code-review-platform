package com.leaf.codereview.projectintegration.application;

import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import com.leaf.codereview.projectintegration.infrastructure.ProjectRepository;
import com.leaf.codereview.ruletemplate.application.RuleTemplateService;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class ProjectService {

    private final ProjectRepository projectRepository;
    private final RuleTemplateService ruleTemplateService;

    public ProjectService(ProjectRepository projectRepository, RuleTemplateService ruleTemplateService) {
        this.projectRepository = projectRepository;
        this.ruleTemplateService = ruleTemplateService;
    }

    public List<ProjectRecord> listEnabledProjects() {
        return projectRepository.findAllEnabled();
    }

    public ProjectRecord updateDefaultTemplate(Long projectId, String templateCode) {
        ruleTemplateService.getEnabledTemplate(templateCode);
        projectRepository.updateDefaultTemplate(projectId, templateCode);
        return projectRepository.findById(projectId).orElseThrow();
    }
}