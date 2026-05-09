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
import com.leaf.codereview.notification.domain.DingTalkMessageContext;
import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import com.leaf.codereview.notification.infrastructure.NotificationRecordRepository;
import com.leaf.codereview.projectintegration.domain.GitLabDiffFile;
import com.leaf.codereview.projectintegration.domain.GitLabPushEvent;
import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import com.leaf.codereview.projectintegration.infrastructure.GitLabClient;
import com.leaf.codereview.projectintegration.infrastructure.GitLabPushWebhookEventRepository;
import com.leaf.codereview.projectintegration.infrastructure.ProjectRepository;
import com.leaf.codereview.reviewrecord.domain.ReviewTaskCreateCommand;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewResultRepository;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewTaskRepository;
import com.leaf.codereview.riskengine.application.RiskCardGenerator;
import com.leaf.codereview.riskengine.domain.RiskCard;
import com.leaf.codereview.ruletemplate.application.RuleTemplateService;
import com.leaf.codereview.ruletemplate.domain.ReviewTemplateDefinition;
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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

@Service
public class GitLabPushWebhookService {

    private static final Logger log = LoggerFactory.getLogger(GitLabPushWebhookService.class);

    private static final String GITLAB_PUSH_HEADER = "Push Hook";
    private static final String OBJECT_KIND = "push";

    private final ObjectMapper objectMapper;
    private final ProjectRepository projectRepository;
    private final ReviewTaskRepository reviewTaskRepository;
    private final ReviewResultRepository reviewResultRepository;
    private final GitLabPushWebhookEventRepository pushEventRepository;
    private final ChangeAnalysisService changeAnalysisService;
    private final RiskCardGenerator riskCardGenerator;
    private final DingTalkNotifier dingTalkNotifier;
    private final NotificationRecordRepository notificationRecordRepository;
    private final RuleTemplateService ruleTemplateService;
    private final GitLabClient gitLabClient;

    public GitLabPushWebhookService(
            ObjectMapper objectMapper,
            ProjectRepository projectRepository,
            ReviewTaskRepository reviewTaskRepository,
            ReviewResultRepository reviewResultRepository,
            GitLabPushWebhookEventRepository pushEventRepository,
            ChangeAnalysisService changeAnalysisService,
            RiskCardGenerator riskCardGenerator,
            DingTalkNotifier dingTalkNotifier,
            NotificationRecordRepository notificationRecordRepository,
            RuleTemplateService ruleTemplateService,
            GitLabClient gitLabClient
    ) {
        this.objectMapper = objectMapper;
        this.projectRepository = projectRepository;
        this.reviewTaskRepository = reviewTaskRepository;
        this.reviewResultRepository = reviewResultRepository;
        this.pushEventRepository = pushEventRepository;
        this.changeAnalysisService = changeAnalysisService;
        this.riskCardGenerator = riskCardGenerator;
        this.dingTalkNotifier = dingTalkNotifier;
        this.notificationRecordRepository = notificationRecordRepository;
        this.ruleTemplateService = ruleTemplateService;
        this.gitLabClient = gitLabClient;
    }

    @Transactional(noRollbackFor = Exception.class)
    public GitLabWebhookResponse handle(String gitlabEventHeader, JsonNode payload) {
        validateGitLabPushEvent(gitlabEventHeader, payload);

        GitLabPushEvent event = resolveChangedFiles(parseEvent(payload));
        ProjectRecord project = projectRepository.upsertGitLabProject(
                event.gitProjectId(),
                event.projectName(),
                event.repositoryUrl()
        );

        Long taskId = reviewTaskRepository.create(new ReviewTaskCreateCommand(
                project.id(),
                "GITLAB_PUSH_WEBHOOK",
                event.afterSha(),
                event.externalUrl(),
                event.branchName(),
                null,
                event.afterSha(),
                event.beforeSha(),
                event.afterSha(),
                event.authorName(),
                event.authorUsername(),
                project.defaultTemplateCode(),
                "RUNNING"
        ));
        pushEventRepository.save(taskId, event);

        try {
            processReviewTask(taskId, project.id(), project.defaultTemplateCode(), event);
            return new GitLabWebhookResponse(taskId, "SUCCESS", event.gitProjectId(), event.projectName(), null);
        } catch (Exception exception) {
            reviewTaskRepository.markFailed(taskId, exception.getMessage());
            if (exception instanceof RuntimeException runtimeException) {
                throw runtimeException;
            }
            throw new BusinessException(ErrorCode.INTERNAL_ERROR, exception.getMessage());
        }
    }

