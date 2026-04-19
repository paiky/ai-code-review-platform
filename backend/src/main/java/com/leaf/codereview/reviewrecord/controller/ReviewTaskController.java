package com.leaf.codereview.reviewrecord.controller;

import com.leaf.codereview.common.response.ApiResponse;
import com.leaf.codereview.common.response.PageResponse;
import com.leaf.codereview.reviewrecord.application.ManualReviewRequest;
import com.leaf.codereview.reviewrecord.application.ManualReviewResponse;
import com.leaf.codereview.reviewrecord.application.ManualReviewService;
import com.leaf.codereview.reviewrecord.application.ReviewTaskDetailResponse;
import com.leaf.codereview.reviewrecord.application.ReviewTaskListItemResponse;
import com.leaf.codereview.reviewrecord.application.ReviewTaskQueryService;
import com.leaf.codereview.reviewrecord.application.ReviewTaskResultResponse;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/review-tasks")
public class ReviewTaskController {

    private final ReviewTaskQueryService reviewTaskQueryService;
    private final ManualReviewService manualReviewService;

    public ReviewTaskController(ReviewTaskQueryService reviewTaskQueryService, ManualReviewService manualReviewService) {
        this.reviewTaskQueryService = reviewTaskQueryService;
        this.manualReviewService = manualReviewService;
    }

    @PostMapping("/manual")
    public ApiResponse<ManualReviewResponse> createManualReview(@Valid @RequestBody ManualReviewRequest request) {
        return ApiResponse.ok(manualReviewService.createManualReview(request));
    }

    @GetMapping
    public ApiResponse<PageResponse<ReviewTaskListItemResponse>> findPage(
            @RequestParam(required = false) Long projectId,
            @RequestParam(required = false) String status,
            @RequestParam(required = false) String riskLevel,
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "1") int pageNo,
            @RequestParam(defaultValue = "20") int pageSize
    ) {
        return ApiResponse.ok(reviewTaskQueryService.findPage(projectId, status, riskLevel, keyword, pageNo, pageSize));
    }

    @GetMapping("/{taskId}")
    public ApiResponse<ReviewTaskDetailResponse> getDetail(@PathVariable Long taskId) {
        return ApiResponse.ok(reviewTaskQueryService.getDetail(taskId));
    }

    @GetMapping("/{taskId}/result")
    public ApiResponse<ReviewTaskResultResponse> getResult(@PathVariable Long taskId) {
        return ApiResponse.ok(reviewTaskQueryService.getResult(taskId));
    }
}