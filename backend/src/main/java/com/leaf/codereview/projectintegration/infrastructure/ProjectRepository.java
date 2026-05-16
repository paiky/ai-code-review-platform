package com.leaf.codereview.projectintegration.infrastructure;

import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;
import org.springframework.stereotype.Repository;

import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

@Repository
public class ProjectRepository {

    private static final String GIT_PROVIDER = "GITLAB";
    private static final String DEFAULT_TEMPLATE_CODE = "backend-default";
    private static final String DEFAULT_CODE_QUALITY_PROFILE_CODE = "backend-default-ai-review";

    private final JdbcTemplate jdbcTemplate;

    public ProjectRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public ProjectRecord upsertGitLabProject(String gitProjectId, String projectName, String repositoryUrl) {
        Optional<ProjectRecord> existing = findByGitProjectId(gitProjectId);
        if (existing.isPresent()) {
            ProjectRecord project = existing.get();
            jdbcTemplate.update("""
                    UPDATE projects
                    SET name = ?, repository_url = ?, status = 'ENABLED'
                    WHERE id = ?
                    """, projectName, repositoryUrl, project.id());
            return findById(project.id()).orElseThrow();
        }

        KeyHolder keyHolder = new GeneratedKeyHolder();
        jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement("""
                    INSERT INTO projects (
                      name, git_provider, git_project_id, repository_url,
                      default_template_code, default_code_quality_profile_code, default_code_quality_provider_code, status, description
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'ENABLED', ?)
                    """, Statement.RETURN_GENERATED_KEYS);
            ps.setString(1, projectName);
            ps.setString(2, GIT_PROVIDER);
            ps.setString(3, gitProjectId);
            ps.setString(4, repositoryUrl);
            ps.setString(5, DEFAULT_TEMPLATE_CODE);
            ps.setString(6, DEFAULT_CODE_QUALITY_PROFILE_CODE);
            ps.setString(7, "Auto-created from GitLab MR webhook");
            return ps;
        }, keyHolder);

        Long id = Objects.requireNonNull(keyHolder.getKey()).longValue();
        return findById(id).orElseThrow();
    }

    public Optional<ProjectRecord> findById(Long id) {
        List<ProjectRecord> projects = jdbcTemplate.query("""
                SELECT id, name, git_provider, git_project_id, repository_url,
                       default_template_code, default_code_quality_profile_code, default_code_quality_provider_code, status
                FROM projects
                WHERE id = ?
                """, rowMapper(), id);
        return projects.stream().findFirst();
    }

    public Optional<ProjectRecord> findByGitProjectId(String gitProjectId) {
        List<ProjectRecord> projects = jdbcTemplate.query("""
                SELECT id, name, git_provider, git_project_id, repository_url,
                       default_template_code, default_code_quality_profile_code, default_code_quality_provider_code, status
                FROM projects
                WHERE git_provider = ? AND git_project_id = ?
                """, rowMapper(), GIT_PROVIDER, gitProjectId);
        return projects.stream().findFirst();
    }


    public List<ProjectRecord> findAllEnabled() {
        return jdbcTemplate.query("""
                SELECT id, name, git_provider, git_project_id, repository_url,
                       default_template_code, default_code_quality_profile_code, default_code_quality_provider_code, status
                FROM projects
                WHERE status = 'ENABLED'
                ORDER BY id DESC
                """, rowMapper());
    }

    public void updateDefaultTemplate(Long projectId, String templateCode) {
        jdbcTemplate.update("""
                UPDATE projects
                SET default_template_code = ?
                WHERE id = ?
                """, templateCode, projectId);
    }

    public void updateDefaultCodeQualityProfile(Long projectId, String profileCode) {
        jdbcTemplate.update("""
                UPDATE projects
                SET default_code_quality_profile_code = ?
                WHERE id = ?
                """, profileCode, projectId);
    }

    public void updateDefaultCodeQualityProvider(Long projectId, String providerCode) {
        jdbcTemplate.update("""
                UPDATE projects
                SET default_code_quality_provider_code = ?
                WHERE id = ?
                """, providerCode, projectId);
    }

    private RowMapper<ProjectRecord> rowMapper() {
        return (rs, rowNum) -> new ProjectRecord(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getString("git_provider"),
                rs.getString("git_project_id"),
                rs.getString("repository_url"),
                rs.getString("default_template_code"),
                rs.getString("default_code_quality_profile_code"),
                rs.getString("default_code_quality_provider_code"),
                rs.getString("status")
        );
    }
}
