package com.leaf.codereview.codequality.infrastructure;

import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
public class CodeQualityReviewProperties {

    private final boolean enabled;
    private final CodeQualityReviewProviderType provider;
    private final String openAiApiKey;
    private final String openAiResponsesUrl;
    private final String openAiModel;
    private final int openAiTimeoutSeconds;
    private final String anthropicApiKey;
    private final String anthropicMessagesUrl;
    private final String anthropicModel;
    private final int anthropicTimeoutSeconds;
    private final String deepSeekApiKey;
    private final String deepSeekBaseUrl;
    private final String deepSeekModel;

    @Autowired
    public CodeQualityReviewProperties(
            @Value("${code-quality.review.enabled:false}") boolean enabled,
            @Value("${code-quality.review.provider:}") String provider,
            @Value("${code-quality.review.openai.api-key:}") String openAiApiKey,
            @Value("${code-quality.review.openai.responses-url:https://api.openai.com/v1/responses}") String openAiResponsesUrl,
            @Value("${code-quality.review.openai.model:gpt-5.4}") String openAiModel,
            @Value("${code-quality.review.openai.timeout-seconds:120}") int openAiTimeoutSeconds,
            @Value("${code-quality.review.anthropic.api-key:}") String anthropicApiKey,
            @Value("${code-quality.review.anthropic.messages-url:https://api.anthropic.com/v1/messages}") String anthropicMessagesUrl,
            @Value("${code-quality.review.anthropic.model:claude-sonnet-4-5}") String anthropicModel,
            @Value("${code-quality.review.anthropic.timeout-seconds:120}") int anthropicTimeoutSeconds,
            @Value("${code-quality.review.deepseek.api-key:}") String deepSeekApiKey,
            @Value("${code-quality.review.deepseek.base-url:https://api.deepseek.com}") String deepSeekBaseUrl,
            @Value("${code-quality.review.deepseek.model:deepseek-v4-pro}") String deepSeekModel
    ) {
        this(
                enabled,
                parseProvider(provider),
                openAiApiKey,
                openAiResponsesUrl,
                openAiModel,
                openAiTimeoutSeconds,
                anthropicApiKey,
                anthropicMessagesUrl,
                anthropicModel,
                anthropicTimeoutSeconds,
                deepSeekApiKey,
                deepSeekBaseUrl,
                deepSeekModel
        );
    }

    public CodeQualityReviewProperties(
            boolean enabled,
            CodeQualityReviewProviderType provider,
            String openAiApiKey,
            String openAiResponsesUrl,
            String openAiModel,
            int openAiTimeoutSeconds,
            String anthropicApiKey,
            String anthropicMessagesUrl,
            String anthropicModel,
            int anthropicTimeoutSeconds,
            String deepSeekApiKey,
            String deepSeekBaseUrl,
            String deepSeekModel
    ) {
        this.enabled = enabled;
        this.provider = provider == null ? CodeQualityReviewProviderType.DEEPSEEK : provider;
        this.openAiApiKey = openAiApiKey;
        this.openAiResponsesUrl = openAiResponsesUrl;
        this.openAiModel = openAiModel;
        this.openAiTimeoutSeconds = openAiTimeoutSeconds;
        this.anthropicApiKey = anthropicApiKey;
        this.anthropicMessagesUrl = anthropicMessagesUrl;
        this.anthropicModel = anthropicModel;
        this.anthropicTimeoutSeconds = anthropicTimeoutSeconds;
        this.deepSeekApiKey = deepSeekApiKey;
        this.deepSeekBaseUrl = deepSeekBaseUrl;
        this.deepSeekModel = deepSeekModel;
    }

    public CodeQualityReviewProperties(
            boolean enabled,
            CodeQualityReviewProviderType provider,
            String ignoredWorkspaceRoot,
            String ignoredCodexCommand,
            String ignoredCodexModel,
            int ignoredCodexTimeoutSeconds,
            String openAiApiKey,
            String openAiResponsesUrl,
            String openAiModel,
            int openAiTimeoutSeconds,
            String anthropicApiKey,
            String anthropicMessagesUrl,
            String anthropicModel,
            int anthropicTimeoutSeconds
    ) {
        this(
                enabled,
                provider,
                openAiApiKey,
                openAiResponsesUrl,
                openAiModel,
                openAiTimeoutSeconds,
                anthropicApiKey,
                anthropicMessagesUrl,
                anthropicModel,
                anthropicTimeoutSeconds,
                "",
                "https://api.deepseek.com",
                "deepseek-v4-pro"
        );
    }

    public CodeQualityReviewProperties(
            boolean enabled,
            String provider,
            String ignoredWorkspaceRoot,
            String ignoredCodexCommand,
            String ignoredCodexModel,
            int ignoredCodexTimeoutSeconds,
            String openAiApiKey,
            String openAiResponsesUrl,
            String openAiModel,
            int openAiTimeoutSeconds,
            String anthropicApiKey,
            String anthropicMessagesUrl,
            String anthropicModel,
            int anthropicTimeoutSeconds
    ) {
        this(
                enabled,
                parseProvider(provider),
                ignoredWorkspaceRoot,
                ignoredCodexCommand,
                ignoredCodexModel,
                ignoredCodexTimeoutSeconds,
                openAiApiKey,
                openAiResponsesUrl,
                openAiModel,
                openAiTimeoutSeconds,
                anthropicApiKey,
                anthropicMessagesUrl,
                anthropicModel,
                anthropicTimeoutSeconds
        );
    }

    public boolean enabled() {
        return enabled;
    }

    public CodeQualityReviewProviderType provider() {
        return provider;
    }

    public String openAiApiKey() {
        return openAiApiKey;
    }

    public String openAiResponsesUrl() {
        return openAiResponsesUrl;
    }

    public String openAiModel() {
        return openAiModel;
    }

    public int openAiTimeoutSeconds() {
        return openAiTimeoutSeconds;
    }

    public String anthropicApiKey() {
        return anthropicApiKey;
    }

    public String anthropicMessagesUrl() {
        return anthropicMessagesUrl;
    }

    public String anthropicModel() {
        return anthropicModel;
    }

    public int anthropicTimeoutSeconds() {
        return anthropicTimeoutSeconds;
    }

    public String deepSeekApiKey() {
        return deepSeekApiKey;
    }

    public String deepSeekBaseUrl() {
        return deepSeekBaseUrl;
    }

    public String deepSeekModel() {
        return deepSeekModel;
    }

    private static CodeQualityReviewProviderType parseProvider(String provider) {
        if (!StringUtils.hasText(provider)) {
            return CodeQualityReviewProviderType.DEEPSEEK;
        }
        return switch (provider.trim()) {
            case "OPENAI_API" -> CodeQualityReviewProviderType.OPENAI;
            case "ANTHROPIC_API" -> CodeQualityReviewProviderType.ANTHROPIC;
            case "CODEX_CLI" -> CodeQualityReviewProviderType.DEEPSEEK;
            default -> CodeQualityReviewProviderType.valueOf(provider.trim());
        };
    }
}
