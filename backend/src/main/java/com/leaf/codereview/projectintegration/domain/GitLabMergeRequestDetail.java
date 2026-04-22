package com.leaf.codereview.projectintegration.domain;

public record GitLabMergeRequestDetail(
        String iid,
        String title,
        String webUrl,
        String sourceBranch,
        String targetBranch,
        String commitSha,
        String authorName,
        String authorUsername
) {
}
