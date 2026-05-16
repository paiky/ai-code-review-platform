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
import com.leaf.codereview.notification.application.DingTalkNotifier;
import com.leaf.codereview.notification.domain.DingTalkMessageContext;
import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import com.leaf.codereview.notification.domain.NotificationStatus;
import com.leaf.codereview.notification.infrastructure.NotificationRecordRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressEventRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressTracker;
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
    private final DingTalkNotifier dingTalkNotifier = mock(DingTalkNotifier.class);
    private final NotificationRecordRepository notificationRecordRepository = mock(NotificationRecordRepository.class);
    private final CodeQualityReviewProgressEventRepository progressEventRepository = mock(CodeQualityReviewProgressEventRepository.class);
    private final CodeQualityReviewProgressTracker progressTracker = new CodeQualityReviewProgressTracker(progressEventRepository);

    @Test
    void triggersOpenAiReviewWithMrDiffAndPersistsResult() {
        CodeQualityAsyncReviewExecutor executor = newExecutor();
        CodeQualityReviewResult result = CodeQualityReviewResult.success(
                CodeQualityReviewProviderType.OPENAI,
                "HIGH",
                "summary",
                List.of(),
                "{}",
                null,
                OffsetDateTime.now(),
                OffsetDateTime.now()
        );
        when(reviewService.review(any(), any())).thenReturn(result);
        when(resultRepository.save(eq(99L), eq(1L), eq("backend-default-ai-review"), eq("gpt-5.4"), eq(result))).thenReturn(500L);
        DingTalkNotificationResult notificationResult = new DingTalkNotificationResult(NotificationStatus.SKIPPED, "DINGTALK_WEBHOOK_URL", "digest", null, "skip");
        when(dingTalkNotifier.sendReviewSummary(eq(99L), any(), any(), eq(result), any(DingTalkMessageContext.class))).thenReturn(notificationResult);

        executor.execute(99L, project(), event(), profile(CodeQualityReviewProviderType.DEEPSEEK), CodeQualityReviewProviderType.OPENAI);

        ArgumentCaptor<CodeQualityReviewRequest> requestCaptor = ArgumentCaptor.forClass(CodeQualityReviewRequest.class);
        verify(reviewService).review(requestCaptor.capture(), eq(CodeQualityReviewProviderType.OPENAI));
        assertThat(requestCaptor.getValue().mode()).isEqualTo(CodeQualityReviewMode.DIFF_TEXT);
        assertThat(requestCaptor.getValue().diffText()).contains("OrderService.java", "createOrder");
        assertThat(requestCaptor.getValue().changedFiles()).contains("src/main/java/com/demo/OrderService.java");
        assertThat(requestCaptor.getValue().instructions()).isEqualTo("OpenAI instructions");
        verify(resultRepository).save(99L, 1L, "backend-default-ai-review", "gpt-5.4", result);
        verify(dingTalkNotifier).sendReviewSummary(eq(99L), any(), any(), eq(result), any(DingTalkMessageContext.class));
        verify(notificationRecordRepository).saveDingTalkRecord(99L, 500L, notificationResult);
    }

    @Test
    void triggersCodexCliReviewWithMrDiffWithoutLocalRepository() {
        CodeQualityAsyncReviewExecutor executor = newExecutor();
        CodeQualityReviewResult result = CodeQualityReviewResult.success(
                CodeQualityReviewProviderType.DEEPSEEK,
                "HIGH",
                "summary",
                List.of(),
                "raw",
                0,
                OffsetDateTime.now(),
                OffsetDateTime.now()
        );
        when(reviewService.review(any(), any())).thenReturn(result);
        when(resultRepository.save(eq(99L), eq(1L), eq("backend-default-ai-review"), eq("gpt-5.4"), eq(result))).thenReturn(501L);
        DingTalkNotificationResult notificationResult = new DingTalkNotificationResult(NotificationStatus.SKIPPED, "DINGTALK_WEBHOOK_URL", "digest", null, "skip");
        when(dingTalkNotifier.sendReviewSummary(eq(99L), any(), any(), eq(result), any(DingTalkMessageContext.class))).thenReturn(notificationResult);

        executor.execute(99L, project(), event(), profile(CodeQualityReviewProviderType.OPENAI), CodeQualityReviewProviderType.DEEPSEEK);

        ArgumentCaptor<CodeQualityReviewRequest> requestCaptor = ArgumentCaptor.forClass(CodeQualityReviewRequest.class);
        verify(reviewService).review(requestCaptor.capture(), eq(CodeQualityReviewProviderType.DEEPSEEK));
        assertThat(requestCaptor.getValue().repositoryPath()).isNull();
        assertThat(requestCaptor.getValue().mode()).isEqualTo(CodeQualityReviewMode.DIFF_TEXT);
        assertThat(requestCaptor.getValue().diffText()).contains("OrderService.java", "createOrder");
        verify(resultRepository).save(99L, 1L, "backend-default-ai-review", "gpt-5.4", result);
        verify(notificationRecordRepository).saveDingTalkRecord(99L, 501L, notificationResult);
    }

    private CodeQualityAsyncReviewExecutor newExecutor() {
        return new CodeQualityAsyncReviewExecutor(progressTracker, reviewService, resultRepository, dingTalkNotifier, notificationRecordRepository);
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


