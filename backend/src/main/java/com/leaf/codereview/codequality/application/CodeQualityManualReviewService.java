package com.leaf.codereview.codequality.application;

import com.leaf.codereview.codequality.controller.CodeQualityManualReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProfile;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProfileRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressEventRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressTracker;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewResultRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewSettingsRepository;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import com.leaf.codereview.projectintegration.infrastructure.ProjectRepository;
import com.leaf.codereview.reviewrecord.domain.ReviewTaskCreateCommand;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewTaskRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

@Service
public class CodeQualityManualReviewService {

    private final ProjectRepository projectRepository;
    private final CodeQualityReviewProfileRepository profileRepository;
    private final ReviewTaskRepository reviewTaskRepository;
    private final CodeQualityReviewService codeQualityReviewService;
    private final CodeQualityReviewResultRepository resultRepository;
    private final CodeQualityReviewProgressEventRepository progressEventRepository;
    private final CodeQualityReviewProgressTracker progressTracker;
    private final CodeQualityReviewProperties properties;
    private final CodeQualityReviewSettingsRepository settingsRepository;

    public CodeQualityManualReviewService(
            ProjectRepository projectRepository,
            CodeQualityReviewProfileRepository profileRepository,
            ReviewTaskRepository reviewTaskRepository,
            CodeQualityReviewService codeQualityReviewService,
            CodeQualityReviewResultRepository resultRepository,
            CodeQualityReviewProgressEventRepository progressEventRepository,
            CodeQualityReviewProgressTracker progressTracker,
            CodeQualityReviewProperties properties,
            CodeQualityReviewSettingsRepository settingsRepository
    ) {
        this.projectRepository = projectRepository;
        this.profileRepository = profileRepository;
        this.reviewTaskRepository = reviewTaskRepository;
        this.codeQualityReviewService = codeQualityReviewService;
        this.resultRepository = resultRepository;
        this.progressEventRepository = progressEventRepository;
        this.progressTracker = progressTracker;
        this.properties = properties;
        this.settingsRepository = settingsRepository;
    }

    @Transactional(noRollbackFor = Exception.class)
    public CodeQualityManualReviewResponse createManualReview(CodeQualityManualReviewRequest request) {
        if (!properties.enabled()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Code quality review is disabled");
        }
        if (request.projectId() == null) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "projectId is required");
        }
        ProjectRecord project = projectRepository.findById(request.projectId())
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND, "Project not found: " + request.projectId()));
        CodeQualityReviewProfile profile = resolveProfile(request, project);
        if (!profile.enabled() || !profile.triggerOnManual()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Code quality review profile does not allow manual trigger: " + profile.profileCode());
        }

        Long taskId = reviewTaskRepository.create(new ReviewTaskCreateCommand(
                project.id(),
                "CODE_QUALITY_MANUAL",
                null,
                null,
                null,
                null,
                request.commitSha(),
                null,
                null,
                null,
                null,
                profile.profileCode(),
                "RUNNING"
        ));

        try {
            progressEventRepository.deleteByTaskId(taskId);
            CodeQualityReviewProviderType provider = resolveProvider(project, profile);
            progressEventRepository.append(taskId, "QUEUED", "INFO", "手动 AI Review 已创建", "provider=" + provider.name() + ", profile=" + profile.profileCode());
            return runManualReview(taskId, project, request, profile, provider);
        } catch (Exception exception) {
            progressEventRepository.append(taskId, "FAILED", "ERROR", "手动 AI Review 执行失败", exception.getMessage());
            reviewTaskRepository.markFailed(taskId, exception.getMessage());
            if (exception instanceof RuntimeException runtimeException) {
                throw runtimeException;
            }
            throw new BusinessException(ErrorCode.INTERNAL_ERROR, exception.getMessage());
        }
    }

    private CodeQualityManualReviewResponse runManualReview(
            Long taskId,
            ProjectRecord project,
            CodeQualityManualReviewRequest request,
            CodeQualityReviewProfile profile,
            CodeQualityReviewProviderType provider
    ) {
        final CodeQualityManualReviewResponse[] response = new CodeQualityManualReviewResponse[1];
        progressTracker.runWithTask(taskId, () -> {
            progressTracker.info("STARTED", "开始执行手动 AI Review", "projectId=" + project.id());
            CodeQualityReviewRequest reviewRequest = enrichRequest(request.toDomain(), profile, provider);
            progressTracker.info("REQUEST_BUILT", "AI Review 请求已构建", "profileCode=" + profile.profileCode() + ", provider=" + provider.name() + ", model=" + reviewRequest.model() + ", mode=" + reviewRequest.mode());
            CodeQualityReviewResult result = codeQualityReviewService.review(reviewRequest, provider);
            progressTracker.info("SAVE_RESULT", "Provider 执行完成，开始保存结果", "status=" + result.status() + ", findingCount=" + result.findings().size());
            resultRepository.save(taskId, project.id(), profile.profileCode(), reviewRequest.model(), result);
            if ("SUCCESS".equals(result.status())) {
                reviewTaskRepository.markSuccess(taskId, result.overallLevel());
            } else {
                reviewTaskRepository.markFailed(taskId, result.errorMessage());
            }
            progressTracker.info("FINISHED", "手动 AI Review 已完成", "status=" + result.status() + ", overallLevel=" + result.overallLevel());
            response[0] = new CodeQualityManualReviewResponse(
                    taskId,
                    result.status(),
                    profile.profileCode(),
                    provider.name(),
                    result.overallLevel(),
                    result.findings().size()
            );
        });
        return response[0];
    }

    private CodeQualityReviewProfile resolveProfile(CodeQualityManualReviewRequest request, ProjectRecord project) {
        String profileCode = StringUtils.hasText(request.profileCode()) ? request.profileCode() : project.defaultCodeQualityProfileCode();
        if (!StringUtils.hasText(profileCode)) {
            profileCode = CodeQualityReviewProfileRepository.DEFAULT_PROFILE_CODE;
        }
        String selectedProfileCode = profileCode;
        return profileRepository.findByCode(selectedProfileCode)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND, "Code quality review profile not found: " + selectedProfileCode));
    }

    private CodeQualityReviewProviderType resolveProvider(ProjectRecord project, CodeQualityReviewProfile profile) {
        if (profile.providerCode() != null) {
            return profile.providerCode();
        }
        if (StringUtils.hasText(project.defaultCodeQualityProviderCode())) {
            return CodeQualityReviewProviderType.valueOf(project.defaultCodeQualityProviderCode());
        }
        return settingsRepository.reviewProvider();
    }

    private CodeQualityReviewRequest enrichRequest(CodeQualityReviewRequest request, CodeQualityReviewProfile profile, CodeQualityReviewProviderType provider) {
        String instructions = joinInstructions(profile.reviewInstructions(), request.instructions());
        String model = StringUtils.hasText(request.model()) ? request.model() : profile.model();
        return new CodeQualityReviewRequest(
                request.repositoryPath(),
                request.mode(),
                request.baseRef(),
                request.commitSha(),
                request.title(),
                model,
                instructions,
                request.diffText(),
                request.changedFiles()
        );
    }

    private String joinInstructions(String profilePrompt, String requestInstructions) {
        if (StringUtils.hasText(profilePrompt) && StringUtils.hasText(requestInstructions)) {
            return profilePrompt + "\n\nAdditional manual instructions:\n" + requestInstructions;
        }
        return StringUtils.hasText(requestInstructions) ? requestInstructions : profilePrompt;
    }
}
