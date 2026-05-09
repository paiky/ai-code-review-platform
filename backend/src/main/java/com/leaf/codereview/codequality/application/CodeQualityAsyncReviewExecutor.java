package com.leaf.codereview.codequality.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewMode;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProfile;
import com.leaf.codereview.codequality.domain.CodeQualityReviewProviderType;
import com.leaf.codereview.codequality.domain.CodeQualityReviewRequest;
import com.leaf.codereview.codequality.domain.CodeQualityReviewResult;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProperties;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewProgressTracker;
import com.leaf.codereview.codequality.infrastructure.CodeQualityReviewResultRepository;
import com.leaf.codereview.projectintegration.domain.GitLabMergeRequestEvent;
import com.leaf.codereview.projectintegration.domain.ProjectRecord;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

@Service
public class CodeQualityAsyncReviewExecutor {

    private static final Logger log = LoggerFactory.getLogger(CodeQualityAsyncReviewExecutor.class);

    private final CodeQualityReviewProperties properties;
    private final CodeQualityReviewProgressTracker progressTracker;
    private final CodeQualityReviewService reviewService;
    private final CodeQualityReviewResultRepository resultRepository;

    public CodeQualityAsyncReviewExecutor(
            CodeQualityReviewProperties properties,
            CodeQualityReviewProgressTracker progressTracker,
            CodeQualityReviewService reviewService,
            CodeQualityReviewResultRepository resultRepository
    ) {
        this.properties = properties;
        this.progressTracker = progressTracker;
        this.reviewService = reviewService;
        this.resultRepository = resultRepository;
    }

    @Async
    public void execute(Long taskId, ProjectRecord project, GitLabMergeRequestEvent event, CodeQualityReviewProfile profile, CodeQualityReviewProviderType provider) {
        progressTracker.runWithTask(taskId, () -> executeInternal(taskId, project, event, profile, provider));
    }

    private void executeInternal(Long taskId, ProjectRecord project, GitLabMergeRequestEvent event, CodeQualityReviewProfile profile, CodeQualityReviewProviderType provider) {
        progressTracker.info("STARTED", "AI Review 异步执行线程已启动", "project=" + project.name() + ", mr=!" + event.mrId() + ", profileCode=" + profile.profileCode());
        CodeQualityReviewRequest request = buildRequest(project, event, profile, provider);
        progressTracker.info("REQUEST_BUILT", "AI Review 请求已构建", "profileCode=" + profile.profileCode() + ", provider=" + provider.name() + ", model=" + request.model() + ", mode=" + request.mode() + ", baseRef=" + request.baseRef() + ", changedFiles=" + request.changedFiles().size());
        if (provider == CodeQualityReviewProviderType.CODEX_CLI && !StringUtils.hasText(request.repositoryPath())) {
            saveFailed(taskId, project.id(), profile, provider, "CODEX_CLI auto review requires a local repository path under CODE_QUALITY_WORKSPACE_ROOT");
            return;
        }

        try {
            progressTracker.info("PROVIDER_START", "开始调用代码质量 Review Provider", "provider=" + provider.name());
            CodeQualityReviewResult result = reviewService.review(request, provider);
            progressTracker.info("SAVE_RESULT", "Provider 执行完成，开始保存结果", "status=" + result.status() + ", findingCount=" + result.findings().size());
            resultRepository.save(taskId, project.id(), profile.profileCode(), request.model(), result);
            progressTracker.info("FINISHED", "AI Review 结果已保存", "status=" + result.status() + ", overallLevel=" + result.overallLevel());
        } catch (Exception exception) {
            log.warn("AI code review failed for taskId={}: {}", taskId, exception.getMessage());
            progressTracker.error("FAILED", "AI Review 执行失败", exception.getMessage());
            saveFailed(taskId, project.id(), profile, provider, exception.getMessage());
        }
    }

    private CodeQualityReviewRequest buildRequest(ProjectRecord project, GitLabMergeRequestEvent event, CodeQualityReviewProfile profile, CodeQualityReviewProviderType provider) {
        String repositoryPath = resolveRepositoryPath(project);
        CodeQualityReviewMode mode = provider == CodeQualityReviewProviderType.CODEX_CLI
                ? CodeQualityReviewMode.BASE
                : CodeQualityReviewMode.DIFF_TEXT;
        return new CodeQualityReviewRequest(
                repositoryPath,
                mode,
                baseRef(event.targetBranch()),
                event.commitSha(),
                "GitLab MR !" + event.mrId() + " " + nullToEmpty(event.sourceBranch()) + " -> " + nullToEmpty(event.targetBranch()),
                profile.model(),
                provider == CodeQualityReviewProviderType.CODEX_CLI ? profile.codexPrompt() : profile.openAiInstructions(),
                buildDiffText(event.changedFilesSummary()),
                changedFilePaths(event.changedFilesSummary())
        );
    }

