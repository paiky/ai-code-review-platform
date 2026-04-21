package com.leaf.codereview.projectintegration.domain;

public record GitLabDiffFile(
        String oldPath,
        String newPath,
        String diffText,
        boolean newFile,
        boolean renamedFile,
        boolean deletedFile,
        boolean collapsed,
        boolean tooLarge
) {
}
