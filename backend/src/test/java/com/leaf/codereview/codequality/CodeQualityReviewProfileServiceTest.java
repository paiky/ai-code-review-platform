package com.leaf.codereview.codequality;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.codequality.application.CodeQualityRenderedPromptResponse;
import com.leaf.codereview.codequality.application.CodeQualityReviewProfileDefaults;
import com.leaf.codereview.codequality.application.CodeQualityReviewProfileService;
import com.leaf.codereview.codequality.application.CodeQualityReviewProfileUpdateRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProfile;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProfileRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewSettingsRepository;
import com.leaf.codereview.codequality.infrastructure.OpenAiCodeQualityRequestFactory;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class CodeQualityReviewProfileServiceTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final CodeQualityReviewProfileRepository repository = mock(CodeQualityReviewProfileRepository.class);
    private final CodeQualityReviewSettingsRepository settingsRepository = mock(CodeQualityReviewSettingsRepository.class);
    private final CodeQualityReviewProfileService service = new CodeQualityReviewProfileService(
            repository,
            properties(),
            settingsRepository,
            new OpenAiCodeQualityRequestFactory()
    );

    @Test
    void rendersPromptPreviewWithHashAndChineseWrapper() {
        when(repository.findByCode("backend-default-ai-review")).thenReturn(Optional.of(profile()));
        when(settingsRepository.reviewProvider()).thenReturn(CodeQualityReviewProviderType.DEEPSEEK);

        CodeQualityRenderedPromptResponse response = service.renderedPrompt("backend-default-ai-review");

        assertThat(response.profileCode()).isEqualTo("backend-default-ai-review");
        assertThat(response.provider()).isEqualTo("DEEPSEEK");
        assertThat(response.prompt()).contains("严格 JSON", "OpenAI instructions", "必须使用简体中文");
        assertThat(response.promptHash()).hasSize(64);
        assertThat(response.promptLength()).isEqualTo(response.prompt().length());
    }

    @Test
    void resetDefaultPromptUpdatesOnlyPromptFields() {
        when(repository.findByCode("backend-default-ai-review")).thenReturn(Optional.of(profile()));

        service.resetDefaultPrompt("backend-default-ai-review");

        ArgumentCaptor<CodeQualityReviewProfileUpdateRequest> captor = ArgumentCaptor.forClass(CodeQualityReviewProfileUpdateRequest.class);
        verify(repository).update(eq("backend-default-ai-review"), eq(profile()), captor.capture());
        assertThat(captor.getValue().reviewInstructions()).isEqualTo(CodeQualityReviewProfileDefaults.DEFAULT_OPENAI_INSTRUCTIONS);
        assertThat(captor.getValue().providerCode()).isNull();
    }

    private CodeQualityReviewProfile profile() {
        return new CodeQualityReviewProfile(
                10L,
                "backend-default-ai-review",
                "Backend AI",
                true,
                CodeQualityReviewProviderType.DEEPSEEK,
                "gpt-5.4",
                true,
                true,
                false,
                "MAJOR",
                objectMapper.createArrayNode(),
                objectMapper.createArrayNode(),
                objectMapper.createArrayNode(),
                objectMapper.createArrayNode(),
                30,
                200000,
                300,
                true,
                "Codex prompt",
                "OpenAI instructions"
        );
    }

    private CodeQualityReviewProperties properties() {
        return new CodeQualityReviewProperties(
                true,
                CodeQualityReviewProviderType.DEEPSEEK,
                "",
                "",
                "",
                600,
                "",
                "https://api.openai.com/v1/responses",
                "gpt-5.4",
                120,
                "",
                "https://api.anthropic.com/v1/messages",
                "claude-sonnet-4-5",
                120
        );
    }
}


