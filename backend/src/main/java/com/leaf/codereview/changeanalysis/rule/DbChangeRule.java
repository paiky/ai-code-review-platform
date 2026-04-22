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

    private static final List<String> ENTITY_PATH_KEYWORDS = List.of("entity", "/domain/", "\\domain\\", "/model/", "\\model\\", "/po/", "\\po\\", "/do/", "\\do\\");
    private static final List<String> ORM_PATH_KEYWORDS = List.of("mapper", "mybatis", "jpa");
    private static final List<String> MIGRATION_PATH_KEYWORDS = List.of("migration", "db/migration", "schema", "liquibase", "flyway", ".sql");
    private static final List<String> ENTITY_CONTENT_KEYWORDS = List.of("@Entity", "@Table", "@Column");
    private static final List<String> ORM_CONTENT_KEYWORDS = List.of("resultMap", "<result ", "<id ", "column=", "property=", "@Table", "@Column", "@JoinColumn", "@OneToMany", "@ManyToOne");
    private static final List<String> DATA_MIGRATION_KEYWORDS = List.of("backfill", "migrate", "migration", "数据修复", "回填", "历史数据");
    private static final List<String> DDL_KEYWORDS = List.of("create table", "alter table", "drop table", "add column", "drop column", "modify column", "rename column", "create index", "drop index");
    private static final List<Pattern> SQL_PATTERNS = List.of(
            Pattern.compile("(?i)\\bselect\\b.+\\bfrom\\b"),
            Pattern.compile("(?i)\\binsert\\s+into\\b"),
            Pattern.compile("(?i)\\bupdate\\b.+\\bset\\b"),
            Pattern.compile("(?i)\\bdelete\\s+from\\b")
    );
    private static final Pattern TABLE_PATTERN = Pattern.compile("(?i)(?:from|into|update|table|join)\\s+[`\"]?([a-zA-Z_][a-zA-Z0-9_]*)[`\"]?");
    private static final Pattern JAVA_FIELD_PATTERN = Pattern.compile("(?m)^\\s*[+-]\\s*(?:private|protected|public)\\s+[\\w<>?, ]+\\s+([a-zA-Z_][a-zA-Z0-9_]*)\\s*(?:=|;)");

    @Override
    public String code() {
        return "DB_FINE_GRAINED_RULE";
    }

    @Override
    public Optional<RuleMatch> analyze(ChangedFile changedFile, String globalDiffText) {
        String content = HeuristicSupport.contentOf(changedFile, globalDiffText);
        DbSignal signal = classify(changedFile, content);
        if (signal == null) {
            return Optional.empty();
        }

        String resourceName = HeuristicSupport.firstRegexGroup(content, TABLE_PATTERN).orElse(changedFile.effectivePath());
        if (signal.changeType() == ChangeType.ENTITY_MODEL) {
            resourceName = HeuristicSupport.firstRegexGroup(content, JAVA_FIELD_PATTERN).orElse(changedFile.effectivePath());
        }

        ChangeEvidence evidence = HeuristicSupport.evidence(signal.changeType(), changedFile, signal.reason() + " | " + resourceName, code());
        ResourceType resourceType = signal.resourceType();
        if (resourceType == ResourceType.DB_TABLE && resourceName.equals(changedFile.effectivePath())) {
            resourceType = ResourceType.SQL;
        }
        ImpactedResource resource = new ImpactedResource(resourceType, resourceName, changedFile.changeType().name(), changedFile.effectivePath(), evidence);
        return Optional.of(new RuleMatch(signal.changeType(), changedFile, List.of(resource), List.of(evidence)));
    }

    private DbSignal classify(ChangedFile changedFile, String content) {
        boolean migrationPath = HeuristicSupport.pathMatches(changedFile, MIGRATION_PATH_KEYWORDS);
        boolean mapperPath = HeuristicSupport.pathMatches(changedFile, ORM_PATH_KEYWORDS);
        boolean entityPath = HeuristicSupport.pathMatches(changedFile, ENTITY_PATH_KEYWORDS);
        boolean ddlMatched = HeuristicSupport.containsAny(content, DDL_KEYWORDS);
        boolean sqlMatched = SQL_PATTERNS.stream().anyMatch(pattern -> pattern.matcher(content).find());
        boolean ormMatched = HeuristicSupport.containsAny(content, ORM_CONTENT_KEYWORDS);
        boolean entityMatched = entityPath && (HeuristicSupport.containsAny(content, ENTITY_CONTENT_KEYWORDS) || JAVA_FIELD_PATTERN.matcher(content).find());

        if (ddlMatched) {
            return new DbSignal(ChangeType.DB_SCHEMA, ResourceType.DB_TABLE, "Detected DDL or migration schema statement");
        }
        if (migrationPath && (sqlMatched || HeuristicSupport.containsAny(content, DATA_MIGRATION_KEYWORDS))) {
            return new DbSignal(ChangeType.DATA_MIGRATION, ResourceType.DATA_MIGRATION, "Detected migration data change");
        }
        if (mapperPath && ormMatched) {
            return new DbSignal(ChangeType.ORM_MAPPING, ResourceType.ORM_MAPPING, "Detected ORM/MyBatis mapping change");
        }
        if (entityMatched) {
            return new DbSignal(ChangeType.ENTITY_MODEL, ResourceType.ENTITY_FIELD, "Detected entity model field or ORM annotation change");
        }
        if (sqlMatched) {
            return new DbSignal(ChangeType.DB_SQL, ResourceType.DB_TABLE, "Detected SQL read/write logic change");
        }
        return null;
    }

    private record DbSignal(ChangeType changeType, ResourceType resourceType, String reason) {
    }
}
