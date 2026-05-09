package com.leaf.codereview.notification.application;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.leaf.codereview.changeanalysis.domain.ChangeType;
import com.leaf.codereview.notification.domain.DingTalkMessageContext;
import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import com.leaf.codereview.notification.domain.NotificationStatus;
import com.leaf.codereview.riskengine.domain.ReviewRole;
import com.leaf.codereview.riskengine.domain.RiskCard;
import com.leaf.codereview.riskengine.domain.RiskItem;
import com.leaf.codereview.riskengine.domain.RiskLevel;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

@Service
public class DingTalkNotifier {

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final String webhookUrl;
    private final String platformBaseUrl;
    private final boolean enabled;

    public DingTalkNotifier(ObjectMapper objectMapper, String webhookUrl, boolean enabled) {
        this(objectMapper, webhookUrl, "", enabled);
    }

    @Autowired
    public DingTalkNotifier(
            ObjectMapper objectMapper,
            @Value("${notification.dingtalk.webhook-url:}") String webhookUrl,
            @Value("${notification.platform-base-url:}") String platformBaseUrl,
            @Value("${notification.dingtalk.enabled:true}") boolean enabled
    ) {
        this.objectMapper = objectMapper;
        this.webhookUrl = webhookUrl;
        this.platformBaseUrl = platformBaseUrl;
        this.enabled = enabled;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
    }

    public DingTalkNotificationResult sendRiskCard(Long taskId, RiskCard riskCard) {
        return sendRiskCard(taskId, riskCard, List.of(), DingTalkMessageContext.empty());
    }

    public DingTalkNotificationResult sendRiskCard(Long taskId, RiskCard riskCard, Collection<String> focusChangeTypes) {
        return sendRiskCard(taskId, riskCard, focusChangeTypes, DingTalkMessageContext.empty());
    }

    public DingTalkNotificationResult sendRiskCard(
            Long taskId,
            RiskCard riskCard,
            Collection<String> focusChangeTypes,
            DingTalkMessageContext context
    ) {
        RiskCard notificationCard = filterRiskCard(riskCard, focusChangeTypes);
        if (notificationCard.riskItems().isEmpty() && focusChangeTypes != null && !focusChangeTypes.isEmpty()) {
            String focusText = focusChangeTypes.stream().collect(Collectors.joining(", "));
            return new DingTalkNotificationResult(
                    NotificationStatus.SKIPPED,
                    "DINGTALK_FOCUS_CHANGE_TYPES",
                    "No focused reminder matched. focusChangeTypes=" + focusText,
                    null,
                    "No focused reminder matched"
            );
        }

        String title = "变更提醒";
        String markdown = formatMarkdown(taskId, notificationCard, context == null ? DingTalkMessageContext.empty() : context);
        String requestBody = buildRequestBody(title, markdown);
        String digest = markdown.length() > 500 ? markdown.substring(0, 500) : markdown;

        if (!enabled || !StringUtils.hasText(webhookUrl)) {
            return new DingTalkNotificationResult(
                    NotificationStatus.SKIPPED,
                    "DINGTALK_WEBHOOK_URL",
                    digest,
                    null,
                    "DingTalk webhook is not configured"
            );
        }

        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(webhookUrl))
                    .timeout(Duration.ofSeconds(8))
                    .header("Content-Type", "application/json; charset=utf-8")
                    .POST(HttpRequest.BodyPublishers.ofString(requestBody, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            NotificationStatus status = response.statusCode() >= 200 && response.statusCode() < 300
                    ? NotificationStatus.SUCCESS
                    : NotificationStatus.FAILED;
            return new DingTalkNotificationResult(status, webhookUrl, digest, response.body(), status == NotificationStatus.SUCCESS ? null : "HTTP " + response.statusCode());
        } catch (Exception exception) {
            return new DingTalkNotificationResult(NotificationStatus.FAILED, webhookUrl, digest, null, exception.getMessage());
        }
    }

