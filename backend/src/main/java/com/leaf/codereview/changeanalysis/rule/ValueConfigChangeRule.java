package com.leaf.codereview.changeanalysis.rule;

import com.leaf.codereview.changeanalysis.domain.ChangeEvidence;
import com.leaf.codereview.changeanalysis.domain.ChangeType;
import com.leaf.codereview.changeanalysis.domain.ChangedFile;
import com.leaf.codereview.changeanalysis.domain.ImpactedResource;
import com.leaf.codereview.changeanalysis.domain.ResourceType;
import com.leaf.codereview.changeanalysis.domain.RuleMatch;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Optional;
import java.util.regex.Pattern;

@Component
public class ValueConfigChangeRule implements ChangeAnalysisRule {

    public static final String RULE_CODE = "VALUE_CONFIG_HEURISTIC_RULE";

    private static final Pattern VALUE_PLACEHOLDER_PATTERN = Pattern.compile("\\$\\{([^}:\\s]+)(?::[^}]*)?}");

    @Override
    public String code() {
        return RULE_CODE;
    }

    @Override
    public Optional<RuleMatch> analyze(ChangedFile changedFile, String globalDiffText) {
        String content = HeuristicSupport.contentOf(changedFile, globalDiffText);
        if (!content.contains("@Value(")) {
            return Optional.empty();
        }

        String configKey = HeuristicSupport.firstRegexGroup(content, VALUE_PLACEHOLDER_PATTERN)
                .orElse(changedFile.effectivePath());
        ChangeEvidence evidence = HeuristicSupport.evidence(ChangeType.CONFIG, changedFile, "@Value config key: " + configKey, code());
        ImpactedResource resource = new ImpactedResource(
                ResourceType.CONFIG_KEY,
                configKey,
                changedFile.changeType().name(),
                changedFile.effectivePath(),
                evidence
        );
        return Optional.of(new RuleMatch(ChangeType.CONFIG, changedFile, List.of(resource), List.of(evidence)));
    }
}
