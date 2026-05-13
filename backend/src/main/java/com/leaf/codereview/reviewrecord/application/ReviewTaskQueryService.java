package com.leaf.codereview.reviewrecord.application;

import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import com.leaf.codereview.common.response.PageResponse;
import com.leaf.codereview.codequality.application.CodeQualityReviewProgressEventResponse;
import com.leaf.codereview.codequality.application.CodeQualityReviewResultResponse;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressEventRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewResultRepository;
import com.leaf.codereview.notification.application.NotificationRecordResponse;
import com.leaf.codereview.notification.infrastructure.NotificationRecordRepository;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewTaskQueryRepository;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class ReviewTaskQueryService {

    private final ReviewTaskQueryRepository reviewTaskQueryRepository;
    private final CodeQualityReviewResultRepository codeQualityReviewResultRepository;
    private final CodeQualityReviewProgressEventRepository codeQualityReviewProgressEventRepository;
    private final NotificationRecordRepository notificationRecordRepository;

    public ReviewTaskQueryService(
            ReviewTaskQueryRepository reviewTaskQueryRepository,
            CodeQualityReviewResultRepository codeQualityReviewResultRepository,
            CodeQualityReviewProgressEventRepository codeQualityReviewProgressEventRepository,
            NotificationRecordRepository notificationRecordRepository
    ) {
        this.reviewTaskQueryRepository = reviewTaskQueryRepository;
        this.codeQualityReviewResultRepository = codeQualityReviewResultRepository;
        this.codeQualityReviewProgressEventRepository = codeQualityReviewProgressEventRepository;
        this.notificationRecordRepository = notificationRecordRepository;
    }

    public PageResponse<ReviewTaskListItemResponse> findPage(Long projectId, String status, String riskLevel, String keyword, int pageNo, int pageSize) {
        return reviewTaskQueryRepository.findPage(projectId, status, riskLevel, keyword, pageNo, pageSize);
    }

    public ReviewTaskDetailResponse getDetail(Long taskId) {
        return reviewTaskQueryRepository.findDetailById(taskId)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND, "Review task not found: " + taskId));
    }

    public ReviewTaskResultResponse getResult(Long taskId) {
        return reviewTaskQueryRepository.findResultByTaskId(taskId)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND, "Review result not found: " + taskId));
    }

    public CodeQualityReviewResultResponse getCodeQualityResult(Long taskId) {
        return codeQualityReviewResultRepository.findByTaskId(taskId)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND, "Code quality review result not found: " + taskId));
    }

    public List<CodeQualityReviewProgressEventResponse> getCodeQualityProgress(Long taskId) {
        reviewTaskQueryRepository.findDetailById(taskId)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND, "Review task not found: " + taskId));
        return codeQualityReviewProgressEventRepository.findByTaskId(taskId);
    }

    public List<NotificationRecordResponse> getNotifications(Long taskId) {
        reviewTaskQueryRepository.findDetailById(taskId)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND, "Review task not found: " + taskId));
        return notificationRecordRepository.findByTaskId(taskId);
    }
}
