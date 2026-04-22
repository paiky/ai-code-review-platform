package com.leaf.codereview.projectintegration.infrastructure;

import com.fasterxml.jackson.databind.JsonNode;
import com.leaf.codereview.common.enums.ErrorCode;
import com.leaf.codereview.common.exception.BusinessException;
import com.leaf.codereview.projectintegration.domain.GitLabDiffFile;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriComponentsBuilder;
import org.springframework.web.util.UriUtils;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

@Component
public class GitLabClient {

    private final GitLabApiProperties properties;
    private final RestClient restClient;

    public GitLabClient(GitLabApiProperties properties, RestClient.Builder restClientBuilder) {
        this.properties = properties;
        this.restClient = restClientBuilder.build();
    }

    public List<GitLabDiffFile> listMergeRequestDiffs(String projectId, String mergeRequestIid) {
        validateReady();
        if (!StringUtils.hasText(projectId)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "GitLab project id is required to fetch MR diffs");
        }
        if (!StringUtils.hasText(mergeRequestIid)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "GitLab merge request iid is required to fetch MR diffs");
        }

        try {
            return listMergeRequestDiffsFromDiffsEndpoint(projectId, mergeRequestIid);
        } catch (GitLabDiffsEndpointNotFoundException exception) {
            return listMergeRequestDiffsFromChangesEndpoint(projectId, mergeRequestIid);
        }
    }

    private List<GitLabDiffFile> listMergeRequestDiffsFromDiffsEndpoint(String projectId, String mergeRequestIid) {
        List<GitLabDiffFile> files = new ArrayList<>();
        int perPage = Math.max(1, properties.perPage());
        int page = 1;
        while (true) {
            JsonNode response = fetchDiffPage(projectId, mergeRequestIid, page, perPage);
            if (response == null || !response.isArray()) {
                throw new BusinessException(ErrorCode.INTERNAL_ERROR, "GitLab MR diffs response must be an array");
            }
            int pageSize = 0;
            for (JsonNode fileNode : response) {
                pageSize++;
                files.add(toDiffFile(fileNode));
            }
            if (pageSize < perPage) {
                return files;
            }
            page++;
        }
    }

    private List<GitLabDiffFile> listMergeRequestDiffsFromChangesEndpoint(String projectId, String mergeRequestIid) {
        JsonNode response = fetchChanges(projectId, mergeRequestIid);
        JsonNode changes = response == null ? null : response.path("changes");
        if (changes == null || !changes.isArray()) {
            throw new BusinessException(ErrorCode.INTERNAL_ERROR, "GitLab MR changes response must contain a changes array");
        }

        List<GitLabDiffFile> files = new ArrayList<>();
        for (JsonNode fileNode : changes) {
            files.add(toDiffFile(fileNode));
        }
        return files;
    }

    private void validateReady() {
        if (!properties.enabled()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "GitLab diff is not provided and GitLab API is disabled");
        }
        if (!StringUtils.hasText(properties.baseUrl())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "GitLab API base-url is required");
        }
        if (!StringUtils.hasText(properties.token())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "GitLab API token is required");
        }
    }

    private JsonNode fetchDiffPage(String projectId, String mergeRequestIid, int page, int perPage) {
        String uri = UriComponentsBuilder
                .fromHttpUrl(normalizeBaseUrl(properties.baseUrl()))
                .path("/api/v4/projects/{projectId}/merge_requests/{mergeRequestIid}/diffs")
                .queryParam("page", page)
                .queryParam("per_page", perPage)
                .buildAndExpand(
                        UriUtils.encodePathSegment(projectId, StandardCharsets.UTF_8),
                        UriUtils.encodePathSegment(mergeRequestIid, StandardCharsets.UTF_8)
                )
                .toUriString();

        return restClient.get()
                .uri(uri)
                .header("PRIVATE-TOKEN", properties.token())
                .retrieve()
                .onStatus(status -> status.value() == 404, (request, response) -> {
                    throw new GitLabDiffsEndpointNotFoundException();
                })
                .onStatus(HttpStatusCode::isError, (request, response) -> {
                    throw new BusinessException(
                            ErrorCode.INTERNAL_ERROR,
                            "Failed to fetch GitLab MR diffs: HTTP " + response.getStatusCode().value()
                    );
                })
                .body(JsonNode.class);
    }

    private JsonNode fetchChanges(String projectId, String mergeRequestIid) {
        String uri = UriComponentsBuilder
                .fromHttpUrl(normalizeBaseUrl(properties.baseUrl()))
                .path("/api/v4/projects/{projectId}/merge_requests/{mergeRequestIid}/changes")
                .buildAndExpand(
                        UriUtils.encodePathSegment(projectId, StandardCharsets.UTF_8),
                        UriUtils.encodePathSegment(mergeRequestIid, StandardCharsets.UTF_8)
                )
                .toUriString();

        return restClient.get()
                .uri(uri)
                .header("PRIVATE-TOKEN", properties.token())
                .retrieve()
                .onStatus(HttpStatusCode::isError, (request, response) -> {
                    throw new BusinessException(
                            ErrorCode.INTERNAL_ERROR,
                            "Failed to fetch GitLab MR changes: HTTP " + response.getStatusCode().value()
                    );
                })
                .body(JsonNode.class);
    }

    private String normalizeBaseUrl(String baseUrl) {
        String trimmed = baseUrl.trim();
        if (trimmed.endsWith("/")) {
            return trimmed.substring(0, trimmed.length() - 1);
        }
        return trimmed;
    }

    private GitLabDiffFile toDiffFile(JsonNode fileNode) {
        return new GitLabDiffFile(
                textAt(fileNode, "/old_path"),
                textAt(fileNode, "/new_path"),
                textAt(fileNode, "/diff"),
                booleanAt(fileNode, "/new_file"),
                booleanAt(fileNode, "/renamed_file"),
                booleanAt(fileNode, "/deleted_file"),
                booleanAt(fileNode, "/collapsed"),
                booleanAt(fileNode, "/too_large")
        );
    }

    private String textAt(JsonNode node, String pointer) {
        JsonNode value = node.at(pointer);
        if (value.isMissingNode() || value.isNull()) {
            return null;
        }
        return value.asText();
    }

    private boolean booleanAt(JsonNode node, String pointer) {
        JsonNode value = node.at(pointer);
        return !value.isMissingNode() && value.asBoolean(false);
    }

    private static class GitLabDiffsEndpointNotFoundException extends RuntimeException {
    }
}
