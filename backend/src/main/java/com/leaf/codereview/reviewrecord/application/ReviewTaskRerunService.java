package com.leaf.codereview.reviewrecord.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import com.leaf.codereview.projectintegration.application.GitLabMergeRequestWebhookService;
import com.leaf.codereview.projectintegration.application.GitLabPushWebhookService;
import com.leaf.codereview.projectintegration.application.GitLabWebhookResponse;
import org.springframework.stereotype.Service;

@Service
public class ReviewTaskRerunService {

    private static final String MR_TRIGGER_TYPE = "GITLAB_MR_WEBHOOK";
    private static final String PUSH_TRIGGER_TYPE = "GITLAB_PUSH_WEBHOOK";

    private final ReviewTaskQueryService reviewTaskQueryService;
    private final GitLabMergeRequestWebhookService mergeRequestWebhookService;
    private final GitLabPushWebhookService pushWebhookService;
    private final ObjectMapper objectMapper;

    public ReviewTaskRerunService(
            ReviewTaskQueryService reviewTaskQueryService,
            GitLabMergeRequestWebhookService mergeRequestWebhookService,
            GitLabPushWebhookService pushWebhookService,
            ObjectMapper objectMapper
    ) {
        this.reviewTaskQueryService = reviewTaskQueryService;
        this.mergeRequestWebhookService = mergeRequestWebhookService;
        this.pushWebhookService = pushWebhookService;
        this.objectMapper = objectMapper;
    }

    public ReviewTaskRerunResponse rerun(Long sourceTaskId) {
        ReviewTaskDetailResponse sourceTask = reviewTaskQueryService.getDetail(sourceTaskId);
        JsonNode replayPayload = replayPayload(sourceTask);
        GitLabWebhookResponse response = switch (sourceTask.triggerType()) {
            case MR_TRIGGER_TYPE -> mergeRequestWebhookService.handle("Merge Request Hook", replayPayload);
            case PUSH_TRIGGER_TYPE -> pushWebhookService.handle("Push Hook", replayPayload);
            default -> throw new BusinessException(
                    ErrorCode.BAD_REQUEST,
                    "Only GitLab MR or Push review tasks can be rerun: " + sourceTask.triggerType()
            );
        };
        return new ReviewTaskRerunResponse(sourceTaskId, response.taskId(), response.status(), sourceTask.triggerType());
    }

    private JsonNode replayPayload(ReviewTaskDetailResponse sourceTask) {
        JsonNode rawPayload = sourceTask.rawPayload();
        if (rawPayload == null || rawPayload.isNull() || rawPayload.isMissingNode() || !rawPayload.isObject()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Source task raw payload is not available");
        }
        ObjectNode payload = rawPayload.deepCopy();
        JsonNode files = sourceTask.changedFilesSummary() == null
                ? objectMapper.createArrayNode()
                : sourceTask.changedFilesSummary().path("files");
        if (files.isArray() && !files.isEmpty()) {
            payload.set("changedFiles", files.deepCopy());
        }
        enrichReplayPayload(payload, sourceTask);
        return payload;
    }

    private void enrichReplayPayload(ObjectNode payload, ReviewTaskDetailResponse sourceTask) {
        ObjectNode project = object(payload, "project");
        putIfText(project, "name", sourceTask.projectName());
        putIfText(project, "path_with_namespace", sourceTask.projectName());

        if (MR_TRIGGER_TYPE.equals(sourceTask.triggerType())) {
            ObjectNode objectAttributes = object(payload, "object_attributes");
            putIfText(objectAttributes, "iid", sourceTask.mrId());
            putIfText(objectAttributes, "url", sourceTask.externalUrl());
            putIfText(objectAttributes, "source_branch", sourceTask.sourceBranch());
            putIfText(objectAttributes, "target_branch", sourceTask.targetBranch());
            ObjectNode lastCommit = object(objectAttributes, "last_commit");
            putIfText(lastCommit, "id", sourceTask.commitSha());
        }

        ObjectNode user = object(payload, "user");
        putIfText(user, "name", sourceTask.authorName());
        putIfText(user, "username", sourceTask.authorUsername());
        putIfText(payload, "user_name", sourceTask.authorName());
        putIfText(payload, "user_username", sourceTask.authorUsername());
    }

    private ObjectNode object(ObjectNode parent, String fieldName) {
        JsonNode value = parent.get(fieldName);
        if (value instanceof ObjectNode objectNode) {
            return objectNode;
        }
        ObjectNode objectNode = objectMapper.createObjectNode();
        parent.set(fieldName, objectNode);
        return objectNode;
    }

    private void putIfText(ObjectNode node, String fieldName, String value) {
        if (value != null && !value.isBlank()) {
            node.put(fieldName, value);
        }
    }
}
