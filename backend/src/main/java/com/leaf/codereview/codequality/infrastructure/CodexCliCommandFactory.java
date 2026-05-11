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

                本轮变更文件白名单：
                %s

                本轮唯一变更来源：
                以下 diff 文本来自平台保存的 GitLab changed files / diff。你必须只审查这段 diff 中新增或修改引入的问题。
                不要读取本地工作区文件，不要执行 git diff，不要根据当前目录的 HEAD 或分支推断审查范围。

                ```diff
                %s
                ```

                输出要求：
                1. 必须使用简体中文。
                2. 每个问题必须以“高风险：”“中风险：”或“低风险：”开头。
                3. 每个问题尽量包含文件路径和行号。
                4. 不要输出英文标题，例如 Findings、Residual Risks、Assumptions。
                5. 不要报告纯代码风格问题。
                6. 每个问题必须简要说明证据、触发条件、潜在影响和修复建议。
                7. 你可以读取相关上下文文件辅助理解，但最终只能报告由白名单文件 diff 引入的问题。
                8. 如果问题需要引用上下文文件，必须说明它如何由白名单文件的 diff 触发。
                9. 不要报告只存在于上下文文件、历史代码或本地其它分支中的问题。
                10. 如果没有发现明确问题，只输出“未发现需要阻断的代码质量风险。”。

                English compatibility note: review only the requested scope, return Simplified Chinese, and do not edit files.
                """.formatted(
                scopeDescription(request),
                fallbackText(request.title(), "Code quality review"),
                request.instructions(),
                changedFilesWhitelist(request),
                diffText(request)
        );
    }

    private String scopeDescription(CodeQualityReviewRequest request) {
        CodeQualityReviewMode mode = request.mode() == null ? CodeQualityReviewMode.UNCOMMITTED : request.mode();
        return switch (mode) {
            case BASE -> "请求来源标记为 BASE 模式，基线分支为 `%s`。本轮仍只审查下方平台提供的 diff 文本，不要执行 git diff。"
                    .formatted(StringUtils.hasText(request.baseRef()) ? request.baseRef() : "origin/main");
            case COMMIT -> "请求来源标记为 COMMIT 模式，commit 为 `%s`。本轮仍只审查下方平台提供的 diff 文本。"
                    .formatted(fallbackText(request.commitSha(), "HEAD"));
            case UNCOMMITTED -> "请求来源标记为 UNCOMMITTED 模式。本轮仍只审查下方平台提供的 diff 文本，不要读取本地未提交变更。";
            case DIFF_TEXT -> "审查平台提供的 diff 文本。这是本轮唯一变更来源，不要读取本地仓库或执行 git diff。";
        };
    }

    private String shortPrompt(Path promptFile) {
        return "Please read the UTF-8 review instructions from " + promptFile.toAbsolutePath()
                + " and follow them exactly. Return the final review in Simplified Chinese only.";
    }

    private String fallbackText(String text, String fallback) {
        return StringUtils.hasText(text) ? text : fallback;
    }

    private String changedFilesWhitelist(CodeQualityReviewRequest request) {
        if (request.changedFiles() == null || request.changedFiles().isEmpty()) {
            return "未提供 changed files 白名单。请严格以审查范围中的 diff 为准。";
        }
        StringBuilder builder = new StringBuilder();
        int index = 1;
        for (String changedFile : request.changedFiles()) {
            if (!StringUtils.hasText(changedFile)) {
                continue;
            }
            builder.append(index++).append(". ").append(changedFile.replace('\\', '/').strip()).append('\n');
        }
        return builder.isEmpty() ? "未提供 changed files 白名单。请严格以审查范围中的 diff 为准。" : builder.toString().stripTrailing();
    }

    private String diffText(CodeQualityReviewRequest request) {
        return StringUtils.hasText(request.diffText()) ? request.diffText() : "未提供 diff 文本。";
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
