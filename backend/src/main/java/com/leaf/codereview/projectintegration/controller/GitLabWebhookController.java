package com.leaf.codereview.projectintegration.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import com.leaf.codereview.common.response.ApiResponse;
import com.leaf.codereview.projectintegration.application.GitLabMergeRequestWebhookService;
import com.leaf.codereview.projectintegration.application.GitLabPushWebhookService;
import com.leaf.codereview.projectintegration.application.GitLabWebhookResponse;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/webhooks/gitlab")
public class GitLabWebhookController {

    private static final String MERGE_REQUEST_HOOK = "Merge Request Hook";
    private static final String PUSH_HOOK = "Push Hook";

    private final GitLabMergeRequestWebhookService mergeRequestWebhookService;
    private final GitLabPushWebhookService pushWebhookService;

    public GitLabWebhookController(
            GitLabMergeRequestWebhookService mergeRequestWebhookService,
            GitLabPushWebhookService pushWebhookService
    ) {
        this.mergeRequestWebhookService = mergeRequestWebhookService;
        this.pushWebhookService = pushWebhookService;
    }

    @PostMapping("/merge-request")
    public ApiResponse<GitLabWebhookResponse> receiveMergeRequestWebhook(
            @RequestHeader(value = "X-Gitlab-Event", required = false) String gitlabEvent,
            @RequestBody JsonNode payload
    ) {
        if (MERGE_REQUEST_HOOK.equals(gitlabEvent) || "merge_request".equals(textAt(payload, "/object_kind"))) {
            return ApiResponse.ok(mergeRequestWebhookService.handle(gitlabEvent, payload));
        }
        if (PUSH_HOOK.equals(gitlabEvent) || "push".equals(textAt(payload, "/object_kind"))) {
            return ApiResponse.ok(pushWebhookService.handle(gitlabEvent, payload));
        }
        throw new BusinessException(ErrorCode.BAD_REQUEST, "Unsupported GitLab event: " + gitlabEvent);
    }

    private String textAt(JsonNode node, String pointer) {
        if (node == null) {
            return null;
        }
        JsonNode value = node.at(pointer);
        if (value.isMissingNode() || value.isNull()) {
            return null;
        }
        return value.asText();
    }
}
