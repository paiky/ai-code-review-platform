package com.leaf.codereview.codequality.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewMode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProfile;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressTracker;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewResultRepository;
import com.leaf.codereview.notification.application.DingTalkNotifier;
import com.leaf.codereview.notification.domain.DingTalkMessageContext;
import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import com.leaf.codereview.notification.infrastructure.NotificationRecordRepository;
import com.leaf.codereview.projectintegration.domain.GitLabMergeRequestEvent;
import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import com.leaf.codereview.riskengine.domain.RiskCard;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

@Service
public class CodeQualityAsyncReviewExecutor {

    private static final Logger log = LoggerFactory.getLogger(CodeQualityAsyncReviewExecutor.class);

    private final CodeQualityReviewProgressTracker progressTracker;
    private final CodeQualityReviewService reviewService;
    private final CodeQualityReviewResultRepository resultRepository;
    private final DingTalkNotifier dingTalkNotifier;
    private final NotificationRecordRepository notificationRecordRepository;

    public CodeQualityAsyncReviewExecutor(
            CodeQualityReviewProgressTracker progressTracker,
            CodeQualityReviewService reviewService,
            CodeQualityReviewResultRepository resultRepository,
            DingTalkNotifier dingTalkNotifier,
            NotificationRecordRepository notificationRecordRepository
    ) {
        this.progressTracker = progressTracker;
        this.reviewService = reviewService;
        this.resultRepository = resultRepository;
        this.dingTalkNotifier = dingTalkNotifier;
        this.notificationRecordRepository = notificationRecordRepository;
    }

    @Async
    public void execute(Long taskId, ProjectRecord project, GitLabMergeRequestEvent event, CodeQualityReviewProfile profile, CodeQualityReviewProviderType provider) {
        execute(taskId, project, event, profile, provider, null, null, List.of(), null);
    }

    @Async
    public void execute(
            Long taskId,
            ProjectRecord project,
            GitLabMergeRequestEvent event,
            CodeQualityReviewProfile profile,
            CodeQualityReviewProviderType provider,
            Long ruleResultId,
            RiskCard riskCard,
            Collection<String> focusChangeTypes,
            DingTalkMessageContext notificationContext
    ) {
        progressTracker.runWithTask(taskId, () -> executeInternal(taskId, project, event, profile, provider, ruleResultId, riskCard, focusChangeTypes, notificationContext));
    }

    private void executeInternal(
            Long taskId,
            ProjectRecord project,
            GitLabMergeRequestEvent event,
            CodeQualityReviewProfile profile,
            CodeQualityReviewProviderType provider,
            Long ruleResultId,
            RiskCard riskCard,
            Collection<String> focusChangeTypes,
            DingTalkMessageContext notificationContext
    ) {
        progressTracker.info("STARTED", "AI Review 异步执行线程已启动", "project=" + project.name() + ", mr=!" + event.mrId() + ", profileCode=" + profile.profileCode());
        CodeQualityReviewRequest request = buildRequest(project, event, profile, provider);
        progressTracker.info("REQUEST_BUILT", "AI Review 请求已构建", "profileCode=" + profile.profileCode() + ", provider=" + provider.name() + ", model=" + request.model() + ", mode=" + request.mode() + ", baseRef=" + request.baseRef() + ", changedFiles=" + request.changedFiles().size());

        try {
            progressTracker.info("PROVIDER_START", "开始调用代码质量 Review Provider", "provider=" + provider.name());
            CodeQualityReviewResult result = reviewService.review(request, provider);
            progressTracker.info("SAVE_RESULT", "Provider 执行完成，开始保存结果", "status=" + result.status() + ", findingCount=" + result.findings().size());
            Long resultId = resultRepository.save(taskId, project.id(), profile.profileCode(), request.model(), result);
            sendNotification(taskId, notificationResultId(ruleResultId, resultId), event, riskCard, focusChangeTypes, notificationContext, result);
            progressTracker.info("FINISHED", "AI Review 结果已保存", "status=" + result.status() + ", overallLevel=" + result.overallLevel());
        } catch (Exception exception) {
            log.warn("AI code review failed for taskId={}: {}", taskId, exception.getMessage());
            progressTracker.error("FAILED", "AI Review 执行失败", exception.getMessage());
            Long resultId = saveFailed(taskId, project.id(), profile, provider, exception.getMessage());
            CodeQualityReviewResult failedResult = CodeQualityReviewResult.failed(
                    provider,
                    exception.getMessage(),
                    null,
                    null,
                    OffsetDateTime.now(),
                    OffsetDateTime.now()
            );
            sendNotification(taskId, notificationResultId(ruleResultId, resultId), event, riskCard, focusChangeTypes, notificationContext, failedResult);
        }
    }

