package com.leaf.codereview.projectintegration.infrastructure;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.projectintegration.domain.GitLabMergeRequestEvent;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class GitLabMrWebhookEventRepository {

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public GitLabMrWebhookEventRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public void save(Long taskId, GitLabMergeRequestEvent event) {
        jdbcTemplate.update("""
                INSERT INTO gitlab_mr_webhook_events (
                  task_id, git_project_id, project_name, mr_id, event_action, event_time,
                  source_branch, target_branch, author_name, author_username,
                  changed_files_summary, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                taskId,
                event.gitProjectId(),
                event.projectName(),
                event.mrId(),
                event.eventAction(),
                event.eventTime(),
                event.sourceBranch(),
                event.targetBranch(),
                event.authorName(),
                event.authorUsername(),
                writeJson(event.changedFilesSummary()),
                writeJson(event.rawPayload())
        );
    }

    public void updateChangedFilesSummary(Long taskId, JsonNode changedFilesSummary) {
        jdbcTemplate.update("""
                UPDATE gitlab_mr_webhook_events
                SET changed_files_summary = ?
                WHERE task_id = ?
                """, writeJson(changedFilesSummary), taskId);
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("Failed to serialize webhook json", exception);
        }
    }
}
