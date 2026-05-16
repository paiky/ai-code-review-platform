package com.leaf.codereview.codequality;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.leaf.codereview.codequality.application.CodeQualityAsyncReviewExecutor;
import com.leaf.codereview.codequality.application.CodeQualityAutoReviewService;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProfile;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProfileRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressEventRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewResultRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewSettingsRepository;
import com.leaf.codereview.projectintegration.domain.GitLabMergeRequestEvent;
import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import com.leaf.codereview.projectintegration.infrastructure.ProjectRepository;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewTaskQueryRepository;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class CodeQualityAutoReviewServiceTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final CodeQualityReviewProfileRepository profileRepository = mock(CodeQualityReviewProfileRepository.class);
    private final CodeQualityReviewResultRepository resultRepository = mock(CodeQualityReviewResultRepository.class);
    private final CodeQualityReviewSettingsRepository settingsRepository = mock(CodeQualityReviewSettingsRepository.class);
    private final CodeQualityReviewProgressEventRepository progressEventRepository = mock(CodeQualityReviewProgressEventRepository.class);
    private final ProjectRepository projectRepository = mock(ProjectRepository.class);
    private final ReviewTaskQueryRepository reviewTaskQueryRepository = mock(ReviewTaskQueryRepository.class);
    private final CodeQualityAsyncReviewExecutor executor = mock(CodeQualityAsyncReviewExecutor.class);

    @Test
    void skipsWhenGlobalCodeQualityReviewIsDisabled() {
        CodeQualityAutoReviewService service = newService(false);

        service.triggerAfterMergeRequestReview(99L, project(), event());

        verify(profileRepository, never()).findByCode(any());
        verify(executor, never()).execute(any(), any(), any(), any(), any());
    }

    @Test
    void skipsWhenMrAutoReviewSwitchIsDisabled() {
        CodeQualityAutoReviewService service = newService(true);
        when(settingsRepository.mrAutoReviewEnabled()).thenReturn(false);

        service.triggerAfterMergeRequestReview(99L, project(), event());

        verify(profileRepository, never()).findByCode(any());
        verify(executor, never()).execute(any(), any(), any(), any(), any());
    }

    @Test
    void writesRunningAndSchedulesAsyncReview() {
        CodeQualityAutoReviewService service = newService(true);
        CodeQualityReviewProfile profile = profile(CodeQualityReviewProviderType.OPENAI, true);
        when(settingsRepository.mrAutoReviewEnabled()).thenReturn(true);
        when(settingsRepository.reviewProvider()).thenReturn(CodeQualityReviewProviderType.ANTHROPIC);
        when(resultRepository.existsByTaskId(99L)).thenReturn(false);
        when(profileRepository.findByCode("backend-default-ai-review")).thenReturn(Optional.of(profile));

        service.triggerAfterMergeRequestReview(99L, project(), event());

        ArgumentCaptor<CodeQualityReviewResult> resultCaptor = ArgumentCaptor.forClass(CodeQualityReviewResult.class);
        verify(resultRepository).save(eq(99L), eq(1L), eq("backend-default-ai-review"), eq("gpt-5.4"), resultCaptor.capture());
        assertThat(resultCaptor.getValue().status()).isEqualTo("RUNNING");
        assertThat(resultCaptor.getValue().provider()).isEqualTo(CodeQualityReviewProviderType.OPENAI);
        assertThat(resultCaptor.getValue().startedAt()).isNotNull();
        verify(executor).execute(eq(99L), eq(project()), any(GitLabMergeRequestEvent.class), eq(profile), eq(CodeQualityReviewProviderType.OPENAI));
    }

    private CodeQualityAutoReviewService newService(boolean enabled) {
        CodeQualityReviewProperties properties = new CodeQualityReviewProperties(
                enabled,
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
        return new CodeQualityAutoReviewService(
                properties,
                profileRepository,
                resultRepository,
                settingsRepository,
                progressEventRepository,
                projectRepository,
                reviewTaskQueryRepository,
                executor
        );
    }

    private CodeQualityReviewProfile profile(CodeQualityReviewProviderType provider, boolean triggerOnMr) {
        return new CodeQualityReviewProfile(
                10L,
                "backend-default-ai-review",
                "Backend AI",
                true,
                provider,
                "gpt-5.4",
                true,
                triggerOnMr,
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

    private ProjectRecord project() {
        return new ProjectRecord(
                1L,
                "demo-service",
                "GITLAB",
                "1001",
                "https://gitlab.example.com/group/demo-service.git",
                "backend-default",
                "backend-default-ai-review",
                "ENABLED"
        );
    }

    private GitLabMergeRequestEvent event() {
        ObjectNode summary = objectMapper.createObjectNode();
        summary.put("source", "gitlab_api");
        var files = objectMapper.createArrayNode();
        ObjectNode file = objectMapper.createObjectNode();
        file.put("path", "src/main/java/com/demo/OrderService.java");
        file.put("diffText", "+ public void createOrder() {}");
        files.add(file);
        summary.set("files", files);
        summary.put("count", 1);
        return new GitLabMergeRequestEvent(
                "1001",
                "demo-service",
                "https://gitlab.example.com/group/demo-service",
                "21",
                "open",
                LocalDateTime.parse("2026-05-08T20:00:00"),
                "https://gitlab.example.com/group/demo-service/-/merge_requests/21",
                "feature/order",
                "main",
                "abcdef",
                "Alice",
                "alice",
                summary,
                objectMapper.createObjectNode()
        );
    }
}


