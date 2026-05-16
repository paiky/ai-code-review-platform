package com.leaf.codereview.codequality;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewResultRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import javax.sql.DataSource;
import java.time.OffsetDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class CodeQualityReviewResultRepositoryTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource());
    private final CodeQualityReviewResultRepository repository = new CodeQualityReviewResultRepository(
            jdbcTemplate,
            objectMapper
    );

    @BeforeEach
    void setUp() {
        jdbcTemplate.execute("DROP TABLE IF EXISTS code_quality_review_results");
        jdbcTemplate.execute("""
                CREATE TABLE code_quality_review_results (
                  id BIGINT AUTO_INCREMENT PRIMARY KEY,
                  task_id BIGINT NOT NULL UNIQUE,
                  project_id BIGINT NOT NULL,
                  profile_code VARCHAR(64) NOT NULL,
                  provider VARCHAR(32) NOT NULL,
                  model VARCHAR(128),
                  status VARCHAR(32) NOT NULL,
                  overall_level VARCHAR(32),
                  summary VARCHAR(1024),
                  finding_count INT NOT NULL DEFAULT 0,
                  findings_json CLOB NOT NULL,
                  raw_output CLOB,
                  exit_code INT,
                  error_message VARCHAR(1024),
                  started_at TIMESTAMP,
                  finished_at TIMESTAMP
                )
                """);
    }

    @Test
    void leavesLegacyRawOutputUnparsedWhenFindingsJsonIsEmpty() {
        jdbcTemplate.update("""
                INSERT INTO code_quality_review_results (
                  task_id, project_id, profile_code, provider, status, finding_count,
                  findings_json, raw_output, exit_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                28L,
                4L,
                "backend-default-ai-review",
                "DEEPSEEK",
                "SUCCESS",
                0,
                "[]",
                """
                        **Findings**

                        - High: [AuthFilter.java](D:/projects/app/src/AuthFilter.java:154) bypasses authentication via substring matching.
                        """,
                0
        );

        var response = repository.findByTaskId(28L).orElseThrow();

        assertThat(response.findingCount()).isZero();
        assertThat(response.overallLevel()).isNull();
        assertThat(response.summary()).isNull();
        assertThat(response.findings()).isEmpty();
        assertThat(response.rawOutput()).contains("AuthFilter.java");
    }

    @Test
    void truncatesOversizedSummaryBeforeSaving() {
        String longSummary = "x".repeat(1500);
        CodeQualityReviewResult result = CodeQualityReviewResult.success(
                CodeQualityReviewProviderType.DEEPSEEK,
                "LOW",
                longSummary,
                List.of(),
                "raw",
                0,
                OffsetDateTime.now(),
                OffsetDateTime.now()
        );

        repository.save(29L, 4L, "backend-default-ai-review", "gpt-5.4", result);

        String savedSummary = jdbcTemplate.queryForObject(
                "SELECT summary FROM code_quality_review_results WHERE task_id = ?",
                String.class,
                29L
        );
        assertThat(savedSummary).hasSize(1024);
    }

    private DataSource dataSource() {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:code_quality_result_repository;MODE=MySQL;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");
        return dataSource;
    }
}

