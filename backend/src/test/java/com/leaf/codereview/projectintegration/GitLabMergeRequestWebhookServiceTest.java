package com.leaf.codereview.projectintegration;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.changeanalysis.application.ChangeAnalysisService;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisRequest;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisResult;
import com.leaf.codereview.notification.application.DingTalkNotifier;
import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import com.leaf.codereview.notification.domain.NotificationStatus;
import com.leaf.codereview.notification.infrastructure.NotificationRecordRepository;
import com.leaf.codereview.projectintegration.application.GitLabMergeRequestWebhookService;
import com.leaf.codereview.projectintegration.domain.GitLabDiffFile;
import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import com.leaf.codereview.projectintegration.infrastructure.GitLabClient;
import com.leaf.codereview.projectintegration.infrastructure.GitLabMrWebhookEventRepository;
import com.leaf.codereview.projectintegration.infrastructure.ProjectRepository;
import com.leaf.codereview.reviewrecord.domain.ReviewTaskCreateCommand;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewResultRepository;
import com.leaf.codereview.reviewrecord.infrastructure.ReviewTaskRepository;
import com.leaf.codereview.riskengine.application.RiskCardGenerator;
import com.leaf.codereview.riskengine.domain.RiskCard;
import com.leaf.codereview.riskengine.domain.RiskLevel;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class GitLabMergeRequestWebhookServiceTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final ProjectRepository projectRepository = mock(ProjectRepository.class);
    private final ReviewTaskRepository reviewTaskRepository = mock(ReviewTaskRepository.class);
    private final ReviewResultRepository reviewResultRepository = mock(ReviewResultRepository.class);
    private final GitLabMrWebhookEventRepository webhookEventRepository = mock(GitLabMrWebhookEventRepository.class);
    private final ChangeAnalysisService changeAnalysisService = mock(ChangeAnalysisService.class);
    private final RiskCardGenerator riskCardGenerator = mock(RiskCardGenerator.class);
    private final DingTalkNotifier dingTalkNotifier = mock(DingTalkNotifier.class);
    private final NotificationRecordRepository notificationRecordRepository = mock(NotificationRecordRepository.class);
    private final GitLabClient gitLabClient = mock(GitLabClient.class);

    @Test
    void fetchesGitLabDiffsWhenWebhookPayloadDoesNotProvideChangedFiles() throws Exception {
        GitLabMergeRequestWebhookService service = newService();
        stubSuccessfulReview();
        when(gitLabClient.listMergeRequestDiffs("1001", "21")).thenReturn(List.of(
                new GitLabDiffFile(
                        "src/main/java/com/demo/order/OrderController.java",
                        "src/main/java/com/demo/order/OrderController.java",
                        "+ @PostMapping(\"/api/orders/{id}/confirm\")",
                        false,
                        false,
                        false,
                        false,
                        false
                )
        ));

        service.handle("Merge Request Hook", objectMapper.readTree("""
                {
                  "object_kind": "merge_request",
                  "project": {
                    "id": 1001,
                    "name": "demo-service",
                    "web_url": "https://gitlab.example.com/group/demo-service"
                  },
                  "object_attributes": {
                    "iid": 21,
                    "action": "open",
                    "source_branch": "feature/gitlab-api-diff",
                    "target_branch": "main",
                    "url": "https://gitlab.example.com/group/demo-service/-/merge_requests/21",
                    "updated_at": "2026-04-21T22:38:00+08:00",
                    "last_commit": {
                      "id": "abcdef123456"
                    }
                  },
                  "user": {
                    "name": "GitLab User",
                    "username": "gitlab-user"
                  }
                }
                """));

        verify(gitLabClient).listMergeRequestDiffs("1001", "21");

        ArgumentCaptor<ChangeAnalysisRequest> requestCaptor = ArgumentCaptor.forClass(ChangeAnalysisRequest.class);
        verify(changeAnalysisService).analyze(requestCaptor.capture());
        assertThat(requestCaptor.getValue().changedFiles()).hasSize(1);
        assertThat(requestCaptor.getValue().changedFiles().getFirst().diffText()).contains("@PostMapping");

        ArgumentCaptor<com.fasterxml.jackson.databind.JsonNode> summaryCaptor = ArgumentCaptor.forClass(com.fasterxml.jackson.databind.JsonNode.class);
        verify(webhookEventRepository).updateChangedFilesSummary(eq(99L), summaryCaptor.capture());
        assertThat(summaryCaptor.getValue().path("source").asText()).isEqualTo("gitlab_api");
        assertThat(summaryCaptor.getValue().path("count").asInt()).isEqualTo(1);
    }

    @Test
    void keepsPayloadChangedFilesWhenWebhookProvidesThem() throws Exception {
        GitLabMergeRequestWebhookService service = newService();
        stubSuccessfulReview();

        service.handle("Merge Request Hook", objectMapper.readTree("""
                {
                  "object_kind": "merge_request",
                  "project": {
                    "id": 1001,
                    "name": "demo-service",
                    "web_url": "https://gitlab.example.com/group/demo-service"
                  },
                  "object_attributes": {
                    "iid": 21,
                    "action": "open",
                    "source_branch": "feature/payload-diff",
                    "target_branch": "main",
                    "url": "https://gitlab.example.com/group/demo-service/-/merge_requests/21",
                    "updated_at": "2026-04-21T22:38:00+08:00",
                    "last_commit": {
                      "id": "abcdef123456"
                    }
                  },
                  "user": {
                    "name": "GitLab User",
                    "username": "gitlab-user"
                  },
                  "changedFiles": [
                    {
                      "old_path": "src/main/resources/application.yml",
                      "new_path": "src/main/resources/application.yml",
                      "diffText": "+ order:\\n+   feature-enabled: true"
                    }
                  ]
                }
                """));

        verify(gitLabClient, never()).listMergeRequestDiffs(any(), any());
        verify(webhookEventRepository, never()).updateChangedFilesSummary(any(), any());
    }

    private GitLabMergeRequestWebhookService newService() {
        return new GitLabMergeRequestWebhookService(
                objectMapper,
                projectRepository,
                reviewTaskRepository,
                reviewResultRepository,
                webhookEventRepository,
                changeAnalysisService,
                riskCardGenerator,
                dingTalkNotifier,
                notificationRecordRepository,
                gitLabClient
        );
    }

    private void stubSuccessfulReview() {
        when(projectRepository.upsertGitLabProject(any(), any(), any())).thenReturn(new ProjectRecord(
                1L,
                "demo-service",
                "GITLAB",
                "1001",
                "https://gitlab.example.com/group/demo-service",
                "backend-default",
                "ACTIVE"
        ));
        when(reviewTaskRepository.create(any(ReviewTaskCreateCommand.class))).thenReturn(99L);
        when(changeAnalysisService.analyze(any())).thenReturn(new ChangeAnalysisResult(
                "summary",
                1,
                Set.of(),
                List.of(),
                List.of(),
                List.of()
        ));
        when(riskCardGenerator.generate(any(), eq("backend-default"))).thenReturn(new RiskCard(
                "risk-card-test",
                "summary",
                RiskLevel.LOW,
                List.of(),
                List.of(),
                List.of(),
                Set.of(),
                OffsetDateTime.parse("2026-04-21T22:38:00+08:00"),
                "test"
        ));
        when(reviewResultRepository.save(any(), any(), any(), any(), any())).thenReturn(88L);
        when(dingTalkNotifier.sendRiskCard(any(), any())).thenReturn(new DingTalkNotificationResult(
                NotificationStatus.SKIPPED,
                "DINGTALK_WEBHOOK_URL",
                null,
                null,
                "DingTalk webhook is not configured"
        ));
    }
}
