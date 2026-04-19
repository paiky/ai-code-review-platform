package com.leaf.codereview.reviewrecord.infrastructure;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.common.response.PageResponse;
import com.leaf.codereview.reviewrecord.application.ReviewTaskDetailResponse;
import com.leaf.codereview.reviewrecord.application.ReviewTaskListItemResponse;
import com.leaf.codereview.reviewrecord.application.ReviewTaskResultResponse;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.util.StringUtils;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

@Repository
public class ReviewTaskQueryRepository {

    private static final DateTimeFormatter DATE_TIME_FORMATTER = DateTimeFormatter.ISO_LOCAL_DATE_TIME;

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public ReviewTaskQueryRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public PageResponse<ReviewTaskListItemResponse> findPage(Long projectId, String status, String riskLevel, String keyword, int pageNo, int pageSize) {
        StringBuilder where = new StringBuilder(" WHERE 1 = 1 ");
        List<Object> args = new ArrayList<>();
        appendFilters(where, args, projectId, status, riskLevel, keyword);

        Long total = jdbcTemplate.queryForObject("""
                SELECT COUNT(1)
                FROM review_tasks rt
                JOIN projects p ON p.id = rt.project_id
                """ + where, Long.class, args.toArray());

        List<Object> queryArgs = new ArrayList<>(args);
        queryArgs.add(Math.max(pageSize, 1));
        queryArgs.add(Math.max(pageNo - 1, 0) * Math.max(pageSize, 1));

        List<ReviewTaskListItemResponse> items = jdbcTemplate.query("""
                SELECT
                  rt.id,
                  rt.project_id,
                  p.name AS project_name,
                  rt.trigger_type,
                  rt.external_source_id,
                  rt.external_url,
                  rt.source_branch,
                  rt.target_branch,
                  rt.author_name,
                  rt.template_code,
                  rt.status,
                  rt.risk_level,
                  rr.risk_item_count,
                  rt.created_at,
                  rt.finished_at
                FROM review_tasks rt
                JOIN projects p ON p.id = rt.project_id
                LEFT JOIN review_results rr ON rr.task_id = rt.id
                """ + where + " ORDER BY rt.created_at DESC LIMIT ? OFFSET ?",
                (rs, rowNum) -> mapListItem(rs),
                queryArgs.toArray());
        return new PageResponse<>(items, pageNo, pageSize, total == null ? 0 : total);
    }

    public Optional<ReviewTaskDetailResponse> findDetailById(Long taskId) {
        List<ReviewTaskDetailResponse> results = jdbcTemplate.query("""
                SELECT
                  rt.id,
                  rt.project_id,
                  p.name AS project_name,
                  p.git_project_id,
                  rt.trigger_type,
                  rt.external_source_id,
                  rt.external_url,
                  rt.source_branch,
                  rt.target_branch,
                  rt.commit_sha,
                  rt.author_name,
                  rt.author_username,
                  rt.template_code,
                  rt.status,
                  rt.risk_level,
                  rt.created_at,
                  rt.updated_at,
                  gwe.mr_id,
                  gwe.event_action,
                  gwe.event_time,
                  gwe.changed_files_summary,
                  gwe.raw_payload
                FROM review_tasks rt
                JOIN projects p ON p.id = rt.project_id
                LEFT JOIN gitlab_mr_webhook_events gwe ON gwe.task_id = rt.id
                WHERE rt.id = ?
                """, (rs, rowNum) -> mapDetail(rs), taskId);
        return results.stream().findFirst();
    }

    public Optional<ReviewTaskResultResponse> findResultByTaskId(Long taskId) {
        List<ReviewTaskResultResponse> results = jdbcTemplate.query("""
                SELECT task_id, risk_level, risk_item_count, summary,
                       change_analysis_json, risk_card_json
                FROM review_results
                WHERE task_id = ?
                """, (rs, rowNum) -> new ReviewTaskResultResponse(
                rs.getLong("task_id"),
                rs.getString("risk_level"),
                rs.getInt("risk_item_count"),
                rs.getString("summary"),
                readJson(rs.getString("change_analysis_json")),
                readJson(rs.getString("risk_card_json"))
        ), taskId);
        return results.stream().findFirst();
    }

    private void appendFilters(StringBuilder where, List<Object> args, Long projectId, String status, String riskLevel, String keyword) {
        if (projectId != null) {
            where.append(" AND rt.project_id = ? ");
            args.add(projectId);
        }
        if (StringUtils.hasText(status)) {
            where.append(" AND rt.status = ? ");
            args.add(status);
        }
        if (StringUtils.hasText(riskLevel)) {
            where.append(" AND rt.risk_level = ? ");
            args.add(riskLevel);
        }
        if (StringUtils.hasText(keyword)) {
            where.append(" AND (p.name LIKE ? OR rt.source_branch LIKE ? OR rt.target_branch LIKE ? OR rt.external_source_id LIKE ?) ");
            String like = "%" + keyword + "%";
            args.add(like);
            args.add(like);
            args.add(like);
            args.add(like);
        }
    }

    private ReviewTaskListItemResponse mapListItem(ResultSet rs) throws SQLException {
        return new ReviewTaskListItemResponse(
                rs.getLong("id"),
                rs.getLong("project_id"),
                rs.getString("project_name"),
                rs.getString("trigger_type"),
                rs.getString("external_source_id"),
                rs.getString("external_url"),
                rs.getString("source_branch"),
                rs.getString("target_branch"),
                rs.getString("author_name"),
                rs.getString("template_code"),
                rs.getString("status"),
                rs.getString("risk_level"),
                nullableInt(rs, "risk_item_count"),
                formatTimestamp(rs.getTimestamp("created_at")),
                formatTimestamp(rs.getTimestamp("finished_at"))
        );
    }

    private ReviewTaskDetailResponse mapDetail(ResultSet rs) throws SQLException {
        String mrId = rs.getString("mr_id");
        if (mrId == null) {
            mrId = rs.getString("external_source_id");
        }
        return new ReviewTaskDetailResponse(
                rs.getLong("id"),
                rs.getLong("project_id"),
                rs.getString("project_name"),
                rs.getString("git_project_id"),
                rs.getString("trigger_type"),
                mrId,
                rs.getString("external_url"),
                rs.getString("source_branch"),
                rs.getString("target_branch"),
                rs.getString("commit_sha"),
                rs.getString("author_name"),
                rs.getString("author_username"),
                rs.getString("template_code"),
                rs.getString("status"),
                rs.getString("risk_level"),
                rs.getString("event_action"),
                formatTimestamp(rs.getTimestamp("event_time")),
                readJson(rs.getString("changed_files_summary")),
                readJson(rs.getString("raw_payload")),
                formatTimestamp(rs.getTimestamp("created_at")),
                formatTimestamp(rs.getTimestamp("updated_at"))
        );
    }

    private Integer nullableInt(ResultSet rs, String column) throws SQLException {
        int value = rs.getInt(column);
        return rs.wasNull() ? null : value;
    }

    private JsonNode readJson(String value) {
        if (value == null || value.isBlank()) {
            return objectMapper.nullNode();
        }
        try {
            return objectMapper.readTree(value);
        } catch (Exception exception) {
            return objectMapper.createObjectNode().put("raw", value);
        }
    }

    private String formatTimestamp(Timestamp timestamp) {
        if (timestamp == null) {
            return null;
        }
        return timestamp.toLocalDateTime().format(DATE_TIME_FORMATTER);
    }
}