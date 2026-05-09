package com.leaf.codereview.notification.domain;

public record DingTalkMessageContext(
        String title,
        String authorName,
        String authorUsername,
        String sourceBranch,
        String targetBranch,
        String externalUrl
) {
    public static DingTalkMessageContext empty() {
        return new DingTalkMessageContext(null, null, null, null, null, null);
    }
}
