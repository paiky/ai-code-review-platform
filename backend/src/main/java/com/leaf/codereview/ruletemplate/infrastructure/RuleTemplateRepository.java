package com.leaf.codereview.ruletemplate.infrastructure;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.ruletemplate.domain.ReviewTemplateDefinition;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

@Repository
public class RuleTemplateRepository {

    private final JdbcTemplate jdbcTemplate;
    private final ObjectMapper objectMapper;

    public RuleTemplateRepository(JdbcTemplate jdbcTemplate, ObjectMapper objectMapper) {
        this.jdbcTemplate = jdbcTemplate;
        this.objectMapper = objectMapper;
    }

    public List<ReviewTemplateDefinition> findEnabledTemplates() {
        return jdbcTemplate.query("""
                SELECT id, template_code, template_name, target_type, version,
                       enabled_rule_codes, config_json, status, description
                FROM rule_templates
                WHERE status = 'ENABLED'
                ORDER BY template_code, version DESC
                """, (rs, rowNum) -> map(rs));
    }

    public Optional<ReviewTemplateDefinition> findLatestEnabledByCode(String templateCode) {
        List<ReviewTemplateDefinition> templates = jdbcTemplate.query("""
                SELECT id, template_code, template_name, target_type, version,
                       enabled_rule_codes, config_json, status, description
                FROM rule_templates
                WHERE status = 'ENABLED' AND template_code = ?
                ORDER BY version DESC
                LIMIT 1
                """, (rs, rowNum) -> map(rs), templateCode);
        return templates.stream().findFirst();
    }

    private ReviewTemplateDefinition map(ResultSet rs) throws SQLException {
        JsonNode config = readJson(rs.getString("config_json"));
        return new ReviewTemplateDefinition(
                rs.getLong("id"),
                rs.getString("template_code"),
                rs.getString("template_name"),
                rs.getString("target_type"),
                rs.getInt("version"),
                readStringArray(rs.getString("enabled_rule_codes")),
                readRecommendedChecks(config),
                config,
                rs.getString("status"),
                rs.getString("description")
        );
    }

    private JsonNode readJson(String json) {
        if (json == null || json.isBlank()) {
            return objectMapper.createObjectNode();
        }
        try {
            return objectMapper.readTree(json);
        } catch (Exception exception) {
            return objectMapper.createObjectNode();
        }
    }

    private List<String> readStringArray(String json) {
        JsonNode node = readJson(json);
        List<String> values = new ArrayList<>();
        if (node.isArray()) {
            node.forEach(item -> values.add(item.asText()));
        }
        return values;
    }

    private List<String> readRecommendedChecks(JsonNode config) {
        List<String> checks = new ArrayList<>();
        JsonNode node = config.path("recommendedChecks");
        if (node.isArray()) {
            node.forEach(item -> checks.add(item.asText()));
        }
        return checks;
    }
}