    private void processReviewTask(Long taskId, Long projectId, String templateCode, GitLabPushEvent event) {
        ReviewTemplateDefinition template = ruleTemplateService.getEnabledTemplate(templateCode);
        ChangeAnalysisResult analysisResult = changeAnalysisService.analyze(toAnalysisRequest(event));
        RiskCard riskCard = riskCardGenerator.generate(analysisResult, templateCode);
        Long resultId = reviewResultRepository.save(taskId, projectId, templateCode, analysisResult, riskCard);
        reviewTaskRepository.markSuccess(taskId, riskCard.riskLevel().name());
        DingTalkNotificationResult notificationResult = dingTalkNotifier.sendRiskCard(taskId, riskCard, template.focusChangeTypes(), new DingTalkMessageContext(
                "GitLab Push " + nullToEmpty(event.branchName()) + " " + abbreviate(event.afterSha(), 8),
                event.authorName(),
                event.authorUsername(),
                event.branchName(),
                null,
                event.externalUrl()
        ));
        notificationRecordRepository.saveDingTalkRecord(taskId, resultId, notificationResult);
    }

    private ChangeAnalysisRequest toAnalysisRequest(GitLabPushEvent event) {
        List<ChangedFile> files = new ArrayList<>();
        JsonNode fileNodes = event.changedFilesSummary().path("files");
        if (fileNodes.isArray()) {
            for (JsonNode fileNode : fileNodes) {
                String path = firstText(fileNode, "/path", "/newPath", "/oldPath");
                String oldPath = firstText(fileNode, "/oldPath", "/path");
                String newPath = firstText(fileNode, "/newPath", "/path");
                String diffText = firstText(fileNode, "/diffText", "/diff", "/patch");
                files.add(new ChangedFile(path, oldPath, newPath, parseFileChangeType(textAt(fileNode, "/changeType")), diffText));
            }
        }
        return new ChangeAnalysisRequest(files, null);
    }

