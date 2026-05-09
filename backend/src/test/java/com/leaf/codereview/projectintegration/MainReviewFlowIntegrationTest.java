package com.leaf.codereview.projectintegration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.common.response.PageResponse;
import com.leaf.codereview.projectintegration.domain.GitLabDiffFile;
import com.leaf.codereview.projectintegration.domain.GitLabMergeRequestDetail;
import com.leaf.codereview.projectintegration.domain.GitLabProjectDetail;
import com.leaf.codereview.projectintegration.infrastructure.GitLabClient;
import com.leaf.codereview.reviewrecord.application.ReviewTaskDetailResponse;
import com.leaf.codereview.reviewrecord.application.ReviewTaskListItemResponse;
import com.leaf.codereview.reviewrecord.application.ReviewTaskQueryService;
import com.leaf.codereview.reviewrecord.application.ReviewTaskResultResponse;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:mainflow;MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.flyway.enabled=false",
        "spring.sql.init.mode=always",
        "spring.sql.init.schema-locations=classpath:main-flow-test-schema.sql",
        "notification.dingtalk.webhook-url=",
        "notification.dingtalk.enabled=true"
})
class MainReviewFlowIntegrationTest {

    private static final String GITLAB_MR_EVENT = "Merge Request Hook";
    private static final String GITLAB_PUSH_EVENT = "Push Hook";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private ReviewTaskQueryService reviewTaskQueryService;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @MockBean
    private GitLabClient gitLabClient;

    @Test
    void mockWebhookCreatesReviewResultAndNotificationRecord() throws Exception {
        JsonNode response = postWebhook(GITLAB_MR_EVENT, readExample("examples/gitlab-mr-webhook.mock.json"));
        long taskId = response.path("data").path("taskId").asLong();

        assertThat(response.path("data").path("status").asText()).isEqualTo("SUCCESS");
        verify(gitLabClient, never()).listMergeRequestDiffs("1001", "21");

        ReviewTaskDetailResponse detail = reviewTaskQueryService.getDetail(taskId);
        assertThat(detail.status()).isEqualTo("SUCCESS");
        assertThat(detail.projectName()).isEqualTo("demo-service");
        assertThat(detail.changedFilesSummary().path("source").asText()).isEqualTo("payload");
        assertThat(detail.changedFilesSummary().path("count").asInt()).isEqualTo(5);

        ReviewTaskResultResponse result = reviewTaskQueryService.getResult(taskId);
        assertThat(result.riskItemCount()).isGreaterThan(0);
        assertThat(textValues(result.changeAnalysis().path("changeTypes")))
                .contains("API", "DB_SQL", "CACHE_INVALIDATION", "MQ_PRODUCER", "CONFIG");
        assertThat(result.riskCard().path("riskItems")).isNotEmpty();

        assertSingleSkippedNotification(taskId);
    }

