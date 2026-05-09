package com.leaf.codereview.codequality.application;

import com.leaf.codereview.codequality.domain.CodeQualityReviewProfile;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProfileRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressEventRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewResultRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewSettingsRepository;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import com.leaf.codereview.projectintegration.domain.GitLabMergeRequestEvent;
import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import com.leaf.codereview.projectintegration.infrastructure.ProjectRepository;
import com.leaf.codereview.reviewrecord.application.ReviewTaskDetailResponse;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewTaskQueryRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;

@Service
public class CodeQualityAutoReviewService {

    private static final Logger log = LoggerFactory.getLogger(CodeQualityAutoReviewService.class);

    private final CodeQualityReviewProperties properties;
    private final CodeQualityReviewProfileRepository profileRepository;
    private final CodeQualityReviewResultRepository resultRepository;
    private final CodeQualityReviewSettingsRepository settingsRepository;
    private final CodeQualityReviewProgressEventRepository progressEventRepository;
    private final ProjectRepository projectRepository;
    private final ReviewTaskQueryRepository reviewTaskQueryRepository;
    private final CodeQualityAsyncReviewExecutor executor;

    public CodeQualityAutoReviewService(
            CodeQualityReviewProperties properties,
            CodeQualityReviewProfileRepository profileRepository,
            CodeQualityReviewResultRepository resultRepository,
            CodeQualityReviewSettingsRepository settingsRepository,
            CodeQualityReviewProgressEventRepository progressEventRepository,
            ProjectRepository projectRepository,
            ReviewTaskQueryRepository reviewTaskQueryRepository,
            CodeQualityAsyncReviewExecutor executor
    ) {
        this.properties = properties;
        this.profileRepository = profileRepository;
        this.resultRepository = resultRepository;
        this.settingsRepository = settingsRepository;
        this.progressEventRepository = progressEventRepository;
        this.projectRepository = projectRepository;
        this.reviewTaskQueryRepository = reviewTaskQueryRepository;
        this.executor = executor;
    }

    public void triggerAfterMergeRequestReview(Long taskId, ProjectRecord project, GitLabMergeRequestEvent event) {
        if (!properties.enabled()) {
            return;
        }
        if (!settingsRepository.mrAutoReviewEnabled()) {
            log.debug("Skip AI code review because MR auto review is disabled globally, taskId={}", taskId);
            return;
        }
        if (resultRepository.existsByTaskId(taskId)) {
            log.debug("Skip AI code review because result already exists for taskId={}", taskId);
            return;
        }

        CodeQualityReviewProfile profile = resolveProfile(project);
        if (profile == null || !profile.enabled() || !profile.triggerOnMr()) {
            return;
        }

        schedule(taskId, project, event, profile, settingsRepository.reviewProvider());
    }

    public CodeQualityManualReviewResponse retryMergeRequestReview(Long taskId) {
        if (!properties.enabled()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Code quality review is disabled");
        }
        ReviewTaskDetailResponse detail = reviewTaskQueryRepository.findDetailById(taskId)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND, "Review task not found: " + taskId));
        if (!"GITLAB_MR_WEBHOOK".equals(detail.triggerType())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Only GitLab MR webhook tasks can retry AI Review: " + taskId);
        }
        ProjectRecord project = projectRepository.findById(detail.projectId())
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND, "Project not found: " + detail.projectId()));
        CodeQualityReviewProfile profile = resolveProfile(project);
        if (profile == null || !profile.enabled()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Code quality review profile is disabled or missing");
        }
        CodeQualityReviewProviderType provider = settingsRepository.reviewProvider();
        schedule(taskId, project, toEvent(detail, project), profile, provider);
        return new CodeQualityManualReviewResponse(
                taskId,
                "RUNNING",
                profile.profileCode(),
                provider.name(),
                null,
                0
        );
    }

    private void schedule(Long taskId, ProjectRecord project, GitLabMergeRequestEvent event, CodeQualityReviewProfile profile, CodeQualityReviewProviderType provider) {
        progressEventRepository.deleteByTaskId(taskId);
        progressEventRepository.append(taskId, "QUEUED", "INFO", "AI Review 已进入执行队列", "provider=" + provider.name() + ", profile=" + profile.profileCode());
        resultRepository.save(
                taskId,
                project.id(),
                profile.profileCode(),
                profile.model(),
                CodeQualityReviewResult.running(provider, OffsetDateTime.now())
        );
        executor.execute(taskId, project, event, profile, provider);
    }

    private CodeQualityReviewProfile resolveProfile(ProjectRecord project) {
        String profileCode = StringUtils.hasText(project.defaultCodeQualityProfileCode())
                ? project.defaultCodeQualityProfileCode()
                : CodeQualityReviewProfileRepository.DEFAULT_PROFILE_CODE;
        return profileRepository.findByCode(profileCode)
                .orElseGet(() -> profileRepository.findByCode(CodeQualityReviewProfileRepository.DEFAULT_PROFILE_CODE).orElse(null));
    }

    private GitLabMergeRequestEvent toEvent(ReviewTaskDetailResponse detail, ProjectRecord project) {
        return new GitLabMergeRequestEvent(
                detail.gitProjectId(),
                detail.projectName(),
                project.repositoryUrl(),
                detail.mrId(),
                detail.eventAction(),
                parseEventTime(detail.eventTime()),
                detail.externalUrl(),
                detail.sourceBranch(),
                detail.targetBranch(),
                detail.commitSha(),
                detail.authorName(),
                detail.authorUsername(),
                detail.changedFilesSummary(),
                detail.rawPayload()
        );
    }

    private LocalDateTime parseEventTime(String eventTime) {
        if (!StringUtils.hasText(eventTime)) {
            return LocalDateTime.now();
        }
        try {
            return LocalDateTime.parse(eventTime);
        } catch (Exception ignored) {
            return LocalDateTime.now();
        }
    }
}
