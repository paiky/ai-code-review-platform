package com.leaf.codereview.codequality;

import com.leaf.codereview.codequality.controller.CodeQualityReviewSettingsUpdateRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewSettingsRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import javax.sql.DataSource;

import static org.assertj.core.api.Assertions.assertThat;

class CodeQualityReviewSettingsRepositoryTest {

    private final JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource());
    private final CodeQualityReviewSettingsRepository repository = new CodeQualityReviewSettingsRepository(jdbcTemplate);

    @BeforeEach
    void setUp() {
        jdbcTemplate.execute("DROP TABLE IF EXISTS code_quality_review_settings");
        jdbcTemplate.execute("""
                CREATE TABLE code_quality_review_settings (
                  id BIGINT PRIMARY KEY,
                  mr_auto_review_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                  review_provider VARCHAR(32) NOT NULL DEFAULT 'CODEX_CLI',
                  openai_api_key VARCHAR(1024),
                  anthropic_api_key VARCHAR(1024),
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """);
    }

    @Test
    void savesMasksAndClearsApiKeys() {
        var saved = repository.update(new CodeQualityReviewSettingsUpdateRequest(
                false,
                CodeQualityReviewProviderType.ANTHROPIC_API,
                "sk-openai-123456",
                null,
                "sk-ant-abcdef",
                null
        ));

        assertThat(saved.mrAutoReviewEnabled()).isFalse();
        assertThat(saved.reviewProvider()).isEqualTo("ANTHROPIC_API");
        assertThat(saved.openAiApiKeyConfigured()).isTrue();
        assertThat(saved.openAiApiKeyMasked()).isEqualTo("sk-o...3456");
        assertThat(saved.anthropicApiKeyConfigured()).isTrue();
        assertThat(saved.anthropicApiKeyMasked()).isEqualTo("sk-a...cdef");
        assertThat(repository.openAiApiKey()).isEqualTo("sk-openai-123456");
        assertThat(repository.anthropicApiKey()).isEqualTo("sk-ant-abcdef");

        var cleared = repository.update(new CodeQualityReviewSettingsUpdateRequest(
                null,
                null,
                null,
                true,
                null,
                true
        ));

        assertThat(cleared.openAiApiKeyConfigured()).isFalse();
        assertThat(cleared.openAiApiKeyMasked()).isNull();
        assertThat(cleared.anthropicApiKeyConfigured()).isFalse();
        assertThat(cleared.anthropicApiKeyMasked()).isNull();
        assertThat(repository.openAiApiKey()).isNull();
        assertThat(repository.anthropicApiKey()).isNull();
    }

    private DataSource dataSource() {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:code_quality_settings_repository;MODE=MySQL;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");
        return dataSource;
    }
}