    private String resolveRepositoryPath(ProjectRecord project) {
        if (StringUtils.hasText(project.repositoryUrl())) {
            try {
                Path directPath = Path.of(project.repositoryUrl()).toAbsolutePath().normalize();
                if (Files.isDirectory(directPath)) {
                    return directPath.toString();
                }
            } catch (Exception ignored) {
                // Repository URL is usually an HTTP URL. Local paths are supported as an opt-in shortcut.
            }
        }
        if (!StringUtils.hasText(properties.workspaceRoot())) {
            return null;
        }
        Path root = Path.of(properties.workspaceRoot()).toAbsolutePath().normalize();
        List<String> candidates = List.of(
                project.gitProjectId(),
                sanitizePathName(project.name()),
                repositoryName(project.repositoryUrl())
        );
        for (String candidate : candidates) {
            if (!StringUtils.hasText(candidate)) {
                continue;
            }
            Path path = root.resolve(candidate).normalize();
            if (Files.isDirectory(path)) {
                return path.toString();
            }
        }
        return null;
    }

    private String buildDiffText(JsonNode changedFilesSummary) {
        StringBuilder builder = new StringBuilder();
        JsonNode files = changedFilesSummary.path("files");
        if (!files.isArray()) {
            return "";
        }
        for (JsonNode file : files) {
            String path = firstText(file, "path", "newPath", "new_path", "oldPath", "old_path");
            String diffText = firstText(file, "diffText", "diff", "patch");
            if (!StringUtils.hasText(diffText)) {
                continue;
            }
            builder.append("File: ").append(path).append('\n');
            builder.append(diffText).append("\n\n");
        }
        return builder.toString();
    }

    private List<String> changedFilePaths(JsonNode changedFilesSummary) {
        List<String> paths = new ArrayList<>();
        JsonNode files = changedFilesSummary.path("files");
        if (files.isArray()) {
            for (JsonNode file : files) {
                String path = firstText(file, "path", "newPath", "new_path", "oldPath", "old_path");
                if (StringUtils.hasText(path)) {
                    paths.add(path);
                }
            }
        }
        return paths;
    }

    private void saveFailed(Long taskId, Long projectId, CodeQualityReviewProfile profile, CodeQualityReviewProviderType provider, String errorMessage) {
        progressTracker.error("SAVE_FAILED", "保存失败状态", errorMessage);
        CodeQualityReviewResult result = CodeQualityReviewResult.failed(
                provider,
                errorMessage,
                null,
                null,
                OffsetDateTime.now(),
                OffsetDateTime.now()
        );
        resultRepository.save(taskId, projectId, profile.profileCode(), profile.model(), result);
    }

    private String baseRef(String targetBranch) {
        if (!StringUtils.hasText(targetBranch)) {
            return "origin/main";
        }
        return targetBranch.startsWith("origin/") ? targetBranch : "origin/" + targetBranch;
    }

    private String firstText(JsonNode node, String... fields) {
        for (String field : fields) {
            JsonNode value = node.path(field);
            if (!value.isMissingNode() && !value.isNull() && StringUtils.hasText(value.asText())) {
                return value.asText();
            }
        }
        return null;
    }

    private String repositoryName(String repositoryUrl) {
        if (!StringUtils.hasText(repositoryUrl)) {
            return null;
        }
        String normalized = repositoryUrl.replace('\\', '/').replaceAll("/+$", "");
        int index = normalized.lastIndexOf('/');
        String name = index >= 0 ? normalized.substring(index + 1) : normalized;
        return name.endsWith(".git") ? name.substring(0, name.length() - 4) : name;
    }

    private String sanitizePathName(String value) {
        return StringUtils.hasText(value) ? value.replaceAll("[^a-zA-Z0-9._-]", "-") : null;
    }

    private String nullToEmpty(String value) {
        return value == null ? "" : value;
    }
}
