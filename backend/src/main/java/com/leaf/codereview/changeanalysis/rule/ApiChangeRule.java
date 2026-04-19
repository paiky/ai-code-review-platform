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
public class ApiChangeRule implements ChangeAnalysisRule {

    private static final List<String> PATH_KEYWORDS = List.of("controller", "endpoint", "/api/", "dto", "request", "response");
    private static final List<String> CONTENT_KEYWORDS = List.of("@RequestMapping", "@GetMapping", "@PostMapping", "@PutMapping", "@DeleteMapping", "@PatchMapping", "@RestController", "@Controller");
    private static final Pattern MAPPING_PATTERN = Pattern.compile("@(Get|Post|Put|Delete|Patch|Request)Mapping\\s*\\([^\"]*\"([^\"]+)\"");

    @Override
    public String code() {
        return "API_HEURISTIC_RULE";
    }

    @Override
    public Optional<RuleMatch> analyze(ChangedFile changedFile, String globalDiffText) {
        String content = HeuristicSupport.contentOf(changedFile, globalDiffText);
        boolean matched = HeuristicSupport.pathMatches(changedFile, PATH_KEYWORDS)
                || HeuristicSupport.containsAny(content, CONTENT_KEYWORDS);
        if (!matched) {
            return Optional.empty();
        }

        String apiName = HeuristicSupport.firstRegexGroup(content, MAPPING_PATTERN)
                .map(value -> HeuristicSupport.firstRegexGroup(content, Pattern.compile("@(Get|Post|Put|Delete|Patch|Request)Mapping\\s*\\([^\"]*\"([^\"]+)\""))
                        .orElse(value))
                .orElse(changedFile.effectivePath());
        String normalizedApiName = extractMappingPath(content).orElse(apiName);
        ChangeEvidence evidence = HeuristicSupport.evidence(ChangeType.API, changedFile, normalizedApiName, code());
        ImpactedResource resource = new ImpactedResource(ResourceType.API, normalizedApiName, changedFile.changeType().name(), changedFile.effectivePath(), evidence);
        return Optional.of(new RuleMatch(ChangeType.API, changedFile, List.of(resource), List.of(evidence)));
    }

    private Optional<String> extractMappingPath(String content) {
        java.util.regex.Matcher matcher = MAPPING_PATTERN.matcher(content == null ? "" : content);
        if (matcher.find()) {
            return Optional.of(matcher.group(1).toUpperCase() + " " + matcher.group(2));
        }
        return Optional.empty();
    }
}