    @Test
    void gitLabApiSourceWebhookCreatesReviewResultAndNotificationRecord() throws Exception {
        when(gitLabClient.getProjectDetail("2002")).thenReturn(new GitLabProjectDetail(
                "2002",
                "real-service",
                "group/real-service",
                "https://gitlab.example.com/group/real-service"
        ));
        when(gitLabClient.getMergeRequestDetail("2002", "31")).thenReturn(new GitLabMergeRequestDetail(
                "31",
                "feat: add migration",
                "https://gitlab.example.com/group/real-service/-/merge_requests/31",
                "feature/real-db-change",
                "main",
                "real-sha-31",
                "Real User",
                "real-user"
        ));
        when(gitLabClient.listMergeRequestDiffs("2002", "31")).thenReturn(List.of(
                new GitLabDiffFile(
                        "backend/src/main/resources/db/migration/V7__add_order_status.sql",
                        "backend/src/main/resources/db/migration/V7__add_order_status.sql",
                        "+ ALTER TABLE orders ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'PENDING';",
                        true,
                        false,
                        false,
                        false,
                        false
                )
        ));

        JsonNode response = postWebhook(GITLAB_MR_EVENT, """
                {
                  "object_kind": "merge_request",
                  "event_type": "merge_request",
                  "event_time": "2026-04-24T20:00:00+08:00",
                  "project": {
                    "id": 2002,
                    "name": "placeholder-service",
                    "web_url": "https://gitlab.example.com/group/placeholder-service"
                  },
                  "object_attributes": {
                    "iid": 31,
                    "action": "open",
                    "source_branch": "placeholder-source",
                    "target_branch": "main",
                    "url": "https://gitlab.example.com/group/placeholder-service/-/merge_requests/31",
                    "updated_at": "2026-04-24T20:00:00+08:00",
                    "last_commit": { "id": "placeholder-sha" }
                  },
                  "user": {
                    "name": "Placeholder User",
                    "username": "placeholder-user"
                  }
                }
                """);
        long taskId = response.path("data").path("taskId").asLong();

        assertThat(response.path("data").path("status").asText()).isEqualTo("SUCCESS");
        verify(gitLabClient).listMergeRequestDiffs("2002", "31");

        ReviewTaskDetailResponse detail = reviewTaskQueryService.getDetail(taskId);
        assertThat(detail.projectName()).isEqualTo("group/real-service");
        assertThat(detail.sourceBranch()).isEqualTo("feature/real-db-change");
        assertThat(detail.commitSha()).isEqualTo("real-sha-31");
        assertThat(detail.changedFilesSummary().path("source").asText()).isEqualTo("gitlab_api");
        assertThat(detail.changedFilesSummary().path("count").asInt()).isEqualTo(1);

        ReviewTaskResultResponse result = reviewTaskQueryService.getResult(taskId);
        assertThat(result.riskLevel()).isEqualTo("HIGH");
        assertThat(result.riskCard().path("riskItems").findValuesAsText("category")).contains("DB_SCHEMA");

        assertSingleSkippedNotification(taskId);
    }

    @Test
    void pushWebhookCreatesReviewResultAndNotificationRecordOnSameEndpoint() throws Exception {
        when(gitLabClient.compare(
                "3003",
                "1111111111111111111111111111111111111111",
                "2222222222222222222222222222222222222222"
        )).thenThrow(new RuntimeException("compare unavailable"));

        JsonNode response = postWebhook(GITLAB_PUSH_EVENT, """
                {
                  "object_kind": "push",
                  "event_name": "push",
                  "before": "1111111111111111111111111111111111111111",
                  "after": "2222222222222222222222222222222222222222",
                  "ref": "refs/heads/feature/push-review",
                  "project_id": 3003,
                  "project": {
                    "id": 3003,
                    "name": "push-service",
                    "path_with_namespace": "group/push-service",
                    "web_url": "https://gitlab.example.com/group/push-service"
                  },
                  "user_name": "Push User",
                  "user_username": "push-user",
                  "commits": [
                    {
                      "id": "2222222222222222222222222222222222222222",
                      "timestamp": "2026-04-27T20:00:00+08:00",
                      "added": ["src/main/resources/application.yml"],
                      "modified": ["src/main/java/com/demo/order/OrderController.java"],
                      "removed": ["src/main/resources/legacy.properties"]
                    }
                  ]
                }
                """);
        long taskId = response.path("data").path("taskId").asLong();

        assertThat(response.path("data").path("status").asText()).isEqualTo("SUCCESS");

        ReviewTaskDetailResponse detail = reviewTaskQueryService.getDetail(taskId);
        assertThat(detail.triggerType()).isEqualTo("GITLAB_PUSH_WEBHOOK");
        assertThat(detail.status()).isEqualTo("SUCCESS");
        assertThat(detail.projectName()).isEqualTo("group/push-service");
        assertThat(detail.sourceBranch()).isEqualTo("feature/push-review");
        assertThat(detail.commitSha()).isEqualTo("2222222222222222222222222222222222222222");
        assertThat(detail.changedFilesSummary().path("source").asText()).isEqualTo("push_payload");
        assertThat(detail.changedFilesSummary().path("count").asInt()).isEqualTo(3);
        assertThat(detail.changedFilesSummary().path("fallbackReason").asText()).isEqualTo("compare unavailable");

        ReviewTaskResultResponse result = reviewTaskQueryService.getResult(taskId);
        assertThat(result.riskItemCount()).isGreaterThan(0);
        assertThat(textValues(result.changeAnalysis().path("changeTypes"))).contains("API", "CONFIG");

        assertSingleSkippedNotification(taskId);
    }

