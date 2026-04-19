package com.leaf.codereview.changeanalysis.domain;

public record ChangedFile(
        String path,
        String oldPath,
        String newPath,
        FileChangeType changeType,
        String diffText
) {
    public static ChangedFile of(String path, String diffText) {
        return new ChangedFile(path, path, path, FileChangeType.MODIFIED, diffText);
    }

    public String effectivePath() {
        if (newPath != null && !newPath.isBlank()) {
            return newPath;
        }
        if (path != null && !path.isBlank()) {
            return path;
        }
        return oldPath;
    }
}