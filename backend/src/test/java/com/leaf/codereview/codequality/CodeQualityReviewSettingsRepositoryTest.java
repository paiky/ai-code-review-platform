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
                  dingtalk_notification_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                  default_provider_code VARCHAR(64) NOT NULL DEFAULT 'DEEPSEEK',
                  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """);
    }

    @Test
    void savesGlobalSwitchesAndDefaultProvider() {
        var saved = repository.update(new CodeQualityReviewSettingsUpdateRequest(
                false,
                false,
                "ANTHROPIC"
        ));

        assertThat(saved.mrAutoReviewEnabled()).isFalse();
        assertThat(saved.dingtalkNotificationEnabled()).isFalse();
        assertThat(repository.dingtalkNotificationEnabled()).isFalse();
        assertThat(saved.defaultProviderCode()).isEqualTo("ANTHROPIC");
        assertThat(repository.reviewProvider()).isEqualTo(CodeQualityReviewProviderType.ANTHROPIC);

        var changed = repository.updateDefaultProvider(CodeQualityReviewProviderType.DEEPSEEK);

        assertThat(changed.defaultProviderCode()).isEqualTo("DEEPSEEK");
        assertThat(repository.reviewProvider()).isEqualTo(CodeQualityReviewProviderType.DEEPSEEK);
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
