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
public class CacheChangeRule implements ChangeAnalysisRule {

    private static final List<String> PATH_KEYWORDS = List.of("cache", "redis", "caffeine", "ehcache");
    private static final List<String> CONTENT_KEYWORDS = List.of("RedisTemplate", "StringRedisTemplate", "@Cacheable", "@CacheEvict", "@CachePut", "cacheManager", "opsForValue", "expire(", "delete(");
    private static final Pattern CACHE_KEY_PATTERN = Pattern.compile("[\"']([a-zA-Z0-9_.:-]+:[a-zA-Z0-9_.:-]+)[\"']");

    @Override
    public String code() {
        return "CACHE_HEURISTIC_RULE";
    }

    @Override
    public Optional<RuleMatch> analyze(ChangedFile changedFile, String globalDiffText) {
        String content = HeuristicSupport.contentOf(changedFile, globalDiffText);
        boolean matched = HeuristicSupport.pathMatches(changedFile, PATH_KEYWORDS)
                || HeuristicSupport.containsAny(content, CONTENT_KEYWORDS);
        if (!matched) {
            return Optional.empty();
        }

        String resourceName = HeuristicSupport.firstRegexGroup(content, CACHE_KEY_PATTERN).orElse(changedFile.effectivePath());
        ChangeEvidence evidence = HeuristicSupport.evidence(ChangeType.CACHE, changedFile, resourceName, code());
        ImpactedResource resource = new ImpactedResource(ResourceType.CACHE_KEY, resourceName, changedFile.changeType().name(), changedFile.effectivePath(), evidence);
        return Optional.of(new RuleMatch(ChangeType.CACHE, changedFile, List.of(resource), List.of(evidence)));
    }
}