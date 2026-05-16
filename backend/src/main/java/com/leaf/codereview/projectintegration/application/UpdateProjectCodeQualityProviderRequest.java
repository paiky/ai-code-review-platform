package com.leaf.codereview.projectintegration.application;

import jakarta.validation.constraints.NotBlank;

public record UpdateProjectCodeQualityProviderRequest(
        @NotBlank String providerCode
) {
}