    private CodeQualityReviewRequest buildRequest(ProjectRecord project, GitLabMergeRequestEvent event, CodeQualityReviewProfile profile, CodeQualityReviewProviderType provider) {
        CodeQualityReviewMode mode = CodeQualityReviewMode.DIFF_TEXT;
        return new CodeQualityReviewRequest(
                null,
                mode,
                baseRef(event.targetBranch()),
                event.commitSha(),
                "GitLab MR !" + event.mrId() + " " + nullToEmpty(event.sourceBranch()) + " -> " + nullToEmpty(event.targetBranch()),
                profile.model(),
                provider == CodeQualityReviewProviderType.CODEX_CLI ? profile.codexPrompt() : profile.openAiInstructions(),
                buildDiffText(event.changedFilesSummary()),
                changedFilePaths(event.changedFilesSummary())
        );
    }

    private String buildDiffText(JsonNode changedFilesSummary) {
        StringBuilder builder = new StringBuilder();
        JsonNode files = changedFilesSummary.path("files");
        if (!files.isArray()) {
            return "";
        }
        for (JsonNode file : files) {
            String path = firstText(file, "path", "newPath", "new_path", "oldPath", "old_path");
            String diffText = firstText(file, "diffText", "diff", "patch");
            if (!StringUtils.hasText(diffText)) {
                continue;
            }
            builder.append("File: ").append(path).append('\n');
            builder.append(diffText).append("\n\n");
        }
        return builder.toString();
    }

    private List<String> changedFilePaths(JsonNode changedFilesSummary) {
        List<String> paths = new ArrayList<>();
        JsonNode files = changedFilesSummary.path("files");
        if (files.isArray()) {
            for (JsonNode file : files) {
                String path = firstText(file, "path", "newPath", "new_path", "oldPath", "old_path");
                if (StringUtils.hasText(path)) {
                    paths.add(path);
                }
            }
        }
        return paths;
    }

    private Long saveFailed(Long taskId, Long projectId, CodeQualityReviewProfile profile, CodeQualityReviewProviderType provider, String errorMessage) {
        progressTracker.error("SAVE_FAILED", "保存失败状态", errorMessage);
        CodeQualityReviewResult result = CodeQualityReviewResult.failed(
                provider,
                errorMessage,
                null,
                null,
                OffsetDateTime.now(),
                OffsetDateTime.now()
        );
        return resultRepository.save(taskId, projectId, profile.profileCode(), profile.model(), result);
    }

    private void sendNotification(
            Long taskId,
            Long resultId,
            GitLabMergeRequestEvent event,
            RiskCard riskCard,
            Collection<String> focusChangeTypes,
            DingTalkMessageContext notificationContext,
            CodeQualityReviewResult result
    ) {
        try {
            DingTalkMessageContext context = notificationContext == null ? defaultContext(event) : notificationContext;
            DingTalkNotificationResult notificationResult = dingTalkNotifier.sendReviewSummary(taskId, riskCard, focusChangeTypes, result, context);
            notificationRecordRepository.saveDingTalkRecord(taskId, resultId, notificationResult);
            progressTracker.info("NOTIFICATION_SENT", "AI Review 钉钉通知已处理", "status=" + notificationResult.status());
        } catch (Exception exception) {
            log.warn("AI code review notification failed for taskId={}: {}", taskId, exception.getMessage());
            progressTracker.warn("NOTIFICATION_FAILED", "AI Review 钉钉通知失败", exception.getMessage());
        }
    }

    private Long notificationResultId(Long ruleResultId, Long codeQualityResultId) {
        return ruleResultId == null ? codeQualityResultId : ruleResultId;
    }

    private DingTalkMessageContext defaultContext(GitLabMergeRequestEvent event) {
        return new DingTalkMessageContext(
                "MR !" + event.mrId() + " " + nullToEmpty(event.sourceBranch()) + " -> " + nullToEmpty(event.targetBranch()),
                event.authorName(),
                event.authorUsername(),
                event.sourceBranch(),
                event.targetBranch(),
                event.externalUrl()
        );
    }

    private String baseRef(String targetBranch) {
        if (!StringUtils.hasText(targetBranch)) {
            return "origin/main";
        }
        return targetBranch.startsWith("origin/") ? targetBranch : "origin/" + targetBranch;
    }

    private String firstText(JsonNode node, String... fields) {
        for (String field : fields) {
            JsonNode value = node.path(field);
            if (!value.isMissingNode() && !value.isNull() && StringUtils.hasText(value.asText())) {
                return value.asText();
            }
        }
        return null;
    }

    private String nullToEmpty(String value) {
        return value == null ? "" : value;
    }
}