    private GitLabPushEvent resolveChangedFiles(GitLabPushEvent event) {
        JsonNode fallbackSummary = event.changedFilesSummary();
        try {
            List<GitLabDiffFile> diffFiles = gitLabClient.compare(event.gitProjectId(), event.beforeSha(), event.afterSha());
            if (diffFiles.isEmpty()) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "GitLab compare diff response is empty");
            }
            return copyWithChangedFilesSummary(event, buildGitLabCompareChangedFilesSummary(event, diffFiles));
        } catch (Exception exception) {
            log.warn("Failed to fetch GitLab compare diff for projectId={}, beforeSha={}, afterSha={}; fallback to push payload: {}",
                    event.gitProjectId(), event.beforeSha(), event.afterSha(), exception.getMessage());
            ObjectNode fallbackWithReason = fallbackSummary.deepCopy();
            fallbackWithReason.put("fallbackReason", exception.getMessage());
            return copyWithChangedFilesSummary(event, fallbackWithReason);
        }
    }

    private void validateGitLabPushEvent(String gitlabEventHeader, JsonNode payload) {
        if (payload == null || payload.isNull() || payload.isMissingNode()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Webhook payload is required");
        }
        if (StringUtils.hasText(gitlabEventHeader) && !GITLAB_PUSH_HEADER.equals(gitlabEventHeader)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "X-Gitlab-Event must be Push Hook");
        }
        if (!OBJECT_KIND.equals(textAt(payload, "/object_kind"))) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "object_kind must be push");
        }
        if (!StringUtils.hasText(firstText(payload, "/project/id", "/project_id"))) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "GitLab project id is required");
        }
        if (!StringUtils.hasText(textAt(payload, "/after"))) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "GitLab push after sha is required");
        }
    }

    private GitLabPushEvent parseEvent(JsonNode payload) {
        String gitProjectId = firstText(payload, "/project/id", "/project_id");
        String projectName = firstText(payload, "/project/path_with_namespace", "/project/name");
        if (!StringUtils.hasText(projectName)) {
            projectName = "gitlab-project-" + gitProjectId;
        }
        String afterSha = textAt(payload, "/after");
        String repositoryUrl = firstText(payload, "/project/web_url", "/repository/homepage", "/repository/git_http_url");
        String externalUrl = buildExternalUrl(repositoryUrl, afterSha);
        return new GitLabPushEvent(
                gitProjectId,
                projectName,
                repositoryUrl,
                textAt(payload, "/ref"),
                branchName(textAt(payload, "/ref")),
                textAt(payload, "/before"),
                afterSha,
                parseEventTime(firstText(payload, "/event_time", "/head_commit/timestamp")),
                externalUrl,
                firstText(payload, "/user_name", "/user/name", "/commits/0/author/name"),
                firstText(payload, "/user_username", "/user/username", "/user_email"),
                buildPushChangedFilesSummary(payload),
                payload.deepCopy()
        );
    }

    private JsonNode buildPushChangedFilesSummary(JsonNode payload) {
        Map<String, ObjectNode> filesByPath = new LinkedHashMap<>();
        JsonNode commits = payload.path("commits");
        if (commits.isArray()) {
            for (JsonNode commit : commits) {
                addCommitFiles(filesByPath, commit.path("added"), FileChangeType.ADDED);
                addCommitFiles(filesByPath, commit.path("modified"), FileChangeType.MODIFIED);
                addCommitFiles(filesByPath, commit.path("removed"), FileChangeType.DELETED);
            }
        }

        ObjectNode summary = objectMapper.createObjectNode();
        ArrayNode files = objectMapper.createArrayNode();
        filesByPath.values().forEach(files::add);
        summary.put("count", files.size());
        summary.put("source", "push_payload");
        summary.put("commitCount", commits.isArray() ? commits.size() : 0);
        summary.put("ref", textAt(payload, "/ref"));
        summary.put("beforeSha", textAt(payload, "/before"));
        summary.put("afterSha", textAt(payload, "/after"));
        summary.set("files", files);
        return summary;
    }

    private JsonNode buildGitLabCompareChangedFilesSummary(GitLabPushEvent event, List<GitLabDiffFile> diffFiles) {
        ObjectNode summary = objectMapper.createObjectNode();
        ArrayNode files = objectMapper.createArrayNode();
        for (GitLabDiffFile diffFile : diffFiles) {
            files.add(normalizeGitLabDiffFile(diffFile));
        }

        summary.put("count", files.size());
        summary.put("source", "gitlab_compare_api");
        summary.put("ref", event.ref());
        summary.put("beforeSha", event.beforeSha());
        summary.put("afterSha", event.afterSha());
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

    private GitLabPushEvent copyWithChangedFilesSummary(GitLabPushEvent event, JsonNode changedFilesSummary) {
        return new GitLabPushEvent(
                event.gitProjectId(),
                event.projectName(),
                event.repositoryUrl(),
                event.ref(),
                event.branchName(),
                event.beforeSha(),
                event.afterSha(),
                event.eventTime(),
                event.externalUrl(),
                event.authorName(),
                event.authorUsername(),
                changedFilesSummary,
                event.rawPayload()
        );
    }

    private void addCommitFiles(Map<String, ObjectNode> filesByPath, JsonNode filePaths, FileChangeType changeType) {
        if (!filePaths.isArray()) {
            return;
        }
        for (JsonNode filePathNode : filePaths) {
            String path = filePathNode.asText();
            if (!StringUtils.hasText(path)) {
                continue;
            }
            ObjectNode file = objectMapper.createObjectNode();
            file.put("path", path);
            if (changeType == FileChangeType.ADDED) {
                file.putNull("oldPath");
            } else {
                file.put("oldPath", path);
            }
            if (changeType == FileChangeType.DELETED) {
                file.putNull("newPath");
            } else {
                file.put("newPath", path);
            }
            file.put("changeType", changeType.name());
            filesByPath.put(path, file);
        }
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

    private String buildExternalUrl(String repositoryUrl, String afterSha) {
        if (!StringUtils.hasText(repositoryUrl) || !StringUtils.hasText(afterSha)) {
            return repositoryUrl;
        }
        return repositoryUrl.replaceAll("/+$", "") + "/-/commit/" + afterSha;
    }

    private String branchName(String ref) {
        if (!StringUtils.hasText(ref)) {
            return null;
        }
        String prefix = "refs/heads/";
        if (ref.startsWith(prefix)) {
            return ref.substring(prefix.length());
        }
        return ref;
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

    private String firstText(JsonNode node, String... pointers) {
        for (String pointer : pointers) {
            String value = textAt(node, pointer);
            if (StringUtils.hasText(value)) {
                return value;
            }
        }
        return null;
    }

    private String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private String abbreviate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value == null ? "" : value;
        }
        return value.substring(0, maxLength);
    }

    private String textAt(JsonNode node, String pointer) {
        JsonNode value = node.at(pointer);
        if (value.isMissingNode() || value.isNull()) {
            return null;
        }
        return value.asText();
    }
}
