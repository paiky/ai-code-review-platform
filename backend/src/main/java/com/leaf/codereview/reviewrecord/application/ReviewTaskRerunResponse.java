package com.leaf.codereview.reviewrecord.application;

public record ReviewTaskRerunResponse(
        Long sourceTaskId,
        Long taskId,
        String status,
        String triggerType
) {
}
