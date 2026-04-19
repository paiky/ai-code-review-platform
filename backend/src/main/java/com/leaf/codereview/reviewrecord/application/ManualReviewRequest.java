package com.leaf.codereview.reviewrecord.application;

import com.leaf.codereview.changeanalysis.domain.ChangedFile;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public record ManualReviewRequest(
        @NotNull Long projectId,
        String templateCode,
        String sourceBranch,
        String targetBranch,
        String authorName,
        String authorUsername,
        List<ChangedFile> changedFiles,
        String diffText
) {
    public ManualReviewRequest {
        changedFiles = changedFiles == null ? List.of() : List.copyOf(changedFiles);
    }
}