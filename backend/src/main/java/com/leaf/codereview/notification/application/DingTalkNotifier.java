package com.leaf.codereview.notification.application;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import com.leaf.codereview.notification.domain.NotificationStatus;
import com.leaf.codereview.riskengine.domain.RiskCard;
import com.leaf.codereview.riskengine.domain.RiskItem;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Comparator;
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
        String title = "AI 变更风险审查 #" + taskId + "：" + riskCard.riskLevel();
        String markdown = formatMarkdown(taskId, riskCard);
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
        return "- [" + item.riskLevel() + "] " + item.title();
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