package com.leaf.codereview.codequality.controller;

import com.leaf.codereview.codequality.application.CodeQualityManualReviewResponse;
import com.leaf.codereview.codequality.application.CodeQualityManualReviewService;
import com.leaf.codereview.codequality.application.CodeQualityAutoReviewService;
import com.leaf.codereview.codequality.application.CodeQualityReviewSettingsResponse;
import com.leaf.codereview.codequality.application.CodeQualityReviewSettingsService;
import com.leaf.codereview.common.response.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/code-quality-reviews")
public class CodeQualityReviewController {

    private final CodeQualityManualReviewService codeQualityManualReviewService;
    private final CodeQualityReviewSettingsService settingsService;
    private final CodeQualityAutoReviewService autoReviewService;

    public CodeQualityReviewController(
            CodeQualityManualReviewService codeQualityManualReviewService,
            CodeQualityReviewSettingsService settingsService,
            CodeQualityAutoReviewService autoReviewService
    ) {
        this.codeQualityManualReviewService = codeQualityManualReviewService;
        this.settingsService = settingsService;
        this.autoReviewService = autoReviewService;
    }

    @PostMapping("/manual")
    public ApiResponse<CodeQualityManualReviewResponse> createManualReview(@RequestBody CodeQualityManualReviewRequest request) {
        return ApiResponse.ok(codeQualityManualReviewService.createManualReview(request));
    }

    @GetMapping("/settings")
    public ApiResponse<CodeQualityReviewSettingsResponse> getSettings() {
        return ApiResponse.ok(settingsService.get());
    }

    @PutMapping("/settings")
    public ApiResponse<CodeQualityReviewSettingsResponse> updateSettings(@RequestBody CodeQualityReviewSettingsUpdateRequest request) {
        return ApiResponse.ok(settingsService.update(request));
    }

    @PostMapping("/tasks/{taskId}/retry")
    public ApiResponse<CodeQualityManualReviewResponse> retry(@PathVariable Long taskId) {
        return ApiResponse.ok(autoReviewService.retryMergeRequestReview(taskId));
    }
}
