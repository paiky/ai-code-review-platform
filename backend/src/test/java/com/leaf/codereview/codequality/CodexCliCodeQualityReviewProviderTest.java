package com.leaf.codereview.codequality;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.codequality.domain.CodeQualityReviewMode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressEventRepository;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressTracker;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.CodexCliCodeQualityReviewProvider;
import com.leaf.codereview.codequality.infrastructure.CodexCliCommandFactory;
import com.leaf.codereview.codequality.infrastructure.CodexCliOutputParser;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class CodexCliCodeQualityReviewProviderTest {

    private final CodexCliCommandFactory commandFactory = mock(CodexCliCommandFactory.class);
    private final CodeQualityReviewProgressEventRepository progressEventRepository = mock(CodeQualityReviewProgressEventRepository.class);
    private final CodeQualityReviewProgressTracker progressTracker = new CodeQualityReviewProgressTracker(progressEventRepository);
    private final CodexCliOutputParser outputParser = new CodexCliOutputParser(new ObjectMapper());

    @TempDir
    Path tempDir;

    @Test
    void rejectsCodexExecutionWhenDiffTextIsMissing() {
        CodexCliCodeQualityReviewProvider provider = newProvider(properties());

        CodeQualityReviewResult result = provider.review(request(null));

        assertThat(result.status()).isEqualTo("FAILED");
        assertThat(result.errorMessage()).contains("diffText is required");
        verify(commandFactory, never()).buildCommand(
                any(CodeQualityReviewProperties.class),
                any(CodeQualityReviewRequest.class),
                any(Path.class),
                any(Path.class)
        );
    }

    @Test
    void runsConfiguredCommandWithoutRepositoryPath() {
        CodexCliCodeQualityReviewProvider provider = newProvider(properties());
        when(commandFactory.renderPrompt(any())).thenReturn("prompt");
        when(commandFactory.buildCommand(
                any(CodeQualityReviewProperties.class),
                any(CodeQualityReviewRequest.class),
                any(Path.class),
                any(Path.class)
        )).thenReturn(List.of(javaExecutable(), "-version"));

        CodeQualityReviewResult result = provider.review(request("+ code"));

        assertThat(result.status()).isEqualTo("SUCCESS");
    }

    private CodexCliCodeQualityReviewProvider newProvider(CodeQualityReviewProperties properties) {
        return new CodexCliCodeQualityReviewProvider(
                properties,
                commandFactory,
                outputParser,
                progressTracker
        );
    }

    private CodeQualityReviewRequest request(String diffText) {
        return new CodeQualityReviewRequest(
                null,
                CodeQualityReviewMode.DIFF_TEXT,
                "origin/main",
                null,
                "MR title",
                null,
                "Review instructions",
                diffText,
                List.of("src/main/java/Foo.java")
        );
    }

    private CodeQualityReviewProperties properties() {
        return new CodeQualityReviewProperties(
                true,
                CodeQualityReviewProviderType.CODEX_CLI,
                tempDir.getParent().toString(),
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
    }

    private String javaExecutable() {
        String javaHome = System.getProperty("java.home");
        String executable = System.getProperty("os.name", "").toLowerCase().contains("win") ? "java.exe" : "java";
        return Path.of(javaHome, "bin", executable).toString();
    }
}
