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
    private static final List<String> PRODUCER_KEYWORDS = List.of("RocketMQTemplate", "KafkaTemplate", "RabbitTemplate", "sendMessage", "convertAndSend", "syncSend", "asyncSend", "send(");
    private static final List<String> CONSUMER_KEYWORDS = List.of("@RocketMQMessageListener", "@KafkaListener", "@RabbitListener", "MessageListener", "Consumer", "Listener");
    private static final List<String> RETRY_DLQ_KEYWORDS = List.of("retry", "reconsume", "dead letter", "deadLetter", "dlq", "ack", "nack", "manualAck", "maxAttempts", "delayLevel", "idempotent", "idempotency");
    private static final List<String> TOPIC_CONFIG_KEYWORDS = List.of("topic", "topics", "tag", "tags", "consumerGroup", "groupId", "destination");
    private static final List<String> MESSAGE_SCHEMA_PATH_KEYWORDS = List.of("message", "event", "payload", "dto");
    private static final Pattern TOPIC_PATTERN = Pattern.compile("(?i)(?:topic|topics|destination)\\s*=\\s*[\"']([a-zA-Z0-9_.:-]+)[\"']");
    private static final Pattern SEND_TOPIC_PATTERN = Pattern.compile("(?i)(?:send|syncSend|asyncSend|convertAndSend)\\s*\\(\\s*[\"']([a-zA-Z0-9_.:-]+)[\"']");
    private static final Pattern JAVA_FIELD_PATTERN = Pattern.compile("(?m)^\\s*[+-]\\s*(?:private|protected|public)\\s+[\\w<>?, ]+\\s+([a-zA-Z_][a-zA-Z0-9_]*)\\s*(?:=|;)");

    @Override
    public String code() {
        return "MQ_FINE_GRAINED_RULE";
    }

    @Override
    public Optional<RuleMatch> analyze(ChangedFile changedFile, String globalDiffText) {
        String content = HeuristicSupport.contentOf(changedFile, globalDiffText);
        boolean matched = HeuristicSupport.pathMatches(changedFile, PATH_KEYWORDS)
                || HeuristicSupport.containsAny(content, CONTENT_KEYWORDS);
        if (!matched) {
            return Optional.empty();
        }

        MqSignal signal = classify(changedFile, content);
        String resourceName = HeuristicSupport.firstRegexGroup(content, TOPIC_PATTERN)
                .or(() -> HeuristicSupport.firstRegexGroup(content, SEND_TOPIC_PATTERN))
                .orElse(changedFile.effectivePath());
        if (signal.changeType() == ChangeType.MQ_MESSAGE_SCHEMA) {
            resourceName = HeuristicSupport.firstRegexGroup(content, JAVA_FIELD_PATTERN).orElse(changedFile.effectivePath());
        }

        ChangeEvidence evidence = HeuristicSupport.evidence(signal.changeType(), changedFile, signal.reason() + " | " + resourceName, code());
        ImpactedResource resource = new ImpactedResource(signal.resourceType(), resourceName, changedFile.changeType().name(), changedFile.effectivePath(), evidence);
        return Optional.of(new RuleMatch(signal.changeType(), changedFile, List.of(resource), List.of(evidence)));
    }

    private MqSignal classify(ChangedFile changedFile, String content) {
        if (HeuristicSupport.containsAny(content, RETRY_DLQ_KEYWORDS)) {
            return new MqSignal(ChangeType.MQ_RETRY_DLQ, ResourceType.MQ_CONSUMER, "Detected MQ retry, dead-letter, ack or idempotency change");
        }
        if (HeuristicSupport.containsAny(content, PRODUCER_KEYWORDS)) {
            return new MqSignal(ChangeType.MQ_PRODUCER, ResourceType.MQ_PRODUCER, "Detected MQ producer send logic change");
        }
        if (HeuristicSupport.containsAny(content, CONSUMER_KEYWORDS)) {
            return new MqSignal(ChangeType.MQ_CONSUMER, ResourceType.MQ_CONSUMER, "Detected MQ consumer listener logic change");
        }
        if (HeuristicSupport.pathMatches(changedFile, MESSAGE_SCHEMA_PATH_KEYWORDS) && JAVA_FIELD_PATTERN.matcher(content).find()) {
            return new MqSignal(ChangeType.MQ_MESSAGE_SCHEMA, ResourceType.MQ_MESSAGE, "Detected MQ message payload schema change");
        }
        if (HeuristicSupport.containsAny(content, TOPIC_CONFIG_KEYWORDS)) {
            return new MqSignal(ChangeType.MQ_TOPIC_CONFIG, ResourceType.MQ_TOPIC, "Detected MQ topic, tag, group or destination change");
        }
        return new MqSignal(ChangeType.MQ_TOPIC_CONFIG, ResourceType.MQ_TOPIC, "Detected MQ topic, group or middleware configuration change");
    }

    private record MqSignal(ChangeType changeType, ResourceType resourceType, String reason) {
    }
}
