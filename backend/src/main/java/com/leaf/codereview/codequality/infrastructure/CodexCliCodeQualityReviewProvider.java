package com.leaf.codereview.codequality.infrastructure;

import com.leaf.codereview.codequality.application.CodeQualityReviewProvider;
import com.leaf.codereview.codequality.domain.CodeQualityFinding;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.OffsetDateTime;
import java.util.Comparator;
import java.util.HexFormat;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

@Component
public class CodexCliCodeQualityReviewProvider implements CodeQualityReviewProvider {

    private final CodeQualityReviewProperties properties;
    private final CodexCliCommandFactory commandFactory;
    private final CodexCliOutputParser outputParser;
    private final CodeQualityReviewProgressTracker progressTracker;

    public CodexCliCodeQualityReviewProvider(
            CodeQualityReviewProperties properties,
            CodexCliCommandFactory commandFactory,
            CodexCliOutputParser outputParser,
            CodeQualityReviewProgressTracker progressTracker
    ) {
        this.properties = properties;
        this.commandFactory = commandFactory;
        this.outputParser = outputParser;
        this.progressTracker = progressTracker;
    }

    @Override
    public CodeQualityReviewProviderType type() {
        return CodeQualityReviewProviderType.CODEX_CLI;
    }

    @Override
    public CodeQualityReviewResult review(CodeQualityReviewRequest request) {
        OffsetDateTime startedAt = OffsetDateTime.now();
        if (!StringUtils.hasText(request.diffText())) {
            String errorMessage = "diffText is required for Codex CLI code quality review; Codex CLI no longer reads local repository diffs";
            progressTracker.error("CODEX_DIFF_TEXT_REQUIRED", "Codex CLI 缺少平台 diff，已拒绝执行", errorMessage);
            return CodeQualityReviewResult.failed(type(), errorMessage, null, null, startedAt, OffsetDateTime.now());
        }
        Path executionDirectory = createExecutionDirectory();
        Path outputFile = createOutputFile();
        Path promptFile = createPromptFile(request);
        progressTracker.info("CODEX_WORKDIR", "Codex CLI 临时工作目录已创建", executionDirectory.toAbsolutePath().toString());
        progressTracker.info("CODEX_OUTPUT_FILE", "Codex CLI 输出文件已创建", outputFile.toAbsolutePath().toString());
        recordPromptMetadata(request, executionDirectory, promptFile);
        List<String> command = commandFactory.buildCommand(properties, request, outputFile, promptFile);
        progressTracker.info("CODEX_COMMAND", "即将启动 Codex CLI 子进程", "commandPreview=" + formatCommand(command));

        try {
            ProcessBuilder processBuilder = new ProcessBuilder(command)
                    .directory(executionDirectory.toFile())
                    .redirectErrorStream(false);
            configureUtf8Environment(processBuilder);
            Process process = processBuilder.start();
            progressTracker.info("CODEX_PROCESS_STARTED", "Codex CLI 子进程已启动", "pid=" + process.pid());
            CompletableFuture<String> stdout = readAsync(process.getInputStream(), "stdout");
            CompletableFuture<String> stderr = readAsync(process.getErrorStream(), "stderr");
            boolean finished = process.waitFor(properties.codexTimeoutSeconds(), TimeUnit.SECONDS);
            OffsetDateTime finishedAt = OffsetDateTime.now();
            if (!finished) {
                process.destroyForcibly();
                progressTracker.warn("CODEX_TIMEOUT", "Codex CLI 执行超时，已强制终止", "timeoutSeconds=" + properties.codexTimeoutSeconds());
                return CodeQualityReviewResult.failed(type(), "Codex CLI review timed out", readOutput(outputFile), null, startedAt, finishedAt);
            }
            int exitCode = process.exitValue();
            String rawOutput = firstText(readOutput(outputFile), stdout.join());
            String errorOutput = stderr.join();
            progressTracker.info("CODEX_PROCESS_EXIT", "Codex CLI 子进程已退出", "exitCode=" + exitCode);
            if (exitCode != 0) {
                progressTracker.error("CODEX_FAILED", "Codex CLI 返回非 0 退出码", outputParser.failureMessage(rawOutput, errorOutput));
                return CodeQualityReviewResult.failed(type(), outputParser.failureMessage(rawOutput, errorOutput), rawOutput, exitCode, startedAt, finishedAt);
            }
            List<CodeQualityFinding> findings = outputParser.findings(rawOutput);
            progressTracker.info("CODEX_PARSED", "Codex CLI 输出已解析", "findingCount=" + findings.size() + ", overallLevel=" + outputParser.overallLevel(findings));
            return CodeQualityReviewResult.success(
                    type(),
                    outputParser.overallLevel(findings),
                    outputParser.summary(rawOutput, findings),
                    findings,
                    rawOutput,
                    exitCode,
                    startedAt,
                    finishedAt
            );
        } catch (IOException exception) {
            progressTracker.error("CODEX_IO_ERROR", "Codex CLI 启动或读取失败", exception.getMessage());
            return CodeQualityReviewResult.failed(type(), exception.getMessage(), null, null, startedAt, OffsetDateTime.now());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            progressTracker.error("CODEX_INTERRUPTED", "Codex CLI 执行被中断", exception.getMessage());
            return CodeQualityReviewResult.failed(type(), "Codex CLI review interrupted", null, null, startedAt, OffsetDateTime.now());
        } finally {
            deleteQuietly(outputFile);
            deleteQuietly(promptFile);
            deleteRecursivelyQuietly(executionDirectory);
        }
    }

