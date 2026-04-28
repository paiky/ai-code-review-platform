package com.leaf.codereview.projectintegration.infrastructure;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.projectintegration.domain.GitLabPushEvent;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class GitLabPushWebhookEventRepository {

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public GitLabPushWebhookEventRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public void save(Long taskId, GitLabPushEvent event) {
        jdbcTemplate.update("""
                INSERT INTO gitlab_push_webhook_events (
                  task_id, git_project_id, project_name, ref, branch_name,
                  before_sha, after_sha, event_time, author_name, author_username,
                  changed_files_summary, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                taskId,
                event.gitProjectId(),
                event.projectName(),
                event.ref(),
                event.branchName(),
                event.beforeSha(),
                event.afterSha(),
                event.eventTime(),
                event.authorName(),
                event.authorUsername(),
                writeJson(event.changedFilesSummary()),
                writeJson(event.rawPayload())
        );
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("Failed to serialize push webhook json", exception);
        }
    }
}
