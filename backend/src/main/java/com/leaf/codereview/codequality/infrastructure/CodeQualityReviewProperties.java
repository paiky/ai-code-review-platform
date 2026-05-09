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
    private final String workspaceRoot;
    private final String codexCommand;
    private final String codexModel;
    private final int codexTimeoutSeconds;
    private final String openAiApiKey;
    private final String openAiResponsesUrl;
    private final String openAiModel;
    private final int openAiTimeoutSeconds;
    private final String anthropicApiKey;
    private final String anthropicMessagesUrl;
    private final String anthropicModel;
    private final int anthropicTimeoutSeconds;

    @Autowired
    public CodeQualityReviewProperties(
            @Value("${code-quality.review.enabled:false}") boolean enabled,
            @Value("${code-quality.review.provider:}") String provider,
            @Value("${code-quality.review.workspace-root:}") String workspaceRoot,
            @Value("${code-quality.review.codex.command:}") String codexCommand,
            @Value("${code-quality.review.codex.model:}") String codexModel,
            @Value("${code-quality.review.codex.timeout-seconds:600}") int codexTimeoutSeconds,
            @Value("${code-quality.review.openai.api-key:}") String openAiApiKey,
            @Value("${code-quality.review.openai.responses-url:https://api.openai.com/v1/responses}") String openAiResponsesUrl,
            @Value("${code-quality.review.openai.model:gpt-5.4}") String openAiModel,
            @Value("${code-quality.review.openai.timeout-seconds:120}") int openAiTimeoutSeconds,
            @Value("${code-quality.review.anthropic.api-key:}") String anthropicApiKey,
            @Value("${code-quality.review.anthropic.messages-url:https://api.anthropic.com/v1/messages}") String anthropicMessagesUrl,
            @Value("${code-quality.review.anthropic.model:claude-sonnet-4-5}") String anthropicModel,
            @Value("${code-quality.review.anthropic.timeout-seconds:120}") int anthropicTimeoutSeconds
    ) {
        this(
                enabled,
                parseProvider(provider),
                workspaceRoot,
                codexCommand,
                codexModel,
                codexTimeoutSeconds,
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

    public CodeQualityReviewProperties(
            boolean enabled,
            CodeQualityReviewProviderType provider,
            String workspaceRoot,
            String codexCommand,
            String codexModel,
            int codexTimeoutSeconds,
            String openAiApiKey,
            String openAiResponsesUrl,
            String openAiModel,
            int openAiTimeoutSeconds,
            String anthropicApiKey,
            String anthropicMessagesUrl,
            String anthropicModel,
            int anthropicTimeoutSeconds
    ) {
        this.enabled = enabled;
        this.provider = provider == null ? CodeQualityReviewProviderType.CODEX_CLI : provider;
        this.workspaceRoot = workspaceRoot;
        this.codexCommand = codexCommand;
        this.codexModel = codexModel;
        this.codexTimeoutSeconds = codexTimeoutSeconds;
        this.openAiApiKey = openAiApiKey;
        this.openAiResponsesUrl = openAiResponsesUrl;
        this.openAiModel = openAiModel;
        this.openAiTimeoutSeconds = openAiTimeoutSeconds;
        this.anthropicApiKey = anthropicApiKey;
        this.anthropicMessagesUrl = anthropicMessagesUrl;
        this.anthropicModel = anthropicModel;
        this.anthropicTimeoutSeconds = anthropicTimeoutSeconds;
    }

    public boolean enabled() {
        return enabled;
    }

    public CodeQualityReviewProviderType provider() {
        return provider;
    }

    public String workspaceRoot() {
        return workspaceRoot;
    }

    public String codexCommand() {
        return codexCommand;
    }

    public String codexModel() {
        return codexModel;
    }

    public int codexTimeoutSeconds() {
        return codexTimeoutSeconds;
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

    private static CodeQualityReviewProviderType parseProvider(String provider) {
        if (!StringUtils.hasText(provider)) {
            return CodeQualityReviewProviderType.CODEX_CLI;
        }
        return CodeQualityReviewProviderType.valueOf(provider.trim());
    }
}
