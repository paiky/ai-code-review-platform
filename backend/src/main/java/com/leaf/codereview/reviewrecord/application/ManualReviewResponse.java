package com.leaf.codereview.reviewrecord.application;

public record ManualReviewResponse(Long taskId, String status, String templateCode, String riskLevel) {
}