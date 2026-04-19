package com.leaf.codereview.reviewrecord.application;

import com.leaf.codereview.changeanalysis.application.ChangeAnalysisService;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisRequest;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisResult;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import com.leaf.codereview.notification.application.DingTalkNotifier;
import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import com.leaf.codereview.notification.infrastructure.NotificationRecordRepository;
import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import com.leaf.codereview.projectintegration.infrastructure.ProjectRepository;
import com.leaf.codereview.reviewrecord.domain.ReviewTaskCreateCommand;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewResultRepository;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewTaskRepository;
import com.leaf.codereview.riskengine.application.RiskCardGenerator;
import com.leaf.codereview.riskengine.domain.RiskCard;
import com.leaf.codereview.ruletemplate.application.RuleTemplateService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

@Service
public class ManualReviewService {

    private final ProjectRepository projectRepository;
    private final RuleTemplateService ruleTemplateService;
    private final ReviewTaskRepository reviewTaskRepository;
    private final ReviewResultRepository reviewResultRepository;
    private final ChangeAnalysisService changeAnalysisService;
    private final RiskCardGenerator riskCardGenerator;
    private final DingTalkNotifier dingTalkNotifier;
    private final NotificationRecordRepository notificationRecordRepository;

    public ManualReviewService(
            ProjectRepository projectRepository,
            RuleTemplateService ruleTemplateService,
            ReviewTaskRepository reviewTaskRepository,
            ReviewResultRepository reviewResultRepository,
            ChangeAnalysisService changeAnalysisService,
            RiskCardGenerator riskCardGenerator,
            DingTalkNotifier dingTalkNotifier,
            NotificationRecordRepository notificationRecordRepository
    ) {
        this.projectRepository = projectRepository;
        this.ruleTemplateService = ruleTemplateService;
        this.reviewTaskRepository = reviewTaskRepository;
        this.reviewResultRepository = reviewResultRepository;
        this.changeAnalysisService = changeAnalysisService;
        this.riskCardGenerator = riskCardGenerator;
        this.dingTalkNotifier = dingTalkNotifier;
        this.notificationRecordRepository = notificationRecordRepository;
    }

    @Transactional(noRollbackFor = Exception.class)
    public ManualReviewResponse createManualReview(ManualReviewRequest request) {
        ProjectRecord project = projectRepository.findById(request.projectId())
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND, "Project not found: " + request.projectId()));
        String templateCode = StringUtils.hasText(request.templateCode()) ? request.templateCode() : project.defaultTemplateCode();
        ruleTemplateService.getEnabledTemplate(templateCode);

        Long taskId = reviewTaskRepository.create(new ReviewTaskCreateCommand(
                project.id(),
                "MANUAL",
                null,
                null,
                request.sourceBranch(),
                request.targetBranch(),
                null,
                null,
                null,
                request.authorName(),
                request.authorUsername(),
                templateCode,
                "RUNNING"
        ));

        try {
            ChangeAnalysisResult analysisResult = changeAnalysisService.analyze(new ChangeAnalysisRequest(request.changedFiles(), request.diffText()));
            RiskCard riskCard = riskCardGenerator.generate(analysisResult, templateCode);
            Long resultId = reviewResultRepository.save(taskId, project.id(), templateCode, analysisResult, riskCard);
            reviewTaskRepository.markSuccess(taskId, riskCard.riskLevel().name());
            DingTalkNotificationResult notificationResult = dingTalkNotifier.sendRiskCard(taskId, riskCard);
            notificationRecordRepository.saveDingTalkRecord(taskId, resultId, notificationResult);
            return new ManualReviewResponse(taskId, "SUCCESS", templateCode, riskCard.riskLevel().name());
        } catch (Exception exception) {
            reviewTaskRepository.markFailed(taskId, exception.getMessage());
            if (exception instanceof RuntimeException runtimeException) {
                throw runtimeException;
            }
            throw new BusinessException(ErrorCode.INTERNAL_ERROR, exception.getMessage());
        }
    }
}