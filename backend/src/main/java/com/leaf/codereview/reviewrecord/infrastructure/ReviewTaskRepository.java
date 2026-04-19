package com.leaf.codereview.reviewrecord.infrastructure;

import com.leaf.codereview.reviewrecord.domain.ReviewTaskCreateCommand;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.LocalDateTime;
import java.util.Objects;

@Repository
public class ReviewTaskRepository {

    private final JdbcTemplate jdbcTemplate;

    public ReviewTaskRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Long create(ReviewTaskCreateCommand command) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement("""
                    INSERT INTO review_tasks (
                      project_id, trigger_type, external_source_id, external_url,
                      source_branch, target_branch, commit_sha, before_sha, after_sha,
                      author_name, author_username, template_code, status, started_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1, command.projectId());
            ps.setString(2, command.triggerType());
            ps.setString(3, command.externalSourceId());
            ps.setString(4, command.externalUrl());
            ps.setString(5, command.sourceBranch());
            ps.setString(6, command.targetBranch());
            ps.setString(7, command.commitSha());
            ps.setString(8, command.beforeSha());
            ps.setString(9, command.afterSha());
            ps.setString(10, command.authorName());
            ps.setString(11, command.authorUsername());
            ps.setString(12, command.templateCode());
            ps.setString(13, command.status());
            ps.setObject(14, LocalDateTime.now());
            return ps;
        }, keyHolder);
        return Objects.requireNonNull(keyHolder.getKey()).longValue();
    }

    public void markSuccess(Long taskId, String riskLevel) {
        jdbcTemplate.update("""
                UPDATE review_tasks
                SET status = 'SUCCESS', risk_level = ?, error_message = NULL, finished_at = ?
                WHERE id = ?
                """, riskLevel, LocalDateTime.now(), taskId);
    }

    public void markFailed(Long taskId, String errorMessage) {
        jdbcTemplate.update("""
                UPDATE review_tasks
                SET status = 'FAILED', error_message = ?, finished_at = ?
                WHERE id = ?
                """, truncate(errorMessage), LocalDateTime.now(), taskId);
    }

    private String truncate(String value) {
        if (value == null || value.length() <= 1024) {
            return value;
        }
        return value.substring(0, 1024);
    }
}