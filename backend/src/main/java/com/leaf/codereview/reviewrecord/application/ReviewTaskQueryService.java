package com.leaf.codereview.reviewrecord.application;

import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import com.leaf.codereview.common.response.PageResponse;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewTaskQueryRepository;
import org.springframework.stereotype.Service;

@Service
public class ReviewTaskQueryService {

    private final ReviewTaskQueryRepository reviewTaskQueryRepository;

    public ReviewTaskQueryService(ReviewTaskQueryRepository reviewTaskQueryRepository) {
        this.reviewTaskQueryRepository = reviewTaskQueryRepository;
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
}