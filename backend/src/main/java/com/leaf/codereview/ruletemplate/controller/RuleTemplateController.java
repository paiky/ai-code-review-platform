package com.leaf.codereview.ruletemplate.controller;

import com.leaf.codereview.common.response.ApiResponse;
import com.leaf.codereview.common.response.PageResponse;
import com.leaf.codereview.ruletemplate.application.RuleTemplateService;
import com.leaf.codereview.ruletemplate.domain.ReviewTemplateDefinition;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/rule-templates")
public class RuleTemplateController {

    private final RuleTemplateService ruleTemplateService;

    public RuleTemplateController(RuleTemplateService ruleTemplateService) {
        this.ruleTemplateService = ruleTemplateService;
    }

    @GetMapping
    public ApiResponse<PageResponse<ReviewTemplateDefinition>> list() {
        List<ReviewTemplateDefinition> items = ruleTemplateService.listEnabledTemplates();
        return ApiResponse.ok(new PageResponse<>(items, 1, items.size(), items.size()));
    }

    @GetMapping("/{templateCode}")
    public ApiResponse<ReviewTemplateDefinition> detail(@PathVariable String templateCode) {
        return ApiResponse.ok(ruleTemplateService.getEnabledTemplate(templateCode));
    }
}