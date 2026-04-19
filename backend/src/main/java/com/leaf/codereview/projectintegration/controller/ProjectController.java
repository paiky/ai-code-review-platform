package com.leaf.codereview.projectintegration.controller;

import com.leaf.codereview.common.response.ApiResponse;
import com.leaf.codereview.common.response.PageResponse;
import com.leaf.codereview.projectintegration.application.ProjectService;
import com.leaf.codereview.projectintegration.application.UpdateProjectTemplateRequest;
import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/projects")
public class ProjectController {

    private final ProjectService projectService;

    public ProjectController(ProjectService projectService) {
        this.projectService = projectService;
    }

    @GetMapping
    public ApiResponse<PageResponse<ProjectRecord>> list() {
        List<ProjectRecord> items = projectService.listEnabledProjects();
        return ApiResponse.ok(new PageResponse<>(items, 1, items.size(), items.size()));
    }

    @PutMapping("/{projectId}/default-template")
    public ApiResponse<ProjectRecord> updateDefaultTemplate(@PathVariable Long projectId, @Valid @RequestBody UpdateProjectTemplateRequest request) {
        return ApiResponse.ok(projectService.updateDefaultTemplate(projectId, request.templateCode()));
    }
}