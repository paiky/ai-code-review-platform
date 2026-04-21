package com.leaf.codereview.projectintegration.infrastructure;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GitLabApiProperties {

    private final boolean enabled;
    private final String baseUrl;
    private final String token;
    private final int perPage;

    public GitLabApiProperties(
            @Value("${gitlab.api.enabled:false}") boolean enabled,
            @Value("${gitlab.api.base-url:}") String baseUrl,
            @Value("${gitlab.api.token:}") String token,
            @Value("${gitlab.api.per-page:100}") int perPage
    ) {
        this.enabled = enabled;
        this.baseUrl = baseUrl;
        this.token = token;
        this.perPage = perPage;
    }

    public boolean enabled() {
        return enabled;
    }

    public String baseUrl() {
        return baseUrl;
    }

    public String token() {
        return token;
    }

    public int perPage() {
        return perPage;
    }
}
