package com.leaf.codereview.changeanalysis.domain;

import java.util.Set;

public record AnalyzedFile(
        String path,
        FileChangeType changeType,
        Set<ChangeType> matchedChangeTypes
) {
    public AnalyzedFile {
        matchedChangeTypes = matchedChangeTypes == null ? Set.of() : Set.copyOf(matchedChangeTypes);
    }
}