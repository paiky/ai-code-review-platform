package com.leaf.codereview.codequality;

import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CodeQualityReviewPropertiesTest {

    @Test
    void treatsBlankProviderAsCodexCliDefault() {
        CodeQualityReviewProperties properties = new CodeQualityReviewProperties(
                true,
                " ",
                "",
                "",
                "",
                600,
                "",
                "https://api.openai.com/v1/responses",
                "gpt-5.4",
                120,
                "",
                "https://api.anthropic.com/v1/messages",
                "claude-sonnet-4-5",
                120
        );

        assertThat(properties.provider()).isEqualTo(CodeQualityReviewProviderType.DEEPSEEK);
    }

}
