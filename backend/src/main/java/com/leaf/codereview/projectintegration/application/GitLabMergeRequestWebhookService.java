package com.leaf.codereview.projectintegration.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.leaf.codereview.changeanalysis.application.ChangeAnalysisService;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisRequest;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisResult;
import com.leaf.codereview.changeanalysis.domain.ChangedFile;
import com.leaf.codereview.changeanalysis.domain.FileChangeType;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import com.leaf.codereview.notification.application.DingTalkNotifier;
import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import com.leaf.codereview.notification.infrastructure.NotificationRecordRepository;
import com.leaf.codereview.projectintegration.domain.GitLabDiffFile;
import com.leaf.codereview.projectintegration.domain.GitLabMergeRequestDetail;
import com.leaf.codereview.projectintegration.domain.GitLabMergeRequestEvent;
import com.leaf.codereview.projectintegration.domain.GitLabProjectDetail;
import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import com.leaf.codereview.projectintegration.infrastructure.GitLabClient;
import com.leaf.codereview.projectintegration.infrastructure.GitLabMrWebhookEventRepository;
import com.leaf.codereview.projectintegration.infrastructure.ProjectRepository;
import com.leaf.codereview.reviewrecord.domain.ReviewTaskCreateCommand;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewResultRepository;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewTaskRepository;
import com.leaf.codereview.riskengine.application.RiskCardGenerator;
import com.leaf.codereview.riskengine.domain.RiskCard;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

@Service
public class GitLabMergeRequestWebhookService {

    private static final Logger log = LoggerFactory.getLogger(GitLabMergeRequestWebhookService.class);

    private static final String GITLAB_MR_HEADER = "Merge Request Hook";
    private static final String OBJECT_KIND = "merge_request";
    private static final String TEMPLATE_CODE = "backend-default";

    private final ObjectMapper objectMapper;
    private final ProjectRepository projectRepository;
    private final ReviewTaskRepository reviewTaskRepository;
    private final ReviewResultRepository reviewResultRepository;
    private final GitLabMrWebhookEventRepository webhookEventRepository;
    private final ChangeAnalysisService changeAnalysisService;
    private final RiskCardGenerator riskCardGenerator;
    private final DingTalkNotifier dingTalkNotifier;
    private final NotificationRecordRepository notificationRecordRepository;
    private final GitLabClient gitLabClient;

    public GitLabMergeRequestWebhookService(
            ObjectMapper objectMapper,
            ProjectRepository projectRepository,
            ReviewTaskRepository reviewTaskRepository,
            ReviewResultRepository reviewResultRepository,
            GitLabMrWebhookEventRepository webhookEventRepository,
            ChangeAnalysisService changeAnalysisService,
            RiskCardGenerator riskCardGenerator,
            DingTalkNotifier dingTalkNotifier,
            NotificationRecordRepository notificationRecordRepository,
            GitLabClient gitLabClient
    ) {
        this.objectMapper = objectMapper;
        this.projectRepository = projectRepository;
        this.reviewTaskRepository = reviewTaskRepository;
        this.reviewResultRepository = reviewResultRepository;
        this.webhookEventRepository = webhookEventRepository;
        this.changeAnalysisService = changeAnalysisService;
        this.riskCardGenerator = riskCardGenerator;
        this.dingTalkNotifier = dingTalkNotifier;
        this.notificationRecordRepository = notificationRecordRepository;
        this.gitLabClient = gitLabClient;
    }

    @Transactional(noRollbackFor = Exception.class)
    public GitLabWebhookResponse handle(String gitlabEventHeader, JsonNode payload) {
        validateGitLabMergeRequestEvent(gitlabEventHeader, payload);

        GitLabMergeRequestEvent event = enrichWithGitLabDetail(parseEvent(payload));
        ProjectRecord project = projectRepository.upsertGitLabProject(
                event.gitProjectId(),
                event.projectName(),
                event.repositoryUrl()
        );

        Long taskId = reviewTaskRepository.create(new ReviewTaskCreateCommand(
                project.id(),
                "GITLAB_MR_WEBHOOK",
                event.mrId(),
                event.externalUrl(),
                event.sourceBranch(),
                event.targetBranch(),
                event.commitSha(),
                null,
                null,
                event.authorName(),
                event.authorUsername(),
                project.defaultTemplateCode(),
                "RUNNING"
        ));
        webhookEventRepository.save(taskId, event);

        try {
            GitLabMergeRequestEvent eventWithChangedFiles = resolveChangedFiles(taskId, event);
            processReviewTask(taskId, project.id(), project.defaultTemplateCode(), eventWithChangedFiles);
            return new GitLabWebhookResponse(taskId, "SUCCESS", event.gitProjectId(), event.projectName(), event.mrId());
        } catch (Exception exception) {
            reviewTaskRepository.markFailed(taskId, exception.getMessage());
            if (exception instanceof RuntimeException runtimeException) {
                throw runtimeException;
            }
            throw new BusinessException(ErrorCode.INTERNAL_ERROR, exception.getMessage());
        }
    }

