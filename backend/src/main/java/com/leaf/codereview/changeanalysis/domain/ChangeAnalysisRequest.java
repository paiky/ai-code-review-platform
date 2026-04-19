package com.leaf.codereview.changeanalysis.domain;

import java.util.List;

public record ChangeAnalysisRequest(
        List<ChangedFile> changedFiles,
        String diffText
) {
    public ChangeAnalysisRequest {
        changedFiles = changedFiles == null ? List.of() : List.copyOf(changedFiles);
    }
}