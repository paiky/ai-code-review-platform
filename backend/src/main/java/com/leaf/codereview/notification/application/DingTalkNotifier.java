package com.leaf.codereview.notification.application;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import com.leaf.codereview.notification.domain.NotificationStatus;
import com.leaf.codereview.riskengine.domain.ReviewRole;
import com.leaf.codereview.riskengine.domain.RiskCard;
import com.leaf.codereview.riskengine.domain.RiskItem;
import com.leaf.codereview.riskengine.domain.RiskLevel;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Collection;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;

@Service
public class DingTalkNotifier {

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final String webhookUrl;
    private final boolean enabled;

    public DingTalkNotifier(
            ObjectMapper objectMapper,
            @Value("${notification.dingtalk.webhook-url:}") String webhookUrl,
            @Value("${notification.dingtalk.enabled:true}") boolean enabled
    ) {
        this.objectMapper = objectMapper;
        this.webhookUrl = webhookUrl;
        this.enabled = enabled;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
    }

    public DingTalkNotificationResult sendRiskCard(Long taskId, RiskCard riskCard) {
        return sendRiskCard(taskId, riskCard, List.of());
    }

    public DingTalkNotificationResult sendRiskCard(Long taskId, RiskCard riskCard, Collection<String> focusChangeTypes) {
        RiskCard notificationCard = filterRiskCard(riskCard, focusChangeTypes);
        if (notificationCard.riskItems().isEmpty() && focusChangeTypes != null && !focusChangeTypes.isEmpty()) {
            String focusText = focusChangeTypes.stream().collect(Collectors.joining(", "));
            return new DingTalkNotificationResult(
                    NotificationStatus.SKIPPED,
                    "DINGTALK_FOCUS_CHANGE_TYPES",
                    "No focused risk item matched. focusChangeTypes=" + focusText,
                    null,
                    "No focused risk item matched"
            );
        }

        String title = "AI 变更风险审查 #" + taskId + "：" + notificationCard.riskLevel();
        String markdown = formatMarkdown(taskId, notificationCard);
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
        String riskItems = riskCard.riskItems().stream()
                .sorted(Comparator.comparingInt(item -> -item.riskLevel().weight()))
                .map(this::formatRiskItem)
                .collect(Collectors.joining("\n"));
        if (riskItems.isBlank()) {
            riskItems = "- 未命中风险规则";
        }

        String checks = riskCard.recommendedChecks().stream()
                .limit(6)
                .map(check -> "- " + check)
                .collect(Collectors.joining("\n"));
        if (checks.isBlank()) {
            checks = "- 暂无推荐检查项";
        }

        String roles = riskCard.suggestedReviewRoles().isEmpty()
                ? "无"
                : riskCard.suggestedReviewRoles().stream().map(Enum::name).collect(Collectors.joining(", "));

        return "### AI 变更风险审查 #" + taskId + "\n\n"
                + "**整体风险：** " + riskCard.riskLevel() + "\n\n"
                + "**摘要：** " + riskCard.summary() + "\n\n"
                + "**风险项：**\n" + riskItems + "\n\n"
                + "**推荐检查：**\n" + checks + "\n\n"
                + "**建议 Review 角色：** " + roles;
    }

    private String formatRiskItem(RiskItem item) {
        String category = item.category() == null ? "-" : item.category().name();
        String confidence = StringUtils.hasText(item.confidence()) ? "，置信度 " + item.confidence() : "";
        String reason = StringUtils.hasText(item.reason()) ? "\n  - 原因：" + item.reason() : "";
        return "- [" + item.riskLevel() + "] [" + category + "] " + item.title() + confidence + reason;
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
                "仅推送关注标签风险项：" + String.join(", ", normalizedFocusTypes) + "。命中 " + focusedItems.size() + " 个。",
                focusedRiskLevel,
                riskCard.affectedResources(),
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
}
