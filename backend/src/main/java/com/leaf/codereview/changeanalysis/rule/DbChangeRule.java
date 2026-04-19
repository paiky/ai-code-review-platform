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
public class DbChangeRule implements ChangeAnalysisRule {

    private static final List<String> PATH_KEYWORDS = List.of("mapper", "repository", "dao", "entity", "migration", "schema", ".sql", "mybatis", "jpa");
    private static final List<String> CONTENT_KEYWORDS = List.of("insert into", "create table", "alter table", "drop table", "@Table", "@Entity");
    private static final List<Pattern> SQL_PATTERNS = List.of(
            Pattern.compile("(?i)\\bselect\\b.+\\bfrom\\b"),
            Pattern.compile("(?i)\\bupdate\\b.+\\bset\\b"),
            Pattern.compile("(?i)\\bdelete\\s+from\\b")
    );
    private static final Pattern TABLE_PATTERN = Pattern.compile("(?i)(?:from|into|update|table|join)\\s+[`\"]?([a-zA-Z_][a-zA-Z0-9_]*)[`\"]?");

    @Override
    public String code() {
        return "DB_HEURISTIC_RULE";
    }

    @Override
    public Optional<RuleMatch> analyze(ChangedFile changedFile, String globalDiffText) {
        String content = HeuristicSupport.contentOf(changedFile, globalDiffText);
        boolean contentMatched = HeuristicSupport.containsAny(content, CONTENT_KEYWORDS)
                || SQL_PATTERNS.stream().anyMatch(pattern -> pattern.matcher(content).find());
        boolean matched = HeuristicSupport.pathMatches(changedFile, PATH_KEYWORDS) || contentMatched;
        if (!matched) {
            return Optional.empty();
        }

        String resourceName = HeuristicSupport.firstRegexGroup(content, TABLE_PATTERN).orElse(changedFile.effectivePath());
        ChangeEvidence evidence = HeuristicSupport.evidence(ChangeType.DB, changedFile, resourceName, code());
        ResourceType resourceType = resourceName.equals(changedFile.effectivePath()) ? ResourceType.SQL : ResourceType.DB_TABLE;
        ImpactedResource resource = new ImpactedResource(resourceType, resourceName, changedFile.changeType().name(), changedFile.effectivePath(), evidence);
        return Optional.of(new RuleMatch(ChangeType.DB, changedFile, List.of(resource), List.of(evidence)));
    }
}