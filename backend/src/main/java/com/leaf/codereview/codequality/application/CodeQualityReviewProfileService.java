package com.leaf.codereview.codequality.application;

import com.leaf.codereview.codequality.domain.CodeQualityReviewProfile;
import com.leaf.codereview.codequality.domain.CodeQualityReviewMode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProfileRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewSettingsRepository;
import com.leaf.codereview.codequality.infrastructure.CodexCliCommandFactory;
import com.leaf.codereview.codequality.infrastructure.OpenAiCodeQualityRequestFactory;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;

@Service
public class CodeQualityReviewProfileService {

    private final CodeQualityReviewProfileRepository repository;
    private final CodeQualityReviewProperties properties;
    private final CodeQualityReviewSettingsRepository settingsRepository;
    private final CodexCliCommandFactory codexCliCommandFactory;
    private final OpenAiCodeQualityRequestFactory openAiRequestFactory;

    public CodeQualityReviewProfileService(
            CodeQualityReviewProfileRepository repository,
            CodeQualityReviewProperties properties,
            CodeQualityReviewSettingsRepository settingsRepository,
            CodexCliCommandFactory codexCliCommandFactory,
            OpenAiCodeQualityRequestFactory openAiRequestFactory
    ) {
        this.repository = repository;
        this.properties = properties;
        this.settingsRepository = settingsRepository;
        this.codexCliCommandFactory = codexCliCommandFactory;
        this.openAiRequestFactory = openAiRequestFactory;
    }

    public List<CodeQualityReviewProfile> listEnabledProfiles() {
        return repository.findAllEnabled();
    }

    public CodeQualityReviewProfile getProfile(String profileCode) {
        return repository.findByCode(profileCode)
                .orElseThrow(() -> new BusinessException(ErrorCode.RESOURCE_NOT_FOUND, "Code quality review profile not found: " + profileCode));
    }

    public CodeQualityReviewProfile updateProfile(String profileCode, CodeQualityReviewProfileUpdateRequest request) {
        CodeQualityReviewProfile existing = getProfile(profileCode);
        repository.update(profileCode, existing, request);
        return getProfile(profileCode);
    }

    public CodeQualityRenderedPromptResponse renderedPrompt(String profileCode) {
        CodeQualityReviewProfile profile = getProfile(profileCode);
        CodeQualityReviewProviderType provider = settingsRepository.reviewProvider();
        CodeQualityReviewRequest request = previewRequest(profile, provider);
        String prompt = provider == CodeQualityReviewProviderType.CODEX_CLI
                ? codexCliCommandFactory.renderPrompt(request)
                : openAiRequestFactory.renderInstructions(request);
        return new CodeQualityRenderedPromptResponse(
                profile.profileCode(),
                provider.name(),
                StringUtils.hasText(request.model()) ? request.model() : defaultModel(provider),
                prompt,
                sha256(prompt),
                prompt.length()
        );
    }

    public CodeQualityReviewProfile resetDefaultPrompt(String profileCode) {
        CodeQualityReviewProfile existing = getProfile(profileCode);
        repository.update(profileCode, existing, new CodeQualityReviewProfileUpdateRequest(
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                CodeQualityReviewProfileDefaults.DEFAULT_CODEX_PROMPT,
                CodeQualityReviewProfileDefaults.DEFAULT_OPENAI_INSTRUCTIONS
        ));
        return getProfile(profileCode);
    }

    private CodeQualityReviewRequest previewRequest(CodeQualityReviewProfile profile, CodeQualityReviewProviderType provider) {
        String instructions = provider == CodeQualityReviewProviderType.CODEX_CLI
                ? profile.codexPrompt()
                : profile.openAiInstructions();
        return new CodeQualityReviewRequest(
                null,
                provider == CodeQualityReviewProviderType.CODEX_CLI ? CodeQualityReviewMode.BASE : CodeQualityReviewMode.DIFF_TEXT,
                "origin/main",
                null,
                "Agent Prompt preview",
                profile.model(),
                instructions,
                "",
                List.of()
        );
    }

    private String defaultModel(CodeQualityReviewProviderType provider) {
        return switch (provider) {
            case CODEX_CLI -> properties.codexModel();
            case OPENAI_API -> properties.openAiModel();
            case ANTHROPIC_API -> properties.anthropicModel();
        };
    }

    private String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest((value == null ? "" : value).getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is not available", exception);
        }
    }
}
