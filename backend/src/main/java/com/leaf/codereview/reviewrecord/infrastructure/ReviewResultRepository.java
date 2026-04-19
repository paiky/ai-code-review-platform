package com.leaf.codereview.reviewrecord.infrastructure;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.changeanalysis.domain.ChangeAnalysisResult;
import com.leaf.codereview.riskengine.domain.RiskCard;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.Objects;

@Repository
public class ReviewResultRepository {

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public ReviewResultRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public Long save(Long taskId, Long projectId, String templateCode, ChangeAnalysisResult analysisResult, RiskCard riskCard) {
        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement("""
                    INSERT INTO review_results (
                      task_id, project_id, template_code, risk_level,
                      risk_item_count, change_analysis_json, risk_card_json, summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, Statement.RETURN_GENERATED_KEYS);
            ps.setLong(1, taskId);
            ps.setLong(2, projectId);
            ps.setString(3, templateCode);
            ps.setString(4, riskCard.riskLevel().name());
            ps.setInt(5, riskCard.riskItems().size());
            ps.setString(6, writeJson(analysisResult));
            ps.setString(7, writeJson(riskCard));
            ps.setString(8, riskCard.summary());
            return ps;
        }, keyHolder);
        return Objects.requireNonNull(keyHolder.getKey()).longValue();
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("Failed to serialize review result", exception);
        }
    }
}