    @Test
    void pushWebhookUsesGitLabCompareDiffsWhenAvailable() throws Exception {
        when(gitLabClient.compare(
                "3004",
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        )).thenReturn(List.of(
                new GitLabDiffFile(
                        "src/main/java/com/demo/order/OrderController.java",
                        "src/main/java/com/demo/order/OrderController.java",
                        "+ @PostMapping(\"/api/orders/{id}/confirm\")",
                        false,
                        false,
                        false,
                        false,
                        false
                ),
                new GitLabDiffFile(
                        "src/main/resources/db/migration/V8__add_order_status.sql",
                        "src/main/resources/db/migration/V8__add_order_status.sql",
                        "+ ALTER TABLE orders ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'PENDING';",
                        true,
                        false,
                        false,
                        false,
                        false
                )
        ));

        JsonNode response = postWebhook(GITLAB_PUSH_EVENT, """
                {
                  "object_kind": "push",
                  "event_name": "push",
                  "before": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                  "after": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                  "ref": "refs/heads/feature/push-compare-review",
                  "project_id": 3004,
                  "project": {
                    "id": 3004,
                    "name": "push-compare-service",
                    "path_with_namespace": "group/push-compare-service",
                    "web_url": "https://gitlab.example.com/group/push-compare-service"
                  },
                  "user_name": "Push User",
                  "user_username": "push-user",
                  "commits": [
                    {
                      "id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                      "timestamp": "2026-04-27T20:00:00+08:00",
                      "added": [],
                      "modified": ["README.md"],
                      "removed": []
                    }
                  ]
                }
                """);
        long taskId = response.path("data").path("taskId").asLong();

        assertThat(response.path("data").path("status").asText()).isEqualTo("SUCCESS");
        verify(gitLabClient).compare(
                "3004",
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        );

        ReviewTaskDetailResponse detail = reviewTaskQueryService.getDetail(taskId);
        assertThat(detail.triggerType()).isEqualTo("GITLAB_PUSH_WEBHOOK");
        assertThat(detail.changedFilesSummary().path("source").asText()).isEqualTo("gitlab_compare_api");
        assertThat(detail.changedFilesSummary().path("count").asInt()).isEqualTo(2);
        assertThat(detail.changedFilesSummary().path("files").get(0).path("diffText").asText()).contains("@PostMapping");

        ReviewTaskResultResponse result = reviewTaskQueryService.getResult(taskId);
        assertThat(textValues(result.changeAnalysis().path("changeTypes"))).contains("API", "DB_SCHEMA");
        assertThat(result.riskCard().path("riskItems").findValuesAsText("category")).contains("DB_SCHEMA");

        PageResponse<ReviewTaskListItemResponse> page = reviewTaskQueryService.findPage(null, null, null, "push-compare", 1, 20);
        assertThat(page.getItems()).singleElement().satisfies(item -> {
            assertThat(item.id()).isEqualTo(taskId);
            assertThat(item.focusIndicators().findValuesAsText("code")).contains("DB_SCHEMA_CHANGE");
            assertThat(item.focusIndicators().findValuesAsText("matched")).contains("true");
        });

        assertSingleSkippedNotification(taskId);
    }

    private JsonNode postWebhook(String gitlabEvent, String payload) throws Exception {
        String response = mockMvc.perform(post("/api/webhooks/gitlab/merge-request")
                        .header("X-Gitlab-Event", gitlabEvent)
                        .contentType("application/json")
                        .content(payload))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();
        return objectMapper.readTree(response);
    }

    private String readExample(String relativePath) throws Exception {
        return Files.readString(Path.of("..", relativePath));
    }

    private List<String> textValues(JsonNode arrayNode) {
        List<String> values = new ArrayList<>();
        arrayNode.forEach(node -> values.add(node.asText()));
        return values;
    }

    private void assertSingleSkippedNotification(long taskId) {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(1) FROM notification_records WHERE task_id = ?",
                Integer.class,
                taskId
        );
        assertThat(count).isEqualTo(1);

        String status = jdbcTemplate.queryForObject(
                "SELECT status FROM notification_records WHERE task_id = ?",
                String.class,
                taskId
        );
        assertThat(status).isEqualTo("SKIPPED");
    }
}
