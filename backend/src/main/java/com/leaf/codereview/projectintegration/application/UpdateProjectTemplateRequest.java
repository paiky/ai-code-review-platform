package com.leaf.codereview.projectintegration.application;

import jakarta.validation.constraints.NotBlank;

public record UpdateProjectTemplateRequest(@NotBlank String templateCode) {
}