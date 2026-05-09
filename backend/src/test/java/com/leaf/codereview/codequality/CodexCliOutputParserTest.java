package com.leaf.codereview.codequality;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.codequality.infrastructure.CodexCliOutputParser;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CodexCliOutputParserTest {

    private final CodexCliOutputParser parser = new CodexCliOutputParser(new ObjectMapper());

    @Test
    void extractsStructuredCodexErrorBeforeStderrWarning() {
        String rawOutput = """
                {"type":"thread.started","thread_id":"thread-1"}
                {"type":"error","message":"{\\"detail\\":\\"The 'gpt-5.5' model requires a newer version of Codex.\\"}"}
                {"type":"turn.failed","error":{"message":"{\\"detail\\":\\"The 'gpt-5.5' model requires a newer version of Codex.\\"}"}}
                """;

        String message = parser.failureMessage(
                rawOutput,
                "Warning: no last agent message; wrote empty content to temp.md"
        );

        assertThat(message).isEqualTo("The 'gpt-5.5' model requires a newer version of Codex.");
    }

    @Test
    void fallsBackToStderrWhenJsonOutputHasNoError() {
        String message = parser.failureMessage("{\"type\":\"thread.started\"}", "Codex failed");

        assertThat(message).isEqualTo("Codex failed");
    }

    @Test
    void parsesCodexMarkdownFindings() {
        String rawOutput = """
                **Findings**

                - High: [AuthFilter.java](D:/projects/app/src/AuthFilter.java:154) bypasses authentication via substring matching. This can expose endpoints.

                - Medium: [ThreadPoolConfig.java](D:/projects/app/src/ThreadPoolConfig.java:233) silently drops saturated tasks.

                **Residual Risks**
                - I did not run tests.
                """;

        var findings = parser.findings(rawOutput);

        assertThat(findings).hasSize(2);
        assertThat(parser.overallLevel(findings)).isEqualTo("HIGH");
        assertThat(parser.summary(rawOutput, findings)).isEqualTo("发现 2 个 Codex 代码质量问题");
        assertThat(findings.get(0).severity()).isEqualTo("HIGH");
        assertThat(findings.get(0).filePath()).isEqualTo("D:/projects/app/src/AuthFilter.java");
        assertThat(findings.get(0).startLine()).isEqualTo(154);
        assertThat(findings.get(0).category()).isEqualTo("CODE_QUALITY");
        assertThat(findings.get(1).body()).doesNotContain("I did not run tests");
        assertThat(findings.get(1).severity()).isEqualTo("MEDIUM");
    }

    @Test
    void parsesNumberedCodexFindingsWithAngleBracketLinks() {
        String rawOutput = """
                **Findings**

                1. High: `ActivityRewardJob` acquires one Redis lock key and releases a different one. See [ActivityRewardJob.java](<D:/projects/app/src/ActivityRewardJob.java:43>) and [ActivityRewardJob.java](<D:/projects/app/src/ActivityRewardJob.java:58>).

                2. Medium: `SystemMessageJob` obtains a lock and never releases it. See [SystemMessageJob.java](<D:/projects/app/src/SystemMessageJob.java:32>).

                **Residual Risks**

                I did not run compile/tests.
                """;

        var findings = parser.findings(rawOutput);

        assertThat(findings).hasSize(2);
        assertThat(findings.get(0).severity()).isEqualTo("HIGH");
        assertThat(findings.get(0).filePath()).isEqualTo("D:/projects/app/src/ActivityRewardJob.java");
        assertThat(findings.get(0).startLine()).isEqualTo(43);
        assertThat(findings.get(1).severity()).isEqualTo("MEDIUM");
        assertThat(findings.get(1).filePath()).isEqualTo("D:/projects/app/src/SystemMessageJob.java");
        assertThat(findings.get(1).body()).doesNotContain("I did not run compile");
    }

    @Test
    void parsesChineseSeverityPrefixes() {
        String rawOutput = """
                **问题**

                高风险：`ActivityRewardJob` 释放了错误的 Redis 锁。见 [ActivityRewardJob.java](<D:/projects/app/src/ActivityRewardJob.java:43>)。

                中风险：迁移接口提前返回成功，调用方无法感知失败。见 [MigrationController.java](<D:/projects/app/src/MigrationController.java:17>)。
                """;

        var findings = parser.findings(rawOutput);

        assertThat(findings).hasSize(2);
        assertThat(findings.get(0).severity()).isEqualTo("HIGH");
        assertThat(findings.get(0).title()).contains("释放了错误的 Redis 锁");
        assertThat(findings.get(1).severity()).isEqualTo("MEDIUM");
    }
}

