package com.leaf.codereview.changeanalysis.rule;

import com.leaf.codereview.changeanalysis.domain.ChangeEvidence;
import com.leaf.codereview.changeanalysis.domain.ChangeType;
import com.leaf.codereview.changeanalysis.domain.ChangedFile;

import java.util.Collection;
import java.util.Locale;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

final class HeuristicSupport {

    private HeuristicSupport() {
    }

    static String normalize(String value) {
        return value == null ? "" : value.toLowerCase(Locale.ROOT);
    }

    static String contentOf(ChangedFile changedFile, String globalDiffText) {
        StringBuilder builder = new StringBuilder();
        if (changedFile.effectivePath() != null) {
            builder.append(changedFile.effectivePath()).append('\n');
        }
        if (changedFile.diffText() != null && !changedFile.diffText().isBlank()) {
            builder.append(changedFile.diffText()).append('\n');
        } else if (globalDiffText != null) {
            builder.append(globalDiffText);
        }
        return builder.toString();
    }

    static boolean containsAny(String value, Collection<String> keywords) {
        String normalized = normalize(value);
        return keywords.stream().map(HeuristicSupport::normalize).anyMatch(normalized::contains);
    }

    static boolean pathMatches(ChangedFile changedFile, Collection<String> keywords) {
        return containsAny(changedFile.effectivePath(), keywords);
    }

    static Optional<String> firstRegexGroup(String value, Pattern pattern) {
        Matcher matcher = pattern.matcher(value == null ? "" : value);
        if (matcher.find()) {
            return Optional.ofNullable(matcher.group(1));
        }
        return Optional.empty();
    }

    static ChangeEvidence evidence(ChangeType changeType, ChangedFile changedFile, String snippet, String matcher) {
        return new ChangeEvidence(
                changeType,
                changedFile.effectivePath(),
                null,
                null,
                trimSnippet(snippet),
                matcher
        );
    }

    static String trimSnippet(String snippet) {
        if (snippet == null) {
            return null;
        }
        String compact = snippet.strip().replaceAll("\\s+", " ");
        if (compact.length() <= 180) {
            return compact;
        }
        return compact.substring(0, 177) + "...";
    }
}