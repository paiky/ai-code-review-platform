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
    private static final List<String> CONTENT_KEYWORDS = List.of("RedisTemplate", "StringRedisTemplate", "@Cacheable", "@CacheEvict", "@CachePut", "cacheManager", "opsForValue", "expire(", "delete(", "RedisSerializer");
    private static final List<String> TTL_KEYWORDS = List.of("expire(", "expireAt(", "ttl", "time-to-live", "timeToLive", "Duration.of", "TimeUnit.");
    private static final List<String> INVALIDATION_KEYWORDS = List.of("@CacheEvict", "delete(", "evict(", "invalidate(", "clear(", "unlink(");
    private static final List<String> READ_WRITE_KEYWORDS = List.of("@Cacheable", "@CachePut", "opsForValue", "opsForHash", "get(", "set(", "put(", "cacheManager");
    private static final List<String> SERIALIZATION_KEYWORDS = List.of("RedisSerializer", "Jackson2JsonRedisSerializer", "GenericJackson2JsonRedisSerializer", "StringRedisSerializer", "serialize(", "deserialize(", "ObjectMapper");
    private static final Pattern CACHE_KEY_PATTERN = Pattern.compile("[\"']([a-zA-Z0-9_.:-]+:[a-zA-Z0-9_.:-]+)[\"']");
    private static final Pattern CACHE_KEY_CONSTANT_PATTERN = Pattern.compile("(?i)(?:cache[_-]?key|key|prefix)\\s*(?:=|:)\\s*[\"']([a-zA-Z0-9_.:-]+)[\"']");

    @Override
    public String code() {
        return "CACHE_FINE_GRAINED_RULE";
    }

    @Override
    public Optional<RuleMatch> analyze(ChangedFile changedFile, String globalDiffText) {
        String content = HeuristicSupport.contentOf(changedFile, globalDiffText);
        boolean matched = HeuristicSupport.pathMatches(changedFile, PATH_KEYWORDS)
                || HeuristicSupport.containsAny(content, CONTENT_KEYWORDS);
        if (!matched) {
            return Optional.empty();
        }

        CacheSignal signal = classify(content);
        String resourceName = HeuristicSupport.firstRegexGroup(content, CACHE_KEY_PATTERN)
                .or(() -> HeuristicSupport.firstRegexGroup(content, CACHE_KEY_CONSTANT_PATTERN))
                .orElse(changedFile.effectivePath());

        ChangeEvidence evidence = HeuristicSupport.evidence(signal.changeType(), changedFile, signal.reason() + " | " + resourceName, code());
        ImpactedResource resource = new ImpactedResource(signal.resourceType(), resourceName, changedFile.changeType().name(), changedFile.effectivePath(), evidence);
        return Optional.of(new RuleMatch(signal.changeType(), changedFile, List.of(resource), List.of(evidence)));
    }

    private CacheSignal classify(String content) {
        if (HeuristicSupport.containsAny(content, SERIALIZATION_KEYWORDS)) {
            return new CacheSignal(ChangeType.CACHE_SERIALIZATION, ResourceType.CACHE_VALUE, "Detected cache serialization or cached value schema change");
        }
        if (HeuristicSupport.containsAny(content, INVALIDATION_KEYWORDS)) {
            return new CacheSignal(ChangeType.CACHE_INVALIDATION, ResourceType.CACHE_KEY, "Detected cache invalidation or eviction change");
        }
        if (HeuristicSupport.containsAny(content, TTL_KEYWORDS)) {
            return new CacheSignal(ChangeType.CACHE_TTL, ResourceType.CACHE_POLICY, "Detected cache TTL or expiration policy change");
        }
        if (HeuristicSupport.containsAny(content, READ_WRITE_KEYWORDS)) {
            return new CacheSignal(ChangeType.CACHE_READ_WRITE, ResourceType.CACHE_KEY, "Detected cache read/write path change");
        }
        if (CACHE_KEY_PATTERN.matcher(content).find() || CACHE_KEY_CONSTANT_PATTERN.matcher(content).find()) {
            return new CacheSignal(ChangeType.CACHE_KEY, ResourceType.CACHE_KEY, "Detected cache key naming or composition change");
        }
        return new CacheSignal(ChangeType.CACHE_READ_WRITE, ResourceType.CACHE_KEY, "Detected cache-related code path change");
    }

    private record CacheSignal(ChangeType changeType, ResourceType resourceType, String reason) {
    }
}