    public String formatMarkdown(Long taskId, RiskCard riskCard) {
        return formatMarkdown(taskId, riskCard, DingTalkMessageContext.empty());
    }

    public String formatMarkdown(Long taskId, RiskCard riskCard, DingTalkMessageContext context) {
        List<ReminderGroup> reminderGroups = reminderGroups(riskCard.riskItems());
        String reminders = reminderGroups.stream()
                .map(this::formatReminderGroup)
                .collect(Collectors.joining("\n"));
        if (reminders.isBlank()) {
            reminders = "- 本次没有命中需推送的重点提醒。";
        }

        String detailUrl = detailUrl(taskId);
        String links = StringUtils.hasText(detailUrl) ? "[查看平台详情](" + detailUrl + ")" : "";

        return "### 变更提醒\n\n"
                + "- **作者：** " + authorText(context) + "\n"
                + "- **变更：** " + valueOrDash(context.title()) + "\n"
                + "- **分支：** " + branchText(context) + "\n\n"
                + "**提醒**\n" + reminders + "\n\n"
                + (StringUtils.hasText(links) ? links : "");
    }

    private String formatReminderGroup(ReminderGroup group) {
        String categories = group.categories().stream()
                .map(category -> changeTypeLabel(category.name()))
                .collect(Collectors.joining("、"));
        return "- " + group.label() + "：命中 " + valueOrDash(categories) + "，共 " + group.items().size() + " 条提醒。";
    }

    private List<ReminderGroup> reminderGroups(List<RiskItem> riskItems) {
        Map<String, ReminderGroup> groups = new LinkedHashMap<>();
        for (RiskItem item : riskItems) {
            ChangeType category = item.category();
            String key = reminderGroupKey(category);
            groups.computeIfAbsent(key, ignored -> new ReminderGroup(key, reminderGroupLabel(category), new ArrayList<>(), new LinkedHashSet<>()));
            groups.get(key).items().add(item);
            if (category != null) {
                groups.get(key).categories().add(category);
            }
        }
        return groups.values().stream()
                .sorted(Comparator.comparingInt(group -> reminderGroupOrder(group.key())))
                .toList();
    }

    private String reminderGroupKey(ChangeType category) {
        if (category == null) {
            return "OTHER";
        }
        if (category.isDbFamily()) {
            return "DB";
        }
        if (category.isMqFamily()) {
            return "MQ";
        }
        if (category.isCacheFamily()) {
            return "CACHE";
        }
        if (category == ChangeType.CONFIG) {
            return "CONFIG";
        }
        return category.name();
    }

    private String reminderGroupLabel(ChangeType category) {
        String key = reminderGroupKey(category);
        return switch (key) {
            case "DB" -> "DB 变更提醒";
            case "MQ" -> "MQ 变更提醒";
            case "CACHE" -> "Redis/缓存提醒";
            case "CONFIG" -> "配置提醒";
            case "OTHER" -> "其他提醒";
            default -> changeTypeLabel(key) + "提醒";
        };
    }

    private int reminderGroupOrder(String key) {
        return switch (key) {
            case "DB" -> 1;
            case "MQ" -> 2;
            case "CACHE" -> 3;
            case "CONFIG" -> 4;
            default -> 99;
        };
    }

    private String authorText(DingTalkMessageContext context) {
        String name = context.authorName();
        String username = context.authorUsername();
        if (StringUtils.hasText(name) && StringUtils.hasText(username)) {
            return name + "(@" + username + ")";
        }
        if (StringUtils.hasText(name)) {
            return name;
        }
        if (StringUtils.hasText(username)) {
            return "@" + username;
        }
        return "-";
    }

    private String branchText(DingTalkMessageContext context) {
        if (StringUtils.hasText(context.sourceBranch()) || StringUtils.hasText(context.targetBranch())) {
            return valueOrDash(context.sourceBranch()) + " -> " + valueOrDash(context.targetBranch());
        }
        return "-";
    }

