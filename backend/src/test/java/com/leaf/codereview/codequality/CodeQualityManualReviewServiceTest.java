package com.leaf.codereview.codequality;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.codequality.application.CodeQualityManualReviewService;
import com.leaf.codereview.codequality.application.CodeQualityReviewService;
import com.leaf.codereview.codequality.controller.CodeQualityManualReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewMode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProfile;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProfileRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressEventRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressTracker;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewResultRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewSettingsRepository;
import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import com.leaf.codereview.projectintegration.infrastructure.ProjectRepository;
import com.leaf.codereview.reviewrecord.domain.ReviewTaskCreateCommand;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewTaskRepository;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class CodeQualityManualReviewServiceTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final ProjectRepository projectRepository = mock(ProjectRepository.class);
    private final CodeQualityReviewProfileRepository profileRepository = mock(CodeQualityReviewProfileRepository.class);
    private final ReviewTaskRepository reviewTaskRepository = mock(ReviewTaskRepository.class);
    private final CodeQualityReviewService codeQualityReviewService = mock(CodeQualityReviewService.class);
    private final CodeQualityReviewResultRepository resultRepository = mock(CodeQualityReviewResultRepository.class);
    private final CodeQualityReviewProgressEventRepository progressEventRepository = mock(CodeQualityReviewProgressEventRepository.class);
    private final CodeQualityReviewProgressTracker progressTracker = new CodeQualityReviewProgressTracker(progressEventRepository);
    private final CodeQualityReviewSettingsRepository settingsRepository = mock(CodeQualityReviewSettingsRepository.class);
    private final CodeQualityReviewProperties properties = new CodeQualityReviewProperties(
            true,
            CodeQualityReviewProviderType.CODEX_CLI,
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
    private final CodeQualityManualReviewService service = new CodeQualityManualReviewService(
            projectRepository,
            profileRepository,
            reviewTaskRepository,
            codeQualityReviewService,
            resultRepository,
            progressEventRepository,
            progressTracker,
            properties,
            settingsRepository
    );

    @Test
    void createsTaskRunsProviderAndPersistsResult() {
        ProjectRecord project = new ProjectRecord(1L, "demo", "GITLAB", "1001", null, "backend-default", "backend-default-ai-review", "ENABLED");
        CodeQualityReviewProfile profile = new CodeQualityReviewProfile(
                10L,
                "backend-default-ai-review",
                "Backend AI",
                true,
                CodeQualityReviewProviderType.OPENAI_API,
                "gpt-5.4",
                true,
                true,
                false,
                "MAJOR",
                objectMapper.createArrayNode().add("CRITICAL"),
                objectMapper.createArrayNode().add("CORRECTNESS"),
                objectMapper.createArrayNode(),
                objectMapper.createArrayNode(),
                30,
                200000,
                300,
                true,
                "Codex prompt",
                "Profile instructions"
        );
        CodeQualityReviewResult result = CodeQualityReviewResult.success(
                CodeQualityReviewProviderType.OPENAI_API,
                "HIGH",
                "Found one issue",
                List.of(),
                "{\"summary\":\"Found one issue\"}",
                null,
                OffsetDateTime.now(),
                OffsetDateTime.now()
        );
        when(projectRepository.findById(1L)).thenReturn(Optional.of(project));
        when(profileRepository.findByCode("backend-default-ai-review")).thenReturn(Optional.of(profile));
        when(reviewTaskRepository.create(any(ReviewTaskCreateCommand.class))).thenReturn(99L);
        when(settingsRepository.reviewProvider()).thenReturn(CodeQualityReviewProviderType.OPENAI_API);
        when(codeQualityReviewService.review(any(CodeQualityReviewRequest.class), any())).thenReturn(result);

        service.createManualReview(new CodeQualityManualReviewRequest(
                1L,
                null,
                null,
                CodeQualityReviewMode.DIFF_TEXT,
                null,
                null,
                "Manual review",
                null,
                "Manual override",
                "+ code",
                List.of("OrderService.java")
        ));

        ArgumentCaptor<ReviewTaskCreateCommand> taskCaptor = ArgumentCaptor.forClass(ReviewTaskCreateCommand.class);
        verify(reviewTaskRepository).create(taskCaptor.capture());
        assertThat(taskCaptor.getValue().triggerType()).isEqualTo("CODE_QUALITY_MANUAL");
        assertThat(taskCaptor.getValue().templateCode()).isEqualTo("backend-default-ai-review");

        ArgumentCaptor<CodeQualityReviewRequest> requestCaptor = ArgumentCaptor.forClass(CodeQualityReviewRequest.class);
        verify(codeQualityReviewService).review(requestCaptor.capture(), any());
        assertThat(requestCaptor.getValue().model()).isEqualTo("gpt-5.4");
        assertThat(requestCaptor.getValue().instructions()).contains("Profile instructions", "Manual override");

        verify(resultRepository).save(99L, 1L, "backend-default-ai-review", "gpt-5.4", result);
        verify(reviewTaskRepository).markSuccess(99L, "HIGH");
    }
}