    private GitLabMergeRequestEvent resolveChangedFiles(Long taskId, GitLabMergeRequestEvent event) {
        if ("payload".equals(textAt(event.changedFilesSummary(), "/source"))) {
            return event;
        }

        List<GitLabDiffFile> diffFiles = gitLabClient.listMergeRequestDiffs(event.gitProjectId(), event.mrId());
        if (diffFiles.isEmpty()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "GitLab MR diffs response is empty");
        }

        JsonNode changedFilesSummary = buildGitLabChangedFilesSummary(diffFiles);
        webhookEventRepository.updateChangedFilesSummary(taskId, changedFilesSummary);
        return copyWithChangedFilesSummary(event, changedFilesSummary);
    }

    private GitLabMergeRequestEvent enrichWithGitLabDetail(GitLabMergeRequestEvent event) {
        if ("payload".equals(textAt(event.changedFilesSummary(), "/source"))) {
            return event;
        }

        try {
            GitLabProjectDetail projectDetail = gitLabClient.getProjectDetail(event.gitProjectId());
            GitLabMergeRequestDetail mergeRequestDetail = gitLabClient.getMergeRequestDetail(event.gitProjectId(), event.mrId());
            return copyWithGitLabDetail(event, projectDetail, mergeRequestDetail);
        } catch (Exception exception) {
            log.warn("Failed to enrich GitLab MR detail for projectId={}, mrId={}: {}",
                    event.gitProjectId(), event.mrId(), exception.getMessage());
            return event;
        }
    }

    private void processReviewTask(Long taskId, Long projectId, String templateCode, GitLabMergeRequestEvent event) {
        ChangeAnalysisResult analysisResult = changeAnalysisService.analyze(toAnalysisRequest(event));
        RiskCard riskCard = riskCardGenerator.generate(analysisResult, templateCode);
        Long resultId = reviewResultRepository.save(taskId, projectId, templateCode, analysisResult, riskCard);
        reviewTaskRepository.markSuccess(taskId, riskCard.riskLevel().name());
        DingTalkNotificationResult notificationResult = dingTalkNotifier.sendRiskCard(taskId, riskCard);
        notificationRecordRepository.saveDingTalkRecord(taskId, resultId, notificationResult);
    }

    private ChangeAnalysisRequest toAnalysisRequest(GitLabMergeRequestEvent event) {
        List<ChangedFile> files = new ArrayList<>();
        JsonNode fileNodes = event.changedFilesSummary().path("files");
        if (fileNodes.isArray()) {
            for (JsonNode fileNode : fileNodes) {
                String path = firstText(fileNode, "/path", "/newPath", "/new_path", "/oldPath", "/old_path");
                String oldPath = firstText(fileNode, "/oldPath", "/old_path", "/path");
                String newPath = firstText(fileNode, "/newPath", "/new_path", "/path");
                String diffText = firstText(fileNode, "/diffText", "/diff", "/patch");
                files.add(new ChangedFile(path, oldPath, newPath, parseFileChangeType(firstText(fileNode, "/changeType", "/change_type")), diffText));
            }
        }
        return new ChangeAnalysisRequest(files, null);
    }

    private FileChangeType parseFileChangeType(String value) {
        if (!StringUtils.hasText(value)) {
            return FileChangeType.UNKNOWN;
        }
        try {
            return FileChangeType.valueOf(value.toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException exception) {
            return FileChangeType.UNKNOWN;
        }
    }

    private void validateGitLabMergeRequestEvent(String gitlabEventHeader, JsonNode payload) {
        if (payload == null || payload.isNull() || payload.isMissingNode()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Webhook payload is required");
        }
        if (StringUtils.hasText(gitlabEventHeader) && !GITLAB_MR_HEADER.equals(gitlabEventHeader)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "X-Gitlab-Event must be Merge Request Hook");
        }
        String objectKind = textAt(payload, "/object_kind");
        if (!OBJECT_KIND.equals(objectKind)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "object_kind must be merge_request");
        }
        if (!StringUtils.hasText(textAt(payload, "/project/id"))
                && !StringUtils.hasText(textAt(payload, "/object_attributes/target_project_id"))) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "GitLab project id is required");
        }
        if (!StringUtils.hasText(textAt(payload, "/object_attributes/iid"))
                && !StringUtils.hasText(textAt(payload, "/object_attributes/id"))) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Merge request id is required");
        }
    }

    private GitLabMergeRequestEvent parseEvent(JsonNode payload) {
        String gitProjectId = firstText(payload, "/project/id", "/object_attributes/target_project_id");
        String projectName = firstText(payload, "/project/name", "/project/path_with_namespace");
        if (!StringUtils.hasText(projectName)) {
            projectName = "gitlab-project-" + gitProjectId;
        }

        return new GitLabMergeRequestEvent(
                gitProjectId,
                projectName,
                firstText(payload, "/project/web_url", "/repository/homepage"),
                firstText(payload, "/object_attributes/iid", "/object_attributes/id"),
                textAt(payload, "/object_attributes/action"),
                parseEventTime(firstText(payload, "/object_attributes/updated_at", "/object_attributes/created_at", "/event_time")),
                textAt(payload, "/object_attributes/url"),
                textAt(payload, "/object_attributes/source_branch"),
                textAt(payload, "/object_attributes/target_branch"),
                firstText(payload, "/object_attributes/last_commit/id", "/object_attributes/last_commit/sha", "/checkout_sha"),
                firstText(payload, "/user/name", "/user_username", "/object_attributes/author/name"),
                firstText(payload, "/user/username", "/user_username", "/object_attributes/author/username"),
                buildPayloadChangedFilesSummary(payload),
                payload.deepCopy()
        );
    }

    private JsonNode buildPayloadChangedFilesSummary(JsonNode payload) {
        JsonNode changedFiles = firstArray(payload,
                "/changedFiles",
                "/changed_files",
                "/object_attributes/changed_files",
                "/changes/changed_files/current"
        );

        ObjectNode summary = objectMapper.createObjectNode();
        ArrayNode files = objectMapper.createArrayNode();
        String source = "not_provided";

        if (changedFiles != null) {
            source = "payload";
            for (JsonNode fileNode : changedFiles) {
                files.add(normalizeChangedFile(fileNode));
            }
        }

        summary.put("count", files.size());
        summary.put("source", source);
        summary.set("files", files);
        return summary;
    }

    private JsonNode buildGitLabChangedFilesSummary(List<GitLabDiffFile> diffFiles) {
        ObjectNode summary = objectMapper.createObjectNode();
        ArrayNode files = objectMapper.createArrayNode();
        for (GitLabDiffFile diffFile : diffFiles) {
            files.add(normalizeGitLabDiffFile(diffFile));
        }

        summary.put("count", files.size());
        summary.put("source", "gitlab_api");
        summary.set("files", files);
        return summary;
    }

    private ObjectNode normalizeGitLabDiffFile(GitLabDiffFile diffFile) {
        ObjectNode file = objectMapper.createObjectNode();
        String path = StringUtils.hasText(diffFile.newPath()) ? diffFile.newPath() : diffFile.oldPath();
        file.put("path", path);
        file.put("oldPath", diffFile.oldPath());
        file.put("newPath", diffFile.newPath());
        file.put("changeType", inferGitLabChangeType(diffFile));
        if (StringUtils.hasText(diffFile.diffText())) {
            file.put("diffText", diffFile.diffText());
        }
        file.put("collapsed", diffFile.collapsed());
        file.put("tooLarge", diffFile.tooLarge());
        return file;
    }

    private String inferGitLabChangeType(GitLabDiffFile diffFile) {
        if (diffFile.newFile()) {
            return "ADDED";
        }
        if (diffFile.deletedFile()) {
            return "DELETED";
        }
        if (diffFile.renamedFile()) {
            return "RENAMED";
        }
        return "MODIFIED";
    }

    private GitLabMergeRequestEvent copyWithChangedFilesSummary(GitLabMergeRequestEvent event, JsonNode changedFilesSummary) {
        return new GitLabMergeRequestEvent(
                event.gitProjectId(),
                event.projectName(),
                event.repositoryUrl(),
                event.mrId(),
                event.eventAction(),
                event.eventTime(),
                event.externalUrl(),
                event.sourceBranch(),
                event.targetBranch(),
                event.commitSha(),
                event.authorName(),
                event.authorUsername(),
                changedFilesSummary,
                event.rawPayload()
        );
    }

    private GitLabMergeRequestEvent copyWithGitLabDetail(
            GitLabMergeRequestEvent event,
            GitLabProjectDetail projectDetail,
            GitLabMergeRequestDetail mergeRequestDetail
    ) {
        return new GitLabMergeRequestEvent(
                event.gitProjectId(),
                firstNonBlank(projectDetail == null ? null : projectDetail.pathWithNamespace(),
                        projectDetail == null ? null : projectDetail.name(),
                        event.projectName()),
                firstNonBlank(projectDetail == null ? null : projectDetail.webUrl(), event.repositoryUrl()),
                firstNonBlank(mergeRequestDetail == null ? null : mergeRequestDetail.iid(), event.mrId()),
                event.eventAction(),
                event.eventTime(),
                firstNonBlank(mergeRequestDetail == null ? null : mergeRequestDetail.webUrl(), event.externalUrl()),
                firstNonBlank(mergeRequestDetail == null ? null : mergeRequestDetail.sourceBranch(), event.sourceBranch()),
                firstNonBlank(mergeRequestDetail == null ? null : mergeRequestDetail.targetBranch(), event.targetBranch()),
                firstNonBlank(mergeRequestDetail == null ? null : mergeRequestDetail.commitSha(), event.commitSha()),
                firstNonBlank(mergeRequestDetail == null ? null : mergeRequestDetail.authorName(), event.authorName()),
                firstNonBlank(mergeRequestDetail == null ? null : mergeRequestDetail.authorUsername(), event.authorUsername()),
                event.changedFilesSummary(),
                event.rawPayload()
        );
    }

    private ObjectNode normalizeChangedFile(JsonNode fileNode) {
        ObjectNode file = objectMapper.createObjectNode();
        if (fileNode.isTextual()) {
            String path = fileNode.asText();
            file.put("path", path);
            file.put("oldPath", path);
            file.put("newPath", path);
            file.put("changeType", "UNKNOWN");
            return file;
        }

        String oldPath = firstText(fileNode, "/old_path", "/oldPath", "/path");
        String newPath = firstText(fileNode, "/new_path", "/newPath", "/path", "/filePath");
        String path = StringUtils.hasText(newPath) ? newPath : oldPath;
        file.put("path", path);
        file.put("oldPath", oldPath);
        file.put("newPath", newPath);
        file.put("changeType", inferChangeType(fileNode));
        String diffText = firstText(fileNode, "/diffText", "/diff", "/patch");
        if (StringUtils.hasText(diffText)) {
            file.put("diffText", diffText);
        }
        return file;
    }

    private String inferChangeType(JsonNode fileNode) {
        if (booleanAt(fileNode, "/new_file") || booleanAt(fileNode, "/newFile")) {
            return "ADDED";
        }
        if (booleanAt(fileNode, "/deleted_file") || booleanAt(fileNode, "/deletedFile")) {
            return "DELETED";
        }
        if (booleanAt(fileNode, "/renamed_file") || booleanAt(fileNode, "/renamedFile")) {
            return "RENAMED";
        }
        String explicit = firstText(fileNode, "/changeType", "/change_type", "/status");
        return StringUtils.hasText(explicit) ? explicit.toUpperCase(Locale.ROOT) : "MODIFIED";
    }

    private LocalDateTime parseEventTime(String rawValue) {
        if (!StringUtils.hasText(rawValue)) {
            return LocalDateTime.now(ZoneOffset.UTC);
        }
        try {
            return OffsetDateTime.parse(rawValue).toLocalDateTime();
        } catch (Exception ignored) {
        }
        try {
            return LocalDateTime.parse(rawValue, DateTimeFormatter.ISO_LOCAL_DATE_TIME);
        } catch (Exception ignored) {
        }
        try {
            return ZonedDateTime.parse(rawValue, DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss z", Locale.ENGLISH)).toLocalDateTime();
        } catch (Exception ignored) {
        }
        return LocalDateTime.now(ZoneOffset.UTC);
    }

    private JsonNode firstArray(JsonNode node, String... pointers) {
        for (String pointer : pointers) {
            JsonNode value = node.at(pointer);
            if (value.isArray()) {
                return value;
            }
        }
        return null;
    }

    private String firstText(JsonNode node, String... pointers) {
        for (String pointer : pointers) {
            String value = textAt(node, pointer);
            if (StringUtils.hasText(value)) {
                return value;
            }
        }
        return null;
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (StringUtils.hasText(value)) {
                return value;
            }
        }
        return null;
    }

    private String textAt(JsonNode node, String pointer) {
        JsonNode value = node.at(pointer);
        if (value.isMissingNode() || value.isNull()) {
            return null;
        }
        return value.asText();
    }

    private boolean booleanAt(JsonNode node, String pointer) {
        JsonNode value = node.at(pointer);
        return !value.isMissingNode() && value.asBoolean(false);
    }
}
