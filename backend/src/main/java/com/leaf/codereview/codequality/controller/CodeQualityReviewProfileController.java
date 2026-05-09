package com.leaf.codereview.codequality.controller;

import com.leaf.codereview.codequality.application.CodeQualityReviewProfileService;
import com.leaf.codereview.codequality.application.CodeQualityReviewProfileUpdateRequest;
import com.leaf.codereview.codequality.application.CodeQualityRenderedPromptResponse;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProfile;
import com.leaf.codereview.common.response.ApiResponse;
import com.leaf.codereview.common.response.PageResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/code-quality-review-profiles")
public class CodeQualityReviewProfileController {

    private final CodeQualityReviewProfileService service;

    public CodeQualityReviewProfileController(CodeQualityReviewProfileService service) {
        this.service = service;
    }

    @GetMapping
    public ApiResponse<PageResponse<CodeQualityReviewProfile>> list() {
        List<CodeQualityReviewProfile> profiles = service.listEnabledProfiles();
        return ApiResponse.ok(new PageResponse<>(profiles, 1, profiles.size(), profiles.size()));
    }

    @GetMapping("/{profileCode}")
    public ApiResponse<CodeQualityReviewProfile> get(@PathVariable String profileCode) {
        return ApiResponse.ok(service.getProfile(profileCode));
    }

    @PutMapping("/{profileCode}")
    public ApiResponse<CodeQualityReviewProfile> update(
            @PathVariable String profileCode,
            @RequestBody CodeQualityReviewProfileUpdateRequest request
    ) {
        return ApiResponse.ok(service.updateProfile(profileCode, request));
    }

    @GetMapping("/{profileCode}/rendered-prompt")
    public ApiResponse<CodeQualityRenderedPromptResponse> renderedPrompt(@PathVariable String profileCode) {
        return ApiResponse.ok(service.renderedPrompt(profileCode));
    }

    @PostMapping("/{profileCode}/reset-default-prompt")
    public ApiResponse<CodeQualityReviewProfile> resetDefaultPrompt(@PathVariable String profileCode) {
        return ApiResponse.ok(service.resetDefaultPrompt(profileCode));
    }
}
