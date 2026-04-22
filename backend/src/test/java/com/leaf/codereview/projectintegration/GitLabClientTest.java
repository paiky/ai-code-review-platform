package com.leaf.codereview.projectintegration;

import com.leaf.codereview.common.exception.BusinessException;
import com.leaf.codereview.projectintegration.domain.GitLabDiffFile;
import com.leaf.codereview.projectintegration.domain.GitLabMergeRequestDetail;
import com.leaf.codereview.projectintegration.domain.GitLabProjectDetail;
import com.leaf.codereview.projectintegration.infrastructure.GitLabApiProperties;
import com.leaf.codereview.projectintegration.infrastructure.GitLabClient;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;

class GitLabClientTest {

    @Test
    void fetchesMergeRequestDiffsWithPagination() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        GitLabClient client = new GitLabClient(
                new GitLabApiProperties(true, "https://gitlab.example.com/", "test-token", 2),
                builder
        );

        server.expect(requestTo("https://gitlab.example.com/api/v4/projects/1001/merge_requests/21/diffs?page=1&per_page=2"))
                .andExpect(header("PRIVATE-TOKEN", "test-token"))
                .andRespond(withSuccess("""
                        [
                          {
                            "old_path": "src/main/java/com/demo/order/OrderController.java",
                            "new_path": "src/main/java/com/demo/order/OrderController.java",
                            "diff": "+ @PostMapping(\\"/api/orders/{id}/confirm\\")",
                            "new_file": false,
                            "renamed_file": false,
                            "deleted_file": false,
                            "collapsed": false,
                            "too_large": false
                          },
                          {
                            "old_path": "src/main/resources/mapper/OrderMapper.xml",
                            "new_path": "src/main/resources/mapper/OrderMapper.xml",
                            "diff": "+ update orders set status = 'CONFIRMED'",
                            "new_file": false,
                            "renamed_file": false,
                            "deleted_file": false,
                            "collapsed": false,
                            "too_large": false
                          }
                        ]
                        """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://gitlab.example.com/api/v4/projects/1001/merge_requests/21/diffs?page=2&per_page=2"))
                .andExpect(header("PRIVATE-TOKEN", "test-token"))
                .andRespond(withSuccess("""
                        [
                          {
                            "old_path": "src/main/resources/application.yml",
                            "new_path": "src/main/resources/application.yml",
                            "diff": "+ order:\\n+   enable-confirm-event: true",
                            "new_file": false,
                            "renamed_file": false,
                            "deleted_file": false,
                            "collapsed": false,
                            "too_large": false
                          }
                        ]
                        """, MediaType.APPLICATION_JSON));

        List<GitLabDiffFile> files = client.listMergeRequestDiffs("1001", "21");

        assertThat(files).hasSize(3);
        assertThat(files.getFirst().newPath()).isEqualTo("src/main/java/com/demo/order/OrderController.java");
        assertThat(files.getFirst().diffText()).contains("@PostMapping");
        assertThat(files.get(2).newPath()).isEqualTo("src/main/resources/application.yml");
        server.verify();
    }

    @Test
    void fallsBackToMergeRequestChangesWhenDiffsEndpointIsMissing() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        GitLabClient client = new GitLabClient(
                new GitLabApiProperties(true, "https://gitlab.example.com/", "test-token", 100),
                builder
        );

        server.expect(requestTo("https://gitlab.example.com/api/v4/projects/1001/merge_requests/21/diffs?page=1&per_page=100"))
                .andExpect(header("PRIVATE-TOKEN", "test-token"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND).body("{\"error\":\"404 Not Found\"}").contentType(MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://gitlab.example.com/api/v4/projects/1001/merge_requests/21/changes"))
                .andExpect(header("PRIVATE-TOKEN", "test-token"))
                .andRespond(withSuccess("""
                        {
                          "id": 4569,
                          "iid": 21,
                          "changes": [
                            {
                              "old_path": "src/main/java/com/demo/order/OrderController.java",
                              "new_path": "src/main/java/com/demo/order/OrderController.java",
                              "diff": "+ @PostMapping(\\"/api/orders/{id}/confirm\\")",
                              "new_file": false,
                              "renamed_file": false,
                              "deleted_file": false
                            }
                          ]
                        }
                        """, MediaType.APPLICATION_JSON));

        List<GitLabDiffFile> files = client.listMergeRequestDiffs("1001", "21");

        assertThat(files).hasSize(1);
        assertThat(files.getFirst().newPath()).isEqualTo("src/main/java/com/demo/order/OrderController.java");
        assertThat(files.getFirst().diffText()).contains("@PostMapping");
        server.verify();
    }

    @Test
    void fetchesProjectAndMergeRequestDetail() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        GitLabClient client = new GitLabClient(
                new GitLabApiProperties(true, "https://gitlab.example.com/", "test-token", 100),
                builder
        );

        server.expect(requestTo("https://gitlab.example.com/api/v4/projects/1001"))
                .andExpect(header("PRIVATE-TOKEN", "test-token"))
                .andRespond(withSuccess("""
                        {
                          "id": 1001,
                          "name": "demo-service",
                          "path_with_namespace": "group/demo-service",
                          "web_url": "https://gitlab.example.com/group/demo-service"
                        }
                        """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://gitlab.example.com/api/v4/projects/1001/merge_requests/21"))
                .andExpect(header("PRIVATE-TOKEN", "test-token"))
                .andRespond(withSuccess("""
                        {
                          "iid": 21,
                          "title": "feat: use real gitlab details",
                          "web_url": "https://gitlab.example.com/group/demo-service/-/merge_requests/21",
                          "source_branch": "feature/real-source",
                          "target_branch": "main",
                          "sha": "abcdef123456",
                          "author": {
                            "name": "GitLab User",
                            "username": "gitlab-user"
                          }
                        }
                        """, MediaType.APPLICATION_JSON));

        GitLabProjectDetail projectDetail = client.getProjectDetail("1001");
        GitLabMergeRequestDetail mergeRequestDetail = client.getMergeRequestDetail("1001", "21");

        assertThat(projectDetail.pathWithNamespace()).isEqualTo("group/demo-service");
        assertThat(projectDetail.webUrl()).isEqualTo("https://gitlab.example.com/group/demo-service");
        assertThat(mergeRequestDetail.webUrl()).isEqualTo("https://gitlab.example.com/group/demo-service/-/merge_requests/21");
        assertThat(mergeRequestDetail.sourceBranch()).isEqualTo("feature/real-source");
        assertThat(mergeRequestDetail.targetBranch()).isEqualTo("main");
        assertThat(mergeRequestDetail.commitSha()).isEqualTo("abcdef123456");
        assertThat(mergeRequestDetail.authorUsername()).isEqualTo("gitlab-user");
        server.verify();
    }

    @Test
    void failsWhenGitLabApiIsDisabled() {
        GitLabClient client = new GitLabClient(
                new GitLabApiProperties(false, "https://gitlab.example.com", "test-token", 100),
                RestClient.builder()
        );

        assertThatThrownBy(() -> client.listMergeRequestDiffs("1001", "21"))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("GitLab API is disabled");
    }
}
