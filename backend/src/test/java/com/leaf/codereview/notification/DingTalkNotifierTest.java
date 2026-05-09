package com.leaf.codereview.notification;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.leaf.codereview.changeanalysis.domain.ChangeType;
import com.leaf.codereview.notification.application.DingTalkNotifier;
import com.leaf.codereview.notification.domain.DingTalkMessageContext;
import com.leaf.codereview.notification.domain.DingTalkNotificationResult;
import com.leaf.codereview.notification.domain.NotificationStatus;
import com.leaf.codereview.riskengine.domain.ReviewRole;
import com.leaf.codereview.riskengine.domain.RiskCard;
import com.leaf.codereview.riskengine.domain.RiskItem;
import com.leaf.codereview.riskengine.domain.RiskLevel;
import org.junit.jupiter.api.Test;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

class DingTalkNotifierTest {

    private final DingTalkNotifier notifier = new DingTalkNotifier(new ObjectMapper(), "", true);

    @Test
    void skipsNotificationWhenFocusedRiskItemsAreMissing() {
        RiskCard riskCard = riskCard(
                riskItem("CACHE_INVALIDATION_CHANGE_CHECK", ChangeType.CACHE_INVALIDATION, RiskLevel.HIGH)
        );

        DingTalkNotificationResult result = notifier.sendRiskCard(
                10L,
                riskCard,
                List.of("DB_SCHEMA", "DATA_MIGRATION", "ENTITY_MODEL")
        );

        assertThat(result.status()).isEqualTo(NotificationStatus.SKIPPED);
        assertThat(result.target()).isEqualTo("DINGTALK_FOCUS_CHANGE_TYPES");
        assertThat(result.errorMessage()).isEqualTo("No focused reminder matched");
    }

    @Test
    void formatsOnlyFocusedRiskItemsBeforeSending() {
        RiskCard riskCard = riskCard(
                riskItem("DB_SCHEMA_CHANGE_CHECK", ChangeType.DB_SCHEMA, RiskLevel.HIGH),
                riskItem("DB_SQL_CHANGE_CHECK", ChangeType.DB_SQL, RiskLevel.MEDIUM),
                riskItem("CACHE_INVALIDATION_CHANGE_CHECK", ChangeType.CACHE_INVALIDATION, RiskLevel.HIGH)
        );

        DingTalkNotificationResult result = notifier.sendRiskCard(
                11L,
                riskCard,
                List.of("DB_SCHEMA", "DB_SQL")
        );

        assertThat(result.status()).isEqualTo(NotificationStatus.SKIPPED);
        assertThat(result.target()).isEqualTo("DINGTALK_WEBHOOK_URL");
        assertThat(result.requestDigest()).contains("作者");
        assertThat(result.requestDigest()).contains("### 变更提醒");
        assertThat(result.requestDigest()).contains("**提醒**");
        assertThat(result.requestDigest()).doesNotContain("维护事项提醒");
        assertThat(result.requestDigest()).doesNotContain("变更提醒 #11");
        assertThat(result.requestDigest()).contains("DB 变更提醒：命中 DB 表结构、SQL，共 2 条提醒");
        assertThat(result.requestDigest()).doesNotContain("触发提醒");
        assertThat(result.requestDigest()).doesNotContain("上线前请准备并核对 SQL");
        assertThat(result.requestDigest()).doesNotContain("DB schema changed");
        assertThat(result.requestDigest()).doesNotContain("高风险");
        assertThat(result.requestDigest()).doesNotContain("置信度");
        assertThat(result.requestDigest()).doesNotContain("CACHE_INVALIDATION");
        assertThat(result.requestDigest()).doesNotContain("Cache invalidation changed");
    }

    @Test
    void formatsAuthorAndPlatformDetailLink() {
        DingTalkNotifier notifierWithPlatformUrl = new DingTalkNotifier(new ObjectMapper(), "", "http://localhost:5173/", true);
        String markdown = notifierWithPlatformUrl.formatMarkdown(
                12L,
                riskCard(riskItem("DB_SCHEMA_CHANGE_CHECK", ChangeType.DB_SCHEMA, RiskLevel.HIGH)),
                new DingTalkMessageContext(
                        "GitLab MR !12 feature/order -> master",
                        "Alice",
                        "alice",
                        "feature/order",
                        "master",
                        "https://gitlab.example.com/group/demo/-/merge_requests/12"
                )
        );

        assertThat(markdown).contains("Alice(@alice)");
        assertThat(markdown).contains("feature/order -> master");
        assertThat(markdown).contains("[查看平台详情](http://localhost:5173/?taskId=12)");
        assertThat(markdown).doesNotContain("查看 GitLab");
        assertThat(markdown).doesNotContain("gitlab.example.com");
    }

    private RiskCard riskCard(RiskItem... riskItems) {
        return new RiskCard(
                "risk-card-test",
                "summary",
                RiskLevel.HIGH,
                List.of(),
                List.of(riskItems),
                List.of("template check"),
                Set.of(ReviewRole.BACKEND),
                OffsetDateTime.parse("2026-04-21T22:38:00+08:00"),
                "test"
        );
    }

    private RiskItem riskItem(String ruleCode, ChangeType category, RiskLevel riskLevel) {
        String title = switch (category) {
            case DB_SCHEMA -> "DB schema changed";
            case DB_SQL -> "SQL changed";
            default -> "Cache invalidation changed";
        };
        return new RiskItem(
                ruleCode + "-001",
                ruleCode,
                category,
                riskLevel,
                title,
                "description",
                "impact",
                List.of(),
                List.of(),
                List.of(title + " check"),
                Set.of(ReviewRole.BACKEND),
                "HIGH",
                "reason",
                List.of()
        );
    }
}