    private Path createExecutionDirectory() {
        try {
            return Files.createTempDirectory("codex-review-work-");
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.INTERNAL_ERROR, "Failed to create Codex execution directory");
        }
    }

    private Path createOutputFile() {
        try {
            return Files.createTempFile("codex-review-", ".md");
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.INTERNAL_ERROR, "Failed to create Codex output file");
        }
    }

    private Path createPromptFile(CodeQualityReviewRequest request) {
        try {
            Path promptFile = Files.createTempFile("codex-review-prompt-", ".md");
            Files.writeString(promptFile, commandFactory.renderPrompt(request), StandardCharsets.UTF_8);
            return promptFile;
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.INTERNAL_ERROR, "Failed to create Codex prompt file");
        }
    }

    private void recordPromptMetadata(CodeQualityReviewRequest request, Path executionDirectory, Path promptFile) {
        String renderedPrompt = commandFactory.renderPrompt(request);
        String detail = "provider=CODEX_CLI"
                + ", model=" + firstText(request.model(), properties.codexModel())
                + ", executionDirectory=" + executionDirectory
                + ", runtimeMode=" + runtimeMode()
                + ", promptFile=" + (promptFile == null ? "-" : promptFile.toAbsolutePath())
                + ", promptHash=" + sha256(renderedPrompt)
                + ", promptLength=" + renderedPrompt.length()
                + ", promptPreview=" + abbreviate(renderedPrompt.replaceAll("\\s+", " ").trim(), 200);
        progressTracker.info("PROMPT_METADATA", "Agent Prompt 元数据已记录", detail);
    }

    private void configureUtf8Environment(ProcessBuilder processBuilder) {
        processBuilder.environment().put("PYTHONUTF8", "1");
        processBuilder.environment().put("PYTHONIOENCODING", "utf-8");
        processBuilder.environment().put("JAVA_TOOL_OPTIONS", "-Dfile.encoding=UTF-8");
        processBuilder.environment().put("LANG", "C.UTF-8");
        processBuilder.environment().put("LC_ALL", "C.UTF-8");
    }

    private CompletableFuture<String> readAsync(InputStream inputStream, String streamName) {
        Long taskId = progressTracker.currentTaskId();
        return CompletableFuture.supplyAsync(() -> {
            StringBuilder output = new StringBuilder();
            progressTracker.runWithTask(taskId, () -> {
                try (
                        inputStream;
                        BufferedReader reader = new BufferedReader(new InputStreamReader(inputStream, StandardCharsets.UTF_8))
                ) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        output.append(line).append('\n');
                        if (StringUtils.hasText(line)) {
                            progressTracker.debug("CODEX_OUTPUT", streamName + ": " + abbreviate(line, 240), line);
                        }
                    }
                } catch (IOException exception) {
                    output.append(exception.getMessage());
                }
            });
            return output.toString();
        });
    }

    private String readOutput(Path outputFile) {
        try {
            if (Files.exists(outputFile)) {
                return Files.readString(outputFile, StandardCharsets.UTF_8);
            }
        } catch (IOException ignored) {
            return null;
        }
        return null;
    }

    private String firstText(String primary, String fallback) {
        return StringUtils.hasText(primary) ? primary : fallback;
    }

    private String sha256(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest((value == null ? "" : value).getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is not available", exception);
        }
    }

    private String runtimeMode() {
        String osName = System.getProperty("os.name", "").toLowerCase();
        if (osName.contains("win")) {
            return "WINDOWS_NATIVE";
        }
        if (osName.contains("linux")) {
            return "LINUX_NATIVE";
        }
        return "NATIVE";
    }

    private String formatCommand(List<String> command) {
        return String.join(" ", command.stream().map(this::quoteIfNeeded).toList());
    }

    private String quoteIfNeeded(String value) {
        if (value == null) {
            return "";
        }
        return value.contains(" ") ? "\"" + value.replace("\"", "\\\"") + "\"" : value;
    }

    private String abbreviate(String value, int maxLength) {
        if (value == null || value.length() <= maxLength) {
            return value;
        }
        return value.substring(0, maxLength - 3) + "...";
    }

    private void deleteQuietly(Path outputFile) {
        if (outputFile == null) {
            return;
        }
        try {
            Files.deleteIfExists(outputFile);
        } catch (IOException ignored) {
            // Temporary output cleanup should not change review result.
        }
    }

    private void deleteRecursivelyQuietly(Path directory) {
        if (directory == null) {
            return;
        }
        try (var paths = Files.walk(directory)) {
            paths.sorted(Comparator.reverseOrder()).forEach(this::deleteQuietly);
        } catch (IOException ignored) {
            // Temporary workdir cleanup should not change review result.
        }
    }
}
