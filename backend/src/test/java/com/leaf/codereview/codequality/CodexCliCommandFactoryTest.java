package com.leaf.codereview.codequality;

import com.leaf.codereview.codequality.domain.CodeQualityReviewMode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.CodexCliCommandFactory;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class CodexCliCommandFactoryTest {

    private final CodexCliCommandFactory factory = new CodexCliCommandFactory();

    @Test
    void buildsWindowsCommandWithPromptFileWhenInstructionsAreConfigured() {
        CodeQualityReviewRequest request = new CodeQualityReviewRequest(
                "D:/repo",
                CodeQualityReviewMode.BASE,
                "origin/main",
                null,
                "MR title",
                null,
                "Focus on regressions",
                null,
                List.of()
        );

        List<String> command = factory.buildCommand(properties("", "gpt-5.5"), request, Path.of("review.md"), Path.of("prompt.md"), "Windows 11");

        assertThat(command).startsWith("cmd.exe", "/d", "/s", "/c", "codex.cmd");
        assertThat(command).containsSequence("--sandbox", "read-only", "-a", "never", "exec");
        assertThat(command).contains("--json", "--ephemeral", "-o");
        assertThat(command).containsSequence("-m", "gpt-5.5");
        assertThat(command).doesNotContain("review", "--base", "origin/main");
        assertThat(command.get(command.size() - 1))
                .contains("Please read the UTF-8 review instructions from", "prompt.md")
                .doesNotContain("Focus on regressions");
    }

    @Test
    void rendersChineseFirstPromptWithReviewScope() {
        CodeQualityReviewRequest request = new CodeQualityReviewRequest(
                "D:/repo",
                CodeQualityReviewMode.BASE,
                "origin/main",
                null,
                "MR title",
                null,
                "Focus on regressions",
                null,
                List.of()
        );

        String prompt = factory.renderPrompt(request);

        assertThat(prompt)
                .contains("你是代码质量审核助手", "审查范围", "origin/main", "MR title", "Focus on regressions")
                .contains("必须使用简体中文")
                .doesNotContain("Run a code quality review");
    }

    @Test
    void buildsLinuxCommandWithCodexDefaultAndCommitScope() {
        CodeQualityReviewRequest request = new CodeQualityReviewRequest(
                "/repo",
                CodeQualityReviewMode.COMMIT,
                null,
                "abc123",
                null,
                null,
                null,
                null,
                List.of()
        );

        List<String> command = factory.buildCommand(properties("", ""), request, Path.of("review.md"), "Linux");

        assertThat(command).startsWith("codex");
        assertThat(command).doesNotContain("cmd.exe", "/c");
        assertThat(command).contains("review");
        assertThat(command).containsSequence("--commit", "abc123");
    }

    @Test
    void usesConfiguredCommandWhenProvided() {
        CodeQualityReviewRequest request = new CodeQualityReviewRequest(
                "/repo",
                CodeQualityReviewMode.UNCOMMITTED,
                null,
                null,
                null,
                null,
                null,
                null,
                List.of()
        );

        List<String> command = factory.buildCommand(properties("/opt/bin/codex", ""), request, Path.of("review.md"), "Linux");

        assertThat(command).startsWith("/opt/bin/codex");
        assertThat(command).contains("--uncommitted");
    }

    private CodeQualityReviewProperties properties(String codexCommand, String model) {
        return new CodeQualityReviewProperties(
                true,
                CodeQualityReviewProviderType.CODEX_CLI,
                "",
                codexCommand,
                model,
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
}


