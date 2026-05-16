package com.leaf.codereview.codequality.controller;

import com.leaf.codereview.codequality.application.CodeQualityModelProviderResponse;
import com.leaf.codereview.codequality.application.CodeQualityModelProviderService;
import com.leaf.codereview.codequality.application.CodeQualityReviewSettingsResponse;
import com.leaf.codereview.common.response.ApiResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/code-quality-review-providers")
public class CodeQualityModelProviderController {

    private final CodeQualityModelProviderService service;

    public CodeQualityModelProviderController(CodeQualityModelProviderService service) {
        this.service = service;
    }

    @GetMapping
    public ApiResponse<List<CodeQualityModelProviderResponse>> list() {
        return ApiResponse.ok(service.list());
    }

    @PutMapping("/{providerCode}")
    public ApiResponse<List<CodeQualityModelProviderResponse>> update(
            @PathVariable String providerCode,
            @RequestBody CodeQualityModelProviderUpdateRequest request
    ) {
        return ApiResponse.ok(service.update(providerCode, request));
    }

    @PostMapping("/{providerCode}/set-default")
    public ApiResponse<CodeQualityReviewSettingsResponse> setDefault(@PathVariable String providerCode) {
        return ApiResponse.ok(service.setDefault(providerCode));
    }
}
