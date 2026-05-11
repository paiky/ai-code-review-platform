package com.leaf.codereview.codequality;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.leaf.codereview.codequality.application.CodeQualityAsyncReviewExecutor;
import com.leaf.codereview.codequality.application.CodeQualityReviewService;
import com.leaf.codereview.codequality.domain.CodeQualityReviewMode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProfile;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressEventRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressTracker;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewResultRepository;
import com.leaf.codereview.projectintegration.domain.GitLabMergeRequestEvent;
import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class CodeQualityAsyncReviewExecutorTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final CodeQualityReviewService reviewService = mock(CodeQualityReviewService.class);
    private final CodeQualityReviewResultRepository resultRepository = mock(CodeQualityReviewResultRepository.class);
    private final CodeQualityReviewProgressEventRepository progressEventRepository = mock(CodeQualityReviewProgressEventRepository.class);
    private final CodeQualityReviewProgressTracker progressTracker = new CodeQualityReviewProgressTracker(progressEventRepository);

    @Test
    void triggersOpenAiReviewWithMrDiffAndPersistsResult() {
        CodeQualityAsyncReviewExecutor executor = newExecutor("");
        CodeQualityReviewResult result = CodeQualityReviewResult.success(
                CodeQualityReviewProviderType.OPENAI_API,
                "HIGH",
                "summary",
                List.of(),
                "{}",
                null,
                OffsetDateTime.now(),
                OffsetDateTime.now()
        );
        when(reviewService.review(any(), any())).thenReturn(result);

        executor.execute(99L, project(), event(), profile(CodeQualityReviewProviderType.CODEX_CLI), CodeQualityReviewProviderType.OPENAI_API);

        ArgumentCaptor<CodeQualityReviewRequest> requestCaptor = ArgumentCaptor.forClass(CodeQualityReviewRequest.class);
        verify(reviewService).review(requestCaptor.capture(), eq(CodeQualityReviewProviderType.OPENAI_API));
        assertThat(requestCaptor.getValue().mode()).isEqualTo(CodeQualityReviewMode.DIFF_TEXT);
        assertThat(requestCaptor.getValue().diffText()).contains("OrderService.java", "createOrder");
        assertThat(requestCaptor.getValue().changedFiles()).contains("src/main/java/com/demo/OrderService.java");
        assertThat(requestCaptor.getValue().instructions()).isEqualTo("OpenAI instructions");
        verify(resultRepository).save(99L, 1L, "backend-default-ai-review", "gpt-5.4", result);
    }

    @Test
    void triggersCodexCliReviewWithMrDiffWithoutLocalRepository() {
        CodeQualityAsyncReviewExecutor executor = newExecutor("");
        CodeQualityReviewResult result = CodeQualityReviewResult.success(
                CodeQualityReviewProviderType.CODEX_CLI,
                "HIGH",
                "summary",
                List.of(),
                "raw",
                0,
                OffsetDateTime.now(),
                OffsetDateTime.now()
        );
        when(reviewService.review(any(), any())).thenReturn(result);

        executor.execute(99L, project(), event(), profile(CodeQualityReviewProviderType.OPENAI_API), CodeQualityReviewProviderType.CODEX_CLI);

        ArgumentCaptor<CodeQualityReviewRequest> requestCaptor = ArgumentCaptor.forClass(CodeQualityReviewRequest.class);
        verify(reviewService).review(requestCaptor.capture(), eq(CodeQualityReviewProviderType.CODEX_CLI));
        assertThat(requestCaptor.getValue().repositoryPath()).isNull();
        assertThat(requestCaptor.getValue().mode()).isEqualTo(CodeQualityReviewMode.DIFF_TEXT);
        assertThat(requestCaptor.getValue().diffText()).contains("OrderService.java", "createOrder");
        verify(resultRepository).save(99L, 1L, "backend-default-ai-review", "gpt-5.4", result);
    }

    private CodeQualityAsyncReviewExecutor newExecutor(String workspaceRoot) {
        CodeQualityReviewProperties properties = new CodeQualityReviewProperties(
                true,
                CodeQualityReviewProviderType.CODEX_CLI,
                workspaceRoot,
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
        return new CodeQualityAsyncReviewExecutor(properties, progressTracker, reviewService, resultRepository);
    }

    private CodeQualityReviewProfile profile(CodeQualityReviewProviderType provider) {
        return new CodeQualityReviewProfile(
                10L,
                "backend-default-ai-review",
                "Backend AI",
                true,
                provider,
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


