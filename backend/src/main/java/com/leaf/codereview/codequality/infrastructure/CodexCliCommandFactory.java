package com.leaf.codereview.codequality.infrastructure;

import com.leaf.codereview.codequality.domain.CodeQualityReviewMode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

@Component
public class CodexCliCommandFactory {

    public List<String> buildCommand(CodeQualityReviewProperties properties, CodeQualityReviewRequest request, Path outputFile) {
        return buildCommand(properties, request, outputFile, System.getProperty("os.name"));
    }

    public List<String> buildCommand(CodeQualityReviewProperties properties, CodeQualityReviewRequest request, Path outputFile, String osName) {
        return buildCommand(properties, request, outputFile, null, osName);
    }

    public List<String> buildCommand(CodeQualityReviewProperties properties, CodeQualityReviewRequest request, Path outputFile, Path promptFile) {
        return buildCommand(properties, request, outputFile, promptFile, System.getProperty("os.name"));
    }

    public List<String> buildCommand(CodeQualityReviewProperties properties, CodeQualityReviewRequest request, Path outputFile, Path promptFile, String osName) {
        List<String> command = new ArrayList<>();
        String executable = StringUtils.hasText(properties.codexCommand())
                ? properties.codexCommand()
                : defaultCommand(osName);
        if (isWindows(osName)) {
            command.add("cmd.exe");
            command.add("/d");
            command.add("/s");
            command.add("/c");
        }
        command.add(executable);
        command.add("--sandbox");
        command.add("read-only");
        command.add("-a");
        command.add("never");
        command.add("exec");
        command.add("--json");
        command.add("--ephemeral");
        command.add("-o");
        command.add(outputFile.toAbsolutePath().toString());
        String model = StringUtils.hasText(request.model()) ? request.model() : properties.codexModel();
        if (StringUtils.hasText(model)) {
            command.add("-m");
            command.add(model);
        }

        if (promptFile != null) {
            command.add(shortPrompt(promptFile));
            return command;
        }

        command.add("review");
        if (StringUtils.hasText(request.title())) {
            command.add("--title");
            command.add(request.title());
        }
        addReviewScope(command, request);
        return command;
    }

    public String renderPrompt(CodeQualityReviewRequest request) {
        return """
                你是代码质量审核助手。请只审查本次变更，不要修改文件。

                审查范围：
                %s

                标题：
                %s

                用户自定义审核规则：
                %s

                输出要求：
                1. 必须使用简体中文。
                2. 每个问题必须以“高风险：”“中风险：”或“低风险：”开头。
                3. 每个问题尽量包含文件路径和行号。
                4. 不要输出英文标题，例如 Findings、Residual Risks、Assumptions。
                5. 不要报告纯代码风格问题。
                6. 如果没有发现明确问题，请简要说明未发现需要阻断的代码质量风险。

                English compatibility note: review only the requested scope, return Simplified Chinese, and do not edit files.
                """.formatted(scopeDescription(request), fallbackText(request.title(), "Code quality review"), request.instructions());
    }

    private String scopeDescription(CodeQualityReviewRequest request) {
        CodeQualityReviewMode mode = request.mode() == null ? CodeQualityReviewMode.UNCOMMITTED : request.mode();
        return switch (mode) {
            case BASE -> "审查当前分支相对基线分支 `%s` 的变更，请使用从该基线到 HEAD 的 git diff。"
                    .formatted(StringUtils.hasText(request.baseRef()) ? request.baseRef() : "origin/main");
            case COMMIT -> "审查 commit `%s` 引入的变更。"
                    .formatted(fallbackText(request.commitSha(), "HEAD"));
            case UNCOMMITTED -> "审查 staged、unstaged 和 untracked 的本地变更。";
            case DIFF_TEXT -> "审查当前工作区变更。原始 diff 文本只会直接提供给 API provider。";
        };
    }

    private String shortPrompt(Path promptFile) {
        return "Please read the UTF-8 review instructions from " + promptFile.toAbsolutePath()
                + " and follow them exactly. Return the final review in Simplified Chinese only.";
    }

    private String fallbackText(String text, String fallback) {
        return StringUtils.hasText(text) ? text : fallback;
    }

    public String defaultCommand(String osName) {
        return isWindows(osName) ? "codex.cmd" : "codex";
    }

    private void addReviewScope(List<String> command, CodeQualityReviewRequest request) {
        CodeQualityReviewMode mode = request.mode() == null ? CodeQualityReviewMode.UNCOMMITTED : request.mode();
        switch (mode) {
            case BASE -> {
                command.add("--base");
                command.add(StringUtils.hasText(request.baseRef()) ? request.baseRef() : "origin/main");
            }
            case COMMIT -> {
                command.add("--commit");
                command.add(request.commitSha());
            }
            case UNCOMMITTED -> command.add("--uncommitted");
            case DIFF_TEXT -> {
                // The API provider handles raw diff text directly. CLI mode still needs a repository scope.
                command.add("--uncommitted");
            }
        }
    }

    private boolean isWindows(String osName) {
        return osName != null && osName.toLowerCase(Locale.ROOT).contains("win");
    }
}
