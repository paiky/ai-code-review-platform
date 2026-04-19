package com.leaf.codereview.projectintegration.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.leaf.codereview.common.response.ApiResponse;
import com.leaf.codereview.projectintegration.application.GitLabMergeRequestWebhookService;
import com.leaf.codereview.projectintegration.application.GitLabWebhookResponse;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/webhooks/gitlab")
public class GitLabWebhookController {

    private final GitLabMergeRequestWebhookService webhookService;

    public GitLabWebhookController(GitLabMergeRequestWebhookService webhookService) {
        this.webhookService = webhookService;
    }

    @PostMapping("/merge-request")
    public ApiResponse<GitLabWebhookResponse> receiveMergeRequestWebhook(
            @RequestHeader(value = "X-Gitlab-Event", required = false) String gitlabEvent,
            @RequestBody JsonNode payload
    ) {
        return ApiResponse.ok(webhookService.handle(gitlabEvent, payload));
    }
}