    private String detailUrl(Long taskId) {
        if (!StringUtils.hasText(platformBaseUrl) || taskId == null) {
            return null;
        }
        String base = platformBaseUrl.replaceAll("/+$", "");
        return base + "/?taskId=" + taskId;
    }

    private String valueOrDash(String value) {
        return StringUtils.hasText(value) ? value : "-";
    }

    private String changeTypeLabel(String category) {
        if (!StringUtils.hasText(category)) {
            return "-";
        }
        try {
            return switch (ChangeType.valueOf(category)) {
                case API -> "接口";
                case DB -> "数据库";
                case DB_SCHEMA -> "DB 表结构";
                case DB_SQL -> "SQL";
                case ORM_MAPPING -> "ORM/MyBatis 映射";
                case ENTITY_MODEL -> "实体模型";
                case DATA_MIGRATION -> "数据迁移";
                case CACHE -> "缓存";
                case CACHE_KEY -> "缓存 Key";
                case CACHE_TTL -> "缓存 TTL";
                case CACHE_INVALIDATION -> "缓存失效";
                case CACHE_READ_WRITE -> "缓存读写";
                case CACHE_SERIALIZATION -> "缓存序列化";
                case MQ -> "MQ";
                case MQ_PRODUCER -> "MQ 生产者";
                case MQ_CONSUMER -> "MQ 消费者";
                case MQ_MESSAGE_SCHEMA -> "MQ 消息结构";
                case MQ_TOPIC_CONFIG -> "MQ Topic/消费组配置";
                case MQ_RETRY_DLQ -> "MQ 重试/死信";
                case CONFIG -> "配置";
            };
        } catch (IllegalArgumentException exception) {
            return category;
        }
    }

    private RiskCard filterRiskCard(RiskCard riskCard, Collection<String> focusChangeTypes) {
        if (focusChangeTypes == null || focusChangeTypes.isEmpty()) {
            return riskCard;
        }

        Set<String> normalizedFocusTypes = focusChangeTypes.stream()
                .filter(StringUtils::hasText)
                .map(value -> value.trim().toUpperCase(Locale.ROOT))
                .collect(Collectors.toCollection(LinkedHashSet::new));
        if (normalizedFocusTypes.isEmpty()) {
            return riskCard;
        }

        List<RiskItem> focusedItems = riskCard.riskItems().stream()
                .filter(item -> item.category() != null && normalizedFocusTypes.contains(item.category().name()))
                .toList();
        RiskLevel focusedRiskLevel = focusedItems.stream()
                .map(RiskItem::riskLevel)
                .max(Comparator.comparingInt(RiskLevel::weight))
                .orElse(RiskLevel.LOW);
        List<String> focusedChecks = focusedItems.stream()
                .flatMap(item -> item.recommendedChecks().stream())
                .distinct()
                .toList();
        Set<ReviewRole> focusedRoles = focusedItems.stream()
                .flatMap(item -> item.suggestedReviewRoles().stream())
                .collect(Collectors.toCollection(LinkedHashSet::new));

        return new RiskCard(
                riskCard.cardId(),
                "仅推送关注标签提醒：" + String.join(", ", normalizedFocusTypes) + "。命中 " + focusedItems.size() + " 个。",
                focusedRiskLevel,
                riskCard.affectedResources(),
                riskCard.focusIndicators(),
                focusedItems,
                focusedChecks,
                focusedRoles,
                riskCard.generatedAt(),
                riskCard.generator()
        );
    }

    private String buildRequestBody(String title, String markdown) {
        ObjectNode root = objectMapper.createObjectNode();
        root.put("msgtype", "markdown");
        ObjectNode markdownNode = root.putObject("markdown");
        markdownNode.put("title", title);
        markdownNode.put("text", markdown);
        return root.toString();
    }

    private record ReminderGroup(String key, String label, List<RiskItem> items, Set<ChangeType> categories) {
    }
}
