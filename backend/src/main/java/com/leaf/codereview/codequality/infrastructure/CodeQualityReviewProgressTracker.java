package com.leaf.codereview.codequality.infrastructure;

import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
public class CodeQualityReviewProgressTracker {

    private final ThreadLocal<Long> currentTaskId = new ThreadLocal<>();
    private final CodeQualityReviewProgressEventRepository repository;

    public CodeQualityReviewProgressTracker(CodeQualityReviewProgressEventRepository repository) {
        this.repository = repository;
    }

    public void runWithTask(Long taskId, Runnable runnable) {
        Long previousTaskId = currentTaskId.get();
        currentTaskId.set(taskId);
        try {
            runnable.run();
        } finally {
            if (previousTaskId == null) {
                currentTaskId.remove();
            } else {
                currentTaskId.set(previousTaskId);
            }
        }
    }

    public void info(String phase, String message) {
        append(phase, "INFO", message, null);
    }

    public void info(String phase, String message, String detail) {
        append(phase, "INFO", message, detail);
    }

    public void debug(String phase, String message, String detail) {
        append(phase, "DEBUG", message, detail);
    }

    public void warn(String phase, String message, String detail) {
        append(phase, "WARN", message, detail);
    }

    public void error(String phase, String message, String detail) {
        append(phase, "ERROR", message, detail);
    }

    public Long currentTaskId() {
        return currentTaskId.get();
    }

    private void append(String phase, String level, String message, String detail) {
        Long taskId = currentTaskId.get();
        if (taskId == null || !StringUtils.hasText(message)) {
            return;
        }
        repository.append(taskId, phase, level, maskSensitive(message), maskSensitive(detail));
    }

    private String maskSensitive(String value) {
        if (!StringUtils.hasText(value)) {
            return value;
        }
        return value
                .replaceAll("(?i)(authorization\\s*[:=]\\s*)(bearer\\s+)?[^\\s,;]+", "$1$2****")
                .replaceAll("(?i)(\"?(password|token|secret|apiKey|accessKeyId|accessKeySecret)\"?\\s*[:=]\\s*\"?)[^\"\\s,;}]+", "$1****");
    }
}
