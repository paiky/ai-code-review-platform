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
public class MqChangeRule implements ChangeAnalysisRule {

    private static final List<String> PATH_KEYWORDS = List.of("mq", "message", "producer", "consumer", "listener", "rocketmq", "kafka", "rabbit");
    private static final List<String> CONTENT_KEYWORDS = List.of("@RocketMQMessageListener", "RocketMQTemplate", "KafkaTemplate", "@KafkaListener", "RabbitTemplate", "@RabbitListener", "sendMessage", "convertAndSend", "topic", "consumerGroup", "rocketmq", "kafka", "rabbitmq");
    private static final Pattern TOPIC_PATTERN = Pattern.compile("(?i)(?:topic|topics|destination)\\s*=\\s*[\"']([a-zA-Z0-9_.:-]+)[\"']");

    @Override
    public String code() {
        return "MQ_HEURISTIC_RULE";
    }

    @Override
    public Optional<RuleMatch> analyze(ChangedFile changedFile, String globalDiffText) {
        String content = HeuristicSupport.contentOf(changedFile, globalDiffText);
        boolean matched = HeuristicSupport.pathMatches(changedFile, PATH_KEYWORDS)
                || HeuristicSupport.containsAny(content, CONTENT_KEYWORDS);
        if (!matched) {
            return Optional.empty();
        }

        String resourceName = HeuristicSupport.firstRegexGroup(content, TOPIC_PATTERN).orElse(changedFile.effectivePath());
        ChangeEvidence evidence = HeuristicSupport.evidence(ChangeType.MQ, changedFile, resourceName, code());
        ImpactedResource resource = new ImpactedResource(ResourceType.MQ_TOPIC, resourceName, changedFile.changeType().name(), changedFile.effectivePath(), evidence);
        return Optional.of(new RuleMatch(ChangeType.MQ, changedFile, List.of(resource), List.of(evidence)));
    }
}