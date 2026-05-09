package com.leaf.codereview.codequality.application;

import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewResultRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class CodeQualityReviewStartupRecovery {

    private static final Logger log = LoggerFactory.getLogger(CodeQualityReviewStartupRecovery.class);

    private final CodeQualityReviewProperties properties;
    private final CodeQualityReviewResultRepository resultRepository;

    public CodeQualityReviewStartupRecovery(
            CodeQualityReviewProperties properties,
            CodeQualityReviewResultRepository resultRepository
    ) {
        this.properties = properties;
        this.resultRepository = resultRepository;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void recoverStaleRunningReviews() {
        int updated = resultRepository.markStaleRunningAsFailed(properties.codexTimeoutSeconds());
        if (updated > 0) {
            log.warn("Marked {} stale RUNNING AI code review result(s) as FAILED", updated);
        }
    }
}
